"""Proyectos y prompts

Un proyecto es un contexto documentado en Markdown. Un prompt nace de un audio
informal y el metaprompter lo convierte en una instruccion hecha y derecha.

`project_id` es nullable a proposito: si la persona no nombro el proyecto al
dictar, el prompt igual se guarda y queda sin asignar. Perder la captura seria
el peor resultado; asignarla despues cuesta un clic.

Revision ID: 0010
Revises: 0009
Create Date: 2026-09-20
"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0010"
down_revision: Union[str, None] = "0009"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "prompt_projects",
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
        sa.Column("name", sa.Text(), nullable=False),
        # El descriptor en Markdown. Es lo que el metaprompter recibe como
        # contexto, asi que la calidad del prompt depende directamente de el.
        sa.Column("description_md", sa.Text(), server_default="", nullable=False),
        sa.Column("position", sa.Integer(), server_default="0", nullable=False),
        sa.PrimaryKeyConstraint("id", name="pk_prompt_projects"),
        sa.UniqueConstraint("name", name="uq_prompt_projects_name"),
    )

    op.create_table(
        "prompts",
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
        # Nullable: sin proyecto nombrado, el prompt igual se guarda.
        sa.Column("project_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("title", sa.Text(), nullable=False),
        # El prompt generado, que es lo que se copia.
        sa.Column("content", sa.Text(), nullable=False),
        # La transcripcion informal de la que salio. Permite regenerarlo si el
        # metaprompter mejora, y entender de que se estaba hablando.
        sa.Column("raw_text", sa.Text(), nullable=False),
        # Si la persona lo edito a mano: regenerar pisaria su trabajo.
        sa.Column("edited", sa.Boolean(), server_default=sa.text("false"), nullable=False),
        sa.PrimaryKeyConstraint("id", name="pk_prompts"),
        sa.ForeignKeyConstraint(
            ["project_id"],
            ["prompt_projects.id"],
            name="fk_prompts_project",
            # SET NULL: borrar un proyecto no debe llevarse los prompts por
            # delante; quedan sin asignar y se reubican.
            ondelete="SET NULL",
        ),
    )

    # La vista siempre lista por proyecto y del mas nuevo al mas viejo: al
    # revisar prompts, el ultimo que dictaste es el que andas buscando.
    op.create_index(
        "ix_prompts_proyecto",
        "prompts",
        ["project_id", sa.text("created_at DESC"), sa.text("id DESC")],
    )

    # updated_at lo mantiene el mismo trigger que ya usan tickets y gastos.
    for tabla in ("prompt_projects", "prompts"):
        op.execute(
            f"""
            CREATE TRIGGER trg_{tabla}_updated_at
            BEFORE UPDATE ON {tabla}
            FOR EACH ROW
            EXECUTE FUNCTION set_updated_at();
            """
        )


def downgrade() -> None:
    for tabla in ("prompts", "prompt_projects"):
        op.execute(f"DROP TRIGGER IF EXISTS trg_{tabla}_updated_at ON {tabla};")
    op.drop_index("ix_prompts_proyecto", table_name="prompts")
    op.drop_table("prompts")
    op.drop_table("prompt_projects")
