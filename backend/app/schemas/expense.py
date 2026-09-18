"""Esquemas de gastos."""

from datetime import date, datetime
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field


class EtiquetaCreate(BaseModel):
    """Alta de una categoría de gasto o de un medio de pago."""

    model_config = ConfigDict(extra="forbid")

    name: str = Field(min_length=1, max_length=60)


class EtiquetaUpdate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    name: str | None = Field(default=None, min_length=1, max_length=60)
    position: int | None = Field(default=None, ge=0)


class EtiquetaRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    name: str
    position: int
    # Cuántos gastos la usan: el gestor lo muestra antes de eliminarla.
    usos: int = 0


class ExpenseCreate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    # gt=0 y entero: el peso chileno no tiene centavos y un gasto de cero o
    # negativo no es un gasto.
    amount: int = Field(gt=0, le=1_000_000_000, description="Monto en pesos")
    category_id: UUID
    payment_method_id: UUID
    # La manda el cliente y no el servidor: el servidor corre en UTC y "hoy" en
    # Chile no siempre coincide.
    spent_on: date | None = None
    description: str | None = Field(default=None, max_length=300)


class ExpenseUpdate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    amount: int | None = Field(default=None, gt=0, le=1_000_000_000)
    category_id: UUID | None = None
    payment_method_id: UUID | None = None
    spent_on: date | None = None
    description: str | None = Field(default=None, max_length=300)


class ExpenseRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    created_at: datetime
    amount: int
    spent_on: date
    description: str | None = None
    category_id: UUID
    category_name: str = ""
    payment_method_id: UUID
    payment_method_name: str = ""


class Tajada(BaseModel):
    """Un corte del total: por categoría o por medio de pago."""

    id: UUID
    name: str
    total: int
    # Porcentaje sobre el total del período, ya calculado: el frontend no
    # debería tener que dividir para dibujar una barra.
    porcentaje: float


class Mes(BaseModel):
    # "2026-09", para ordenar y etiquetar sin ambigüedad de zona horaria.
    mes: str
    total: int


class Resumen(BaseModel):
    desde: date
    hasta: date
    total: int
    cantidad: int
    por_categoria: list[Tajada]
    por_medio: list[Tajada]
    # Serie mensual para comparar con los meses anteriores.
    meses: list[Mes]
