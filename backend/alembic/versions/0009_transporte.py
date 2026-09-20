"""Transporte como categoria propia

Transporte deja de ser una subcategoria de Extras y pasa a ser categoria, con
su propio detalle. Se elimina de Extras: con una categoria propia, tenerlo en
los dos lugares dejaria que el mismo gasto fuera a dos sitios distintos y los
totales dejarian de ser comparables.

Ademas ajusta la clasificacion de los gastos ya registrados.

Revision ID: 0009
Revises: 0008
Create Date: 2026-09-20
"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "0009"
down_revision: Union[str, None] = "0008"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

SUBCATEGORIAS = ["Bencina", "Recarga TNE", "Uber", "Otro"]

# Transporte queda segundo, entre Alimento y Ocio; Extras se mantiene al final
# porque es el cajon de sastre.
ORDEN = ["Alimento", "Transporte", "Ocio", "Compras", "Extras"]


def upgrade() -> None:
    conexion = op.get_bind()

    conexion.execute(
        sa.text(
            """
            INSERT INTO expense_categories (name, position)
            VALUES ('Transporte', 1)
            ON CONFLICT (name) DO NOTHING
            """
        )
    )

    for orden, nombre in enumerate(SUBCATEGORIAS):
        conexion.execute(
            sa.text(
                """
                INSERT INTO expense_subcategories (category_id, name, position)
                SELECT id, :sub, :orden
                FROM expense_categories WHERE name = 'Transporte'
                ON CONFLICT (category_id, name) DO NOTHING
                """
            ).bindparams(sub=nombre, orden=orden)
        )

    for posicion, nombre in enumerate(ORDEN):
        conexion.execute(
            sa.text(
                "UPDATE expense_categories SET position = :posicion WHERE name = :name"
            ).bindparams(posicion=posicion, name=nombre)
        )

    # --- Reclasificacion de lo ya registrado ---
    #
    # category_id y subcategory_id se actualizan juntos: la clave foranea es
    # compuesta y un paso intermedio con la pareja descalzada seria rechazado.

    # Lo que estaba en Extras > Transporte pasa a Transporte > Recarga TNE.
    conexion.execute(
        sa.text(
            """
            UPDATE expenses SET
                category_id = (
                    SELECT id FROM expense_categories WHERE name = 'Transporte'
                ),
                subcategory_id = (
                    SELECT s.id FROM expense_subcategories s
                    JOIN expense_categories c ON c.id = s.category_id
                    WHERE c.name = 'Transporte' AND s.name = 'Recarga TNE'
                )
            WHERE subcategory_id = (
                SELECT s.id FROM expense_subcategories s
                JOIN expense_categories c ON c.id = s.category_id
                WHERE c.name = 'Extras' AND s.name = 'Transporte'
            )
            """
        )
    )

    # Los de la fonda pasan de Restaurant a Chucheria.
    conexion.execute(
        sa.text(
            """
            UPDATE expenses SET subcategory_id = (
                SELECT s.id FROM expense_subcategories s
                JOIN expense_categories c ON c.id = s.category_id
                WHERE c.name = 'Alimento' AND s.name = 'Chuchería'
            )
            WHERE subcategory_id = (
                SELECT s.id FROM expense_subcategories s
                JOIN expense_categories c ON c.id = s.category_id
                WHERE c.name = 'Alimento' AND s.name = 'Restaurant'
            )
            """
        )
    )

    # Ya sin gastos apuntandole.
    conexion.execute(
        sa.text(
            """
            DELETE FROM expense_subcategories s
            USING expense_categories c
            WHERE c.id = s.category_id
              AND c.name = 'Extras'
              AND s.name = 'Transporte'
              AND NOT EXISTS (
                  SELECT 1 FROM expenses e WHERE e.subcategory_id = s.id
              )
            """
        )
    )


def downgrade() -> None:
    """Devuelve Transporte a Extras y elimina la categoria.

    No restituye a que subcategoria pertenecia cada gasto antes: esa
    informacion se pierde al aplicar la migracion.
    """
    conexion = op.get_bind()

    conexion.execute(
        sa.text(
            """
            INSERT INTO expense_subcategories (category_id, name, position)
            SELECT id, 'Transporte', 0 FROM expense_categories WHERE name = 'Extras'
            ON CONFLICT (category_id, name) DO NOTHING
            """
        )
    )
    conexion.execute(
        sa.text(
            """
            UPDATE expenses SET
                category_id = (
                    SELECT id FROM expense_categories WHERE name = 'Extras'
                ),
                subcategory_id = (
                    SELECT s.id FROM expense_subcategories s
                    JOIN expense_categories c ON c.id = s.category_id
                    WHERE c.name = 'Extras' AND s.name = 'Transporte'
                )
            WHERE category_id = (
                SELECT id FROM expense_categories WHERE name = 'Transporte'
            )
            """
        )
    )
    # CASCADE se lleva sus subcategorias.
    conexion.execute(
        sa.text("DELETE FROM expense_categories WHERE name = 'Transporte'")
    )
