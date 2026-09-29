"""De lo anotado en una reunión a unos párrafos que se puedan pegar en otra parte.

Mismo criterio que la redacción de prompts: el modelo escribe lo que está, no
lo completa. Lo anotado en la reunión es telegráfico ("Antonia entrega el
reporte mañana") y el trabajo es volverlo prosa, no sacar conclusiones que
nadie dijo.

Devuelve texto plano y no JSON: el resultado es exactamente lo que se copia,
y envolverlo en un objeto solo agregaría una forma más de que falle el parseo.
"""

import logging
import re

import httpx

from app.core.config import Settings

logger = logging.getLogger(__name__)

SYSTEM_PROMPT = """\
Recibes lo que una persona anotó durante una reunión de trabajo, ordenado en
secciones: los temas que se conversaron, las tareas que quedaron pendientes,
los apuntes que se tomaron al pasar y, si los hay, los temas que no se
alcanzaron a conversar. Tu trabajo es escribir el resumen de esa reunión.

## Cómo es el resumen

- Párrafos de prosa, separados por una línea en blanco. Sin encabezados, sin
  viñetas, sin listas numeradas, sin negritas.
- Primero lo que se conversó, integrando los apuntes donde corresponden: un
  apunte suele ser un dato o un acuerdo que salió de uno de los temas.
- Después las tareas que quedaron pendientes, con quién las hace y para cuándo
  si la anotación lo dice.
- Si hay temas que no se alcanzaron a conversar, una oración al final que lo
  diga. Si no hay, no se menciona.
- Entre dos y cinco párrafos. Proporcional a lo anotado: una reunión con tres
  anotaciones no da para cinco párrafos.
- Español de Chile, en tono neutro, impersonal o en tercera persona.

## Qué NO haces

- NO inventas nada. Ni conclusiones, ni acuerdos, ni plazos, ni responsables
  que no estén en lo anotado. Las anotaciones son telegráficas: puedes
  escribirlas en oraciones completas, pero sin agregarles contenido.
- NO omites nada anotado. Todo tema conversado, tarea y apunte aparece.
- NO comentas lo que falta. Frases como "no se definió un plazo" son ruido:
  quien lea el resumen no necesita saber lo que no se anotó.
- NO cambias nombres propios, fechas ni cifras.

## Salida

Devuelve EXCLUSIVAMENTE el texto del resumen, sin nada antes ni después.
"""


class ResumenError(Exception):
    """El modelo no devolvió algo utilizable."""


class Resumidor:
    def __init__(self, settings: Settings) -> None:
        if not settings.resolved_llm_api_key:
            raise ResumenError("Falta OPENAI_API_KEY")
        self._api_key = settings.resolved_llm_api_key
        self._base_url = settings.resolved_llm_base_url.rstrip("/")
        # El mismo modelo que ordena los prompts: es trabajo de redacción, y
        # el modelo chico de los tickets escribe prosa más pobre.
        self._model = settings.prompt_model
        self._timeout = httpx.Timeout(settings.prompt_timeout_seconds)

    def resumir(self, notas: str) -> str:
        payload = {
            "model": self._model,
            "messages": [
                {"role": "system", "content": SYSTEM_PROMPT},
                {"role": "user", "content": notas},
            ],
        }

        try:
            with httpx.Client(timeout=self._timeout) as client:
                respuesta = client.post(
                    f"{self._base_url}/chat/completions",
                    headers={"Authorization": f"Bearer {self._api_key}"},
                    json=payload,
                )
                respuesta.raise_for_status()
        except httpx.HTTPError as exc:
            raise ResumenError(f"El modelo no respondió: {exc}") from exc

        try:
            contenido = respuesta.json()["choices"][0]["message"]["content"]
        except (KeyError, IndexError, TypeError) as exc:
            raise ResumenError("Respuesta con forma inesperada") from exc

        return self._limpiar(contenido)

    @staticmethod
    def _limpiar(contenido: str | None) -> str:
        """Quita lo que el modelo agrega aunque se le pida que no.

        Un bloque de código alrededor, o espacios de más, terminarían pegados
        en el correo o el documento donde se use el resumen.
        """
        texto = (contenido or "").strip()
        cercado = re.fullmatch(r"```[a-zA-Z]*\s*(.+?)\s*```", texto, re.DOTALL)
        if cercado:
            texto = cercado.group(1).strip()
        if not texto:
            raise ResumenError("El modelo devolvió un resumen vacío")
        return texto
