"""Endpoints de gastos."""

from datetime import date
from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, Query, Response, status

from app.api.deps import SessionDep, require_session
from app.db.models import ExpenseCategory, PaymentMethod
from app.schemas.common import ErrorResponse
from app.schemas.expense import (
    EtiquetaCreate,
    EtiquetaRead,
    EtiquetaUpdate,
    ExpenseCreate,
    ExpenseRead,
    ExpenseUpdate,
    Resumen,
)
from app.services.expense import EtiquetaService, ExpenseService

router = APIRouter(
    prefix="/expenses",
    tags=["gastos"],
    dependencies=[Depends(require_session)],
)

NOT_FOUND = {status.HTTP_404_NOT_FOUND: {"model": ErrorResponse}}

# El rango lo manda siempre el cliente: el servidor corre en UTC y "este mes"
# en Chile no siempre coincide con el mes del servidor.
DesdeQ = Annotated[date, Query(description="Inicio del período, inclusive")]
HastaQ = Annotated[date, Query(description="Fin del período, inclusive")]


def _etiqueta(etiqueta, usos: int = 0) -> EtiquetaRead:
    return EtiquetaRead(
        id=etiqueta.id, name=etiqueta.name, position=etiqueta.position, usos=usos
    )


# --- Categorías y medios de pago ---
#
# Van antes que /{expense_id}: si fueran después, la ruta con parámetro
# capturaría "categories" e intentaría leerlo como UUID.


@router.get("/categories", summary="Categorías de gasto")
def list_categories(session: SessionDep) -> list[EtiquetaRead]:
    servicio = EtiquetaService(session, ExpenseCategory)
    return [_etiqueta(e, usos) for e, usos in servicio.list_con_usos()]


@router.post(
    "/categories", status_code=status.HTTP_201_CREATED, summary="Crear categoría"
)
def create_category(data: EtiquetaCreate, session: SessionDep) -> EtiquetaRead:
    return _etiqueta(EtiquetaService(session, ExpenseCategory).create(data))


@router.patch("/categories/{category_id}", summary="Editar categoría")
def update_category(
    category_id: UUID, data: EtiquetaUpdate, session: SessionDep
) -> EtiquetaRead:
    return _etiqueta(
        EtiquetaService(session, ExpenseCategory).update(category_id, data)
    )


@router.delete(
    "/categories/{category_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    summary="Eliminar categoría sin uso",
)
def delete_category(category_id: UUID, session: SessionDep) -> Response:
    EtiquetaService(session, ExpenseCategory).delete(category_id)
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.get("/methods", summary="Medios de pago")
def list_methods(session: SessionDep) -> list[EtiquetaRead]:
    servicio = EtiquetaService(session, PaymentMethod)
    return [_etiqueta(e, usos) for e, usos in servicio.list_con_usos()]


@router.post(
    "/methods", status_code=status.HTTP_201_CREATED, summary="Crear medio de pago"
)
def create_method(data: EtiquetaCreate, session: SessionDep) -> EtiquetaRead:
    return _etiqueta(EtiquetaService(session, PaymentMethod).create(data))


@router.patch("/methods/{method_id}", summary="Editar medio de pago")
def update_method(
    method_id: UUID, data: EtiquetaUpdate, session: SessionDep
) -> EtiquetaRead:
    return _etiqueta(EtiquetaService(session, PaymentMethod).update(method_id, data))


@router.delete(
    "/methods/{method_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    summary="Eliminar medio de pago sin uso",
)
def delete_method(method_id: UUID, session: SessionDep) -> Response:
    EtiquetaService(session, PaymentMethod).delete(method_id)
    return Response(status_code=status.HTTP_204_NO_CONTENT)


# --- Gastos ---


@router.get("/summary", summary="Totales del período")
def summary(session: SessionDep, desde: DesdeQ, hasta: HastaQ) -> Resumen:
    """Total, cortes por categoría y medio de pago, y la serie mensual."""
    return ExpenseService(session).resumen(desde=desde, hasta=hasta)


@router.get("", summary="Listar gastos de un período")
def list_expenses(
    session: SessionDep, desde: DesdeQ, hasta: HastaQ
) -> list[ExpenseRead]:
    return [
        ExpenseRead.model_validate(e)
        for e in ExpenseService(session).list(desde=desde, hasta=hasta)
    ]


@router.post("", status_code=status.HTTP_201_CREATED, summary="Registrar un gasto")
def create_expense(data: ExpenseCreate, session: SessionDep) -> ExpenseRead:
    """Solo se registra desde aquí, nunca desde el LLM.

    Un monto alucinado contamina los totales en silencio, y un total
    equivocado es peor que un gasto no registrado.
    """
    return ExpenseRead.model_validate(ExpenseService(session).create(data))


@router.patch("/{expense_id}", summary="Editar un gasto", responses=NOT_FOUND)
def update_expense(
    expense_id: UUID, data: ExpenseUpdate, session: SessionDep
) -> ExpenseRead:
    return ExpenseRead.model_validate(ExpenseService(session).update(expense_id, data))


@router.delete(
    "/{expense_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    summary="Eliminar un gasto",
    responses=NOT_FOUND,
)
def delete_expense(expense_id: UUID, session: SessionDep) -> Response:
    ExpenseService(session).delete(expense_id)
    return Response(status_code=status.HTTP_204_NO_CONTENT)
