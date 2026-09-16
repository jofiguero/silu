"""Acceso a datos de tickets."""

from collections.abc import Sequence
from uuid import UUID

from sqlalchemy import func, select

from app.db.models import Ticket
from app.repositories.base import BaseRepository
from app.schemas.ticket import TicketStatus


class TicketRepository(BaseRepository[Ticket]):
    model = Ticket

    def get(self, ticket_id: UUID) -> Ticket | None:
        return self.session.get(Ticket, ticket_id)

    def list(
        self,
        *,
        status: TicketStatus | None = None,
        search: str | None = None,
        limit: int = 50,
        offset: int = 0,
    ) -> Sequence[Ticket]:
        stmt = self._filtered(status=status, search=search)
        # created_at DESC es el orden natural de la bandeja; id DESC desempata.
        # Sin el desempate, dos tickets con el mismo timestamp quedan en orden
        # arbitrario y la paginación puede repetir o perder filas. uuidv7 ya es
        # cronológico, así que como criterio secundario es exacto.
        stmt = (
            stmt.order_by(Ticket.created_at.desc(), Ticket.id.desc())
            .limit(limit)
            .offset(offset)
        )
        return self.session.execute(stmt).scalars().all()

    def count(
        self,
        *,
        status: TicketStatus | None = None,
        search: str | None = None,
    ) -> int:
        stmt = self._filtered(status=status, search=search)
        total = self.session.execute(
            select(func.count()).select_from(stmt.subquery())
        ).scalar_one()
        return int(total)

    def add(self, ticket: Ticket) -> Ticket:
        self.session.add(ticket)
        # flush, no commit: empuja el INSERT para que Postgres calcule los
        # valores por defecto (id, created_at) sin cerrar la transacción.
        self.session.flush()
        self.session.refresh(ticket)
        return ticket

    def delete(self, ticket: Ticket) -> None:
        self.session.delete(ticket)
        self.session.flush()

    def _filtered(
        self,
        *,
        status: TicketStatus | None,
        search: str | None,
    ):
        stmt = select(Ticket)
        if status is not None:
            stmt = stmt.where(Ticket.status == status.value)
        if search:
            pattern = f"%{search}%"
            stmt = stmt.where(
                Ticket.title.ilike(pattern) | Ticket.summary.ilike(pattern)
            )
        return stmt
