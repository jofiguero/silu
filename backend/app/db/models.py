"""Modelos de datos de Silu.

La bandeja (`tickets`) es una sola lista, genérica por diseño: no hay campos
distintos por tipo ni taxonomía propia. Separar frentes de trabajo es rol del
panel de Tareas (`threads`), y tener dos taxonomías paralelas era complejidad
sin destinatario.
"""

import uuid
from datetime import date, datetime

from sqlalchemy import (
    BigInteger,
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


class User(Base):
    """Una cuenta. La contraseña se guarda hasheada, nunca en claro."""

    __tablename__ = "users"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, server_default=text("uuidv7()")
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )

    email: Mapped[str] = mapped_column(Text, nullable=False)
    password_hash: Mapped[str] = mapped_column(Text, nullable=False)
    role: Mapped[str] = mapped_column(Text, nullable=False, server_default="usuario")

    # Desactivar en vez de borrar: quitarle el acceso a alguien no es lo mismo
    # que destruir lo que escribió.
    is_active: Mapped[bool] = mapped_column(
        Boolean, nullable=False, server_default=text("true")
    )

    # Se llena al vincular Telegram, con un código de un solo uso. Nunca por
    # nombre de usuario: los @ se cambian y se liberan, así que no prueban nada.
    telegram_id: Mapped[int | None] = mapped_column(BigInteger, nullable=True)

    last_login_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    # Cambiar la contraseña invalida lo abierto antes de ese instante.
    password_changed_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )

    sessions: Mapped[list["UserSession"]] = relationship(
        back_populates="user", cascade="all, delete-orphan"
    )

    __table_args__ = (
        UniqueConstraint("telegram_id", name="uq_users_telegram"),
        CheckConstraint("role IN ('admin', 'usuario')", name="ck_users_role"),
    )

    @property
    def is_admin(self) -> bool:
        return self.role == "admin"

    def __repr__(self) -> str:
        return f"<User {self.email!r} {self.role}>"


class UserSession(Base):
    """Una sesión abierta. Vive en la base para poder cerrarla.

    Con la sesión solo en una cookie firmada no hay forma de revocarla: el
    servidor no sabe que existe. Aquí se puede cerrar una, cerrarlas todas al
    cambiar la contraseña, y ver desde dónde se entró.
    """

    __tablename__ = "sessions"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, server_default=text("uuidv7()")
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )

    user_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"), nullable=False
    )
    user: Mapped[User] = relationship(back_populates="sessions")

    # El SHA-256 del token, no el token: leer esta tabla no entrega sesiones
    # utilizables.
    token_hash: Mapped[str] = mapped_column(Text, nullable=False, unique=True)

    expires_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False
    )
    last_seen_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
    user_agent: Mapped[str | None] = mapped_column(Text, nullable=True)
    ip: Mapped[str | None] = mapped_column(Text, nullable=True)

    __table_args__ = (Index("ix_sessions_user", "user_id"),)


class LoginAttempt(Base):
    """Un intento de inicio de sesión. Nunca guarda la contraseña."""

    __tablename__ = "login_attempts"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, server_default=text("uuidv7()")
    )
    at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=text("clock_timestamp()"),
    )
    email: Mapped[str | None] = mapped_column(Text, nullable=True)
    ip: Mapped[str] = mapped_column(Text, nullable=False)
    ok: Mapped[bool] = mapped_column(Boolean, nullable=False)

    __table_args__ = (
        Index("ix_login_attempts_ip", "ip", "at"),
        Index("ix_login_attempts_email", "email", "at"),
    )


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

    # El detalle que no cabe en el papel adhesivo: contexto, enlaces, lo que
    # haya que recordar al retomar la tarea. Se ve solo al abrirla.
    description: Mapped[str | None] = mapped_column(Text, nullable=True)

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

    # Las dos coordenadas de la tarea. No son tres listas con copias que haya
    # que sincronizar, es una fila con dos campos:
    #
    #   week NULL,  day NULL   -> otras tareas (del thread, sin fecha)
    #   week puesta, day NULL  -> comprometida para esa semana
    #   week puesta, day puesto -> bajada a ese dia
    #
    # Por eso cerrarla en el dia la cierra en la semana sin ninguna regla que
    # lo haga: es la misma tarea vista con dos filtros distintos.
    week: Mapped[date | None] = mapped_column(Date, nullable=True)
    day: Mapped[date | None] = mapped_column(Date, nullable=True)

    __table_args__ = (
        Index("ix_thread_tasks_thread", "thread_id", "position"),
        Index("ix_thread_tasks_semana", "week", "day"),
        # Las invariantes van tambien en la base y no solo en el servicio: una
        # tarea con un dia que no cae en su semana quedaria invisible en las
        # dos vistas, que es el unico error de verdad grave aqui.
        CheckConstraint(
            "week IS NOT NULL OR day IS NULL",
            name="ck_thread_tasks_dia_necesita_semana",
        ),
        CheckConstraint(
            "week IS NULL OR EXTRACT(ISODOW FROM week) = 1",
            name="ck_thread_tasks_semana_es_lunes",
        ),
        CheckConstraint(
            "day IS NULL OR week = date_trunc('week', day::timestamp)::date",
            name="ck_thread_tasks_dia_en_su_semana",
        ),
    )

    @property
    def done(self) -> bool:
        return self.done_at is not None

    def __repr__(self) -> str:
        return f"<ThreadTask {self.text_!r} done={self.done}>"


