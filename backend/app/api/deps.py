"""Dependencias compartidas de la API.

Se declaran como alias de tipo con Annotated para que los endpoints queden
legibles (`service: TicketServiceDep`) en vez de arrastrar `Depends(...)` en cada
firma.
"""

from typing import Annotated

from fastapi import Depends, Query
from sqlalchemy.orm import Session

from app.core.config import Settings, get_settings
from app.db.session import get_session
from app.services.ticket import TicketService

SessionDep = Annotated[Session, Depends(get_session)]
SettingsDep = Annotated[Settings, Depends(get_settings)]


def get_ticket_service(session: SessionDep) -> TicketService:
    return TicketService(session)


TicketServiceDep = Annotated[TicketService, Depends(get_ticket_service)]


class Pagination:
    """Parámetros de paginación, validados y acotados en un solo lugar."""

    def __init__(
        self,
        limit: Annotated[
            int, Query(ge=1, le=200, description="Máximo de elementos a devolver")
        ] = 50,
        offset: Annotated[
            int, Query(ge=0, description="Elementos a omitir desde el inicio")
        ] = 0,
    ) -> None:
        self.limit = limit
        self.offset = offset


PaginationDep = Annotated[Pagination, Depends(Pagination)]
