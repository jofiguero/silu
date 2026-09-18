"""Esquemas de entrada y salida de tickets.

Separados de los modelos de SQLAlchemy a propósito: el modelo describe cómo se
guarda un ticket, el esquema describe qué acepta y qué expone la API. Mezclarlos
obliga a filtrar campos a mano y hace fácil filtrar de menos.
"""

from datetime import datetime
from enum import StrEnum
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, model_validator


class TicketStatus(StrEnum):
    """Ciclo de vida de un ticket."""

    PENDIENTE = "pendiente"
    EN_CURSO = "en_curso"
    ARCHIVADO = "archivado"


class TicketBase(BaseModel):
    title: str = Field(
        min_length=1,
        max_length=200,
        description="Título corto, generado por el LLM",
    )
    summary: str = Field(
        min_length=1,
        description=(
            "Descripción autocontenida del hecho o la tarea. No es un resumen: "
            "debe permitir entender de qué se trataba sin el audio original."
        ),
    )


class TicketCreate(TicketBase):
    """Alta de un ticket, tal como la produce el pipeline de captura."""

    model_config = ConfigDict(extra="forbid")

    raw_text: str = Field(
        min_length=1,
        description="Transcripción o texto original, tal cual llegó",
    )
    status: TicketStatus = TicketStatus.PENDIENTE
    urgent: bool = False


class TicketUpdate(BaseModel):
    """Edición parcial. Solo se modifican los campos presentes.

    `extra="forbid"` hace que un campo mal escrito falle con 422 en vez de
    ignorarse en silencio, que es la forma más común de perder una edición.
    """

    model_config = ConfigDict(extra="forbid")

    title: str | None = Field(default=None, min_length=1, max_length=200)
    summary: str | None = Field(default=None, min_length=1)
    raw_text: str | None = Field(default=None, min_length=1)
    status: TicketStatus | None = None
    resolution: str | None = None
    urgent: bool | None = None

    @model_validator(mode="after")
    def at_least_one_field(self) -> "TicketUpdate":
        if not self.model_fields_set:
            raise ValueError("Se requiere al menos un campo para actualizar")
        return self


class TicketDispatch(BaseModel):
    """Despacho de un ticket a su destino final.

    Es una operación distinta de una edición cualquiera: deja constancia de qué
    se hizo y cierra el ticket, así que exige una resolución no vacía.
    """

    model_config = ConfigDict(extra="forbid")

    resolution: str = Field(
        min_length=1,
        description=(
            "Qué se hizo finalmente con el ticket, "
            "ej. 'Registrado como gasto de comida, $1.000'"
        ),
    )
    status: TicketStatus = Field(
        default=TicketStatus.ARCHIVADO,
        description="Estado final; por defecto queda archivado",
    )


class TicketRead(TicketBase):
    """Representación pública de un ticket."""

    model_config = ConfigDict(from_attributes=True)

    id: UUID
    created_at: datetime
    updated_at: datetime
    raw_text: str
    status: TicketStatus
    resolution: str | None = None
    urgent: bool = False
