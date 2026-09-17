"""Excepciones del dominio.

El dominio no sabe nada de HTTP: lanza errores en sus propios términos y la capa
de API los traduce a códigos de estado. Así los servicios se pueden usar desde
el bot de Telegram o un script sin arrastrar semántica web.
"""

from uuid import UUID


class SiluError(Exception):
    """Raíz de todos los errores del dominio."""

    message = "Error interno"

    def __init__(self, message: str | None = None) -> None:
        self.message = message or self.message
        super().__init__(self.message)


class TicketNotFoundError(SiluError):
    def __init__(self, ticket_id: UUID) -> None:
        self.ticket_id = ticket_id
        super().__init__(f"No existe un ticket con id {ticket_id}")


class InvalidTicketTransitionError(SiluError):
    """Se intentó un cambio de estado que el ciclo de vida no permite."""


class CategoryNotFoundError(SiluError):
    def __init__(self, category_id: UUID) -> None:
        self.category_id = category_id
        super().__init__(f"No existe una categoría con id {category_id}")


class CategoryNameTakenError(SiluError):
    def __init__(self, name: str) -> None:
        super().__init__(f"Ya existe una categoría llamada {name!r}")


class ProtectedCategoryError(SiluError):
    """Se intentó eliminar una categoría que no puede eliminarse."""


class CategoryInUseError(SiluError):
    """La categoría todavía tiene tickets."""
