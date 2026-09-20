"""Endpoints de proyectos y prompts, y el webhook del bot de prompts."""

import logging
import secrets
from collections.abc import Callable
from typing import Annotated
from uuid import UUID

from fastapi import (
    APIRouter,
    BackgroundTasks,
    Depends,
    Header,
    HTTPException,
    Query,
    Response,
    status,
)
from sqlalchemy.orm import Session

from app.api.deps import (
    SessionDep,
    SessionFactoryDep,
    SettingsDep,
    require_session,
)
from app.core.config import Settings
from app.schemas.common import ErrorResponse
from app.schemas.prompt import (
    ProjectCreate,
    ProjectRead,
    ProjectUpdate,
    PromptCreate,
    PromptRead,
    PromptUpdate,
)
from app.schemas.telegram import TelegramUpdate
from app.services.prompt import (
    ProjectService,
    PromptCaptureService,
    PromptService,
)

logger = logging.getLogger(__name__)

# El webhook va en su propio router sin la guardia de sesión: se protege con el
# secreto compartido con Telegram, igual que el bot de tickets.
webhook_router = APIRouter(prefix="/prompts", tags=["prompts"])

router = APIRouter(
    prefix="/prompts",
    tags=["prompts"],
    dependencies=[Depends(require_session)],
)

NOT_FOUND = {status.HTTP_404_NOT_FOUND: {"model": ErrorResponse}}


def _proyecto(proyecto) -> ProjectRead:
    return ProjectRead(
        id=proyecto.id,
        created_at=proyecto.created_at,
        updated_at=proyecto.updated_at,
        name=proyecto.name,
        description_md=proyecto.description_md,
        position=proyecto.position,
        prompts_count=len(proyecto.prompts),
    )


# --- Webhook del bot de prompts ---


def _procesar(
    update: TelegramUpdate,
    settings: Settings,
    session_factory: Callable[[], Session],
) -> None:
    """Procesa fuera del ciclo de la petición.

    El metaprompting puede tardar decenas de segundos; hacerlo dentro del
    webhook garantizaría que Telegram lo dé por fallido y reenvíe el mensaje.
    """
    try:
        with session_factory() as session:
            PromptCaptureService(session, settings).handle(update)
    except Exception:  # noqa: BLE001
        logger.exception("Falló el procesamiento del prompt %s", update.update_id)


@webhook_router.post(
    "/telegram/webhook",
    status_code=status.HTTP_200_OK,
    summary="Webhook del bot de prompts",
    include_in_schema=False,
)
def telegram_webhook(
    update: TelegramUpdate,
    background: BackgroundTasks,
    settings: SettingsDep,
    session_factory: SessionFactoryDep,
    secret_token: Annotated[
        str | None, Header(alias="X-Telegram-Bot-Api-Secret-Token")
    ] = None,
) -> dict[str, bool]:
    if not settings.prompts_bot_configured:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="El bot de prompts no está configurado",
        )

    esperado = settings.telegram_prompts_webhook_secret or ""
    if not secret_token or not secrets.compare_digest(secret_token, esperado):
        logger.warning("Webhook de prompts rechazado: secreto inválido")
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN, detail="Secreto inválido"
        )

    background.add_task(_procesar, update, settings, session_factory)
    return {"ok": True}


# --- Proyectos ---


@router.get("/projects", summary="Listar proyectos")
def list_projects(session: SessionDep) -> list[ProjectRead]:
    return [_proyecto(p) for p in ProjectService(session).list()]


@router.post(
    "/projects", status_code=status.HTTP_201_CREATED, summary="Crear proyecto"
)
def create_project(data: ProjectCreate, session: SessionDep) -> ProjectRead:
    return _proyecto(ProjectService(session).create(data))


@router.patch("/projects/{project_id}", summary="Editar proyecto", responses=NOT_FOUND)
def update_project(
    project_id: UUID, data: ProjectUpdate, session: SessionDep
) -> ProjectRead:
    return _proyecto(ProjectService(session).update(project_id, data))


@router.delete(
    "/projects/{project_id}", summary="Eliminar proyecto", responses=NOT_FOUND
)
def delete_project(project_id: UUID, session: SessionDep) -> dict[str, int]:
    """Los prompts del proyecto no se borran: quedan sin asignar."""
    return {"prompts_sueltos": ProjectService(session).delete(project_id)}


# --- Prompts ---


@router.get("", summary="Listar prompts")
def list_prompts(
    session: SessionDep,
    project_id: Annotated[
        UUID | None, Query(description="Filtrar por proyecto")
    ] = None,
    sin_proyecto: Annotated[
        bool, Query(description="Solo los que quedaron sin asignar")
    ] = False,
) -> list[PromptRead]:
    return [
        PromptRead.model_validate(p)
        for p in PromptService(session).list(
            project_id=project_id, sin_proyecto=sin_proyecto
        )
    ]


@router.post("", status_code=status.HTTP_201_CREATED, summary="Crear un prompt")
def create_prompt(data: PromptCreate, session: SessionDep) -> PromptRead:
    return PromptRead.model_validate(PromptService(session).create(data))


@router.patch("/{prompt_id}", summary="Editar un prompt", responses=NOT_FOUND)
def update_prompt(
    prompt_id: UUID, data: PromptUpdate, session: SessionDep
) -> PromptRead:
    """Editar el contenido marca el prompt como retocado a mano."""
    return PromptRead.model_validate(PromptService(session).update(prompt_id, data))


@router.delete(
    "/{prompt_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    summary="Eliminar un prompt",
    responses=NOT_FOUND,
)
def delete_prompt(prompt_id: UUID, session: SessionDep) -> Response:
    PromptService(session).delete(prompt_id)
    return Response(status_code=status.HTTP_204_NO_CONTENT)
