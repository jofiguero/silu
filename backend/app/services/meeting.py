"""Carpetas de reuniones, reuniones y su tablero."""

from __future__ import annotations

from collections.abc import Sequence
from datetime import datetime, timezone
from uuid import UUID

from sqlalchemy.orm import Session

from app.core.calendario import hoy
from app.core.config import Settings, get_settings
from app.core.exceptions import (
    MeetingFolderNameTakenError,
    MeetingFolderNotFoundError,
    MeetingItemNotFoundError,
    MeetingNotFoundError,
    ReunionVaciaError,
)
from app.db.models import Meeting, MeetingFolder, MeetingItem
from app.integrations.resumen import Resumidor
from app.repositories.meeting import (
    FolderRepository,
    ItemRepository,
    MeetingRepository,
)
from app.schemas.meeting import (
    FolderCreate,
    FolderUpdate,
    ItemCreate,
    ItemUpdate,
    MeetingCreate,
    MeetingUpdate,
)

# Cómo se le presenta cada cuadrante al modelo. "temas" es lo que quedó sin
# conversar al cerrar la reunión, que es lo que significa a esa altura.
SECCIONES = (
    ("conversado", "Temas conversados"),
    ("tareas", "Tareas pendientes"),
    ("apuntes", "Apuntes"),
    ("temas", "Temas que no se alcanzaron a conversar"),
)


class FolderService:
    def __init__(self, session: Session) -> None:
        self.session = session
        self.repository = FolderRepository(session)

    def get(self, folder_id: UUID) -> MeetingFolder:
        folder = self.repository.get(folder_id)
        if folder is None:
            raise MeetingFolderNotFoundError(folder_id)
        return folder

    def list(self) -> Sequence[MeetingFolder]:
        return self.repository.list()

    def create(self, data: FolderCreate) -> MeetingFolder:
        name = data.name.strip()
        if self.repository.get_by_name(name) is not None:
            raise MeetingFolderNameTakenError(name)

        folder = MeetingFolder(name=name, position=self.repository.next_position())
        self.repository.add(folder)
        self.session.commit()
        self.session.refresh(folder)
        return folder

    def update(self, folder_id: UUID, data: FolderUpdate) -> MeetingFolder:
        folder = self.get(folder_id)
        changes = data.model_dump(exclude_unset=True)

        if changes.get("name"):
            nuevo = changes["name"].strip()
            existente = self.repository.get_by_name(nuevo)
            if existente is not None and existente.id != folder.id:
                raise MeetingFolderNameTakenError(nuevo)
            folder.name = nuevo
        if changes.get("position") is not None:
            folder.position = changes["position"]

        self.session.commit()
        self.session.refresh(folder)
        return folder

    def delete(self, folder_id: UUID) -> None:
        """Borra la carpeta con sus reuniones.

        Al revés de los proyectos de prompts, donde los prompts quedan
        sueltos: una reunión sin su carpeta no tiene dónde verse. Quien pide
        el borrado ya confirmó que se las lleva.
        """
        folder = self.get(folder_id)
        self.repository.delete(folder)
        self.session.commit()


