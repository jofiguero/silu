"""Marca de "trabajando en esto ahora" en las tareas

Distinta de done y de urgente: no dice que la tarea sea importante ni que este
terminada, dice donde esta puesta la atencion en este momento. Sirve para
retomar el hilo al volver al panel despues de una interrupcion.

Revision ID: 0005
Revises: 0004
Create Date: 2026-09-18
"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "0005"
down_revision: Union[str, None] = "0004"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        "thread_tasks",
        sa.Column(
            "active", sa.Boolean(), server_default=sa.text("false"), nullable=False
        ),
    )


def downgrade() -> None:
    op.drop_column("thread_tasks", "active")
