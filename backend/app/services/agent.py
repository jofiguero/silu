"""Agente del panel lateral.

Recibe una instrucción en lenguaje natural y la traduce en acciones sobre los
tickets, usando el mecanismo de herramientas del LLM. Cada herramienta es una
operación del dominio, no una consulta SQL: el agente opera con el mismo
`TicketService` que la API, así que las reglas de negocio —como exigir
resolución al archivar— se aplican igual venga la orden de donde venga.
"""

import json
import logging
from typing import Any
from uuid import UUID

import httpx
from sqlalchemy.orm import Session

from app.core.config import Settings, get_settings
from app.core.exceptions import SiluError
from app.schemas.ticket import (
    TicketDispatch,
    TicketStatus,
    TicketUpdate,
)
from app.services.ticket import TicketService

logger = logging.getLogger(__name__)

SYSTEM_PROMPT = """\
Eres el asistente de revisión de Silu, un sistema personal de tickets.

La persona captura ideas, tareas y gastos por voz durante el día, y ahora los
está revisando. Tu trabajo es ejecutar lo que te pida sobre esos tickets.

Cómo trabajar:

- Antes de modificar algo, busca los tickets involucrados para saber sobre
  cuáles actuar. No adivines identificadores.
- Al archivar un ticket, siempre incluye una resolución que describa qué se
  hizo con él. Es obligatorio y es lo que hace útil releer la bandeja después.
- ELIMINAR es irreversible. Nunca elimines sin preguntar antes y recibir una
  confirmación explícita en el mensaje siguiente. Si la persona pide eliminar,
  primero di exactamente qué tickets se borrarían y espera el sí.
- Si una instrucción es ambigua —"archiva los gastos" cuando hay varios—,
  enumera lo que encontraste y pregunta, en vez de actuar sobre todos.
- Responde en español de Chile, breve y concreto. Di qué hiciste, no cómo.
- Si no hiciste ningún cambio, dilo claramente.
"""

