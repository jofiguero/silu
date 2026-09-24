"""Registro historico de tareas

`thread_tasks` guarda el estado actual, no lo que paso. Eso deja tres
preguntas sin respuesta: desmarcar borra `done_at`, reprogramar pisa `day` (y
con eso se pierde cuantas veces se pospuso algo), y borrar una tarea se lleva
su rastro, con lo que el historico solo mostraria exitos.

Esta tabla es un registro append-only: una fila por cosa que paso. Nunca se
actualiza ni se borra.

`thread_name` y `task_text` van denormalizados y `task_id` queda en NULL al
borrar la tarea, en vez de cascada. Un registro que desaparece cuando se borra
lo que registraba no sirve para lo unico que existe: saber que paso.

Revision ID: 0014
Revises: 0013
Create Date: 2026-09-24
"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0014"
down_revision: Union[str, None] = "0013"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

TIPOS = ("creada", "hecha", "reabierta", "movida", "eliminada")


def upgrade() -> None:
    op.create_table(
        "thread_task_events",
        sa.Column(
            "id",
            postgresql.UUID(as_uuid=True),
            server_default=sa.text("uuidv7()"),
            nullable=False,
        ),
        # Cuando paso. Es la columna por la que se consulta todo el historico.
        sa.Column(
            "at",
            sa.DateTime(timezone=True),
            server_default=sa.text("clock_timestamp()"),
            nullable=False,
        ),
        sa.Column("task_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("thread_name", sa.Text(), nullable=False),
        sa.Column("task_text", sa.Text(), nullable=False),
        sa.Column("kind", sa.Text(), nullable=False),
        # Para "movida": de que dia a cual. Para "hecha": el dia al que estaba
        # comprometida, que es contra lo que se mide el atraso.
        sa.Column("from_day", sa.Date(), nullable=True),
        sa.Column("to_day", sa.Date(), nullable=True),
        sa.PrimaryKeyConstraint("id", name="pk_thread_task_events"),
        sa.ForeignKeyConstraint(
            ["task_id"],
            ["thread_tasks.id"],
            name="fk_task_events_task",
            ondelete="SET NULL",
        ),
        sa.CheckConstraint(
            "kind IN " + str(TIPOS), name="ck_task_events_kind"
        ),
    )

    op.create_index("ix_task_events_at", "thread_task_events", ["at"])
    op.create_index("ix_task_events_kind", "thread_task_events", ["kind", "at"])

    # --- Lo que ya paso ---
    #
    # Se reconstruye lo que las columnas actuales permiten: la creacion de
    # cada tarea y su ultimo cierre. Los cierres intermedios y las
    # reprogramaciones anteriores a esta migracion no existen en ninguna parte
    # y no se inventan.
    conexion = op.get_bind()
    conexion.execute(
        sa.text(
            """
            INSERT INTO thread_task_events
                (at, task_id, thread_name, task_text, kind, from_day)
            SELECT t.created_at, t.id, h.name, t.text, 'creada', t.day
            FROM thread_tasks t JOIN threads h ON h.id = t.thread_id
            """
        )
    )
    conexion.execute(
        sa.text(
            """
            INSERT INTO thread_task_events
                (at, task_id, thread_name, task_text, kind, from_day)
            SELECT t.done_at, t.id, h.name, t.text, 'hecha', t.day
            FROM thread_tasks t JOIN threads h ON h.id = t.thread_id
            WHERE t.done_at IS NOT NULL
            """
        )
    )


def downgrade() -> None:
    op.drop_index("ix_task_events_kind", table_name="thread_task_events")
    op.drop_index("ix_task_events_at", table_name="thread_task_events")
    op.drop_table("thread_task_events")
