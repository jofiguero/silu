"""Endpoints del dashboard semanal."""

from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, Query, Response, status

from app.api.deps import SessionDep, require_session
from app.db.models import THREAD_COLORS
from app.schemas.common import ErrorResponse
from app.schemas.thread import (
    CleanupResult,
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


def _read(thread, *, include_cleared: bool = False) -> ThreadRead:
    """Arma la salida dejando fuera lo ya limpiado del pizarrón."""
    tareas = [
        TaskRead.model_validate(t)
        for t in thread.tasks
        if include_cleared or t.cleared_at is None
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
) -> list[ThreadRead]:
    return [
        _read(thread, include_cleared=include_cleared)
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


@router.post("/cleanup", summary="Limpiar lo tachado del pizarrón")
def cleanup(session: SessionDep) -> CleanupResult:
    """Saca de la vista las tareas marcadas. No las borra: quedan archivadas."""
    return CleanupResult(limpiadas=ThreadService(session).cleanup())
