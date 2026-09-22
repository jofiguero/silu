"""Esquemas del dashboard semanal."""

from datetime import date, datetime
from typing import Literal
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field

from app.db.models import THREAD_COLORS

# Literal y no str: un color fuera de la paleta se rechaza con 422 en vez de
# guardarse y romper la coherencia visual del pizarrón.
ThreadColor = Literal[THREAD_COLORS]  # type: ignore[valid-type]


class TaskCreate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    text: str = Field(min_length=1, max_length=300)
    description: str | None = Field(default=None, max_length=5000)

    # Donde nace la tarea. Sin nada, nace en la semana en curso, que es lo que
    # significa escribirla en el pizarron. `day` la baja de una a ese dia y la
    # semana se deduce sola. `backlog` la deja en "otras tareas", sin fecha.
    day: date | None = None
    backlog: bool = False


class TaskUpdate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    text: str | None = Field(default=None, min_length=1, max_length=300)
    # Explicitamente nullable: mandar null borra la descripcion.
    description: str | None = Field(default=None, max_length=5000)
    done: bool | None = None
    active: bool | None = Field(
        default=None, description="Trabajando en esto ahora mismo"
    )
    position: int | None = Field(default=None, ge=0)

    # Mover la tarea entre areas es escribir una de estas dos fechas, no
    # copiarla a otra lista. Ambas son explicitamente nullable porque mandar
    # null es como se saca de un area:
    #
    #   {"day": "2026-09-22"} -> a ese dia (y a su semana, que se deduce)
    #   {"day": null}         -> vuelve a la lista de la semana
    #   {"week": null}        -> vuelve a "otras tareas"
    #
    # Cambiar de semana suelta el dia: un dia de otra semana no significa nada.
    week: date | None = None
    day: date | None = None


class TaskRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    text: str = Field(validation_alias="text_")
    description: str | None = None
    done: bool
    active: bool = False
    done_at: datetime | None = None
    created_at: datetime
    position: int
    week: date | None = None
    day: date | None = None


class ThreadCreate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    name: str = Field(min_length=1, max_length=60)
    color: ThreadColor = "arena"


class ThreadUpdate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    name: str | None = Field(default=None, min_length=1, max_length=60)
    color: ThreadColor | None = None
    position: int | None = Field(default=None, ge=0)
    width: int | None = Field(default=None, ge=180, le=1200)
    height: int | None = Field(default=None, ge=120, le=1600)


class ThreadRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    created_at: datetime
    name: str
    color: str
    position: int
    width: int | None = None
    height: int | None = None
    tasks: list[TaskRead] = []


class ReorderRequest(BaseModel):
    """Nuevo orden completo del pizarrón, de izquierda a derecha."""

    model_config = ConfigDict(extra="forbid")

    ids: list[UUID] = Field(min_length=1)


class CleanupResult(BaseModel):
    limpiadas: int
