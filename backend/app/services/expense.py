"""Lógica de negocio de gastos."""

from __future__ import annotations

from collections.abc import Sequence
from datetime import date
from uuid import UUID

from sqlalchemy.orm import Session

from app.core.exceptions import (
    EtiquetaEnUsoError,
    EtiquetaNameTakenError,
    EtiquetaNotFoundError,
    ExpenseNotFoundError,
)
from app.db.models import Expense, ExpenseCategory, PaymentMethod
from app.repositories.expense import EtiquetaRepository, ExpenseRepository
from app.schemas.expense import (
    EtiquetaCreate,
    EtiquetaUpdate,
    ExpenseCreate,
    ExpenseUpdate,
    Mes,
    Resumen,
    Tajada,
)

# Cuántos meses se muestran en la comparación. Seis cabe en pantalla y alcanza
# para ver una tendencia sin volverse un gráfico que hay que interpretar.
MESES_COMPARACION = 6


class EtiquetaService:
    """Categorías de gasto y medios de pago: misma lógica, distinta tabla."""

    def __init__(self, session: Session, model) -> None:
        self.session = session
        self.model = model
        self.repository = EtiquetaRepository(session, model)

    def get(self, etiqueta_id: UUID):
        etiqueta = self.repository.get(etiqueta_id)
        if etiqueta is None:
            raise EtiquetaNotFoundError(etiqueta_id)
        return etiqueta

    def list_con_usos(self) -> list[tuple]:
        usos = self.repository.usos()
        return [(e, usos.get(e.id, 0)) for e in self.repository.list()]

    def create(self, data: EtiquetaCreate):
        name = data.name.strip()
        if self.repository.get_by_name(name) is not None:
            raise EtiquetaNameTakenError(name)

        etiqueta = self.model(name=name, position=self.repository.next_position())
        self.repository.add(etiqueta)
        self.session.commit()
        self.session.refresh(etiqueta)
        return etiqueta

    def update(self, etiqueta_id: UUID, data: EtiquetaUpdate):
        etiqueta = self.get(etiqueta_id)
        changes = data.model_dump(exclude_unset=True)

        if changes.get("name"):
            nuevo = changes["name"].strip()
            existente = self.repository.get_by_name(nuevo)
            if existente is not None and existente.id != etiqueta.id:
                raise EtiquetaNameTakenError(nuevo)
            etiqueta.name = nuevo

        if changes.get("position") is not None:
            etiqueta.position = changes["position"]

        self.session.commit()
        self.session.refresh(etiqueta)
        return etiqueta

    def delete(self, etiqueta_id: UUID) -> None:
        """Elimina una etiqueta que no esté en uso.

        A diferencia de las categorías de tickets, aquí no se reasignan los
        gastos a otra: cambiarle la categoría a un gasto pasado falsea el
        historial, que es justamente lo que este panel existe para conservar.
        """
        etiqueta = self.get(etiqueta_id)
        usos = self.repository.usos().get(etiqueta.id, 0)
        if usos:
            raise EtiquetaEnUsoError(
                f"{etiqueta.name!r} está en {usos} gastos. Reasígnalos antes de "
                "eliminarla, o renómbrala si solo quieres cambiarle el nombre."
            )

        self.repository.delete(etiqueta)
        self.session.commit()


class ExpenseService:
    def __init__(self, session: Session) -> None:
        self.session = session
        self.repository = ExpenseRepository(session)
        self.categories = EtiquetaService(session, ExpenseCategory)
        self.methods = EtiquetaService(session, PaymentMethod)

    def get(self, expense_id: UUID) -> Expense:
        expense = self.repository.get(expense_id)
        if expense is None:
            raise ExpenseNotFoundError(expense_id)
        return expense

    def list(self, *, desde: date, hasta: date) -> Sequence[Expense]:
        return self.repository.list(desde=desde, hasta=hasta)

    def create(self, data: ExpenseCreate) -> Expense:
        # get() valida que existan: sin esto, un id inventado fallaría con un
        # error de integridad de Postgres en vez de un 404 legible.
        self.categories.get(data.category_id)
        self.methods.get(data.payment_method_id)

        expense = Expense(
            amount=data.amount,
            category_id=data.category_id,
            payment_method_id=data.payment_method_id,
            description=(data.description or "").strip() or None,
        )
        if data.spent_on is not None:
            expense.spent_on = data.spent_on

        self.repository.add(expense)
        self.session.commit()
        self.session.refresh(expense)
        return expense

    def update(self, expense_id: UUID, data: ExpenseUpdate) -> Expense:
        expense = self.get(expense_id)
        changes = data.model_dump(exclude_unset=True)

        if "category_id" in changes and changes["category_id"]:
            self.categories.get(changes["category_id"])
        if "payment_method_id" in changes and changes["payment_method_id"]:
            self.methods.get(changes["payment_method_id"])

        for campo, valor in changes.items():
            if campo == "description":
                valor = (valor or "").strip() or None
            if valor is not None or campo == "description":
                setattr(expense, campo, valor)

        self.session.commit()
        self.session.refresh(expense)
        return expense

    def delete(self, expense_id: UUID) -> None:
        self.repository.delete(self.get(expense_id))
        self.session.commit()

    def resumen(self, *, desde: date, hasta: date) -> Resumen:
        """Total del período con sus cortes y la serie mensual."""
        total, cantidad = self.repository.total(desde=desde, hasta=hasta)

        def tajadas(modelo) -> list[Tajada]:
            filas = self.repository.por_etiqueta(
                desde=desde, hasta=hasta, modelo=modelo
            )
            return [
                Tajada(
                    id=id_,
                    name=nombre,
                    total=monto,
                    # El porcentaje se calcula aquí: el frontend no debería
                    # tener que dividir para dibujar una barra.
                    porcentaje=round(monto * 100 / total, 1) if total else 0.0,
                )
                for id_, nombre, monto in filas
            ]

        return Resumen(
            desde=desde,
            hasta=hasta,
            total=total,
            cantidad=cantidad,
            por_categoria=tajadas(ExpenseCategory),
            por_medio=tajadas(PaymentMethod),
            meses=[
                Mes(mes=mes, total=monto)
                for mes, monto in self.repository.por_mes(meses=MESES_COMPARACION)
            ],
        )