# --- Gastos ---


class ThreadTaskEvent(Base):
    """Una cosa que le pasó a una tarea. Registro append-only.

    `thread_tasks` guarda el estado actual; esto guarda la historia. Sin esta
    tabla, desmarcar borra la fecha de cierre, reprogramar pisa el día —y con
    eso se pierde cuántas veces se pospuso algo— y borrar una tarea se lleva
    su rastro, con lo que el histórico solo mostraría éxitos.

    El nombre del thread y el texto de la tarea van copiados, y `task_id` pasa
    a NULL al borrar la tarea en vez de arrastrar la fila: un registro que
    desaparece con lo que registraba no sirve para lo único que existe.
    """

    __tablename__ = "thread_task_events"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, server_default=text("uuidv7()")
    )
    # clock_timestamp() y no now(): dentro de una transacción now() devuelve
    # su inicio, y dos eventos seguidos quedarían con la misma hora.
    at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=text("clock_timestamp()"),
    )

    task_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("thread_tasks.id", ondelete="SET NULL"),
        nullable=True,
    )
    thread_name: Mapped[str] = mapped_column(Text, nullable=False)
    task_text: Mapped[str] = mapped_column(Text, nullable=False)

    kind: Mapped[str] = mapped_column(Text, nullable=False)

    # En "movida", de qué día a cuál. En "hecha", el día al que estaba
    # comprometida: es contra eso que se mide el atraso.
    from_day: Mapped[date | None] = mapped_column(Date, nullable=True)
    to_day: Mapped[date | None] = mapped_column(Date, nullable=True)

    __table_args__ = (
        Index("ix_task_events_at", "at"),
        Index("ix_task_events_kind", "kind", "at"),
        CheckConstraint(
            "kind IN ('creada', 'hecha', 'reabierta', 'movida', 'eliminada')",
            name="ck_task_events_kind",
        ),
    )

    def __repr__(self) -> str:
        return f"<ThreadTaskEvent {self.kind} {self.task_text!r}>"


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


# --- Prompts ---


class PromptProject(Base):
    """Un proyecto con su contexto documentado en Markdown.

    El descriptor va como glosario al ordenar una transcripción: sirve para
    escribir bien un nombre propio o un módulo que se dijo a medias. No es la
    fuente del contenido del prompt, que sale solo de lo que se dictó.
    """

    __tablename__ = "prompt_projects"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, server_default=text("uuidv7()")
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )

    name: Mapped[str] = mapped_column(Text, nullable=False, unique=True)
    description_md: Mapped[str] = mapped_column(Text, nullable=False, server_default="")
    position: Mapped[int] = mapped_column(Integer, nullable=False, server_default="0")

    prompts: Mapped[list["Prompt"]] = relationship(
        back_populates="project", passive_deletes="all"
    )

    def __repr__(self) -> str:
        return f"<PromptProject {self.name!r}>"


class Prompt(Base):
    """Un prompt nacido de un audio informal."""

    __tablename__ = "prompts"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, server_default=text("uuidv7()")
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )

    # Nullable: si no se nombró el proyecto al dictar, el prompt igual se
    # guarda y queda sin asignar. Perder la captura sería el peor resultado.
    project_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("prompt_projects.id", ondelete="SET NULL"),
        nullable=True,
    )
    project: Mapped["PromptProject | None"] = relationship(back_populates="prompts")

    title: Mapped[str] = mapped_column(Text, nullable=False)

    # Lo que se copia.
    content: Mapped[str] = mapped_column(Text, nullable=False)

    # La transcripción informal de la que salió: permite regenerarlo si la
    # redacción mejora, y comparar con lo que efectivamente se dijo.
    raw_text: Mapped[str] = mapped_column(Text, nullable=False)

    # Si se editó a mano, regenerar pisaría ese trabajo.
    edited: Mapped[bool] = mapped_column(
        Boolean, nullable=False, server_default=text("false")
    )

    __table_args__ = (
        Index(
            "ix_prompts_proyecto",
            "project_id",
            text("created_at DESC"),
            text("id DESC"),
        ),
    )

    @property
    def project_name(self) -> str:
        return self.project.name if self.project else ""

    def __repr__(self) -> str:
        return f"<Prompt {self.title!r}>"
