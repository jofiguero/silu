"""Lógica de negocio de categorías."""

from collections.abc import Sequence
from uuid import UUID

from sqlalchemy.orm import Session

from app.core.exceptions import (
    CategoryInUseError,
    CategoryNameTakenError,
    CategoryNotFoundError,
    ProtectedCategoryError,
)
from app.db.models import Category
from app.repositories.category import CategoryRepository
from app.schemas.category import CategoryCreate, CategoryUpdate


class CategoryService:
    def __init__(self, session: Session) -> None:
        self.session = session
        self.repository = CategoryRepository(session)

    # --- Lectura ---

    def get(self, category_id: UUID) -> Category:
        category = self.repository.get(category_id)
        if category is None:
            raise CategoryNotFoundError(category_id)
        return category

    def list(self) -> Sequence[Category]:
        return self.repository.list()

    def list_with_counts(self) -> list[tuple[Category, int]]:
        counts = self.repository.open_counts()
        return [(c, counts.get(c.id, 0)) for c in self.repository.list()]

    def get_default(self) -> Category:
        return self.repository.get_default()

    def resolve(self, name: str | None) -> Category:
        """Nombre a categoría, cayendo en la bandeja si no calza.

        Lo usa el pipeline de captura: si el modelo devuelve una categoría que
        no existe, el ticket igual se guarda —en la bandeja— en vez de perderse.
        """
        if name:
            found = self.repository.get_by_name(name)
            if found is not None:
                return found
        return self.repository.get_default()

    # --- Escritura ---

    def create(self, data: CategoryCreate) -> Category:
        name = data.name.strip()
        if self.repository.get_by_name(name) is not None:
            raise CategoryNameTakenError(name)

        category = Category(
            name=name,
            position=(
                data.position
                if data.position is not None
                else self.repository.next_position()
            ),
        )
        self.repository.add(category)
        self.session.commit()
        self.session.refresh(category)
        return category

    def update(self, category_id: UUID, data: CategoryUpdate) -> Category:
        category = self.get(category_id)
        changes = data.model_dump(exclude_unset=True)

        if "name" in changes and changes["name"]:
            new_name = changes["name"].strip()
            existing = self.repository.get_by_name(new_name)
            if existing is not None and existing.id != category.id:
                raise CategoryNameTakenError(new_name)
            category.name = new_name

        if "position" in changes and changes["position"] is not None:
            category.position = changes["position"]

        self.session.commit()
        self.session.refresh(category)
        return category

    def delete(self, category_id: UUID, *, move_tickets: bool = True) -> int:
        """Elimina una categoría. Devuelve cuántos tickets se movieron.

        Los tickets nunca se borran junto con su categoría: se mueven a la
        bandeja. Perder capturas por reorganizar las líneas de vida sería el
        peor resultado posible.
        """
        category = self.get(category_id)

        if category.is_default:
            raise ProtectedCategoryError(
                "La bandeja no se puede eliminar: es el destino de los tickets "
                "sin clasificar."
            )

        movidos = len(category.tickets)
        if movidos and not move_tickets:
            raise CategoryInUseError(
                f"La categoría tiene {movidos} tickets. Muévelos antes de eliminarla."
            )

        default = self.repository.get_default()
        for ticket in category.tickets:
            ticket.category_id = default.id
        self.session.flush()

        self.repository.delete(category)
        self.session.commit()
        return movidos
