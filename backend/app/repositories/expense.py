"""Acceso a datos de gastos."""

# Las anotaciones se evalúan de forma diferida: el método `list` de la clase
# tapa al `list` de Python y rompería las anotaciones que lo usan después.
from __future__ import annotations

from collections.abc import Sequence
from datetime import date
from uuid import UUID

from sqlalchemy import Select, func, select
from sqlalchemy.orm import selectinload

from app.db.models import (
    Expense,
    ExpenseCategory,
    ExpenseSubcategory,
    PaymentMethod,
)
from app.repositories.base import BaseRepository


class EtiquetaRepository(BaseRepository):
    """Categorías de gasto y medios de pago comparten estructura y consultas.

    Hereda de BaseRepository por `dueno` y `mios`: el modelo se recibe en el
    constructor en vez de fijarse en la clase, pero el filtrado por dueño es
    el mismo que en cualquier otro repositorio.
    """

    def __init__(self, session, model) -> None:
        self.session = session
        self.model = model

    def get(self, etiqueta_id: UUID):
        return self.mio(self.session.get(self.model, etiqueta_id))

    def get_by_name(self, name: str):
        stmt = self.mios(
            select(self.model).where(
                func.lower(self.model.name) == name.strip().lower()
            )
        )
        return self.session.execute(stmt).scalar_one_or_none()

    def list(self) -> Sequence:
        stmt = self.mios(
            select(self.model).order_by(self.model.position, self.model.name)
        )
        return self.session.execute(stmt).scalars().all()

    def add(self, etiqueta):
        self.session.add(etiqueta)
        self.session.flush()
        self.session.refresh(etiqueta)
        return etiqueta

    def delete(self, etiqueta) -> None:
        self.session.delete(etiqueta)
        self.session.flush()

    def next_position(self) -> int:
        stmt = self.mios(
            select(func.coalesce(func.max(self.model.position), -1) + 1)
        )
        return int(self.session.execute(stmt).scalar_one())

    def usos(self) -> dict[UUID, int]:
        """Cuántos gastos usa cada etiqueta, en una sola consulta."""
        columna = {
            ExpenseCategory: Expense.category_id,
            ExpenseSubcategory: Expense.subcategory_id,
        }.get(self.model, Expense.payment_method_id)
        stmt = (
            select(columna, func.count())
            .where(Expense.user_id == self.dueno)
            .group_by(columna)
        )
        return {fila[0]: fila[1] for fila in self.session.execute(stmt)}


class ExpenseRepository(BaseRepository[Expense]):
    model = Expense

    def get(self, expense_id: UUID) -> Expense | None:
        return self.mio(self.session.get(Expense, expense_id))

    def list(self, *, desde: date, hasta: date) -> Sequence[Expense]:
        stmt = (
            self._rango(desde, hasta)
            .options(
                selectinload(Expense.category),
                selectinload(Expense.subcategory),
                selectinload(Expense.payment_method),
            )
            # Lo más reciente primero: al revisar gastos, lo de ayer importa
            # más que lo del mes pasado. Es el caso opuesto a la bandeja.
            .order_by(Expense.spent_on.desc(), Expense.id.desc())
        )
        return self.session.execute(stmt).scalars().all()

    def total(self, *, desde: date, hasta: date) -> tuple[int, int]:
        """Suma y cantidad del período, en una sola consulta."""
        stmt = self.mios(
            select(func.coalesce(func.sum(Expense.amount), 0), func.count()).where(
                Expense.spent_on.between(desde, hasta)
            )
        )
        suma, cantidad = self.session.execute(stmt).one()
        return int(suma), int(cantidad)

    def por_etiqueta(self, *, desde: date, hasta: date, modelo) -> list[tuple]:
        """Total agrupado por categoría o por medio de pago."""
        columna = (
            Expense.category_id
            if modelo is ExpenseCategory
            else Expense.payment_method_id
        )
        stmt = (
            select(modelo.id, modelo.name, func.sum(Expense.amount))
            .join(Expense, columna == modelo.id)
            .where(
                Expense.spent_on.between(desde, hasta),
                Expense.user_id == self.dueno,
            )
            .group_by(modelo.id, modelo.name)
            .order_by(func.sum(Expense.amount).desc())
        )
        return [(fila[0], fila[1], int(fila[2])) for fila in self.session.execute(stmt)]

    def por_subcategoria(self, *, desde: date, hasta: date) -> list[tuple]:
        """Total por subcategoría, con la categoría a la que pertenece."""
        stmt = (
            select(
                ExpenseSubcategory.category_id,
                ExpenseSubcategory.id,
                ExpenseSubcategory.name,
                func.sum(Expense.amount),
            )
            .join(Expense, Expense.subcategory_id == ExpenseSubcategory.id)
            .where(
                Expense.spent_on.between(desde, hasta),
                Expense.user_id == self.dueno,
            )
            .group_by(
                ExpenseSubcategory.category_id,
                ExpenseSubcategory.id,
                ExpenseSubcategory.name,
            )
            .order_by(func.sum(Expense.amount).desc())
        )
        return [
            (fila[0], fila[1], fila[2], int(fila[3]))
            for fila in self.session.execute(stmt)
        ]

    def por_mes(self, *, meses: int) -> list[tuple[str, int]]:
        """Serie mensual de los últimos N meses, del más antiguo al más nuevo."""
        mes = func.to_char(Expense.spent_on, "YYYY-MM")
        stmt = (
            select(mes, func.sum(Expense.amount))
            .where(Expense.user_id == self.dueno)
            .group_by(mes)
            .order_by(mes.desc())
            .limit(meses)
        )
        filas = [(fila[0], int(fila[1])) for fila in self.session.execute(stmt)]
        return list(reversed(filas))

    def add(self, expense: Expense) -> Expense:
        self.session.add(expense)
        self.session.flush()
        self.session.refresh(expense)
        return expense

    def delete(self, expense: Expense) -> None:
        self.session.delete(expense)
        self.session.flush()

    def _rango(self, desde: date, hasta: date) -> Select:
        return self.mios(select(Expense).where(Expense.spent_on.between(desde, hasta)))
