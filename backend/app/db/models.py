"""Modelos de datos de Silu.

Dos tablas: `tickets` y `categories`. El ticket sigue siendo genérico en su
contenido —no hay campos distintos por tipo— pero ahora cuelga de una categoría,
que representa una "línea de vida": gastos, conversaciones con alguien, cosas
para hacer en el metro.

La categoría es una tabla aparte y no un enum para que se puedan crear, renombrar
y eliminar desde la web sin desplegar código: las líneas de vida de una persona
cambian con el tiempo.
"""

import uuid
from datetime import datetime

from sqlalchemy import (
    Boolean,
    CheckConstraint,
    DateTime,
    ForeignKey,
    Index,
    Integer,
    Text,
    func,
    text,
)
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, relationship

# Estados posibles de un ticket a lo largo de su ciclo de vida. Es un eje
# distinto de la categoría: la categoría dice de qué trata, el estado dice en
# qué punto va.
TICKET_STATUSES: tuple[str, ...] = ("pendiente", "en_curso", "archivado")

# Nombre de la categoría que recibe todo lo que llega sin clasificar.
DEFAULT_CATEGORY_NAME = "Bandeja"


class Base(DeclarativeBase):
    pass


class Category(Base):
    __tablename__ = "categories"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, server_default=text("uuidv7()")
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )

    name: Mapped[str] = mapped_column(Text, nullable=False, unique=True)

    # Orden en que aparecen los botones de la barra superior.
    position: Mapped[int] = mapped_column(Integer, nullable=False, server_default="0")

    # La bandeja de entrada. Protegida: no se puede eliminar, porque es el
    # destino al que van los tickets cuando se borra su categoría.
    is_default: Mapped[bool] = mapped_column(
        Boolean, nullable=False, server_default=text("false")
    )

    # passive_deletes="all": al borrar la categoría, SQLAlchemy no toca los
    # tickets. Por defecto les pondría category_id en NULL, deshaciendo el
    # movimiento a la bandeja que hace el servicio justo antes. Quien protege
    # de verdad es el RESTRICT de la base.
    tickets: Mapped[list["Ticket"]] = relationship(
        back_populates="category", passive_deletes="all"
    )

    def __repr__(self) -> str:
        return f"<Category {self.name!r}>"


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
    # Lo mantiene el trigger trg_tickets_updated_at, no la aplicación.
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

    # Marcado por la persona al dictar ("esto es urgente"). Sin niveles: o lo es
    # o no lo es. Sube el ticket al tope de su categoría.
    urgent: Mapped[bool] = mapped_column(
        Boolean, nullable=False, server_default=text("false")
    )

    # RESTRICT en vez de CASCADE: borrar una categoría no debe llevarse los
    # tickets por delante. El servicio los mueve a la bandeja primero.
    category_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("categories.id", ondelete="RESTRICT"),
        nullable=False,
    )
    category: Mapped[Category] = relationship(back_populates="tickets")

    # Qué se hizo finalmente con el ticket. Lo rellena el agente al despacharlo.
    resolution: Mapped[str | None] = mapped_column(Text, nullable=True)

    __table_args__ = (
        CheckConstraint(
            "status IN ('pendiente', 'en_curso', 'archivado')",
            name="ck_tickets_status",
        ),
        # El orden de la bandeja: urgentes primero, y dentro de cada grupo del
        # más antiguo al más nuevo, porque lo viejo sin resolver es lo que
        # conviene mirar primero. id desempata para que paginar sea estable.
        Index(
            "ix_tickets_category_orden",
            "category_id",
            text("urgent DESC"),
            text("created_at ASC"),
            text("id ASC"),
        ),
        Index("ix_tickets_status", "status"),
    )

    @property
    def category_name(self) -> str:
        """Nombre de la categoría, para que el esquema de salida lo exponga
        sin que la interfaz tenga que cruzar dos listas."""
        return self.category.name if self.category else ""

    def __repr__(self) -> str:
        return f"<Ticket {self.id} [{self.status}] {self.title!r}>"


# --- Dashboard semanal ---

# Paleta opaca, de pigmento: colores que existen en un papel adhesivo real.
# Se validan contra esta lista para que el tablero no termine con un fucsia
# fosforescente que rompa la coherencia visual.
THREAD_COLORS: tuple[str, ...] = (
    "arena",
    "durazno",
    "terracota",
    "oliva",
    "salvia",
    "pizarra",
    "niebla",
    "lavanda",
    "ciruela",
    "mostaza",
    "arcilla",
    "musgo",
)


class Thread(Base):
    """Un frente de trabajo de la semana. Se dibuja como un papel adhesivo."""

    __tablename__ = "threads"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, server_default=text("uuidv7()")
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )

    name: Mapped[str] = mapped_column(Text, nullable=False, unique=True)
    color: Mapped[str] = mapped_column(Text, nullable=False, server_default="'arena'")

    # Orden en el pizarrón, que la persona reacomoda arrastrando.
    position: Mapped[int] = mapped_column(Integer, nullable=False, server_default="0")

    # Tamaño elegido a mano, en píxeles. Se guarda porque reacomodar el tablero
    # cada vez que se abre sería trabajo perdido.
    width: Mapped[int | None] = mapped_column(Integer, nullable=True)
    height: Mapped[int | None] = mapped_column(Integer, nullable=True)

    tasks: Mapped[list["ThreadTask"]] = relationship(
        back_populates="thread",
        # Borrar un thread se lleva sus tareas: sin su frente de trabajo no
        # significan nada, al revés de los tickets con su categoría.
        cascade="all, delete-orphan",
        order_by="ThreadTask.position",
    )

    def __repr__(self) -> str:
        return f"<Thread {self.name!r}>"


class ThreadTask(Base):
    """Una macro tarea de la semana dentro de un thread."""

    __tablename__ = "thread_tasks"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, server_default=text("uuidv7()")
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )

    thread_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("threads.id", ondelete="CASCADE"), nullable=False
    )
    thread: Mapped[Thread] = relationship(back_populates="tasks")

    text_: Mapped[str] = mapped_column("text", Text, nullable=False)
    position: Mapped[int] = mapped_column(Integer, nullable=False, server_default="0")

    # Cuándo se marcó. Null significa pendiente; guardar el instante y no solo
    # un booleano permite después responder "qué cerré esta semana".
    done_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )

    # Cuándo se limpió del pizarrón. La tarea no se borra: desaparece de la
    # vista pero queda el registro de lo que efectivamente se cerró.
    cleared_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )

    __table_args__ = (
        Index("ix_thread_tasks_thread", "thread_id", "position"),
    )

    @property
    def done(self) -> bool:
        return self.done_at is not None

    def __repr__(self) -> str:
        return f"<ThreadTask {self.text_!r} done={self.done}>"
