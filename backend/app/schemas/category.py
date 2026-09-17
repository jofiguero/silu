"""Esquemas de categorías (líneas de vida)."""

from datetime import datetime
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field


class CategoryBase(BaseModel):
    name: str = Field(
        min_length=1,
        max_length=60,
        description="Nombre de la línea de vida, ej. 'Gastos'",
    )


class CategoryCreate(CategoryBase):
    model_config = ConfigDict(extra="forbid")

    position: int | None = Field(
        default=None, ge=0, description="Orden en la barra superior"
    )


class CategoryUpdate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    name: str | None = Field(default=None, min_length=1, max_length=60)
    position: int | None = Field(default=None, ge=0)


class CategoryRead(CategoryBase):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    created_at: datetime
    position: int
    is_default: bool
    # Cuántos tickets vivos tiene: el frontend lo muestra junto al nombre para
    # saber dónde hay trabajo sin entrar a la categoría.
    open_count: int = 0
