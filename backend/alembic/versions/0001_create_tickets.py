"""Crear tabla tickets

Revision ID: 0001
Revises:
Create Date: 2026-09-15
"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0001"
down_revision: Union[str, None] = None
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "tickets",
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
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column("raw_text", sa.Text(), nullable=False),
        sa.Column("title", sa.Text(), nullable=False),
        sa.Column("summary", sa.Text(), nullable=False),
        sa.Column(
            "status",
            sa.Text(),
            server_default=sa.text("'pendiente'"),
            nullable=False,
        ),
        sa.Column("resolution", sa.Text(), nullable=True),
        sa.PrimaryKeyConstraint("id", name="pk_tickets"),
        sa.CheckConstraint(
            "status IN ('pendiente', 'en_curso', 'archivado')",
            name="ck_tickets_status",
        ),
    )

    # La bandeja siempre se lee filtrando por estado y ordenando por fecha,
    # así que ese es el índice que importa.
    op.create_index(
        "ix_tickets_status_created_at",
        "tickets",
        ["status", sa.text("created_at DESC")],
    )

    # updated_at se mantiene solo: cualquier UPDATE lo refresca, sin depender
    # de que la aplicación se acuerde de hacerlo.
    op.execute(
        """
        CREATE OR REPLACE FUNCTION set_updated_at()
        RETURNS TRIGGER AS $$
        BEGIN
            NEW.updated_at = now();
            RETURN NEW;
        END;
        $$ LANGUAGE plpgsql;
        """
    )
    op.execute(
        """
        CREATE TRIGGER trg_tickets_updated_at
        BEFORE UPDATE ON tickets
        FOR EACH ROW
        EXECUTE FUNCTION set_updated_at();
        """
    )


def downgrade() -> None:
    op.execute("DROP TRIGGER IF EXISTS trg_tickets_updated_at ON tickets;")
    op.execute("DROP FUNCTION IF EXISTS set_updated_at();")
    op.drop_index("ix_tickets_status_created_at", table_name="tickets")
    op.drop_table("tickets")
