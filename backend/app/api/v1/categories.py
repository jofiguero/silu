"""Endpoints de categorías (líneas de vida)."""

from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, Query, status

from app.api.deps import SessionDep, require_session
from app.schemas.category import CategoryCreate, CategoryRead, CategoryUpdate
from app.schemas.common import ErrorResponse
from app.services.category import CategoryService

router = APIRouter(
    prefix="/categories",
    tags=["categorías"],
    dependencies=[Depends(require_session)],
)

NOT_FOUND = {status.HTTP_404_NOT_FOUND: {"model": ErrorResponse}}


def _read(category, open_count: int = 0) -> CategoryRead:
    return CategoryRead(
        id=category.id,
        created_at=category.created_at,
        name=category.name,
        position=category.position,
        is_default=category.is_default,
        open_count=open_count,
    )


@router.get("", summary="Listar categorías")
def list_categories(session: SessionDep) -> list[CategoryRead]:
    """Las líneas de vida, en el orden en que se muestran arriba."""
    return [
        _read(category, count)
        for category, count in CategoryService(session).list_with_counts()
    ]


@router.post("", status_code=status.HTTP_201_CREATED, summary="Crear categoría")
def create_category(data: CategoryCreate, session: SessionDep) -> CategoryRead:
    return _read(CategoryService(session).create(data))


@router.patch("/{category_id}", summary="Editar categoría", responses=NOT_FOUND)
def update_category(
    category_id: UUID, data: CategoryUpdate, session: SessionDep
) -> CategoryRead:
    return _read(CategoryService(session).update(category_id, data))


@router.delete("/{category_id}", summary="Eliminar categoría", responses=NOT_FOUND)
def delete_category(
    category_id: UUID,
    session: SessionDep,
    move_tickets: Annotated[
        bool,
        Query(description="Mover sus tickets a la bandeja en vez de rechazar"),
    ] = True,
) -> dict[str, int]:
    """Elimina la categoría y devuelve cuántos tickets se movieron a la bandeja.

    Los tickets nunca se borran junto con su categoría: perder capturas por
    reorganizar las líneas de vida sería el peor resultado posible.
    """
    movidos = CategoryService(session).delete(category_id, move_tickets=move_tickets)
    return {"tickets_movidos": movidos}
