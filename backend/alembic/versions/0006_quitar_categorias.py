"""Quitar las categorias de los tickets

Las categorias existian para separar frentes de trabajo dentro de la bandeja.
Ese rol lo cumple ahora el panel de Tareas, con sus threads, asi que mantener
dos taxonomias paralelas era complejidad sin destinatario.

La bandeja vuelve a ser una sola lista. Ningun ticket se pierde: solo dejan de
colgar de una categoria.

Revision ID: 0006
Revises: 0005
Create Date: 2026-09-18
"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0006"
down_revision: Union[str, None] = "0005"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # El indice incluia category_id como primera columna: sin categorias, el
    # orden de la bandeja es urgentes primero y luego del mas antiguo al mas
    # nuevo, con id como desempate estable.
    op.drop_index("ix_tickets_category_orden", table_name="tickets")
    op.create_index(
        "ix_tickets_orden",
        "tickets",
        [sa.text("urgent DESC"), sa.text("created_at ASC"), sa.text("id ASC")],
    )

    op.drop_constraint("fk_tickets_category", "tickets", type_="foreignkey")
    op.drop_column("tickets", "category_id")

    op.drop_index("ix_categories_unica_default", table_name="categories")
    op.drop_table("categories")


def downgrade() -> None:
    """Rehace la estructura y deja todos los tickets en la bandeja.

    No restituye a que categoria pertenecia cada uno: esa informacion se
    elimina al aplicar la migracion.
    """
    op.create_table(
        "categories",
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
        sa.Column("position", sa.Integer(), server_default="0", nullable=False),
        sa.Column(
            "is_default", sa.Boolean(), server_default=sa.text("false"), nullable=False
        ),
        sa.PrimaryKeyConstraint("id", name="pk_categories"),
        sa.UniqueConstraint("name", name="uq_categories_name"),
    )
    op.create_index(
        "ix_categories_unica_default",
        "categories",
        ["is_default"],
        unique=True,
        postgresql_where=sa.text("is_default"),
    )
    op.execute(
        "INSERT INTO categories (name, position, is_default) "
        "VALUES ('Bandeja', 0, true)"
    )

    op.add_column(
        "tickets", sa.Column("category_id", postgresql.UUID(as_uuid=True), nullable=True)
    )
    op.execute(
        "UPDATE tickets SET category_id = (SELECT id FROM categories WHERE is_default)"
    )
    op.alter_column("tickets", "category_id", nullable=False)
    op.create_foreign_key(
        "fk_tickets_category",
        "tickets",
        "categories",
        ["category_id"],
        ["id"],
        ondelete="RESTRICT",
    )

    op.drop_index("ix_tickets_orden", table_name="tickets")
    op.create_index(
        "ix_tickets_category_orden",
        "tickets",
        [
            "category_id",
            sa.text("urgent DESC"),
            sa.text("created_at ASC"),
            sa.text("id ASC"),
        ],
    )
