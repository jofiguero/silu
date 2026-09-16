"""Lógica de negocio de tickets.

Esta capa es la que conoce las reglas del ciclo de vida. No sabe de HTTP ni de
SQL: recibe y devuelve objetos del dominio, y controla la transacción. Eso la
hace reutilizable desde el webhook de Telegram o desde un script, sin pasar por
la API.
"""

from collections.abc import Sequence
from uuid import UUID

from sqlalchemy.orm import Session

from app.core.exceptions import (
    InvalidTicketTransitionError,
    TicketNotFoundError,
)
from app.db.models import Ticket
from app.repositories.ticket import TicketRepository
from app.schemas.ticket import (
    TicketCreate,
    TicketDispatch,
    TicketStatus,
    TicketUpdate,
)


class TicketService:
    def __init__(self, session: Session) -> None:
        self.session = session
        self.repository = TicketRepository(session)

    # --- Lectura ---

    def get(self, ticket_id: UUID) -> Ticket:
        ticket = self.repository.get(ticket_id)
        if ticket is None:
            raise TicketNotFoundError(ticket_id)
        return ticket

    def list(
        self,
        *,
        status: TicketStatus | None = None,
        search: str | None = None,
        limit: int = 50,
        offset: int = 0,
    ) -> tuple[Sequence[Ticket], int]:
        """Devuelve la página y el total, en una sola operación de negocio."""
        items = self.repository.list(
            status=status, search=search, limit=limit, offset=offset
        )
        total = self.repository.count(status=status, search=search)
        return items, total

    # --- Escritura ---

    def create(self, data: TicketCreate) -> Ticket:
        ticket = Ticket(
            raw_text=data.raw_text,
            title=data.title,
            summary=data.summary,
            status=data.status.value,
        )
        self.repository.add(ticket)
        self.session.commit()
        self.session.refresh(ticket)
        return ticket

    def update(self, ticket_id: UUID, data: TicketUpdate) -> Ticket:
        ticket = self.get(ticket_id)

        # exclude_unset distingue "no lo mandaron" de "lo mandaron en null":
        # sin eso, una edición parcial borraría los campos ausentes.
        changes = data.model_dump(exclude_unset=True)

        if "status" in changes:
            self._guard_transition(ticket, changes["status"], changes)

        for field, value in changes.items():
            setattr(ticket, field, value.value if hasattr(value, "value") else value)

        self.session.commit()
        self.session.refresh(ticket)
        return ticket

    def dispatch(self, ticket_id: UUID, data: TicketDispatch) -> Ticket:
        """Cierra un ticket dejando constancia de qué se hizo con él."""
        ticket = self.get(ticket_id)
        ticket.resolution = data.resolution
        ticket.status = data.status.value
        self.session.commit()
        self.session.refresh(ticket)
        return ticket

    def delete(self, ticket_id: UUID) -> None:
        ticket = self.get(ticket_id)
        self.repository.delete(ticket)
        self.session.commit()

    # --- Reglas del ciclo de vida ---

    @staticmethod
    def _guard_transition(
        ticket: Ticket,
        new_status: TicketStatus,
        changes: dict[str, object],
    ) -> None:
        """Un ticket no se archiva sin decir qué se hizo con él.

        Archivar es el único estado terminal: si se permite hacerlo sin
        resolución, se pierde justo la información que hace útil releer la
        bandeja meses después.
        """
        if new_status is not TicketStatus.ARCHIVADO:
            return

        resolution = changes.get("resolution", ticket.resolution)
        if not resolution or not str(resolution).strip():
            raise InvalidTicketTransitionError(
                "Archivar un ticket requiere una resolución que describa qué se "
                "hizo con él. Usa el endpoint de despacho o incluye 'resolution'."
            )
