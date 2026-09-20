"""Cliente de la API de Telegram.

Solo cubre lo que Silu necesita: mandar mensajes y descargar los audios que
llegan. La API de Telegram entrega los archivos en dos pasos —primero pides la
ruta, después la descargas— y eso queda encapsulado aquí.
"""

import logging

import httpx

from app.core.config import Settings

logger = logging.getLogger(__name__)

API_BASE = "https://api.telegram.org"


class TelegramError(Exception):
    """Falló una llamada a la API de Telegram."""


class TelegramClient:
    def __init__(self, settings: Settings, token: str | None = None) -> None:
        """El token se puede pasar explícitamente para usar el bot de prompts.

        Sin ese parámetro toma el del bot de tickets, que es el caso habitual.
        """
        elegido = token or settings.telegram_bot_token
        if not elegido:
            raise TelegramError("Falta el token del bot")
        self._token = elegido
        self._timeout = httpx.Timeout(30.0)

    @property
    def _api_url(self) -> str:
        return f"{API_BASE}/bot{self._token}"

    def send_message(self, chat_id: int, text: str) -> None:
        """Manda un mensaje. No levanta excepción si falla.

        Un aviso que no se pudo entregar no debe tumbar el procesamiento del
        ticket, que es lo que realmente importa conservar.
        """
        try:
            with httpx.Client(timeout=self._timeout) as client:
                response = client.post(
                    f"{self._api_url}/sendMessage",
                    json={
                        "chat_id": chat_id,
                        "text": text,
                        "parse_mode": "HTML",
                        "disable_web_page_preview": True,
                    },
                )
                response.raise_for_status()
        except httpx.HTTPError:
            logger.exception("No se pudo enviar el mensaje a Telegram")

    def download_file(self, file_id: str) -> bytes:
        """Descarga un archivo en dos pasos, como exige la API de Telegram."""
        with httpx.Client(timeout=self._timeout) as client:
            info = client.get(f"{self._api_url}/getFile", params={"file_id": file_id})
            info.raise_for_status()
            payload = info.json()

            if not payload.get("ok"):
                raise TelegramError(f"getFile falló: {payload}")

            file_path = payload["result"]["file_path"]

            download = client.get(f"{API_BASE}/file/bot{self._token}/{file_path}")
            download.raise_for_status()
            return download.content
