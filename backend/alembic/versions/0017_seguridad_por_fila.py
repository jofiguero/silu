"""Seguridad por fila

La red de seguridad del aislamiento. El codigo ya filtra por `user_id` y hay
tests que lo comprueban, pero un camino nuevo mal escrito podria saltarselo.
Con RLS, Postgres se niega a devolver filas ajenas aunque la consulta las
pida.

Por que hace falta un rol aparte: en Postgres el DUENO de una tabla se salta
sus propias politicas. Si la aplicacion entrara como `silu` --que es quien
crea las tablas en las migraciones-- RLS no protegeria nada. Asi que la app
entra con `silu_app`, que solo puede leer y escribir filas, y las migraciones
siguen entrando con el dueno, que es justo lo que necesitan para tocar las
filas de todos.

La contrasena del rol sale del entorno y nunca del codigo: un archivo de
migracion vive en un repositorio publico.

Revision ID: 0017
Revises: 0016
Create Date: 2026-09-25
"""

import os
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "0017"
down_revision: Union[str, None] = "0016"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

# Las mismas de 0016: todo lo que pertenece a una persona.
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

# `users`, `sessions` y `login_attempts` quedan FUERA a proposito: hay que
# poder leerlas para averiguar quien es quien, justo antes de saberlo. Se
# protegen porque solo el servicio de autenticacion las toca.


def _rol() -> tuple[str, str] | None:
    usuario = os.environ.get("APP_DB_USER")
    clave = os.environ.get("APP_DB_PASSWORD")
    if not usuario or not clave:
        return None
    return usuario, clave


def upgrade() -> None:
    conexion = op.get_bind()
    datos = _rol()

    if datos is None:
        # Sin rol configurado se crean las politicas igual, para que la base
        # quede lista, pero no hay a quien aplicarselas. Es lo que pasa en un
        # entorno a medio configurar; mejor eso que detener el despliegue.
        print(
            "AVISO: APP_DB_USER/APP_DB_PASSWORD no estan definidos. "
            "Las politicas quedan creadas pero la aplicacion seguira entrando "
            "como dueno, y el dueno se las salta."
        )
    else:
        usuario, clave = datos
        existe = conexion.execute(
            sa.text("SELECT 1 FROM pg_roles WHERE rolname = :u").bindparams(u=usuario)
        ).scalar()

        # CREATE/ALTER ROLE son sentencias de utilidad y no aceptan
        # parametros, asi que la contrasena va como literal. Se duplican las
        # comillas simples, que es como Postgres las escapa dentro de una
        # cadena; sin eso, una contrasena con comilla partiria la sentencia.
        literal = "'" + clave.replace("'", "''") + "'"
        verbo = "ALTER" if existe else "CREATE"
        sufijo = "WITH LOGIN PASSWORD" if existe else "LOGIN PASSWORD"
        conexion.execute(sa.text(f'{verbo} ROLE "{usuario}" {sufijo} {literal}'))

        # Lo justo para atender peticiones: leer y escribir filas. Nada de
        # crear ni alterar tablas, que es trabajo de las migraciones.
        conexion.execute(sa.text(f'GRANT USAGE ON SCHEMA public TO "{usuario}"'))
        conexion.execute(
            sa.text(
                "GRANT SELECT, INSERT, UPDATE, DELETE ON ALL TABLES IN SCHEMA public "
                f'TO "{usuario}"'
            )
        )
        conexion.execute(
            sa.text(f'GRANT USAGE ON ALL SEQUENCES IN SCHEMA public TO "{usuario}"')
        )
        # Para las tablas que creen las migraciones futuras, sin tener que
        # acordarse de repetir el GRANT en cada una.
        conexion.execute(
            sa.text(
                "ALTER DEFAULT PRIVILEGES IN SCHEMA public "
                "GRANT SELECT, INSERT, UPDATE, DELETE ON TABLES "
                f'TO "{usuario}"'
            )
        )

    # --- Politicas ---
    #
    # Una sola politica por tabla cubre las cuatro operaciones. USING decide
    # que filas se ven al leer, actualizar o borrar; WITH CHECK, cuales se
    # pueden dejar escritas. Sin WITH CHECK se podria insertar una fila a
    # nombre de otra persona.
    #
    # current_setting(..., true) devuelve NULL si nadie declaro el dueno, y
    # comparar contra NULL no calza con ninguna fila: una sesion que no dice
    # quien es no ve nada, en vez de verlo todo.
    #
    # NULLIF encima, porque la variable tambien puede quedar como cadena
    # vacia, y ''::uuid no es NULL sino un error. Sin esto, una sesion mal
    # declarada no devolveria cero filas: reventaria la consulta.
    dueno_actual = "NULLIF(current_setting('silu.user_id', true), '')::uuid"

    for tabla in TABLAS:
        op.execute(f"ALTER TABLE {tabla} ENABLE ROW LEVEL SECURITY")
        op.execute(
            f"""
            CREATE POLICY {tabla}_por_dueno ON {tabla}
            USING (user_id = {dueno_actual})
            WITH CHECK (user_id = {dueno_actual})
            """
        )
        # El valor por defecto de la columna, por el mismo motivo: con la
        # variable vacia conviene un NOT NULL violado --que dice que falto
        # declarar el dueno-- antes que un error de conversion.
        op.execute(f"ALTER TABLE {tabla} ALTER COLUMN user_id SET DEFAULT {dueno_actual}")


def downgrade() -> None:
    for tabla in TABLAS:
        op.execute(f"DROP POLICY IF EXISTS {tabla}_por_dueno ON {tabla}")
        op.execute(f"ALTER TABLE {tabla} DISABLE ROW LEVEL SECURITY")

    datos = _rol()
    if datos is not None:
        usuario, _ = datos
        # El rol no se borra: podria tener objetos u otras conexiones. Se le
        # quitan los permisos, que es lo que esta migracion le dio.
        op.execute(
            f'REVOKE ALL ON ALL TABLES IN SCHEMA public FROM "{usuario}"'
        )
