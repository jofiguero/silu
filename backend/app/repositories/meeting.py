"""Acceso a datos de reuniones."""

from __future__ import annotations

from collections.abc import Sequence
from uuid import UUID

from sqlalchemy import func, select
from sqlalchemy.orm import selectinload

from app.db.models import Meeting, MeetingFolder, MeetingItem
from app.repositories.base import BaseRepository


class FolderRepository(BaseRepository[MeetingFolder]):
    model = MeetingFolder

    def get(self, folder_id: UUID) -> MeetingFolder | None:
        return self.mio(self.session.get(MeetingFolder, folder_id))

    def get_by_name(self, name: str) -> MeetingFolder | None:
        stmt = self.mios(
            select(MeetingFolder).where(
                func.lower(MeetingFolder.name) == name.strip().lower()
            )
        )
        return self.session.execute(stmt).scalar_one_or_none()

    def list(self) -> Sequence[MeetingFolder]:
        # selectinload: la lista muestra cuántas reuniones tiene cada carpeta,
        # y sin esto se dispara una consulta por carpeta.
        stmt = self.mios(
            select(MeetingFolder)
            .options(selectinload(MeetingFolder.meetings))
            .order_by(MeetingFolder.position, MeetingFolder.name)
        )
        return self.session.execute(stmt).scalars().unique().all()

    def add(self, folder: MeetingFolder) -> MeetingFolder:
        self.session.add(folder)
        self.session.flush()
        self.session.refresh(folder)
        return folder

    def delete(self, folder: MeetingFolder) -> None:
        self.session.delete(folder)
        self.session.flush()

    def next_position(self) -> int:
        stmt = select(
            func.coalesce(func.max(MeetingFolder.position), -1) + 1
        ).where(MeetingFolder.user_id == self.dueno)
        return int(self.session.execute(stmt).scalar_one())


class MeetingRepository(BaseRepository[Meeting]):
    model = Meeting

    def get(self, meeting_id: UUID) -> Meeting | None:
        return self.mio(self.session.get(Meeting, meeting_id))

    def list(self, folder_id: UUID) -> Sequence[Meeting]:
        # De la más reciente a la más antigua: la que se busca casi siempre es
        # la próxima o la última.
        stmt = self.mios(
            select(Meeting)
            .where(Meeting.folder_id == folder_id)
            .order_by(Meeting.fecha.desc(), Meeting.id.desc())
        )
        return self.session.execute(stmt).scalars().all()

    def add(self, meeting: Meeting) -> Meeting:
        self.session.add(meeting)
        self.session.flush()
        self.session.refresh(meeting)
        return meeting

    def delete(self, meeting: Meeting) -> None:
        self.session.delete(meeting)
        self.session.flush()


class ItemRepository(BaseRepository[MeetingItem]):
    model = MeetingItem

    def get(self, item_id: UUID) -> MeetingItem | None:
        return self.mio(self.session.get(MeetingItem, item_id))

    def add(self, item: MeetingItem) -> MeetingItem:
        self.session.add(item)
        self.session.flush()
        self.session.refresh(item)
        return item

    def delete(self, item: MeetingItem) -> None:
        self.session.delete(item)
        self.session.flush()

    def next_position(self, meeting_id: UUID, zona: str) -> int:
        """La posición al final de un cuadrante.

        Por cuadrante y no por reunión: lo que se arrastra a "conversado" va
        al final de lo conversado, que es el orden en que se fue hablando.
        """
        stmt = self.mios(
            select(func.coalesce(func.max(MeetingItem.position), -1) + 1).where(
                MeetingItem.meeting_id == meeting_id, MeetingItem.zona == zona
            )
        )
        return int(self.session.execute(stmt).scalar_one())
