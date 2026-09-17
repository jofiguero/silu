"""Acceso a datos de categorías."""

from collections.abc import Sequence
from uuid import UUID

from sqlalchemy import func, select

from app.db.models import Category, Ticket
from app.repositories.base import BaseRepository


class CategoryRepository(BaseRepository[Category]):
    model = Category

    def get(self, category_id: UUID) -> Category | None:
        return self.session.get(Category, category_id)

    def get_by_name(self, name: str) -> Category | None:
        # Comparación sin distinguir mayúsculas: el LLM puede devolver "gastos"
        # donde la categoría se llama "Gastos".
        stmt = select(Category).where(func.lower(Category.name) == name.strip().lower())
        return self.session.execute(stmt).scalar_one_or_none()

    def get_default(self) -> Category:
        stmt = select(Category).where(Category.is_default.is_(True))
        return self.session.execute(stmt).scalar_one()

    def list(self) -> Sequence[Category]:
        stmt = select(Category).order_by(Category.position, Category.name)
        return self.session.execute(stmt).scalars().all()

    def open_counts(self) -> dict[UUID, int]:
        """Tickets no archivados por categoría, en una sola consulta.

        Contar dentro de un bucle sería una consulta por categoría; aquí son
        pocas, pero el patrón es el que se paga caro cuando crecen.
        """
        stmt = (
            select(Ticket.category_id, func.count())
            .where(Ticket.status != "archivado")
            .group_by(Ticket.category_id)
        )
        return {row[0]: row[1] for row in self.session.execute(stmt)}

    def add(self, category: Category) -> Category:
        self.session.add(category)
        self.session.flush()
        self.session.refresh(category)
        return category

    def delete(self, category: Category) -> None:
        self.session.delete(category)
        self.session.flush()

    def next_position(self) -> int:
        stmt = select(func.coalesce(func.max(Category.position), -1) + 1)
        return int(self.session.execute(stmt).scalar_one())
