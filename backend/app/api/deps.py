"""Dependencias compartidas de la API.

Se declaran como alias de tipo con Annotated para que los endpoints queden
legibles (`service: TicketServiceDep`) en vez de arrastrar `Depends(...)` en cada
firma.
"""

from collections.abc import Callable
from typing import Annotated

from fastapi import Cookie, Depends, HTTPException, Query, Request, status
from sqlalchemy.orm import Session

from app.core.config import Settings, get_settings
from app.core.security import SESSION_COOKIE
from app.db.models import User
from app.db.session import SessionFactory, declarar_dueno, get_session
from app.services.auth import AuthService
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


def ip_del_cliente(request: Request) -> str:
    """La IP de quien llama, mirando la cabecera que pone Caddy.

    Sin esto, todas las peticiones vendrían de la IP del contenedor de Caddy y
    el límite por IP sería en realidad un límite global: un bot dejaría a
    todos afuera con diez intentos.

    Confiar en X-Forwarded-For es seguro AQUÍ porque el backend no está
    publicado: solo Caddy alcanza el puerto, y Caddy reescribe la cabecera.
    Con el backend expuesto a internet, cualquiera podría falsificarla.
    """
    reenviada = request.headers.get("x-forwarded-for")
    if reenviada:
        # El primero de la lista es el cliente original.
        return reenviada.split(",")[0].strip()
    return request.client.host if request.client else "desconocida"


def current_user(
    session: SessionDep,
    silu_session: Annotated[str | None, Cookie(alias=SESSION_COOKIE)] = None,
) -> User:
    """El usuario dueño de la sesión. Corta el paso si no hay una válida."""
    if not silu_session:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED, detail="Sesión inválida"
        )

    usuario = AuthService(session).usuario_de_sesion(silu_session)
    if usuario is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED, detail="Sesión inválida"
        )

    # Desde aquí la sesión sabe de quién es la petición: es lo que llena el
    # `user_id` de lo que se inserte y lo que filtra lo que se lee.
    declarar_dueno(session, usuario.id)
    return usuario


CurrentUser = Annotated[User, Depends(current_user)]


def require_session(_: CurrentUser) -> None:
    """Exige una sesión válida, sin que al endpoint le importe de quién.

    Se mantiene para los routers que solo necesitan cerrar el paso. Cuando
    cada cosa tenga dueño, esos routers van a pedir CurrentUser en su lugar.
    """


def require_admin(usuario: CurrentUser) -> User:
    if not usuario.is_admin:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Necesitas ser administrador",
        )
    return usuario


AdminUser = Annotated[User, Depends(require_admin)]

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
