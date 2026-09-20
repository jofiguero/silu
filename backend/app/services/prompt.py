"""Proyectos y prompts."""

from __future__ import annotations

import html
import logging
from collections.abc import Sequence
from uuid import UUID

import httpx
from sqlalchemy.orm import Session

from app.core.config import Settings, get_settings
from app.core.exceptions import (
    ProjectNameTakenError,
    ProjectNotFoundError,
    PromptNotFoundError,
)
from app.db.models import Prompt, PromptProject
from app.integrations.metaprompt import Metaprompter, MetapromptError
from app.integrations.telegram import TelegramClient, TelegramError
from app.integrations.transcription import Transcriber, TranscriptionError
from app.repositories.prompt import ProjectRepository, PromptRepository
from app.schemas.prompt import (
    ProjectCreate,
    ProjectUpdate,
    PromptCreate,
    PromptUpdate,
)
from app.schemas.telegram import TelegramMessage, TelegramUpdate

logger = logging.getLogger(__name__)

ACK_AUDIO = "🎧 Escuchando…"
ACK_TEXTO = "✍️ Armando el prompt…"


class UnsupportedMessageError(Exception):
    """El mensaje no se puede convertir en prompt; el texto es para el usuario."""


class ProjectService:
    def __init__(self, session: Session) -> None:
        self.session = session
        self.repository = ProjectRepository(session)

    def get(self, project_id: UUID) -> PromptProject:
        proyecto = self.repository.get(project_id)
        if proyecto is None:
            raise ProjectNotFoundError(project_id)
        return proyecto

    def list(self) -> Sequence[PromptProject]:
        return self.repository.list()

    def resolve(self, name: str | None) -> PromptProject | None:
        """Nombre a proyecto. Devuelve None si no calza con ninguno.

        Un nombre inventado por el modelo deja el prompt sin asignar en vez de
        mandarlo a un proyecto equivocado, que es peor: ahí se pierde de vista.
        """
        if not name:
            return None
        return self.repository.get_by_name(name)

    def create(self, data: ProjectCreate) -> PromptProject:
        name = data.name.strip()
        if self.repository.get_by_name(name) is not None:
            raise ProjectNameTakenError(name)

        proyecto = PromptProject(
            name=name,
            description_md=data.description_md or "",
            position=self.repository.next_position(),
        )
        self.repository.add(proyecto)
        self.session.commit()
        self.session.refresh(proyecto)
        return proyecto

    def update(self, project_id: UUID, data: ProjectUpdate) -> PromptProject:
        proyecto = self.get(project_id)
        changes = data.model_dump(exclude_unset=True)

        if changes.get("name"):
            nuevo = changes["name"].strip()
            existente = self.repository.get_by_name(nuevo)
            if existente is not None and existente.id != proyecto.id:
                raise ProjectNameTakenError(nuevo)
            proyecto.name = nuevo

        if "description_md" in changes:
            proyecto.description_md = changes["description_md"] or ""
        if changes.get("position") is not None:
            proyecto.position = changes["position"]

        self.session.commit()
        self.session.refresh(proyecto)
        return proyecto

    def delete(self, project_id: UUID) -> int:
        """Elimina el proyecto. Sus prompts quedan sin asignar, no se borran.

        Devuelve cuántos quedaron sueltos.
        """
        proyecto = self.get(project_id)
        sueltos = len(proyecto.prompts)
        self.repository.delete(proyecto)
        self.session.commit()
        return sueltos


class PromptService:
    def __init__(self, session: Session) -> None:
        self.session = session
        self.repository = PromptRepository(session)
        self.projects = ProjectService(session)

    def get(self, prompt_id: UUID) -> Prompt:
        prompt = self.repository.get(prompt_id)
        if prompt is None:
            raise PromptNotFoundError(prompt_id)
        return prompt

    def list(
        self, *, project_id: UUID | None = None, sin_proyecto: bool = False
    ) -> Sequence[Prompt]:
        return self.repository.list(project_id=project_id, sin_proyecto=sin_proyecto)

    def create(self, data: PromptCreate) -> Prompt:
        if data.project_id is not None:
            self.projects.get(data.project_id)

        prompt = Prompt(
            project_id=data.project_id,
            title=data.title.strip(),
            content=data.content,
            raw_text=data.raw_text or data.content,
        )
        self.repository.add(prompt)
        self.session.commit()
        self.session.refresh(prompt)
        return prompt

    def update(self, prompt_id: UUID, data: PromptUpdate) -> Prompt:
        prompt = self.get(prompt_id)
        changes = data.model_dump(exclude_unset=True)

        if "project_id" in changes and changes["project_id"] is not None:
            self.projects.get(changes["project_id"])

        if "content" in changes and changes["content"] is not None:
            # Se marca editado para que una futura regeneración no pise el
            # trabajo hecho a mano sin avisar.
            if changes["content"] != prompt.content:
                prompt.edited = True

        for campo in ("project_id", "title", "content"):
            if campo in changes:
                valor = changes[campo]
                if campo == "title" and valor:
                    valor = valor.strip()
                setattr(prompt, campo, valor)

        self.session.commit()
        self.session.refresh(prompt)
        return prompt

    def delete(self, prompt_id: UUID) -> None:
        self.repository.delete(self.get(prompt_id))
        self.session.commit()