class MeetingService:
    def __init__(self, session: Session, settings: Settings | None = None) -> None:
        self.session = session
        self.settings = settings or get_settings()
        self.meetings = MeetingRepository(session)
        self.items = ItemRepository(session)
        self.folders = FolderService(session)

    # --- Reuniones ---

    def get(self, meeting_id: UUID) -> Meeting:
        meeting = self.meetings.get(meeting_id)
        if meeting is None:
            raise MeetingNotFoundError(meeting_id)
        return meeting

    def list(self, folder_id: UUID) -> Sequence[Meeting]:
        # Se pide la carpeta primero para que una ajena o inexistente dé 404,
        # y no una lista vacía que parezca una carpeta sin reuniones.
        self.folders.get(folder_id)
        return self.meetings.list(folder_id)

    def create(self, data: MeetingCreate) -> Meeting:
        folder = self.folders.get(data.folder_id)
        fecha = data.fecha or hoy()
        titulo = (data.title or "").strip() or f"Reunión del {fecha:%d/%m}"

        meeting = Meeting(folder_id=folder.id, title=titulo, fecha=fecha)
        self.meetings.add(meeting)
        self.session.commit()
        self.session.refresh(meeting)
        return meeting

    def update(self, meeting_id: UUID, data: MeetingUpdate) -> Meeting:
        meeting = self.get(meeting_id)
        changes = data.model_dump(exclude_unset=True)

        if changes.get("title"):
            meeting.title = changes["title"].strip()
        if changes.get("fecha") is not None:
            meeting.fecha = changes["fecha"]

        self.session.commit()
        self.session.refresh(meeting)
        return meeting

    def delete(self, meeting_id: UUID) -> None:
        meeting = self.get(meeting_id)
        self.meetings.delete(meeting)
        self.session.commit()

    # --- Lo anotado ---

    def get_item(self, item_id: UUID) -> MeetingItem:
        item = self.items.get(item_id)
        if item is None:
            raise MeetingItemNotFoundError(item_id)
        return item

    def add_item(self, meeting_id: UUID, data: ItemCreate) -> MeetingItem:
        meeting = self.get(meeting_id)
        item = MeetingItem(
            meeting_id=meeting.id,
            zona=data.zona,
            text_=data.text.strip(),
            position=self.items.next_position(meeting.id, data.zona),
        )
        self.items.add(item)
        self.session.commit()
        self.session.refresh(item)
        return item

    def update_item(self, item_id: UUID, data: ItemUpdate) -> MeetingItem:
        item = self.get_item(item_id)
        changes = data.model_dump(exclude_unset=True)

        if changes.get("text"):
            item.text_ = changes["text"].strip()

        # Mover a otro cuadrante lo deja al final de ese cuadrante: arrastrar
        # un tema a "conversado" lo pone después de lo ya conversado, que es
        # el orden en que se fue hablando.
        nueva = changes.get("zona")
        if nueva is not None and nueva != item.zona:
            item.position = self.items.next_position(item.meeting_id, nueva)
            item.zona = nueva

        self.session.commit()
        self.session.refresh(item)
        return item

    def delete_item(self, item_id: UUID) -> None:
        item = self.get_item(item_id)
        self.items.delete(item)
        self.session.commit()

    # --- Resumen ---

    def summarize(self, meeting_id: UUID) -> Meeting:
        """Genera el resumen con el modelo y lo guarda en la reunión.

        Si el modelo falla, la reunión queda como estaba, con el resumen
        anterior si lo había: el error sube antes de tocar nada.
        """
        meeting = self.get(meeting_id)
        notas = self.notas(meeting)

        meeting.summary = Resumidor(self.settings).resumir(notas)
        meeting.summary_at = datetime.now(timezone.utc)
        self.session.commit()
        self.session.refresh(meeting)
        return meeting

    @staticmethod
    def notas(meeting: Meeting) -> str:
        """Lo que se le manda al modelo: lo anotado, por cuadrante.

        Los cuadrantes vacíos no van. Un encabezado sin nada debajo invita al
        modelo a comentar que no hubo tareas, que es justo el ruido que el
        prompt le pide evitar.
        """
        por_zona: dict[str, list[str]] = {}
        for item in sorted(meeting.items, key=lambda i: i.position):
            por_zona.setdefault(item.zona, []).append(item.text_)

        # Solo con temas sin conversar no hubo reunión que resumir.
        if not any(por_zona.get(z) for z in ("conversado", "tareas", "apuntes")):
            raise ReunionVaciaError()

        partes = [
            f"Carpeta: {meeting.folder_name}",
            f"Reunión: {meeting.title} ({meeting.fecha:%d-%m-%Y})",
        ]
        for zona, titulo in SECCIONES:
            if por_zona.get(zona):
                lineas = "\n".join(f"- {texto}" for texto in por_zona[zona])
                partes.append(f"{titulo}:\n{lineas}")
        return "\n\n".join(partes)
