"""Endpoints de salud."""

from fastapi import APIRouter, status
from pydantic import BaseModel
from sqlalchemy import text

from app.api.deps import SessionDep

router = APIRouter(tags=["salud"])


class Health(BaseModel):
    status: str
    database: str


@router.get("/health", summary="Estado del servicio")
def health() -> Health:
    """Responde sin tocar la base: sirve para saber si el proceso está vivo."""
    return Health(status="ok", database="no verificada")


@router.get(
    "/health/db",
    summary="Estado de la base de datos",
    responses={status.HTTP_503_SERVICE_UNAVAILABLE: {"description": "Base caída"}},
)
def health_db(session: SessionDep) -> Health:
    """Verifica que la conexión a Postgres esté realmente operativa."""
    session.execute(text("SELECT 1"))
    return Health(status="ok", database="ok")
