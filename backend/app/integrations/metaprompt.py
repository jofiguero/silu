"""Metaprompting: de un audio informal a un prompt hecho y derecho.

La persona habla suelto mientras camina —"necesito que haga tal cosa, ah y que
ojo con lo otro"— y esto lo convierte en una instrucción que un agente de
código puede ejecutar sin volver a preguntar.
"""

import json
import logging
import re

import httpx
from pydantic import BaseModel, Field, ValidationError

from app.core.config import Settings

logger = logging.getLogger(__name__)

SYSTEM_PROMPT = """\
Eres un ingeniero de prompts. Recibes la transcripción de alguien hablando
suelto sobre lo que quiere lograr en un proyecto de software, y la conviertes
en un prompt listo para entregarle a un agente de programación.

Quien habla lo hace caminando o en el metro: divaga, se corrige, deja frases a
medias y no ordena las ideas. Tu trabajo es entender la intención y escribirla
bien, no transcribir mejor.

## Cómo escribir el prompt

- Parte por el OBJETIVO en una o dos frases: qué tiene que existir cuando el
  trabajo esté hecho. No "implementar X" sino qué comportamiento se espera.
- Sigue con el CONTEXTO necesario del proyecto, tomado del descriptor. Incluye
  solo lo que hace falta para esta tarea: el stack, las convenciones, los
  archivos o módulos involucrados.
- Después las RESTRICCIONES y decisiones ya tomadas: lo que NO hay que hacer,
  lo que hay que respetar, las trampas conocidas. Esto es lo que más valor
  aporta y es lo que la persona suele mencionar al pasar.
- Termina con CRITERIOS DE ACEPTACIÓN concretos y verificables: cómo se sabe
  que quedó bien. Si la persona mencionó casos borde, ponlos aquí.
- Si algo quedó genuinamente ambiguo, agrega una sección corta de PREGUNTAS
  ABIERTAS en vez de inventar una respuesta. Un prompt honesto sobre lo que no
  se decidió es mejor que uno que asume mal.

## Reglas

- Escribe en español, en Markdown, con encabezados de nivel 2.
- Sé específico y concreto. Nada de "seguir buenas prácticas" o "código
  limpio": si la persona mencionó una práctica concreta, nómbrala; si no, no
  la inventes.
- NO inventes requisitos, archivos, nombres de funciones ni tecnologías que no
  aparezcan en la transcripción o en el descriptor del proyecto.
- No incluyas la instrucción de en qué proyecto va: eso se guarda aparte.
- El prompt se lo lleva un agente que NO escuchó el audio. Todo lo que
  necesite saber tiene que estar escrito.

## Proyecto

`project`: el nombre EXACTO de uno de los proyectos de la lista, SOLO si la
persona lo nombró explícitamente al dictar. Si no lo nombró, o nombró algo que
no está en la lista, devuelve null. NO lo deduzcas del contenido técnico: dos
proyectos pueden usar el mismo stack y equivocarse manda el prompt a otra
carpeta.

Proyectos disponibles y su contexto:

{proyectos}

## Salida

Devuelve EXCLUSIVAMENTE un objeto JSON, sin texto alrededor:

{{"title": "...", "project": "..." o null, "content": "..."}}

`title`: máximo 70 caracteres, describe la tarea. Debe permitir reconocer este
prompt entre veinte.
`content`: el prompt completo en Markdown.
"""

SIN_PROYECTOS = "(todavía no hay proyectos documentados)"


class PromptDraft(BaseModel):
    title: str = Field(min_length=1, max_length=200)
    content: str = Field(min_length=1)
    # Nombre del proyecto; se resuelve contra la base. Si no calza con ninguno,
    # el prompt queda sin asignar en vez de perderse.
    project: str | None = None


class MetapromptError(Exception):
    """El modelo no devolvió algo utilizable."""


class Metaprompter:
    def __init__(self, settings: Settings) -> None:
        if not settings.resolved_llm_api_key:
            raise MetapromptError("Falta OPENAI_API_KEY")
        self._api_key = settings.resolved_llm_api_key
        self._base_url = settings.resolved_llm_base_url.rstrip("/")
        self._model = settings.prompt_model
        self._timeout = httpx.Timeout(settings.prompt_timeout_seconds)

    def draft(self, raw_text: str, proyectos: list[tuple[str, str]]) -> PromptDraft:
        """Convierte la transcripción en un prompt.

        `proyectos` son pares (nombre, descriptor). Se pasan en cada llamada y
        no se fijan en el prompt: se crean y editan desde la web.
        """
        content = self._complete(raw_text, self._render(proyectos))
        return self._parse(content)

    @staticmethod
    def _render(proyectos: list[tuple[str, str]]) -> str:
        if not proyectos:
            return SIN_PROYECTOS

        bloques = []
        for nombre, descriptor in proyectos:
            cuerpo = descriptor.strip() or "(sin descripción todavía)"
            bloques.append(f"### {nombre}\n\n{cuerpo}")
        return "\n\n".join(bloques)

    def _complete(self, raw_text: str, proyectos: str) -> str:
        payload: dict = {
            "model": self._model,
            "messages": [
                {
                    "role": "system",
                    "content": SYSTEM_PROMPT.format(proyectos=proyectos),
                },
                {"role": "user", "content": raw_text},
            ],
            "response_format": {"type": "json_object"},
        }

        try:
            with httpx.Client(timeout=self._timeout) as client:
                respuesta = client.post(
                    f"{self._base_url}/chat/completions",
                    headers={"Authorization": f"Bearer {self._api_key}"},
                    json=payload,
                )
                if respuesta.status_code == 400:
                    # Algunos modelos no aceptan response_format; el prompt ya
                    # exige JSON y el parseo tolera texto alrededor.
                    logger.warning("El modelo rechazó response_format; reintentando")
                    payload.pop("response_format", None)
                    respuesta = client.post(
                        f"{self._base_url}/chat/completions",
                        headers={"Authorization": f"Bearer {self._api_key}"},
                        json=payload,
                    )
                respuesta.raise_for_status()
        except httpx.HTTPError as exc:
            raise MetapromptError(f"El modelo no respondió: {exc}") from exc

        try:
            return respuesta.json()["choices"][0]["message"]["content"]
        except (KeyError, IndexError, TypeError) as exc:
            raise MetapromptError("Respuesta con forma inesperada") from exc

    @staticmethod
    def _parse(content: str) -> PromptDraft:
        """Extrae el JSON aunque venga envuelto en texto o en un bloque."""
        candidato = content.strip()

        fenced = re.search(r"```(?:json)?\s*(.+?)\s*```", candidato, re.DOTALL)
        if fenced:
            candidato = fenced.group(1)
        else:
            llaves = re.search(r"\{.*\}", candidato, re.DOTALL)
            if llaves:
                candidato = llaves.group(0)

        try:
            data = json.loads(candidato)
        except json.JSONDecodeError as exc:
            raise MetapromptError(f"No devolvió JSON válido: {content[:200]!r}") from exc

        try:
            return PromptDraft.model_validate(data)
        except ValidationError as exc:
            raise MetapromptError(f"El JSON no tiene los campos esperados: {data}") from exc
