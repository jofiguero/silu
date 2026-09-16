"""Generación de título y descripción con un LLM.

El cliente habla el protocolo de OpenAI (`/chat/completions`), que es lo que
expone prácticamente cualquier gateway hoy. Cambiar de proveedor o de modelo es
cambiar tres variables de entorno, no código.
"""

import json
import logging
import re

import httpx
from pydantic import BaseModel, Field, ValidationError

from app.core.config import Settings

logger = logging.getLogger(__name__)

SYSTEM_PROMPT = """\
Eres el generador de tickets de Silu, un sistema personal de captura de ideas.

Recibes la transcripción de un mensaje de voz o un texto que una persona se dijo
a sí misma en el momento en que se le ocurrió algo: una tarea, un gasto, una
idea, un recordatorio. Tu trabajo es convertirlo en un ticket legible.

Devuelve EXCLUSIVAMENTE un objeto JSON con esta forma, sin texto alrededor:
{"title": "...", "summary": "..."}

Reglas:

- `title`: máximo 60 caracteres. Concreto y específico, no genérico. Debe
  permitir reconocer el ticket en una lista de cincuenta.
- `summary`: NO es un resumen. Es una descripción autocontenida del hecho o la
  tarea, escrita para que la persona entienda de qué se trataba al releerla
  semanas después, sin volver al audio original. Una a tres oraciones.
- Conserva todos los datos concretos: montos, nombres de personas, plazos,
  lugares. Son lo primero que se olvida y lo que hace accionable el ticket.
- No inventes información que no esté en el mensaje. Si algo quedó ambiguo en la
  transcripción, descríbelo tal como se entendió, sin completar los huecos.
- Escribe en español de Chile, en tercera persona o impersonal, en tono neutro.
- No agregues categorías, etiquetas ni prioridades: eso lo decide la persona
  después, al revisar.
"""


class TicketDraft(BaseModel):
    """Lo que el LLM debe producir."""

    title: str = Field(min_length=1, max_length=200)
    summary: str = Field(min_length=1)


class LLMError(Exception):
    """El modelo no devolvió algo utilizable."""


class TicketDrafter:
    def __init__(self, settings: Settings) -> None:
        if not settings.llm_api_key:
            raise LLMError("Falta LLM_API_KEY")
        self._api_key = settings.llm_api_key
        self._base_url = settings.llm_base_url.rstrip("/")
        self._model = settings.llm_model
        self._timeout = httpx.Timeout(settings.llm_timeout_seconds)

    def draft(self, raw_text: str) -> TicketDraft:
        content = self._complete(raw_text)
        return self._parse(content)

    def _complete(self, raw_text: str) -> str:
        payload = {
            "model": self._model,
            "messages": [
                {"role": "system", "content": SYSTEM_PROMPT},
                {"role": "user", "content": raw_text},
            ],
            "temperature": 0.3,
            # Pedir JSON explícitamente; si el gateway no soporta el parámetro,
            # el prompt ya lo exige y el parseo tolera texto alrededor.
            "response_format": {"type": "json_object"},
        }

        try:
            with httpx.Client(timeout=self._timeout) as client:
                response = client.post(
                    f"{self._base_url}/chat/completions",
                    headers={"Authorization": f"Bearer {self._api_key}"},
                    json=payload,
                )
                if response.status_code == 400:
                    # Algunos gateways rechazan response_format. Se reintenta
                    # sin él antes de darse por vencido.
                    logger.warning("El modelo rechazó response_format; reintentando")
                    payload.pop("response_format")
                    response = client.post(
                        f"{self._base_url}/chat/completions",
                        headers={"Authorization": f"Bearer {self._api_key}"},
                        json=payload,
                    )
                response.raise_for_status()
        except httpx.HTTPError as exc:
            raise LLMError(f"El proveedor del LLM falló: {exc}") from exc

        try:
            return response.json()["choices"][0]["message"]["content"]
        except (KeyError, IndexError, TypeError) as exc:
            raise LLMError(f"Respuesta con forma inesperada: {response.text}") from exc

    @staticmethod
    def _parse(content: str) -> TicketDraft:
        """Extrae el JSON aunque venga envuelto en texto o en un bloque de código.

        Los modelos ignoran la instrucción de "solo JSON" con cierta frecuencia,
        y perder un ticket por un ```json de más sería absurdo.
        """
        candidate = content.strip()

        fenced = re.search(r"```(?:json)?\s*(.+?)\s*```", candidate, re.DOTALL)
        if fenced:
            candidate = fenced.group(1)
        else:
            braces = re.search(r"\{.*\}", candidate, re.DOTALL)
            if braces:
                candidate = braces.group(0)

        try:
            data = json.loads(candidate)
        except json.JSONDecodeError as exc:
            raise LLMError(f"El modelo no devolvió JSON válido: {content!r}") from exc

        try:
            return TicketDraft.model_validate(data)
        except ValidationError as exc:
            raise LLMError(f"El JSON no tiene los campos esperados: {data}") from exc
