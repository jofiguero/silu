"""Dependencias compartidas de la API.

Se declaran como alias de tipo con Annotated para que los endpoints queden
legibles (`service: TicketServiceDep`) en vez de arrastrar `Depends(...)` en cada
firma.
"""

from collections.abc import Callable
from typing import Annotated

from fastapi import Cookie, Depends, HTTPException, Query, status
from sqlalchemy.orm import Session

from app.core.config import Settings, get_settings
from app.core.security import SESSION_COOKIE, verify_session_token
from app.db.session import SessionFactory, get_session
from app.services.ticket import TicketService

SessionDep = Annotated[Session, Depends(get_session)]
SettingsDep = Annotated[Settings, Depends(get_settings)]


def get_session_factory() -> Callable[[], Session]:
    """Fábrica de sesiones para trabajo fuera del ciclo de la petición.

    Se expone como dependencia, y no se importa directamente donde se usa, para
    que los tests puedan sustituirla. Sin esto, una tarea en segundo plano
    escribiría en la base real aunque el test haya sustituido la sesión.
    """
    return SessionFactory


SessionFactoryDep = Annotated[Callable[[], Session], Depends(get_session_factory)]


def require_session(
    settings: SettingsDep,
    silu_session: Annotated[str | None, Cookie(alias=SESSION_COOKIE)] = None,
) -> None:
    """Exige una sesión válida.

    Si la autenticación no está configurada, cierra el paso en vez de dejar
    todo abierto: una credencial que falta no debe traducirse en una API
    pública con los tickets de una persona.
    """
    if not settings.auth_configured:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="La autenticación no está configurada",
        )

    assert settings.session_secret  # garantizado por auth_configured

    if not silu_session or not verify_session_token(
        silu_session, settings.session_secret
    ):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED, detail="Sesión inválida"
        )


SessionGuard = Annotated[None, Depends(require_session)]


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
