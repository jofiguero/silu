"""Inicio y cierre de sesión."""

import logging

from fastapi import APIRouter, HTTPException, Response, status
from pydantic import BaseModel, ConfigDict, Field

from app.api.deps import SessionGuard, SettingsDep
from app.core.security import (
    SESSION_COOKIE,
    create_session_token,
    verify_password,
)

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/auth", tags=["auth"])


class LoginRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    password: str = Field(min_length=1)


class SessionStatus(BaseModel):
    authenticated: bool


@router.post("/login", summary="Iniciar sesión")
def login(
    data: LoginRequest, response: Response, settings: SettingsDep
) -> SessionStatus:
    if not settings.auth_configured:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="La autenticación no está configurada",
        )

    assert settings.app_password and settings.session_secret  # garantizado arriba

    if not verify_password(data.password, settings.app_password):
        logger.warning("Intento de inicio de sesión fallido")
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED, detail="Contraseña incorrecta"
        )

    ttl = settings.session_days * 24 * 3600
    response.set_cookie(
        key=SESSION_COOKIE,
        value=create_session_token(settings.session_secret, ttl_seconds=ttl),
        max_age=ttl,
        # httponly: el token no es legible desde JavaScript, así que un XSS no
        # puede robarlo. secure: solo viaja por HTTPS.
        httponly=True,
        secure=True,
        # lax en vez de strict: strict rompe el caso de llegar a la app desde un
        # enlace externo, que es justo como se abre desde el celular.
        samesite="lax",
        path="/",
    )
    return SessionStatus(authenticated=True)


@router.post("/logout", summary="Cerrar sesión")
def logout(response: Response) -> SessionStatus:
    response.delete_cookie(SESSION_COOKIE, path="/")
    return SessionStatus(authenticated=False)


@router.get("/me", summary="Estado de la sesión")
def me(_: SessionGuard) -> SessionStatus:
    """Sirve para que el frontend sepa si mostrar el login o la bandeja."""
    return SessionStatus(authenticated=True)
