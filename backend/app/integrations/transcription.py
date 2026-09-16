"""Transcripción de audio con Whisper en Groq.

Groq expone Whisper detrás del protocolo de OpenAI, así que basta una llamada
multipart a /audio/transcriptions.
"""

import logging

import httpx

from app.core.config import Settings

logger = logging.getLogger(__name__)


class TranscriptionError(Exception):
    """No se pudo transcribir el audio."""


class Transcriber:
    """Convierte audio en texto.

    Se declara como clase, y no como función suelta, para que la capa que la usa
    dependa de una interfaz y no del proveedor: cambiar Groq por otro servicio
    es reemplazar esta clase.
    """

    def __init__(self, settings: Settings) -> None:
        if not settings.groq_api_key:
            raise TranscriptionError("Falta GROQ_API_KEY")
        self._api_key = settings.groq_api_key
        self._base_url = settings.groq_base_url.rstrip("/")
        self._model = settings.transcription_model
        self._language = settings.transcription_language

    def transcribe(self, audio: bytes, filename: str = "audio.ogg") -> str:
        try:
            with httpx.Client(timeout=httpx.Timeout(120.0)) as client:
                response = client.post(
                    f"{self._base_url}/audio/transcriptions",
                    headers={"Authorization": f"Bearer {self._api_key}"},
                    files={"file": (filename, audio, "application/octet-stream")},
                    data={
                        "model": self._model,
                        # Fijar el idioma evita que Whisper "detecte" inglés en
                        # audios cortos o con ruido y devuelva una traducción.
                        "language": self._language,
                        "response_format": "json",
                    },
                )
                response.raise_for_status()
        except httpx.HTTPError as exc:
            raise TranscriptionError(f"Groq rechazó la transcripción: {exc}") from exc

        text = response.json().get("text", "").strip()
        if not text:
            raise TranscriptionError("La transcripción llegó vacía")

        logger.info("Audio transcrito: %d caracteres", len(text))
        return text
