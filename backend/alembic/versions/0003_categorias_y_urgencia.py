"""Categorias (lineas de vida) y marca de urgencia

Los tickets pasan a colgar de una categoria. Se crean las cuatro iniciales y
todos los tickets existentes quedan en la bandeja, para que la persona los
reclasifique con calma.

El orden de la bandeja cambia: urgentes primero y, dentro de cada grupo, del
mas antiguo al mas nuevo. Lo viejo sin resolver es lo que conviene mirar
primero, al reves de un feed.

Revision ID: 0003
Revises: 0002
Create Date: 2026-09-17
"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0003"
down_revision: Union[str, None] = "0002"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

# Las que la persona definió al crear el sistema. Se pueden editar, agregar y
# eliminar después desde la web, así que esto es solo el punto de partida.
CATEGORIAS_INICIALES = [
    ("Bandeja", 0, True),
    ("Gastos", 1, False),
    ("Conversar con Luna", 2, False),
    ("Metro", 3, False),
]


def upgrade() -> None:
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

    # Solo puede haber una categoría por defecto: es el destino de los tickets
    # sin clasificar y de los que quedan huérfanos al borrar una categoría.
    op.create_index(
        "ix_categories_unica_default",
        "categories",
        ["is_default"],
        unique=True,
        postgresql_where=sa.text("is_default"),
    )

    for name, position, is_default in CATEGORIAS_INICIALES:
        op.execute(
            sa.text(
                "INSERT INTO categories (name, position, is_default) "
                "VALUES (:name, :position, :is_default)"
            ).bindparams(name=name, position=position, is_default=is_default)
        )

    op.add_column(
        "tickets",
        sa.Column(
            "urgent", sa.Boolean(), server_default=sa.text("false"), nullable=False
        ),
    )

    # Se agrega como nullable, se rellena, y recién entonces se exige NOT NULL:
    # agregarla directamente obligatoria fallaría con filas existentes.
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
        # RESTRICT: borrar una categoría no debe llevarse los tickets por
        # delante. El servicio los mueve a la bandeja antes de borrarla.
        ondelete="RESTRICT",
    )

    op.drop_index("ix_tickets_status_created_at", table_name="tickets")
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
    op.create_index("ix_tickets_status", "tickets", ["status"])


def downgrade() -> None:
    op.drop_index("ix_tickets_status", table_name="tickets")
    op.drop_index("ix_tickets_category_orden", table_name="tickets")
    op.create_index(
        "ix_tickets_status_created_at",
        "tickets",
        ["status", sa.text("created_at DESC"), sa.text("id DESC")],
    )

    op.drop_constraint("fk_tickets_category", "tickets", type_="foreignkey")
    op.drop_column("tickets", "category_id")
    op.drop_column("tickets", "urgent")

    op.drop_index("ix_categories_unica_default", table_name="categories")
    op.drop_table("categories")
