"""Captura de tickets desde Telegram.

Orquesta el pipeline completo: descargar el audio, transcribirlo, pedirle al LLM
un título y una descripción, guardar el ticket y avisar por el chat.

Esta clase no sabe nada de FastAPI. Recibe un `TelegramUpdate` ya validado y
hace el trabajo, así que se puede invocar desde el webhook, desde un script de
reproceso o desde un test.
"""

import html
import logging
import re

import httpx

from sqlalchemy.orm import Session

from app.core.config import Settings, get_settings
from app.db.models import Ticket
from app.db.session import declarar_dueno
from app.services.auth import AuthService
from app.integrations.llm import LLMError, TicketDrafter
from app.integrations.telegram import TelegramClient, TelegramError
from app.integrations.transcription import Transcriber, TranscriptionError
from app.schemas.telegram import TelegramMessage, TelegramUpdate
from app.schemas.ticket import TicketCreate
from app.services.ticket import TicketService

logger = logging.getLogger(__name__)

# "Oye Silu, genérame un ticket sobre X" -> "X". El prefijo es una muletilla de
# dictado, no parte de lo que la persona quiere recordar.
WAKE_PREFIX = re.compile(
    r"^\s*(oye\s+|hey\s+)?silu[,:;.\s]+"
    r"(gener[ae]me|crea(me)?|anota(me)?|gu[aá]rda(me)?|ap[uú]nta(me)?)?\s*"
    r"(un\s+)?(ticket\s+)?(sobre|de|que)?[:\s]*",
    re.IGNORECASE,
)

ACK_AUDIO = "🎧 Escuchando…"
ACK_TEXT = "✍️ Procesando…"


class UnsupportedMessageError(Exception):
    """El mensaje no se puede convertir en ticket; el texto es para el usuario."""


class CaptureService:
    def __init__(self, session: Session, settings: Settings | None = None) -> None:
        self.settings = settings or get_settings()
        self.tickets = TicketService(session)
        self.telegram = TelegramClient(self.settings)

    # --- Punto de entrada ---

    def handle(self, update: TelegramUpdate) -> Ticket | None:
        message = update.effective_message
        if message is None:
            return None

        chat_id = message.chat.id

        if self._is_command(message):
            self._handle_command(message)
            return None

        if not self._is_authorized(message):
            logger.warning(
                "Mensaje rechazado de usuario no autorizado: %s",
                message.from_user.id if message.from_user else "desconocido",
            )
            return None

        # De quién es esta captura. Sin esto la sesión no sabe a qué bandeja
        # escribir, y el INSERT se caería por no tener dueño.
        dueno = AuthService(self.session).usuario_de_telegram(message.from_user.id)
        if dueno is None:
            self.telegram.send_message(
                chat_id,
                "No encuentro tu cuenta de Silu. Vincúlala desde la web.",
            )
            return None
        declarar_dueno(self.session, dueno.id)

        try:
            raw_text = self._extract_raw_text(message)
        except UnsupportedMessageError as exc:
            self.telegram.send_message(chat_id, str(exc))
            return None

        try:
            draft = TicketDrafter(self.settings).draft(raw_text)
        except LLMError:
            logger.exception("El LLM falló; se guarda el ticket sin procesar")
            # Perder la captura sería el peor resultado posible: se guarda con
            # la transcripción cruda y se avisa para editarlo a mano después.
            draft = None

        ticket = self._store(raw_text, draft)
        self.telegram.send_message(chat_id, self._render(ticket, degraded=draft is None))
        return ticket

    # --- Pasos ---

    def _extract_raw_text(self, message: TelegramMessage) -> str:
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

        text = message.plain_text
        if text:
            self.telegram.send_message(chat_id, ACK_TEXT)
            return WAKE_PREFIX.sub("", text).strip() or text

        raise UnsupportedMessageError(
            "Solo entiendo mensajes de voz y texto por ahora."
        )

    def _store(self, raw_text: str, draft) -> Ticket:
        if draft is None:
            # Título provisorio con las primeras palabras, para que el ticket
            # sea reconocible en la bandeja aunque el LLM haya fallado.
            fallback_title = " ".join(raw_text.split()[:8])[:60]
            return self.tickets.create(
                TicketCreate(
                    raw_text=raw_text,
                    title=fallback_title or "Ticket sin procesar",
                    summary=raw_text,
                )
            )

        return self.tickets.create(
            TicketCreate(
                raw_text=raw_text,
                title=draft.title,
                summary=draft.summary,
                urgent=draft.urgent,
            )
        )

    # --- Autorización y comandos ---

    def _is_authorized(self, message: TelegramMessage) -> bool:
        allowed = self.settings.telegram_allowed_user_id
        if allowed is None:
            return False
        return message.from_user is not None and message.from_user.id == allowed

    @staticmethod
    def _is_command(message: TelegramMessage) -> bool:
        text = message.plain_text or ""
        return text.startswith("/")

    def _handle_command(self, message: TelegramMessage) -> None:
        command = (message.plain_text or "").split()[0].lower()
        chat_id = message.chat.id
        user_id = message.from_user.id if message.from_user else None

        if command in {"/id", "/start"}:
            # /id responde a cualquiera a propósito: solo devuelve el id de quien
            # pregunta, y es la única forma de conocerlo para configurar la
            # restricción de acceso la primera vez.
            self.telegram.send_message(
                chat_id,
                f"Tu id de Telegram es <code>{user_id}</code>.\n"
                "Configúralo en TELEGRAM_ALLOWED_USER_ID para poder crear tickets.",
            )
            return

        if not self._is_authorized(message):
            return

        self.telegram.send_message(
            chat_id,
            "Mándame un audio o un texto y lo convierto en ticket.\n"
            "<code>/id</code> — muestra tu id de Telegram",
        )

    # --- Presentación ---

    @staticmethod
    def _render(ticket: Ticket, *, degraded: bool) -> str:
        title = html.escape(ticket.title)
        summary = html.escape(ticket.summary)

        if degraded:
            return (
                "⚠️ Guardado, pero no pude procesarlo con el modelo.\n\n"
                f"<b>{title}</b>\n{summary}\n\n"
                "Queda pendiente para que lo edites al revisar."
            )

        # La urgencia va en la respuesta: si el modelo la interpretó mal, se
        # nota al instante y no semanas después.
        marca = "🔴 <b>URGENTE</b>\n" if ticket.urgent else ""
        return f"{marca}✅ <b>{title}</b>\n{summary}"

