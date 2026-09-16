"""Panel del agente."""

import logging
from typing import Literal

from fastapi import APIRouter, HTTPException, status
from pydantic import BaseModel, ConfigDict, Field

from app.api.deps import SessionDep, SessionGuard, SettingsDep
from app.services.agent import AgentError, AgentService

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/agent", tags=["agente"])


class ChatMessage(BaseModel):
    model_config = ConfigDict(extra="forbid")

    role: Literal["user", "assistant"]
    content: str = Field(min_length=1, max_length=4000)


class ChatRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    # Se manda la conversación completa: el agente no guarda estado entre
    # peticiones, y asi el historial vive donde el usuario lo ve.
    messages: list[ChatMessage] = Field(min_length=1, max_length=40)


class ChatResponse(BaseModel):
    reply: str
    actions: list[str]
    # Le dice al frontend si vale la pena recargar la bandeja.
    changed: bool


@router.post("/chat", summary="Conversar con el agente")
def chat(
    data: ChatRequest,
    session: SessionDep,
    settings: SettingsDep,
    _: SessionGuard,
) -> ChatResponse:
    try:
        service = AgentService(session, settings)
        result = service.run([m.model_dump() for m in data.messages])
    except AgentError as exc:
        logger.warning("El agente falló: %s", exc)
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY, detail=str(exc)
        ) from exc

    return ChatResponse(**result)
