"""Endpoints de tickets."""

from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Query, Response, status

from app.api.deps import PaginationDep, TicketServiceDep
from app.schemas.common import ErrorResponse, Page
from app.schemas.ticket import (
    TicketCreate,
    TicketDispatch,
    TicketRead,
    TicketStatus,
    TicketUpdate,
)

router = APIRouter(prefix="/tickets", tags=["tickets"])

NOT_FOUND = {status.HTTP_404_NOT_FOUND: {"model": ErrorResponse}}


@router.get("", summary="Listar tickets")
def list_tickets(
    service: TicketServiceDep,
    pagination: PaginationDep,
    status_filter: Annotated[
        TicketStatus | None,
        Query(alias="status", description="Filtrar por estado"),
    ] = None,
    search: Annotated[
        str | None,
        Query(min_length=1, description="Buscar en título y descripción"),
    ] = None,
) -> Page[TicketRead]:
    """Bandeja de tickets, del más reciente al más antiguo."""
    items, total = service.list(
        status=status_filter,
        search=search,
        limit=pagination.limit,
        offset=pagination.offset,
    )
    return Page[TicketRead](
        items=[TicketRead.model_validate(item) for item in items],
        total=total,
        limit=pagination.limit,
        offset=pagination.offset,
    )


@router.post(
    "",
    status_code=status.HTTP_201_CREATED,
    summary="Crear un ticket",
)
def create_ticket(data: TicketCreate, service: TicketServiceDep) -> TicketRead:
    """Alta de un ticket. Es lo que invoca el pipeline de captura."""
    return TicketRead.model_validate(service.create(data))


@router.get("/{ticket_id}", summary="Obtener un ticket", responses=NOT_FOUND)
def get_ticket(ticket_id: UUID, service: TicketServiceDep) -> TicketRead:
    return TicketRead.model_validate(service.get(ticket_id))


@router.patch("/{ticket_id}", summary="Editar un ticket", responses=NOT_FOUND)
def update_ticket(
    ticket_id: UUID, data: TicketUpdate, service: TicketServiceDep
) -> TicketRead:
    """Edición parcial: solo se tocan los campos presentes en el cuerpo."""
    return TicketRead.model_validate(service.update(ticket_id, data))


@router.post(
    "/{ticket_id}/dispatch",
    summary="Despachar un ticket a su destino",
    responses=NOT_FOUND,
)
def dispatch_ticket(
    ticket_id: UUID, data: TicketDispatch, service: TicketServiceDep
) -> TicketRead:
    """Cierra el ticket registrando qué se hizo finalmente con él."""
    return TicketRead.model_validate(service.dispatch(ticket_id, data))


@router.delete(
    "/{ticket_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    summary="Eliminar un ticket",
    responses=NOT_FOUND,
)
def delete_ticket(ticket_id: UUID, service: TicketServiceDep) -> Response:
    service.delete(ticket_id)
    return Response(status_code=status.HTTP_204_NO_CONTENT)
