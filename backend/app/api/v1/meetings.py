"""Endpoints de reuniones."""

import logging
from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query, Response, status

from app.api.deps import SessionDep, SettingsDep, require_session
from app.integrations.resumen import ResumenError
from app.schemas.common import ErrorResponse
from app.schemas.meeting import (
    FolderCreate,
    FolderRead,
    FolderUpdate,
    ItemCreate,
    ItemRead,
    ItemUpdate,
    MeetingCreate,
    MeetingListRead,
    MeetingRead,
    MeetingUpdate,
)
from app.services.meeting import FolderService, MeetingService

logger = logging.getLogger(__name__)

router = APIRouter(
    prefix="/meetings",
    tags=["reuniones"],
    dependencies=[Depends(require_session)],
)

NOT_FOUND = {status.HTTP_404_NOT_FOUND: {"model": ErrorResponse}}


def _carpeta(folder) -> FolderRead:
    return FolderRead(
        id=folder.id,
        created_at=folder.created_at,
        name=folder.name,
        position=folder.position,
        meetings_count=len(folder.meetings),
    )


# --- Carpetas ---
#
# Van antes que /{meeting_id}: declaradas después, "folders" se leería como
# un id y la petición moriría en la validación del UUID.


@router.get("/folders", summary="Listar carpetas")
def list_folders(session: SessionDep) -> list[FolderRead]:
    return [_carpeta(f) for f in FolderService(session).list()]


@router.post("/folders", status_code=status.HTTP_201_CREATED, summary="Crear carpeta")
def create_folder(data: FolderCreate, session: SessionDep) -> FolderRead:
    return _carpeta(FolderService(session).create(data))


@router.patch("/folders/{folder_id}", summary="Editar carpeta", responses=NOT_FOUND)
def update_folder(
    folder_id: UUID, data: FolderUpdate, session: SessionDep
) -> FolderRead:
    return _carpeta(FolderService(session).update(folder_id, data))


@router.delete(
    "/folders/{folder_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    summary="Eliminar carpeta y sus reuniones",
    responses=NOT_FOUND,
)
def delete_folder(folder_id: UUID, session: SessionDep) -> Response:
    FolderService(session).delete(folder_id)
    return Response(status_code=status.HTTP_204_NO_CONTENT)


# --- Lo anotado ---


@router.patch("/items/{item_id}", summary="Editar o mover un ítem", responses=NOT_FOUND)
def update_item(item_id: UUID, data: ItemUpdate, session: SessionDep) -> ItemRead:
    return ItemRead.model_validate(MeetingService(session).update_item(item_id, data))


@router.delete(
    "/items/{item_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    summary="Eliminar un ítem",
    responses=NOT_FOUND,
)
def delete_item(item_id: UUID, session: SessionDep) -> Response:
    MeetingService(session).delete_item(item_id)
    return Response(status_code=status.HTTP_204_NO_CONTENT)


# --- Reuniones ---


@router.get("", summary="Reuniones de una carpeta", responses=NOT_FOUND)
def list_meetings(
    session: SessionDep,
    folder_id: Annotated[UUID, Query(description="La carpeta a listar")],
) -> list[MeetingListRead]:
    return [
        MeetingListRead.model_validate(m)
        for m in MeetingService(session).list(folder_id)
    ]


@router.post(
    "",
    status_code=status.HTTP_201_CREATED,
    summary="Crear reunión",
    responses=NOT_FOUND,
)
def create_meeting(data: MeetingCreate, session: SessionDep) -> MeetingRead:
    return MeetingRead.model_validate(MeetingService(session).create(data))


@router.get("/{meeting_id}", summary="Una reunión con su tablero", responses=NOT_FOUND)
def get_meeting(meeting_id: UUID, session: SessionDep) -> MeetingRead:
    return MeetingRead.model_validate(MeetingService(session).get(meeting_id))


@router.patch("/{meeting_id}", summary="Editar reunión", responses=NOT_FOUND)
def update_meeting(
    meeting_id: UUID, data: MeetingUpdate, session: SessionDep
) -> MeetingRead:
    return MeetingRead.model_validate(MeetingService(session).update(meeting_id, data))


@router.delete(
    "/{meeting_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    summary="Eliminar reunión",
    responses=NOT_FOUND,
)
def delete_meeting(meeting_id: UUID, session: SessionDep) -> Response:
    MeetingService(session).delete(meeting_id)
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.post(
    "/{meeting_id}/items",
    status_code=status.HTTP_201_CREATED,
    summary="Anotar en un cuadrante",
    responses=NOT_FOUND,
)
def add_item(meeting_id: UUID, data: ItemCreate, session: SessionDep) -> ItemRead:
    return ItemRead.model_validate(MeetingService(session).add_item(meeting_id, data))


@router.post(
    "/{meeting_id}/summary",
    summary="Generar el resumen de la reunión",
    responses={
        **NOT_FOUND,
        status.HTTP_409_CONFLICT: {"model": ErrorResponse},
        status.HTTP_502_BAD_GATEWAY: {"model": ErrorResponse},
    },
)
def summarize(
    meeting_id: UUID, session: SessionDep, settings: SettingsDep
) -> MeetingRead:
    try:
        meeting = MeetingService(session, settings).summarize(meeting_id)
    except ResumenError as exc:
        logger.warning("Falló el resumen de la reunión %s: %s", meeting_id, exc)
        # 502: la petición estaba bien, falló el proveedor del modelo.
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail="No se pudo generar el resumen. Inténtalo de nuevo.",
        ) from exc
    return MeetingRead.model_validate(meeting)
