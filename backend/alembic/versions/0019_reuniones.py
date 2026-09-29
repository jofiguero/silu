"""Reuniones

Carpetas ("Reuniones con Leonardo"), reuniones dentro de ellas, y lo que se
anota en cada una.

Los cuatro cuadrantes del tablero son UNA tabla con una columna `zona`, no
cuatro tablas. Un tema que se arrastra de "por conversar" a "conversado" es el
mismo item en otro lugar, y uno que en la reunion resulta ser una tarea se
arrastra a tareas sin copiarlo. Es la misma idea que las tareas con semana y
dia: una fila, no copias que sincronizar.

`user_id` va en las tres tablas y la coherencia entre padre e hija se amarra
con claves foraneas compuestas, igual que en 0016: una reunion no puede
colgar de la carpeta de otra persona aunque el codigo se equivoque.

Revision ID: 0019
Revises: 0018
Create Date: 2026-09-28
"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0019"
down_revision: Union[str, None] = "0018"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

TABLAS = ("meeting_folders", "meetings", "meeting_items")

ZONAS = ("temas", "conversado", "tareas", "apuntes")

# El mismo que dejo 0017 en las demas tablas.
DUENO_ACTUAL = "NULLIF(current_setting('silu.user_id', true), '')::uuid"


def _id() -> sa.Column:
    return sa.Column(
        "id",
        postgresql.UUID(as_uuid=True),
        server_default=sa.text("uuidv7()"),
        nullable=False,
    )


def _creado() -> sa.Column:
    return sa.Column(
        "created_at",
        sa.DateTime(timezone=True),
        server_default=sa.text("now()"),
        nullable=False,
    )


def _dueno() -> sa.Column:
    return sa.Column(
        "user_id",
        postgresql.UUID(as_uuid=True),
        server_default=sa.text(DUENO_ACTUAL),
        nullable=False,
    )


def upgrade() -> None:
    op.create_table(
        "meeting_folders",
        _id(),
        _creado(),
        _dueno(),
        sa.Column("name", sa.Text(), nullable=False),
        sa.Column("position", sa.Integer(), server_default="0", nullable=False),
        sa.PrimaryKeyConstraint("id", name="pk_meeting_folders"),
        sa.ForeignKeyConstraint(
            ["user_id"], ["users.id"], name="fk_meeting_folders_user", ondelete="CASCADE"
        ),
        # Destino de la clave compuesta de meetings.
        sa.UniqueConstraint("id", "user_id", name="uq_meeting_folders_id_user"),
        sa.CheckConstraint(
            "length(btrim(name)) > 0", name="ck_meeting_folders_nombre_no_vacio"
        ),
    )
    # Sin distinguir mayusculas, como los demas nombres unicos por usuario.
    op.create_index(
        "uq_meeting_folders_nombre_por_usuario",
        "meeting_folders",
        ["user_id", sa.text("lower(name)")],
        unique=True,
    )

    op.create_table(
        "meetings",
        _id(),
        _creado(),
        _dueno(),
        sa.Column("folder_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("title", sa.Text(), nullable=False),
        # El dia de la reunion, que no es cuando se creo: se suele preparar la
        # pauta dias antes.
        sa.Column("fecha", sa.Date(), nullable=False),
        sa.Column("summary", sa.Text(), nullable=True),
        sa.Column("summary_at", sa.DateTime(timezone=True), nullable=True),
        sa.PrimaryKeyConstraint("id", name="pk_meetings"),
        sa.ForeignKeyConstraint(
            ["user_id"], ["users.id"], name="fk_meetings_user", ondelete="CASCADE"
        ),
        # Borrar la carpeta se lleva sus reuniones: una reunion sin su carpeta
        # no tiene donde verse.
        sa.ForeignKeyConstraint(
            ["folder_id", "user_id"],
            ["meeting_folders.id", "meeting_folders.user_id"],
            name="fk_meetings_folder_user",
            ondelete="CASCADE",
        ),
        sa.UniqueConstraint("id", "user_id", name="uq_meetings_id_user"),
        sa.CheckConstraint(
            "length(btrim(title)) > 0", name="ck_meetings_titulo_no_vacio"
        ),
        # Un resumen sin fecha, o una fecha sin resumen, no dice nada cierto.
        sa.CheckConstraint(
            "(summary IS NULL) = (summary_at IS NULL)",
            name="ck_meetings_resumen_con_fecha",
        ),
    )
    op.create_index(
        "ix_meetings_carpeta",
        "meetings",
        ["folder_id", sa.text("fecha DESC"), sa.text("id DESC")],
    )

    op.create_table(
        "meeting_items",
        _id(),
        _creado(),
        _dueno(),
        sa.Column("meeting_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("zona", sa.Text(), nullable=False),
        sa.Column("text", sa.Text(), nullable=False),
        sa.Column("position", sa.Integer(), server_default="0", nullable=False),
        sa.PrimaryKeyConstraint("id", name="pk_meeting_items"),
        sa.ForeignKeyConstraint(
            ["user_id"], ["users.id"], name="fk_meeting_items_user", ondelete="CASCADE"
        ),
        sa.ForeignKeyConstraint(
            ["meeting_id", "user_id"],
            ["meetings.id", "meetings.user_id"],
            name="fk_meeting_items_meeting_user",
            ondelete="CASCADE",
        ),
        sa.CheckConstraint(
            "zona IN (" + ", ".join(f"'{z}'" for z in ZONAS) + ")",
            name="ck_meeting_items_zona",
        ),
        sa.CheckConstraint(
            "length(btrim(text)) > 0", name="ck_meeting_items_texto_no_vacio"
        ),
    )
    op.create_index(
        "ix_meeting_items_reunion", "meeting_items", ["meeting_id", "zona", "position"]
    )

    for tabla in TABLAS:
        op.create_index(f"ix_{tabla}_user", tabla, ["user_id"])
        op.execute(f"ALTER TABLE {tabla} ENABLE ROW LEVEL SECURITY")
        op.execute(
            f"""
            CREATE POLICY {tabla}_por_dueno ON {tabla}
            USING (user_id = {DUENO_ACTUAL})
            WITH CHECK (user_id = {DUENO_ACTUAL})
            """
        )
    # Los permisos del rol de la aplicacion no se repiten: 0017 dejo
    # ALTER DEFAULT PRIVILEGES, que cubre las tablas que se crean despues.


def downgrade() -> None:
    for tabla in reversed(TABLAS):
        op.execute(f"DROP POLICY IF EXISTS {tabla}_por_dueno ON {tabla}")
    op.drop_table("meeting_items")
    op.drop_table("meetings")
    op.drop_index("uq_meeting_folders_nombre_por_usuario", table_name="meeting_folders")
    op.drop_table("meeting_folders")
