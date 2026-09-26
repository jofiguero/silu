"""Cada dato tiene dueno

Le pone `user_id` a todo lo que es de alguien: bandeja, tareas, gastos y
prompts, con sus taxonomias.

Tres decisiones que vale la pena dejar escritas:

1. `user_id` va en TODAS las tablas, incluidas las hijas, en vez de deducirse
   por el padre. Es duplicacion a proposito: una politica de RLS que tuviera
   que subir por un JOIN hasta el padre seria lenta y facil de escribir mal.
   La coherencia entre padre e hija se amarra con claves foraneas compuestas,
   igual que ya se hacia entre gasto y subcategoria.

2. El DEFAULT sale de `current_setting('silu.user_id')`. Asi un INSERT no
   puede olvidarse de poner el dueno: si la aplicacion no declaro quien es,
   el valor queda nulo y el NOT NULL lo rechaza. Es preferible un error
   ruidoso a una fila sin dueno.

3. Los nombres unicos pasan a serlo POR USUARIO. Hoy "SILU" como thread, o
   "Alimento" como categoria, solo pueden existir una vez en toda la base:
   con dos personas, la segunda no podria crear los suyos.

No habilita RLS todavia. Eso viene aparte, junto con el rol de base de datos
con el que se conecta la aplicacion.

Revision ID: 0016
Revises: 0015
Create Date: 2026-09-25
"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0016"
down_revision: Union[str, None] = "0015"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

# Todo lo que pertenece a una persona.
TABLAS = (
    "tickets",
    "threads",
    "thread_tasks",
    "thread_task_events",
    "expense_categories",
    "expense_subcategories",
    "payment_methods",
    "expenses",
    "prompt_projects",
    "prompts",
)

# (tabla, constraint vieja global, columnas del indice nuevo por usuario)
UNICOS = (
    ("threads", "uq_threads_name", "threads"),
    ("expense_categories", "uq_expense_categories_name", "expense_categories"),
    ("payment_methods", "uq_payment_methods_name", "payment_methods"),
    ("prompt_projects", "uq_prompt_projects_name", "prompt_projects"),
)

DEFAULT_DUENO = "current_setting('silu.user_id', true)::uuid"


def upgrade() -> None:
    conexion = op.get_bind()

    # --- A quien se le asigna lo que ya existe ---
    #
    # Todo lo escrito hasta ahora es de la unica cuenta que existe. Si hubiera
    # mas de una no habria forma de saber de quien es cada cosa, y repartirlo
    # al azar seria peor que detenerse.
    duenos = conexion.execute(
        sa.text("SELECT id FROM users ORDER BY created_at")
    ).scalars().all()

    if len(duenos) == 0:
        # Base recien creada: lo unico que hay son las semillas globales que
        # sembraron las migraciones viejas (threads y taxonomia de gastos).
        # Esas pasan a sembrarse por cuenta al crearla, porque una taxonomia
        # compartida entre personas distintas no tiene sentido. Se borran aqui
        # para no dejar filas sin dueno.
        for tabla in reversed(TABLAS):
            conexion.execute(sa.text(f"DELETE FROM {tabla}"))
        dueno = None
    elif len(duenos) > 1:
        raise RuntimeError(
            f"Hay {len(duenos)} cuentas y los datos existentes no dicen de quien "
            "son. Esta migracion solo sabe repartir cuando hay una sola."
        )
    else:
        dueno = duenos[0]

    for tabla in TABLAS:
        op.add_column(
            tabla, sa.Column("user_id", postgresql.UUID(as_uuid=True), nullable=True)
        )
        if dueno is not None:
            conexion.execute(
                sa.text(f"UPDATE {tabla} SET user_id = :dueno").bindparams(dueno=dueno)
            )
        op.alter_column(
            tabla,
            "user_id",
            nullable=False,
            server_default=sa.text(DEFAULT_DUENO),
        )
        op.create_foreign_key(
            f"fk_{tabla}_user",
            tabla,
            "users",
            ["user_id"],
            ["id"],
            # Borrar una cuenta se lleva sus datos. Para sacarle el acceso a
            # alguien sin destruir lo que escribio esta `is_active`.
            ondelete="CASCADE",
        )
        op.create_index(f"ix_{tabla}_user", tabla, ["user_id"])

    # --- Coherencia entre padre e hija ---
    #
    # Sin esto, una tarea podria quedar apuntando al thread de otra persona.
    # La clave foranea compuesta lo vuelve imposible en la base, no solo en el
    # codigo. Requiere un unico sobre (id, user_id) en el padre.
    for padre in ("threads", "expense_categories", "payment_methods", "prompt_projects"):
        op.create_unique_constraint(
            f"uq_{padre}_id_user", padre, ["id", "user_id"]
        )
    op.create_unique_constraint(
        "uq_expense_subcategories_id_user", "expense_subcategories", ["id", "user_id"]
    )

    op.create_foreign_key(
        "fk_thread_tasks_thread_user",
        "thread_tasks",
        "threads",
        ["thread_id", "user_id"],
        ["id", "user_id"],
        ondelete="CASCADE",
    )
    op.create_foreign_key(
        "fk_subcategories_category_user",
        "expense_subcategories",
        "expense_categories",
        ["category_id", "user_id"],
        ["id", "user_id"],
        ondelete="CASCADE",
    )
    op.create_foreign_key(
        "fk_expenses_category_user",
        "expenses",
        "expense_categories",
        ["category_id", "user_id"],
        ["id", "user_id"],
        ondelete="RESTRICT",
    )
    op.create_foreign_key(
        "fk_expenses_method_user",
        "expenses",
        "payment_methods",
        ["payment_method_id", "user_id"],
        ["id", "user_id"],
        ondelete="RESTRICT",
    )
    # project_id es nulo cuando el prompt esta en Principal. Con MATCH SIMPLE
    # --el comportamiento por defecto-- una columna nula desactiva la
    # comprobacion, que es justo lo que se quiere.
    op.create_foreign_key(
        "fk_prompts_project_user",
        "prompts",
        "prompt_projects",
        ["project_id", "user_id"],
        ["id", "user_id"],
        ondelete="SET NULL",
    )

    # --- Unicidad por usuario ---
    for tabla, vieja, _ in UNICOS:
        op.drop_constraint(vieja, tabla, type_="unique")
        # Sin distinguir mayusculas, como ya lo hacia la busqueda por nombre.
        op.create_index(
            f"uq_{tabla}_nombre_por_usuario",
            tabla,
            ["user_id", sa.text("lower(name)")],
            unique=True,
        )


def downgrade() -> None:
    for tabla, vieja, _ in UNICOS:
        op.drop_index(f"uq_{tabla}_nombre_por_usuario", table_name=tabla)
        op.create_unique_constraint(vieja, tabla, ["name"])

    for nombre, tabla in (
        ("fk_prompts_project_user", "prompts"),
        ("fk_expenses_method_user", "expenses"),
        ("fk_expenses_category_user", "expenses"),
        ("fk_subcategories_category_user", "expense_subcategories"),
        ("fk_thread_tasks_thread_user", "thread_tasks"),
    ):
        op.drop_constraint(nombre, tabla, type_="foreignkey")

    op.drop_constraint(
        "uq_expense_subcategories_id_user", "expense_subcategories", type_="unique"
    )
    for padre in ("threads", "expense_categories", "payment_methods", "prompt_projects"):
        op.drop_constraint(f"uq_{padre}_id_user", padre, type_="unique")

    for tabla in TABLAS:
        op.drop_index(f"ix_{tabla}_user", table_name=tabla)
        op.drop_constraint(f"fk_{tabla}_user", tabla, type_="foreignkey")
        op.drop_column(tabla, "user_id")
