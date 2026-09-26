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
        return self.mio(self.session.get(Ticket, ticket_id))

    def list(
        self,
        *,
        status: TicketStatus | None = None,
        search: str | None = None,
        include_archived: bool = False,
        limit: int = 50,
        offset: int = 0,
    ) -> Sequence[Ticket]:
        stmt = self._filtered(
            status=status, search=search, include_archived=include_archived
        )
        # Urgentes primero y, dentro de cada grupo, del más antiguo al más
        # nuevo: lo viejo sin resolver es lo que conviene mirar primero, al
        # revés de un feed. id desempata para que paginar sea estable.
        stmt = (
            stmt.order_by(
                Ticket.urgent.desc(), Ticket.created_at.asc(), Ticket.id.asc()
            )
            .limit(limit)
            .offset(offset)
        )
        return self.session.execute(stmt).scalars().all()

    def count(
        self,
        *,
        status: TicketStatus | None = None,
        search: str | None = None,
        include_archived: bool = False,
    ) -> int:
        stmt = self._filtered(
            status=status, search=search, include_archived=include_archived
        )
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
        include_archived: bool = False,
    ):
        stmt = self.mios(select(Ticket))
        if status is not None:
            stmt = stmt.where(Ticket.status == status.value)
        elif not include_archived:
            # Sin filtro explícito, lo archivado no estorba: con el tiempo
            # enterraría lo que sigue vivo.
            stmt = stmt.where(Ticket.status != TicketStatus.ARCHIVADO.value)
        if search:
            pattern = f"%{search}%"
            stmt = stmt.where(
                Ticket.title.ilike(pattern) | Ticket.summary.ilike(pattern)
            )
        return stmt
