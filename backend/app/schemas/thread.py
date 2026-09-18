"""Esquemas del dashboard semanal."""

from datetime import datetime
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


class TaskUpdate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    text: str | None = Field(default=None, min_length=1, max_length=300)
    done: bool | None = None
    position: int | None = Field(default=None, ge=0)


class TaskRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    text: str = Field(validation_alias="text_")
    done: bool
    done_at: datetime | None = None
    created_at: datetime
    position: int


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
