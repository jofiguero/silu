"""Esquemas de proyectos y prompts."""

from datetime import datetime
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field


class ProjectCreate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    name: str = Field(min_length=1, max_length=80)
    # El descriptor que recibe el metaprompter como contexto.
    description_md: str = Field(default="", max_length=20_000)


class ProjectUpdate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    name: str | None = Field(default=None, min_length=1, max_length=80)
    description_md: str | None = Field(default=None, max_length=20_000)
    position: int | None = Field(default=None, ge=0)


class ProjectRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    created_at: datetime
    updated_at: datetime
    name: str
    description_md: str
    position: int
    # Cuántos prompts tiene: se muestra junto al nombre para saber dónde hay
    # material sin entrar al proyecto.
    prompts_count: int = 0


class PromptCreate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    title: str = Field(min_length=1, max_length=200)
    content: str = Field(min_length=1)
    project_id: UUID | None = None
    raw_text: str | None = None


class PromptUpdate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    title: str | None = Field(default=None, min_length=1, max_length=200)
    content: str | None = Field(default=None, min_length=1)
    # Explícitamente nullable: mandar null lo saca del proyecto.
    project_id: UUID | None = None


class PromptRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    created_at: datetime
    updated_at: datetime
    title: str
    content: str
    raw_text: str
    edited: bool
    project_id: UUID | None = None
    project_name: str = ""
