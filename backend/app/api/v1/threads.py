"""Endpoints del dashboard semanal."""

from datetime import date
from typing import Annotated, Literal
from uuid import UUID

from fastapi import APIRouter, Depends, Query, Response, status

from app.api.deps import SessionDep, require_session
from app.core.calendario import lunes_de, semana_actual
from app.db.models import THREAD_COLORS
from app.schemas.common import ErrorResponse
from app.schemas.thread import (
    CleanupResult,
    HistoryRead,
    TaskEventRead,
    ReorderRequest,
    TaskCreate,
    TaskRead,
    TaskUpdate,
    ThreadCreate,
    ThreadRead,
    ThreadUpdate,
)
from app.services.thread import ThreadService

router = APIRouter(
    prefix="/threads",
    tags=["dashboard"],
    dependencies=[Depends(require_session)],
)

NOT_FOUND = {status.HTTP_404_NOT_FOUND: {"model": ErrorResponse}}


Scope = Literal["week", "day", "backlog", "all"]


def _en_scope(task, scope: Scope, week: date, day: date) -> bool:
    """Si la tarea pertenece al área que se está mirando."""
    if scope == "all":
        return True
    if scope == "backlog":
        # "Otras tareas": lo que hay que hacer en el thread pero no está
        # comprometido para ninguna semana.
        return task.week is None
    if scope == "week":
        return task.week == week

    if task.day == day:
        return True

    # Atrasadas. Lo que quedó pendiente en un día anterior sigue a la vista,
    # conservando su día: moverlo solo al día de hoy haría que el panel
    # mintiera sobre lo que se comprometió, y avisar es justo para lo que
    # sirve. Solo aparecen mirando hoy; un martes pasado muestra su martes.
    return (
        day == date.today()
        and task.day is not None
        and task.day < day
        and task.done_at is None
    )


def _read(
    thread,
    *,
    include_cleared: bool = False,
    scope: Scope = "all",
    week: date | None = None,
    day: date | None = None,
) -> ThreadRead:
    """Arma la salida dejando fuera lo ya limpiado del pizarrón."""
    tareas = [
        TaskRead.model_validate(t)
        for t in thread.tasks
        if (include_cleared or t.cleared_at is None)
        and _en_scope(t, scope, week or semana_actual(), day or date.today())
    ]
    return ThreadRead(
        id=thread.id,
        created_at=thread.created_at,
        name=thread.name,
        color=thread.color,
        position=thread.position,
        width=thread.width,
        height=thread.height,
        tasks=tareas,
    )


@router.get("/colors", summary="Paleta disponible")
def colors() -> list[str]:
    """Los colores que acepta el pizarrón. El frontend dibuja a partir de esto."""
    return list(THREAD_COLORS)


@router.get("", summary="Listar threads con sus tareas")
def list_threads(
    session: SessionDep,
    include_cleared: Annotated[
        bool, Query(description="Incluir las tareas ya limpiadas")
    ] = False,
    scope: Annotated[
        Scope,
        Query(description="Área a mirar: la semana, un día, otras tareas, o todo"),
    ] = "week",
    week: Annotated[
        date | None,
        Query(description="Cualquier día de la semana a mirar; por defecto, la actual"),
    ] = None,
    day: Annotated[
        date | None,
        Query(description="El día a mirar con scope=day; por defecto, hoy"),
    ] = None,
) -> list[ThreadRead]:
    """Los threads con las tareas del área pedida.

    El pizarrón pide siempre un área concreta: devolver todas las tareas de
    todas las semanas y filtrar en el navegador haría crecer la respuesta sin
    techo a medida que se acumule historial.
    """
    # Se acepta cualquier día y se normaliza al lunes: así el frontend no
    # tiene que repetir la aritmética de semanas ni arriesgarse a discrepar.
    lunes = lunes_de(week) if week is not None else semana_actual()
    return [
        _read(
            thread,
            include_cleared=include_cleared,
            scope=scope,
            week=lunes,
            day=day or date.today(),
        )
        for thread in ThreadService(session).list()
    ]


@router.post("", status_code=status.HTTP_201_CREATED, summary="Crear thread")
def create_thread(data: ThreadCreate, session: SessionDep) -> ThreadRead:
    return _read(ThreadService(session).create(data))


@router.patch("/{thread_id}", summary="Editar thread", responses=NOT_FOUND)
def update_thread(
    thread_id: UUID, data: ThreadUpdate, session: SessionDep
) -> ThreadRead:
    return _read(ThreadService(session).update(thread_id, data))


@router.delete(
    "/{thread_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    summary="Eliminar thread y sus tareas",
    responses=NOT_FOUND,
)
def delete_thread(thread_id: UUID, session: SessionDep) -> Response:
    ThreadService(session).delete(thread_id)
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.post("/reorder", summary="Reordenar el pizarrón")
def reorder(data: ReorderRequest, session: SessionDep) -> list[ThreadRead]:
    """Recibe el orden completo, no un movimiento.

    Mandar la lista entera evita que el orden quede inconsistente si dos
    reacomodos se pisan.
    """
    return [_read(t) for t in ThreadService(session).reorder(data.ids)]


@router.post(
    "/{thread_id}/tasks",
    status_code=status.HTTP_201_CREATED,
    summary="Agregar tarea",
    responses=NOT_FOUND,
)
def add_task(thread_id: UUID, data: TaskCreate, session: SessionDep) -> TaskRead:
    return TaskRead.model_validate(ThreadService(session).add_task(thread_id, data))


@router.post(
    "/{thread_id}/tasks/reorder",
    summary="Reordenar las tareas de un papel",
    responses=NOT_FOUND,
)
def reorder_tasks(
    thread_id: UUID, data: ReorderRequest, session: SessionDep
) -> list[TaskRead]:
    return [
        TaskRead.model_validate(t)
        for t in ThreadService(session).reorder_tasks(thread_id, data.ids)
    ]


@router.patch("/tasks/{task_id}", summary="Editar o marcar tarea", responses=NOT_FOUND)
def update_task(task_id: UUID, data: TaskUpdate, session: SessionDep) -> TaskRead:
    return TaskRead.model_validate(ThreadService(session).update_task(task_id, data))


@router.delete(
    "/tasks/{task_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    summary="Eliminar tarea",
    responses=NOT_FOUND,
)
def delete_task(task_id: UUID, session: SessionDep) -> Response:
    ThreadService(session).delete_task(task_id)
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.get("/history", summary="Qué pasó entre dos fechas")
def history(
    session: SessionDep,
    desde: Annotated[date, Query(description="Primer día incluido")],
    hasta: Annotated[date, Query(description="Último día incluido")],
) -> HistoryRead:
    """El registro de lo que le pasó a las tareas, con su resumen.

    El atraso no se guarda: se calcula al leer, comparando el cierre con el
    día al que la tarea estaba comprometida. Guardarlo sería un dato derivado
    que puede quedar desincronizado del que lo origina.
    """
    datos = ThreadService(session).history(desde, hasta)
    return HistoryRead(
        **{k: v for k, v in datos.items() if k != "eventos"},
        eventos=[
            TaskEventRead.model_validate(evento).model_copy(
                update={"atraso": atraso}
            )
            for evento, atraso in datos["eventos"]
        ],
    )


@router.post("/cleanup", summary="Limpiar lo tachado del pizarrón")
def cleanup(session: SessionDep) -> CleanupResult:
    """Saca de la vista las tareas marcadas. No las borra: quedan archivadas."""
    return CleanupResult(limpiadas=ThreadService(session).cleanup())
