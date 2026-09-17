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

Devuelve EXCLUSIVAMENTE un objeto JSON, sin texto alrededor. Su forma exacta
se indica al final de estas instrucciones.

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
- No comentes lo que la persona NO dijo. Frases como "no se especifica la
  cantidad" o "no se indica el plazo" son ruido: la persona ya sabe qué omitió,
  y al releer solo estorban.
- Escribe en español de Chile, en tercera persona o impersonal, en tono neutro.
Además debes decidir dos cosas, y en ambas la regla es la misma: SOLO si la
persona lo dice explícitamente.

`category`: la línea de vida donde va el ticket. Las disponibles son:

{categorias}

Asigna una distinta de "{default}" SOLO si la persona lo pide de forma
explícita: "clasifícalo en gastos", "déjalo en metro", "esto va a conversar con
la Luna". NO la infieras del contenido. Que el ticket hable de plata no lo
convierte en un gasto: la persona clasifica cuando revisa, no cuando captura.
Si no lo dice, usa "{default}".

`urgent`: true SOLO si la persona dice que es urgente o equivalente ("esto es
urgente", "esto corre", "prioridad"). Si no lo dice, false. No lo deduzcas del
tono ni del contenido.

Cuando la persona dé una instrucción de clasificación o urgencia, no la
incluyas en el `summary`: es una orden para el sistema, no parte de lo que
quiere recordar.

El JSON completo es:
{{"title": "...", "summary": "...", "category": "...", "urgent": false}}
"""


class TicketDraft(BaseModel):
    """Lo que el LLM debe producir."""

    title: str = Field(min_length=1, max_length=200)
    summary: str = Field(min_length=1)
    # Nombre de la categoría. Se resuelve contra la base; si no calza con
    # ninguna, el ticket cae en la bandeja en vez de perderse.
    category: str | None = None
    urgent: bool = False


class LLMError(Exception):
    """El modelo no devolvió algo utilizable."""


class TicketDrafter:
    def __init__(self, settings: Settings) -> None:
        if not settings.resolved_llm_api_key:
            raise LLMError("Falta OPENAI_API_KEY (o LLM_API_KEY)")
        self._api_key = settings.resolved_llm_api_key
        self._base_url = settings.resolved_llm_base_url.rstrip("/")
        self._model = settings.llm_model
        self._temperature = settings.llm_temperature
        self._timeout = httpx.Timeout(settings.llm_timeout_seconds)

    def draft(
        self,
        raw_text: str,
        *,
        categories: list[str] | None = None,
        default_category: str = "Bandeja",
    ) -> TicketDraft:
        """Genera el ticket.

        Las categorías se pasan en cada llamada, no se fijan en el prompt: se
        crean y eliminan desde la web, y un prompt con una lista desactualizada
        clasificaría en líneas de vida que ya no existen.
        """
        prompt = SYSTEM_PROMPT.format(
            categorias="\n".join(
                f"- {name}" for name in (categories or [default_category])
            ),
            default=default_category,
        )
        content = self._complete(raw_text, prompt)
        return self._parse(content)

    def _complete(self, raw_text: str, system_prompt: str) -> str:
        payload: dict = {
            "model": self._model,
            "messages": [
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": raw_text},
            ],
            # Pedir JSON explícitamente; si el modelo no soporta el parámetro,
            # el prompt ya lo exige y el parseo tolera texto alrededor.
            "response_format": {"type": "json_object"},
        }
        # Varios modelos de razonamiento rechazan una temperatura distinta de la
        # por defecto, así que solo se envía si se configuró explícitamente.
        if self._temperature is not None:
            payload["temperature"] = self._temperature

        try:
            with httpx.Client(timeout=self._timeout) as client:
                response = client.post(
                    f"{self._base_url}/chat/completions",
                    headers={"Authorization": f"Bearer {self._api_key}"},
                    json=payload,
                )
                if response.status_code == 400:
                    # Un 400 casi siempre es un parámetro que este modelo no
                    # acepta (response_format o temperature). Se reintenta con
                    # lo mínimo antes de darse por vencido: el prompt ya exige
                    # JSON y el parseo tolera texto alrededor.
                    logger.warning(
                        "El modelo rechazó la petición (%s); reintentando sin "
                        "parámetros opcionales",
                        response.text[:200],
                    )
                    payload.pop("response_format", None)
                    payload.pop("temperature", None)
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
