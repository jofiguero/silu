"""Vinculo con Telegram y cuota del bot

Un bot de Telegram no es de una persona: es una identidad con un token que
atiende a todo el mundo. Cada mensaje trae `from.id`, un numero estable y
unico por cuenta de Telegram que la propia Telegram ya autentico. Multi-
usuario es, entonces, una tabla de correspondencia entre ese numero y una
cuenta de Silu.

Lo unico delicado es como se establece esa correspondencia: hay que probar
que la misma persona controla las dos cuentas. Por eso un codigo de un solo
uso que se genera en la web --donde ya hay sesion iniciada-- y se manda al
bot desde el Telegram que se quiere vincular.

Nunca por nombre de usuario: los @ se cambian y se liberan, asi que no
prueban nada.

`telegram_links` y `telegram_usage` quedan fuera de RLS a proposito. La
primera se consulta por codigo JUSTO ANTES de saber de quien es, que es el
punto entero. La segunda la lee el mismo camino, y su unica clave es el
usuario.

Revision ID: 0018
Revises: 0017
Create Date: 2026-09-25
"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0018"
down_revision: Union[str, None] = "0017"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "telegram_links",
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
        sa.Column("user_id", postgresql.UUID(as_uuid=True), nullable=False),
        # El codigo que se dicta al bot. Corto porque hay que escribirlo a
        # mano, y de un solo uso y con vencimiento porque es corto.
        sa.Column("code", sa.Text(), nullable=False),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("used_at", sa.DateTime(timezone=True), nullable=True),
        sa.PrimaryKeyConstraint("id", name="pk_telegram_links"),
        sa.ForeignKeyConstraint(
            ["user_id"], ["users.id"], name="fk_telegram_links_user", ondelete="CASCADE"
        ),
        sa.UniqueConstraint("code", name="uq_telegram_links_code"),
    )
    op.create_index("ix_telegram_links_user", "telegram_links", ["user_id"])

    op.create_table(
        "telegram_usage",
        sa.Column("user_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("day", sa.Date(), nullable=False),
        sa.Column("usados", sa.Integer(), server_default="0", nullable=False),
        sa.PrimaryKeyConstraint("user_id", "day", name="pk_telegram_usage"),
        sa.ForeignKeyConstraint(
            ["user_id"], ["users.id"], name="fk_telegram_usage_user", ondelete="CASCADE"
        ),
    )


def downgrade() -> None:
    op.drop_table("telegram_usage")
    op.drop_index("ix_telegram_links_user", table_name="telegram_links")
    op.drop_table("telegram_links")
