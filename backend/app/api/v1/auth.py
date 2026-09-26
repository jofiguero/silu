"""Inicio y cierre de sesión."""

import logging
from typing import Annotated

from fastapi import APIRouter, Cookie, Depends, HTTPException, Request, Response, status
from pydantic import BaseModel, ConfigDict, EmailStr, Field

from app.api.deps import CurrentUser, SessionDep, SettingsDep, ip_del_cliente
from app.core.security import SESSION_COOKIE
from app.services.auth import (
    AuthService,
    CredencialesInvalidas,
    DemasiadosIntentos,
    SinUsuarios,
)

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/auth", tags=["auth"])


class LoginRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    email: EmailStr
    password: str = Field(min_length=1)


class SessionStatus(BaseModel):
    authenticated: bool
    email: str | None = None
    role: str | None = None


@router.post("/login", summary="Iniciar sesión")
def login(
    data: LoginRequest,
    request: Request,
    response: Response,
    session: SessionDep,
    settings: SettingsDep,
) -> SessionStatus:
    auth = AuthService(session)
    ip = ip_del_cliente(request)

    try:
        usuario, token = auth.login(
            data.email,
            data.password,
            ip=ip,
            user_agent=request.headers.get("user-agent"),
            dias=settings.session_days,
        )
    except SinUsuarios:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail=(
                "Todavía no hay ninguna cuenta. Créala en el servidor con "
                "scripts/crear_usuario.py"
            ),
        ) from None
    except DemasiadosIntentos as exc:
        logger.warning("Límite de intentos alcanzado desde %s", ip)
        raise HTTPException(
            status_code=status.HTTP_429_TOO_MANY_REQUESTS,
            detail="Demasiados intentos. Espera unos minutos.",
            headers={"Retry-After": str(exc.segundos)},
        ) from None
    except CredencialesInvalidas:
        logger.warning("Inicio de sesión fallido desde %s", ip)
        # Mensaje único para correo inexistente, contraseña mala y cuenta
        # desactivada: separarlos diría cuáles correos están registrados.
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Credenciales incorrectas",
        ) from None

    ttl = settings.session_days * 24 * 3600
    response.set_cookie(
        key=SESSION_COOKIE,
        value=token,
        max_age=ttl,
        # httponly: el token no es legible desde JavaScript, así que un XSS no
        # puede robarlo. secure: solo viaja por HTTPS.
        httponly=True,
        secure=True,
        # lax en vez de strict: strict rompe el caso de llegar a la app desde
        # un enlace externo, que es justo como se abre desde el celular.
        samesite="lax",
        path="/",
    )
    return SessionStatus(
        authenticated=True, email=usuario.email, role=usuario.role
    )


@router.post("/logout", summary="Cerrar sesión")
def logout(
    response: Response,
    session: SessionDep,
    silu_session: Annotated[str | None, Cookie(alias=SESSION_COOKIE)] = None,
) -> SessionStatus:
    # Se borra también del servidor: sin esto la cookie desaparece del
    # navegador pero la sesión seguiría siendo válida para quien la tuviera.
    if silu_session:
        AuthService(session).cerrar_sesion(silu_session)
    response.delete_cookie(SESSION_COOKIE, path="/")
    return SessionStatus(authenticated=False)


@router.get("/me", summary="Estado de la sesión")
def me(usuario: CurrentUser) -> SessionStatus:
    """Sirve para que el frontend sepa si mostrar el login o la bandeja."""
    return SessionStatus(
        authenticated=True, email=usuario.email, role=usuario.role
    )