class PromptCaptureService:
    """Recibe un audio o texto del bot de prompts y lo convierte en prompt."""

    def __init__(self, session: Session, settings: Settings | None = None) -> None:
        self.settings = settings or get_settings()
        self.prompts = PromptService(session)
        self.projects = ProjectService(session)
        self.telegram = TelegramClient(
            self.settings, token=self.settings.telegram_prompts_bot_token
        )

    def handle(self, update: TelegramUpdate) -> Prompt | None:
        message = update.effective_message
        if message is None:
            return None

        chat_id = message.chat.id

        if (message.plain_text or "").startswith("/"):
            self._comando(message)
            return None

        if not self._autorizado(message):
            logger.warning(
                "Mensaje al bot de prompts rechazado: %s",
                message.from_user.id if message.from_user else "desconocido",
            )
            return None

        try:
            raw_text = self._texto(message)
        except UnsupportedMessageError as exc:
            self.telegram.send_message(chat_id, str(exc))
            return None

        proyectos = [
            (p.name, p.description_md) for p in self.projects.list()
        ]

        try:
            draft = Metaprompter(self.settings).draft(raw_text, proyectos)
        except MetapromptError:
            logger.exception("Falló el metaprompting")
            # La captura no se pierde: queda la transcripción cruda para
            # reescribirla a mano o reintentar desde la web.
            self.telegram.send_message(
                chat_id,
                "⚠️ No pude armar el prompt. Guardé lo que dijiste tal cual "
                "para que lo revises en la web.",
            )
            draft = None

        prompt = self._guardar(raw_text, draft)
        self.telegram.send_message(chat_id, self._respuesta(prompt, draft is not None))
        return prompt

    # --- Pasos ---

    def _texto(self, message: TelegramMessage) -> str:
        chat_id = message.chat.id

        if message.audio_file_id:
            self.telegram.send_message(chat_id, ACK_AUDIO)
            try:
                audio = self.telegram.download_file(message.audio_file_id)
            except (TelegramError, httpx.HTTPError) as exc:
                raise UnsupportedMessageError(
                    "No pude descargar el audio. Inténtalo de nuevo."
                ) from exc

            try:
                return Transcriber(self.settings).transcribe(audio)
            except TranscriptionError as exc:
                raise UnsupportedMessageError(
                    "No pude transcribir el audio. Inténtalo de nuevo o escríbelo."
                ) from exc

        texto = message.plain_text
        if texto:
            self.telegram.send_message(chat_id, ACK_TEXTO)
            return texto

        raise UnsupportedMessageError("Solo entiendo mensajes de voz y texto.")

    def _guardar(self, raw_text: str, draft) -> Prompt:
        if draft is None:
            titulo = " ".join(raw_text.split()[:10])[:70]
            return self.prompts.create(
                PromptCreate(
                    title=titulo or "Prompt sin procesar",
                    content=raw_text,
                    raw_text=raw_text,
                )
            )

        proyecto = self.projects.resolve(draft.project)
        return self.prompts.create(
            PromptCreate(
                project_id=proyecto.id if proyecto else None,
                title=draft.title,
                content=draft.content,
                raw_text=raw_text,
            )
        )

    # --- Autorización y comandos ---

    def _autorizado(self, message: TelegramMessage) -> bool:
        permitido = self.settings.telegram_allowed_user_id
        if permitido is None:
            return False
        return message.from_user is not None and message.from_user.id == permitido

    def _comando(self, message: TelegramMessage) -> None:
        chat_id = message.chat.id
        user_id = message.from_user.id if message.from_user else None
        comando = (message.plain_text or "").split()[0].lower()

        if comando in {"/id", "/start"}:
            self.telegram.send_message(
                chat_id,
                f"Bot de prompts de Silu. Tu id es <code>{user_id}</code>.\n\n"
                "Mándame un audio contando qué quieres lograr y en qué proyecto, "
                "y lo convierto en un prompt.",
            )
            return

        if not self._autorizado(message):
            return

        proyectos = [p.name for p in self.projects.list()]
        lista = "\n".join(f"· {n}" for n in proyectos) or "(ninguno todavía)"
        self.telegram.send_message(
            chat_id, f"Proyectos documentados:\n{lista}"
        )

    @staticmethod
    def _respuesta(prompt: Prompt, procesado: bool) -> str:
        titulo = html.escape(prompt.title)
        if not procesado:
            return f"📝 <b>{titulo}</b>\n\nGuardado sin procesar."

        # Se nombra el proyecto asignado: si quedó en el equivocado o sin
        # asignar, se nota al instante y no al buscarlo días después.
        destino = (
            f"📁 {html.escape(prompt.project_name)}"
            if prompt.project_name
            else "📂 Sin proyecto — asígnalo en la web"
        )
        return f"✅ <b>{titulo}</b>\n{destino}"
