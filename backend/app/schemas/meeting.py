"""Esquemas de carpetas, reuniones y lo que se anota en ellas."""

from datetime import date, datetime
from typing import Annotated, Literal
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, StringConstraints

# Literal y no str: una zona desconocida se rechaza con 422 en el borde, antes
# de llegar al CHECK de la base.
Zona = Literal["temas", "conversado", "tareas", "apuntes"]

# Se recorta antes de medir: un texto de puros espacios pasaría un min_length
# y después chocaría con el CHECK de la base, que respondería con un 500.
Nombre = Annotated[
    str, StringConstraints(strip_whitespace=True, min_length=1, max_length=80)
]
Titulo = Annotated[
    str, StringConstraints(strip_whitespace=True, min_length=1, max_length=120)
]
Texto = Annotated[
    str, StringConstraints(strip_whitespace=True, min_length=1, max_length=2000)
]


class FolderCreate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    name: Nombre


class FolderUpdate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    name: Nombre | None = None
    position: int | None = Field(default=None, ge=0)


class FolderRead(BaseModel):
    id: UUID
    created_at: datetime
    name: str
    position: int
    # Se muestra junto al nombre para saber dónde hay reuniones sin entrar.
    meetings_count: int = 0


class MeetingCreate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    folder_id: UUID
    # Opcionales: sin título se llama por su fecha, y sin fecha es hoy. Crear
    # una reunión tiene que ser un clic, no un formulario.
    title: str | None = Field(default=None, max_length=120)
    fecha: date | None = None


class MeetingUpdate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    title: Titulo | None = None
    fecha: date | None = None


class ItemCreate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    zona: Zona
    text: Texto


class ItemUpdate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    text: Texto | None = None
    # Cambiar la zona es arrastrarlo a otro cuadrante.
    zona: Zona | None = None


class ItemRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    zona: Zona
    text: str = Field(validation_alias="text_")
    position: int


class MeetingListRead(BaseModel):
    """Una fila de la lista de reuniones de una carpeta, sin su tablero."""

    model_config = ConfigDict(from_attributes=True)

    id: UUID
    folder_id: UUID
    title: str
    fecha: date
    tiene_resumen: bool


class MeetingRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    created_at: datetime
    folder_id: UUID
    folder_name: str
    title: str
    fecha: date
    summary: str | None
    summary_at: datetime | None
    items: list[ItemRead]
