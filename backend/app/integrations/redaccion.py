"""De un audio hablado a un texto ordenado. Nada más.

Esto NO hace metaprompting. Antes sí: convertía lo dictado en un prompt con
objetivo, contexto, restricciones y criterios de aceptacion. El resultado era
largo y se llevaba el foco a donde el modelo creia que debia estar, no a donde
la persona lo habia puesto.

Ahora el trabajo es solo de redaccion: quitar las muletillas, juntar las ideas
que quedaron partidas y ordenar los parrafos. Lo que sale tiene que decir lo
mismo que se dijo, ni mas ni menos.
"""

import json
import logging
import re

import httpx
from pydantic import BaseModel, Field, ValidationError

from app.core.config import Settings

logger = logging.getLogger(__name__)

SYSTEM_PROMPT = """\
Recibes la transcripción de una persona hablando sola, dictando lo que quiere
pedirle a un agente de programación. Tu único trabajo es ordenar ese texto.

No eres un ingeniero de prompts. No mejoras la petición, no la completas, no
la estructuras en secciones. La persona ya sabe lo que quiere pedir; tú solo
escribes bien lo que dijo.

## Qué corriges

- Las muletillas y los titubeos: "eeehm", "o sea", "no sé", "ya", los
  arranques en falso y las frases que se abandonan a medias.
- Las repeticiones: si dijo lo mismo dos veces con otras palabras, queda una.
- El orden. Es lo más importante. Al hablar se salta de una idea a otra y se
  vuelve atrás: junta en un mismo párrafo lo que pertenece a la misma idea,
  aunque en el audio haya quedado separado por otra cosa.
- La puntuación y la gramática, para que se lea como un texto escrito.

## Qué NO haces

- NO agregas nada. Ni un requisito, ni un detalle técnico, ni una
  consideración sensata que la persona no dijo. Si notas que falta algo
  importante, no lo agregues: no es tu decisión.
- NO quitas nada. Si dijo algo confuso o poco relevante, va igual, ordenado.
  Lo único que desaparece son las muletillas y las repeticiones literales.
- NO estructuras el texto: sin encabezados, sin viñetas, sin secciones de
  objetivo o criterios de aceptación, sin negritas. Párrafos y ya.
- NO cambias el registro. Si habla de tú al agente, sigue de tú. Si dice "el
  botón de arriba", no lo traduzcas a "el componente de navegación".
- NO resumes. El largo del resultado se parece al de lo dictado, descontando
  las muletillas.

## El contexto de los proyectos

Más abajo hay descripciones de los proyectos de la persona. Son un glosario,
no una guía: sirven para escribir bien un nombre propio, un módulo o una
tecnología que la persona mencionó a medias o que el transcriptor entendió
mal. No saques contenido de ahí ni orientes el texto hacia lo que dice.

{proyectos}

## Salida

Devuelve EXCLUSIVAMENTE un objeto JSON, sin texto alrededor:

{{"title": "...", "content": "..."}}

`title`: máximo 70 caracteres, para reconocer este prompt entre veinte. Sale
de lo que la persona dijo, no lo inventas.
`content`: el texto ordenado, en párrafos separados por una línea en blanco.
"""

SIN_PROYECTOS = "(todavía no hay proyectos documentados)"


class PromptDraft(BaseModel):
    title: str = Field(min_length=1, max_length=200)
    content: str = Field(min_length=1)


class RedaccionError(Exception):
    """El modelo no devolvió algo utilizable."""


class Redactor:
    def __init__(self, settings: Settings) -> None:
        if not settings.resolved_llm_api_key:
            raise RedaccionError("Falta OPENAI_API_KEY")
        self._api_key = settings.resolved_llm_api_key
        self._base_url = settings.resolved_llm_base_url.rstrip("/")
        self._model = settings.prompt_model
        self._timeout = httpx.Timeout(settings.prompt_timeout_seconds)

    def draft(self, raw_text: str, proyectos: list[tuple[str, str]]) -> PromptDraft:
        """Ordena la transcripción.

        `proyectos` son pares (nombre, descriptor), y van solo como glosario.
        Se pasan en cada llamada y no se fijan en el prompt: se crean y editan
        desde la web.
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
            raise RedaccionError(f"El modelo no respondió: {exc}") from exc

        try:
            return respuesta.json()["choices"][0]["message"]["content"]
        except (KeyError, IndexError, TypeError) as exc:
            raise RedaccionError("Respuesta con forma inesperada") from exc

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
            raise RedaccionError(f"No devolvió JSON válido: {content[:200]!r}") from exc

        try:
            return PromptDraft.model_validate(data)
        except ValidationError as exc:
            raise RedaccionError(f"El JSON no tiene los campos esperados: {data}") from exc
