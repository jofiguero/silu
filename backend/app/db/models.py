"""Modelos de datos de Silu.

La bandeja (`tickets`) es una sola lista, genérica por diseño: no hay campos
distintos por tipo ni taxonomía propia. Separar frentes de trabajo es rol del
panel de Tareas (`threads`), y tener dos taxonomías paralelas era complejidad
sin destinatario.
"""

import uuid
from datetime import date, datetime

from sqlalchemy import (
    Boolean,
    CheckConstraint,
    Date,
    DateTime,
    ForeignKey,
    ForeignKeyConstraint,
    Index,
    Integer,
    Text,
    UniqueConstraint,
    func,
    text,
)
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, relationship

# Estados posibles de un ticket a lo largo de su ciclo de vida.
TICKET_STATUSES: tuple[str, ...] = ("pendiente", "en_curso", "archivado")


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
    # o no lo es. Sube el ticket al tope de la bandeja.
    urgent: Mapped[bool] = mapped_column(
        Boolean, nullable=False, server_default=text("false")
    )

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
            "ix_tickets_orden",
            text("urgent DESC"),
            text("created_at ASC"),
            text("id ASC"),
        ),
        Index("ix_tickets_status", "status"),
    )

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
        # significan nada.
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

    # "Estoy en esto ahora mismo". Es distinto de done y de urgente: no dice
    # que sea importante ni que esté terminada, dice dónde está puesta la
    # atención en este momento. Sirve para retomar el hilo al volver al panel.
    active: Mapped[bool] = mapped_column(
        Boolean, nullable=False, server_default=text("false")
    )

    __table_args__ = (
        Index("ix_thread_tasks_thread", "thread_id", "position"),
    )

    @property
    def done(self) -> bool:
        return self.done_at is not None

    def __repr__(self) -> str:
        return f"<ThreadTask {self.text_!r} done={self.done}>"


# --- Gastos ---


class _Etiqueta(Base):
    """Base de las listas cortas que el usuario mantiene: categorías de gasto y
    medios de pago. Son tablas y no enums para poder editarlas desde la web."""

    __abstract__ = True

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, server_default=text("uuidv7()")
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
    name: Mapped[str] = mapped_column(Text, nullable=False, unique=True)
    position: Mapped[int] = mapped_column(Integer, nullable=False, server_default="0")

    def __repr__(self) -> str:
        return f"<{type(self).__name__} {self.name!r}>"


class ExpenseCategory(_Etiqueta):
    __tablename__ = "expense_categories"

    expenses: Mapped[list["Expense"]] = relationship(
        back_populates="category", passive_deletes="all", overlaps="subcategory"
    )
    subcategories: Mapped[list["ExpenseSubcategory"]] = relationship(
        back_populates="category",
        cascade="all, delete-orphan",
        order_by="ExpenseSubcategory.position",
    )


class ExpenseSubcategory(Base):
    """El detalle fino dentro de una categoría: Alimento › Restaurant."""

    __tablename__ = "expense_subcategories"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, server_default=text("uuidv7()")
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
    category_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("expense_categories.id", ondelete="CASCADE"),
        nullable=False,
    )
    category: Mapped[ExpenseCategory] = relationship(back_populates="subcategories")

    name: Mapped[str] = mapped_column(Text, nullable=False)
    position: Mapped[int] = mapped_column(Integer, nullable=False, server_default="0")

    expenses: Mapped[list["Expense"]] = relationship(
        back_populates="subcategory", passive_deletes="all", overlaps="category,expenses"
    )

    __table_args__ = (
        # El nombre es único dentro de su categoría, no globalmente: "Otro"
        # existe en varias.
        UniqueConstraint("category_id", "name", name="uq_subcategory_nombre"),
        # Destino de la clave foránea compuesta de Expense.
        UniqueConstraint("id", "category_id", name="uq_subcategory_con_categoria"),
    )

    def __repr__(self) -> str:
        return f"<ExpenseSubcategory {self.name!r}>"


class PaymentMethod(_Etiqueta):
    __tablename__ = "payment_methods"

    expenses: Mapped[list["Expense"]] = relationship(
        back_populates="payment_method", passive_deletes="all"
    )


class Expense(Base):
    """Un gasto ya ocurrido.

    Solo se escribe desde el formulario de la web, nunca desde el LLM: un monto
    alucinado contamina los totales en silencio, y un total equivocado es peor
    que un gasto no registrado.
    """

    __tablename__ = "expenses"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, server_default=text("uuidv7()")
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )

    # Entero: el peso chileno no tiene centavos, y usar decimales solo invita a
    # errores de redondeo al sumar.
    amount: Mapped[int] = mapped_column(Integer, nullable=False)

    # Cuándo ocurrió el gasto, que no es cuándo se anotó: los gastos se
    # registran de forma esporádica y con la fecha de registro los totales
    # mensuales quedarían corridos.
    spent_on: Mapped[date] = mapped_column(
        Date, nullable=False, server_default=text("CURRENT_DATE")
    )

    description: Mapped[str | None] = mapped_column(Text, nullable=True)

    category_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("expense_categories.id", ondelete="RESTRICT"),
        nullable=False,
    )
    category: Mapped[ExpenseCategory] = relationship(
        back_populates="expenses", overlaps="subcategory,expenses"
    )

    subcategory_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), nullable=False
    )
    # overlaps: la clave foránea compuesta hace que esta relación y `category`
    # escriban la misma columna category_id. Es intencional, no un error de
    # modelado, y así SQLAlchemy no lo reporta como conflicto.
    subcategory: Mapped[ExpenseSubcategory] = relationship(
        back_populates="expenses", overlaps="category,expenses"
    )

    payment_method_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("payment_methods.id", ondelete="RESTRICT"),
        nullable=False,
    )
    payment_method: Mapped[PaymentMethod] = relationship(back_populates="expenses")

    __table_args__ = (
        CheckConstraint("amount > 0", name="ck_expenses_amount_positivo"),
        # Clave foránea COMPUESTA: amarra el par (subcategoría, categoría), así
        # la base impide guardar "Alimento › Cine" aunque falle una validación
        # del código. Una FK simple sobre subcategory_id no podría garantizarlo.
        ForeignKeyConstraint(
            ["subcategory_id", "category_id"],
            ["expense_subcategories.id", "expense_subcategories.category_id"],
            name="fk_expenses_subcategory",
            ondelete="RESTRICT",
        ),
        Index("ix_expenses_fecha", text("spent_on DESC"), text("id DESC")),
        Index("ix_expenses_category", "category_id"),
        Index("ix_expenses_subcategory", "subcategory_id"),
    )

    @property
    def category_name(self) -> str:
        return self.category.name if self.category else ""

    @property
    def subcategory_name(self) -> str:
        return self.subcategory.name if self.subcategory else ""

    @property
    def payment_method_name(self) -> str:
        return self.payment_method.name if self.payment_method else ""

    def __repr__(self) -> str:
        return f"<Expense {self.amount} {self.spent_on}>"
