"""Usuarios, sesiones e intentos de acceso

Reemplaza la contrasena unica compartida por cuentas de verdad.

Tres tablas:

- `users`: la cuenta. La contrasena se guarda hasheada con argon2id, nunca en
  claro. El rol distingue admin de usuario normal.
- `sessions`: la sesion vive en la base y no solo en la cookie. Sin esto no
  hay forma de cerrar una sesion robada salvo rotar el secreto y echar a
  todos.
- `login_attempts`: cada intento, para frenar la fuerza bruta y para poder
  mirar despues quien lo intento.

No toca los datos existentes: en esta fase todo sigue siendo de una sola
persona. Repartir la propiedad de tickets, tareas, gastos y prompts viene
despues, y es un cambio mucho mas delicado.

Revision ID: 0015
Revises: 0014
Create Date: 2026-09-25
"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0015"
down_revision: Union[str, None] = "0014"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "users",
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
        sa.Column("email", sa.Text(), nullable=False),
        # El hash de argon2id, con sus parametros incluidos en la cadena: subir
        # el costo mas adelante no invalida los hashes viejos.
        sa.Column("password_hash", sa.Text(), nullable=False),
        sa.Column("role", sa.Text(), nullable=False, server_default="usuario"),
        # Desactivar en vez de borrar: borrar se llevaria los datos por
        # cascada, y sacarle el acceso a alguien no es lo mismo que destruir
        # lo que escribio.
        sa.Column(
            "is_active", sa.Boolean(), nullable=False, server_default=sa.text("true")
        ),
        # El id de Telegram de esa persona. Se llena al vincular, con un codigo
        # de un solo uso; nunca por nombre de usuario, que se puede cambiar.
        sa.Column("telegram_id", sa.BigInteger(), nullable=True),
        sa.Column("last_login_at", sa.DateTime(timezone=True), nullable=True),
        # Cambiar la contrasena invalida las sesiones abiertas antes de ese
        # instante: si alguien mas la tenia, cambiarla lo tiene que echar.
        sa.Column(
            "password_changed_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.PrimaryKeyConstraint("id", name="pk_users"),
        sa.UniqueConstraint("telegram_id", name="uq_users_telegram"),
        sa.CheckConstraint("role IN ('admin', 'usuario')", name="ck_users_role"),
    )

    # Unico sin distinguir mayusculas: nadie entiende que Joaquin@x.cl y
    # joaquin@x.cl sean cuentas distintas, y permitirlo invita a suplantar.
    op.create_index(
        "uq_users_email", "users", [sa.text("lower(email)")], unique=True
    )

    op.create_table(
        "sessions",
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
        # Se guarda el SHA-256 del token, no el token. Si alguien lee esta
        # tabla no se lleva sesiones utilizables.
        #
        # SHA-256 y no argon2: el token son 256 bits al azar generados por
        # nosotros, no una contrasena que alguien pueda adivinar. Lo que
        # argon2 compra --hacer lento el adivinar-- aqui no compra nada, y
        # costaria 200 ms en cada peticion.
        sa.Column("token_hash", sa.Text(), nullable=False),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column(
            "last_seen_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column("user_agent", sa.Text(), nullable=True),
        sa.Column("ip", sa.Text(), nullable=True),
        sa.PrimaryKeyConstraint("id", name="pk_sessions"),
        sa.ForeignKeyConstraint(
            ["user_id"], ["users.id"], name="fk_sessions_user", ondelete="CASCADE"
        ),
        sa.UniqueConstraint("token_hash", name="uq_sessions_token"),
    )
    op.create_index("ix_sessions_user", "sessions", ["user_id"])

    op.create_table(
        "login_attempts",
        sa.Column(
            "id",
            postgresql.UUID(as_uuid=True),
            server_default=sa.text("uuidv7()"),
            nullable=False,
        ),
        sa.Column(
            "at",
            sa.DateTime(timezone=True),
            server_default=sa.text("clock_timestamp()"),
            nullable=False,
        ),
        # El correo que se intento, exista o no la cuenta. Nunca la contrasena.
        sa.Column("email", sa.Text(), nullable=True),
        sa.Column("ip", sa.Text(), nullable=False),
        sa.Column("ok", sa.Boolean(), nullable=False),
        sa.PrimaryKeyConstraint("id", name="pk_login_attempts"),
    )
    # Los dos indices que usa el limitador: fallos recientes por IP y por
    # cuenta. Sin ellos, cada intento de login recorreria la tabla entera.
    op.create_index("ix_login_attempts_ip", "login_attempts", ["ip", "at"])
    op.create_index("ix_login_attempts_email", "login_attempts", ["email", "at"])


def downgrade() -> None:
    op.drop_table("login_attempts")
    op.drop_index("ix_sessions_user", table_name="sessions")
    op.drop_table("sessions")
    op.drop_index("uq_users_email", table_name="users")
    op.drop_table("users")
