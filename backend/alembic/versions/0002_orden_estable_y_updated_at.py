"""Orden estable de la bandeja y updated_at con hora real

Dos correcciones que aparecieron al escribir los tests:

1. El trigger usaba now(), que en Postgres devuelve la hora de INICIO de la
   transaccion. Si una transaccion inserta y luego actualiza la misma fila,
   updated_at quedaba igual a created_at. clock_timestamp() devuelve la hora
   real del momento, que es lo que updated_at debe reflejar.

2. Ordenar solo por created_at DESC deja el desempate al azar cuando dos
   tickets comparten timestamp, y eso rompe la paginacion: una fila puede
   repetirse o perderse entre paginas. Se agrega id como criterio de
   desempate, aprovechando que uuidv7 ya es cronologico.

Revision ID: 0002
Revises: 0001
Create Date: 2026-09-16
"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "0002"
down_revision: Union[str, None] = "0001"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.execute(
        """
        CREATE OR REPLACE FUNCTION set_updated_at()
        RETURNS TRIGGER AS $$
        BEGIN
            NEW.updated_at = clock_timestamp();
            RETURN NEW;
        END;
        $$ LANGUAGE plpgsql;
        """
    )

    op.drop_index("ix_tickets_status_created_at", table_name="tickets")
    op.create_index(
        "ix_tickets_status_created_at",
        "tickets",
        ["status", sa.text("created_at DESC"), sa.text("id DESC")],
    )


def downgrade() -> None:
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

    op.drop_index("ix_tickets_status_created_at", table_name="tickets")
    op.create_index(
        "ix_tickets_status_created_at",
        "tickets",
        ["status", sa.text("created_at DESC")],
    )
