"""Webhook de Telegram.

El endpoint hace lo mínimo: verifica que la petición venga de Telegram, valida
la forma del mensaje y devuelve 200 de inmediato. Todo el trabajo pesado
—descargar, transcribir, llamar al LLM— ocurre después de responder.

Responder rápido no es un lujo: si el webhook demora, Telegram lo da por
fallido y reenvía el mismo mensaje, lo que crearía tickets duplicados.
"""

import logging
import secrets
from typing import Annotated

from fastapi import APIRouter, BackgroundTasks, Header, HTTPException, status

from app.api.deps import SettingsDep
from app.core.config import Settings
from app.db.session import SessionFactory
from app.schemas.telegram import TelegramUpdate
from app.services.capture import CaptureService

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/telegram", tags=["telegram"])


def _process(update: TelegramUpdate, settings: Settings) -> None:
    """Procesa el mensaje fuera del ciclo de la petición.

    Abre su propia sesión: la de la petición ya se cerró cuando esto corre.
    Cualquier excepción se registra y muere aquí — si escapara, terminaría en
    los logs de Telegram como un webhook fallido y provocaría reintentos.
    """
    try:
        with SessionFactory() as session:
            CaptureService(session, settings).handle(update)
    except Exception:  # noqa: BLE001
        logger.exception("Falló el procesamiento del update %s", update.update_id)


@router.post(
    "/webhook",
    status_code=status.HTTP_200_OK,
    summary="Webhook de Telegram",
    include_in_schema=False,
)
def telegram_webhook(
    update: TelegramUpdate,
    background: BackgroundTasks,
    settings: SettingsDep,
    secret_token: Annotated[
        str | None, Header(alias="X-Telegram-Bot-Api-Secret-Token")
    ] = None,
) -> dict[str, bool]:
    if not settings.telegram_configured:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="El bot de Telegram no está configurado",
        )

    # compare_digest en vez de ==: evita filtrar el secreto por el tiempo que
    # tarda la comparación.
    expected = settings.telegram_webhook_secret or ""
    if not secret_token or not secrets.compare_digest(secret_token, expected):
        logger.warning("Webhook rechazado: secreto inválido o ausente")
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN, detail="Secreto inválido"
        )

    background.add_task(_process, update, settings)
    return {"ok": True}
