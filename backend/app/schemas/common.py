"""Esquemas transversales."""

from typing import Generic, TypeVar

from pydantic import BaseModel, Field

T = TypeVar("T")


class Page(BaseModel, Generic[T]):
    """Una página de resultados con el contexto necesario para navegar.

    Se devuelve `total` para que el frontend pueda mostrar cuántos tickets hay
    sin pedir la colección completa.
    """

    items: list[T]
    total: int = Field(description="Total de elementos que cumplen el filtro")
    limit: int = Field(description="Tamaño de página solicitado")
    offset: int = Field(description="Elementos omitidos desde el inicio")


class ErrorResponse(BaseModel):
    """Forma única de todos los errores que devuelve la API."""

    detail: str