TOOLS: list[dict[str, Any]] = [
    {
        "type": "function",
        "function": {
            "name": "buscar_tickets",
            "description": (
                "Busca tickets por estado y/o texto. Úsala siempre antes de "
                "modificar algo, para obtener los identificadores reales."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "status": {
                        "type": "string",
                        "enum": ["pendiente", "en_curso", "archivado"],
                        "description": "Filtrar por estado",
                    },
                    "search": {
                        "type": "string",
                        "description": "Texto a buscar en título y descripción",
                    },
                    "incluir_archivados": {
                        "type": "boolean",
                        "description": "Por defecto los archivados no aparecen",
                    },
                    "limit": {"type": "integer", "description": "Máximo a devolver"},
                },
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "cambiar_estado",
            "description": (
                "Cambia el estado de un ticket. Archivar exige una resolución "
                "que describa qué se hizo con él."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "ticket_id": {"type": "string"},
                    "status": {
                        "type": "string",
                        "enum": ["pendiente", "en_curso", "archivado"],
                    },
                    "resolution": {
                        "type": "string",
                        "description": "Qué se hizo finalmente con el ticket",
                    },
                },
                "required": ["ticket_id", "status"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "editar_ticket",
            "description": "Corrige el título o la descripción de un ticket.",
            "parameters": {
                "type": "object",
                "properties": {
                    "ticket_id": {"type": "string"},
                    "title": {"type": "string"},
                    "summary": {"type": "string"},
                },
                "required": ["ticket_id"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "marcar_urgente",
            "description": (
                "Marca o desmarca un ticket como urgente. Los urgentes van al "
                "tope de la bandeja."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "ticket_id": {"type": "string"},
                    "urgente": {"type": "boolean"},
                },
                "required": ["ticket_id", "urgente"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "eliminar_ticket",
            "description": (
                "Elimina un ticket de forma definitiva. Irreversible. Solo se "
                "puede llamar con confirmado=true, y la persona debe haber "
                "confirmado explícitamente en el mensaje anterior."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "ticket_id": {"type": "string"},
                    "confirmado": {
                        "type": "boolean",
                        "description": "Debe ser true; la persona ya confirmó",
                    },
                },
                "required": ["ticket_id", "confirmado"],
            },
        },
    },
]


class AgentError(Exception):
    """El agente no pudo completar la petición."""


class AgentService:
    def __init__(self, session: Session, settings: Settings | None = None) -> None:
        self.settings = settings or get_settings()
        self.tickets = TicketService(session)
        if not self.settings.resolved_llm_api_key:
            raise AgentError("Falta OPENAI_API_KEY")

    def run(self, messages: list[dict[str, Any]]) -> dict[str, Any]:
        """Ejecuta el ciclo de herramientas hasta que el modelo responde texto.

        Devuelve la respuesta y la lista de acciones ejecutadas, para que la
        interfaz pueda refrescar la bandeja solo cuando algo cambió.
        """
        conversation: list[dict[str, Any]] = [
            {"role": "system", "content": SYSTEM_PROMPT},
            *messages,
        ]
        actions: list[str] = []

        for _ in range(self.settings.agent_max_steps):
            message = self._complete(conversation)
            conversation.append(message)

            tool_calls = message.get("tool_calls")
            if not tool_calls:
                return {
                    "reply": message.get("content") or "",
                    "actions": actions,
                    "changed": any(a != "buscar_tickets" for a in actions),
                }

            for call in tool_calls:
                name = call["function"]["name"]
                result = self._execute(name, call["function"]["arguments"])
                actions.append(name)
                conversation.append(
                    {
                        "role": "tool",
                        "tool_call_id": call["id"],
                        "content": json.dumps(result, ensure_ascii=False),
                    }
                )

        # Sin este tope, un modelo que insiste en llamar herramientas dejaría la
        # petición colgada y quemando créditos.
        raise AgentError("El agente no llegó a una respuesta; intenta reformular")

    # --- Llamada al modelo ---

    def _complete(self, conversation: list[dict[str, Any]]) -> dict[str, Any]:
        payload = {
            "model": self.settings.agent_model,
            "messages": conversation,
            "tools": TOOLS,
        }

        try:
            with httpx.Client(
                timeout=httpx.Timeout(self.settings.llm_timeout_seconds)
            ) as client:
                response = client.post(
                    f"{self.settings.resolved_llm_base_url.rstrip('/')}/chat/completions",
                    headers={
                        "Authorization": f"Bearer {self.settings.resolved_llm_api_key}"
                    },
                    json=payload,
                )
                response.raise_for_status()
        except httpx.HTTPError as exc:
            raise AgentError(f"El modelo no respondió: {exc}") from exc

        try:
            return response.json()["choices"][0]["message"]
        except (KeyError, IndexError, TypeError) as exc:
            raise AgentError("El modelo devolvió una respuesta inesperada") from exc

    # --- Herramientas ---

    def _execute(self, name: str, raw_arguments: str) -> dict[str, Any]:
        """Ejecuta una herramienta y devuelve siempre un dict serializable.

        Los errores se devuelven como datos, no como excepciones: el modelo
        necesita leerlos para corregir el rumbo o explicárselos a la persona.
        """
        try:
            arguments = json.loads(raw_arguments or "{}")
        except json.JSONDecodeError:
            return {"error": "argumentos mal formados"}

        handler = {
            "buscar_tickets": self._buscar,
            "cambiar_estado": self._cambiar_estado,
            "editar_ticket": self._editar,
            "marcar_urgente": self._marcar_urgente,
            "eliminar_ticket": self._eliminar,
        }.get(name)

        if handler is None:
            return {"error": f"herramienta desconocida: {name}"}

        try:
            return handler(arguments)
        except SiluError as exc:
            return {"error": exc.message}
        except Exception as exc:  # noqa: BLE001
            logger.exception("Falló la herramienta %s", name)
            return {"error": str(exc)}

    def _buscar(self, args: dict[str, Any]) -> dict[str, Any]:
        status_value = args.get("status")
        items, total = self.tickets.list(
            status=TicketStatus(status_value) if status_value else None,
            search=args.get("search"),
            include_archived=bool(args.get("incluir_archivados")),
            limit=min(int(args.get("limit", 20)), 50),
        )
        return {
            "total": total,
            "tickets": [
                {
                    "id": str(t.id),
                    "title": t.title,
                    "summary": t.summary,
                    "status": t.status,
                    "urgente": t.urgent,
                    "resolution": t.resolution,
                    "created_at": t.created_at.isoformat(),
                }
                for t in items
            ],
        }

    def _cambiar_estado(self, args: dict[str, Any]) -> dict[str, Any]:
        ticket_id = UUID(args["ticket_id"])
        new_status = TicketStatus(args["status"])
        resolution = args.get("resolution")

        if new_status is TicketStatus.ARCHIVADO and resolution:
            ticket = self.tickets.dispatch(
                ticket_id, TicketDispatch(resolution=resolution)
            )
        else:
            ticket = self.tickets.update(
                ticket_id,
                TicketUpdate(status=new_status, **({"resolution": resolution} if resolution else {})),
            )

        return {"id": str(ticket.id), "status": ticket.status, "title": ticket.title}

    def _editar(self, args: dict[str, Any]) -> dict[str, Any]:
        changes = {k: v for k, v in args.items() if k in {"title", "summary"} and v}
        if not changes:
            return {"error": "no se indicó qué editar"}

        ticket = self.tickets.update(UUID(args["ticket_id"]), TicketUpdate(**changes))
        return {"id": str(ticket.id), "title": ticket.title, "summary": ticket.summary}

    def _marcar_urgente(self, args: dict[str, Any]) -> dict[str, Any]:
        ticket = self.tickets.update(
            UUID(args["ticket_id"]), TicketUpdate(urgent=bool(args["urgente"]))
        )
        return {"id": str(ticket.id), "title": ticket.title, "urgente": ticket.urgent}

    def _eliminar(self, args: dict[str, Any]) -> dict[str, Any]:
        if not args.get("confirmado"):
            # Segundo cerrojo, además de la instrucción del prompt: aunque el
            # modelo se salte la regla, sin confirmación explícita no borra.
            return {
                "error": (
                    "eliminar requiere confirmación explícita de la persona; "
                    "pregúntale antes"
                )
            }

        ticket_id = UUID(args["ticket_id"])
        ticket = self.tickets.get(ticket_id)
        title = ticket.title
        self.tickets.delete(ticket_id)
        logger.info("Ticket eliminado por el agente: %s (%s)", ticket_id, title)
        return {"eliminado": True, "title": title}
