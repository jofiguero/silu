"""Modelos de datos de Silu.

Una sola tabla `tickets`, deliberadamente genérica: cualquier cosa que se le diga
a Silu (tarea, gasto, idea, recordatorio) se guarda con la misma estructura.
La taxonomía específica vive en el destino final, no aquí.
"""

import uuid
from datetime import datetime

from sqlalchemy import CheckConstraint, DateTime, Text, func, text
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column

# Estados posibles de un ticket a lo largo de su ciclo de vida.
TICKET_STATUSES = ("pendiente", "en_curso", "archivado")


class Base(DeclarativeBase):
    pass


class Ticket(Base):
    __tablename__ = "tickets"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        primary_key=True,
        # uuidv7() es nativo en Postgres 18: aleatorio pero ordenable por tiempo,
        # así que el índice no se fragmenta y ordenar por id equivale a ordenar
        # por fecha de creación.
        server_default=text("uuidv7()"),
    )

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )

    # Transcripción o texto original tal cual llegó. No es lo que se lee
    # normalmente en la web; queda disponible como opción secundaria.
    raw_text: Mapped[str] = mapped_column(Text, nullable=False)

    # Título corto generado por el LLM.
    title: Mapped[str] = mapped_column(Text, nullable=False)

    # Descripción autocontenida del hecho o la tarea: debe permitir entender de
    # qué se trataba sin volver al audio original. Esto es lo que el usuario lee.
    summary: Mapped[str] = mapped_column(Text, nullable=False)

    status: Mapped[str] = mapped_column(
        Text, nullable=False, server_default=text("'pendiente'")
    )

    # Qué se hizo finalmente con el ticket. Lo rellena el agente al despacharlo.
    resolution: Mapped[str | None] = mapped_column(Text, nullable=True)

    __table_args__ = (
        CheckConstraint(
            "status IN ('pendiente', 'en_curso', 'archivado')",
            name="ck_tickets_status",
        ),
    )

    def __repr__(self) -> str:
        return f"<Ticket {self.id} [{self.status}] {self.title!r}>"
