"""Dashboard semanal: threads y sus tareas

Un thread es un frente de trabajo de la semana, dibujado como un papel adhesivo
en un pizarron. Dentro lleva las macro tareas que hay que cerrar.

Las tareas no se borran al limpiar el pizarron: se marcan con cleared_at. Asi
el tablero queda limpio y queda el registro de lo que efectivamente se cerro
cada semana.

Revision ID: 0004
Revises: 0003
Create Date: 2026-09-17
"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0004"
down_revision: Union[str, None] = "0003"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

# Los frentes con que parte la persona. Se crean y eliminan desde la interfaz.
THREADS_INICIALES = [
    ("Guitarra", "terracota", 0),
    ("ICAI", "pizarra", 1),
    ("Chilean2Sign", "salvia", 2),
    ("SILU", "mostaza", 3),
]


def upgrade() -> None:
    op.create_table(
        "threads",
        sa.Column(
            "id",
            postgresql.UUID(as_uuid=True),
            server_default=sa.text("uuidv7()"),
            nullable=False,
        ),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column("name", sa.Text(), nullable=False),
        sa.Column("color", sa.Text(), server_default="arena", nullable=False),
        sa.Column("position", sa.Integer(), server_default="0", nullable=False),
        sa.Column("width", sa.Integer(), nullable=True),
        sa.Column("height", sa.Integer(), nullable=True),
        sa.PrimaryKeyConstraint("id", name="pk_threads"),
        sa.UniqueConstraint("name", name="uq_threads_name"),
    )

    op.create_table(
        "thread_tasks",
        sa.Column(
            "id",
            postgresql.UUID(as_uuid=True),
            server_default=sa.text("uuidv7()"),
            nullable=False,
        ),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column("thread_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("text", sa.Text(), nullable=False),
        sa.Column("position", sa.Integer(), server_default="0", nullable=False),
        sa.Column("done_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("cleared_at", sa.DateTime(timezone=True), nullable=True),
        sa.PrimaryKeyConstraint("id", name="pk_thread_tasks"),
        sa.ForeignKeyConstraint(
            ["thread_id"],
            ["threads.id"],
            name="fk_thread_tasks_thread",
            # CASCADE aquí sí: una tarea sin su frente de trabajo no significa
            # nada, al revés de un ticket sin su categoría.
            ondelete="CASCADE",
        ),
    )
    op.create_index(
        "ix_thread_tasks_thread", "thread_tasks", ["thread_id", "position"]
    )

    for name, color, position in THREADS_INICIALES:
        op.execute(
            sa.text(
                "INSERT INTO threads (name, color, position) "
                "VALUES (:name, :color, :position)"
            ).bindparams(name=name, color=color, position=position)
        )


def downgrade() -> None:
    op.drop_index("ix_thread_tasks_thread", table_name="thread_tasks")
    op.drop_table("thread_tasks")
    op.drop_table("threads")
