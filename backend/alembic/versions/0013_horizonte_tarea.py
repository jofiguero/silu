"""Semana y dia de una tarea

Una tarea deja de vivir en "una lista" y pasa a tener dos coordenadas:
la semana a la que se comprometio y el dia al que se bajo.

    week NULL, day NULL  -> otras tareas (pendiente del thread, sin fecha)
    week puesta, day NULL -> comprometida para esa semana
    week puesta, day puesto -> bajada a ese dia

Es una sola fila con dos campos, no tres copias sincronizadas: por eso
cerrarla en el dia la cierra en la semana sin ninguna regla que lo haga, y
crearla en el dia la mete en la semana sola.

Las invariantes van como CHECK y no solo en el servicio: un dia cuya semana
no le corresponde volveria invisible la tarea en las dos vistas, y eso es
justo lo que no puede pasar.

Revision ID: 0013
Revises: 0012
Create Date: 2026-09-22
"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "0013"
down_revision: Union[str, None] = "0012"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column("thread_tasks", sa.Column("week", sa.Date(), nullable=True))
    op.add_column("thread_tasks", sa.Column("day", sa.Date(), nullable=True))

    # date_trunc('week', ...) devuelve el lunes en Postgres.
    op.create_check_constraint(
        "ck_thread_tasks_dia_necesita_semana",
        "thread_tasks",
        "week IS NOT NULL OR day IS NULL",
    )
    op.create_check_constraint(
        "ck_thread_tasks_semana_es_lunes",
        "thread_tasks",
        "week IS NULL OR EXTRACT(ISODOW FROM week) = 1",
    )
    op.create_check_constraint(
        "ck_thread_tasks_dia_en_su_semana",
        "thread_tasks",
        "day IS NULL OR week = date_trunc('week', day::timestamp)::date",
    )

    op.create_index(
        "ix_thread_tasks_semana", "thread_tasks", ["week", "day"]
    )

    # --- Lo que ya existe ---
    #
    # Lo que sigue en el pizarron esta ahi porque es de esta semana: el panel
    # se llama "Esta semana". Lo ya limpiado se fecha por su creacion, que es
    # cuando efectivamente se trabajo, para no falsear el historial metiendo
    # tareas de hace un mes en la semana en curso.
    conexion = op.get_bind()
    conexion.execute(
        sa.text(
            """
            UPDATE thread_tasks SET week = CASE
                WHEN cleared_at IS NULL THEN date_trunc('week', now())::date
                ELSE date_trunc('week', created_at)::date
            END
            """
        )
    )


def downgrade() -> None:
    op.drop_index("ix_thread_tasks_semana", table_name="thread_tasks")
    for nombre in (
        "ck_thread_tasks_dia_en_su_semana",
        "ck_thread_tasks_semana_es_lunes",
        "ck_thread_tasks_dia_necesita_semana",
    ):
        op.drop_constraint(nombre, "thread_tasks", type_="check")
    op.drop_column("thread_tasks", "day")
    op.drop_column("thread_tasks", "week")
