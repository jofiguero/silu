"""Descripcion en las tareas del panel

El texto de la tarea es el titular que se lee en el papel adhesivo; la
descripcion es el detalle que no cabe ahi y que solo se mira al abrirla.

Revision ID: 0012
Revises: 0011
Create Date: 2026-09-20
"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "0012"
down_revision: Union[str, None] = "0011"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column("thread_tasks", sa.Column("description", sa.Text(), nullable=True))


def downgrade() -> None:
    op.drop_column("thread_tasks", "description")
