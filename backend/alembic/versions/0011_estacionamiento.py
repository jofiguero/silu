"""Estacionamiento dentro de Transporte

Queda antes de "Otro" y lo empuja al final: la red de seguridad de la
migracion 0008 y la lectura de la lista asumen que el cajon de sastre va
ultimo.

Revision ID: 0011
Revises: 0010
Create Date: 2026-09-20
"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "0011"
down_revision: Union[str, None] = "0010"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    conexion = op.get_bind()

    conexion.execute(
        sa.text(
            """
            INSERT INTO expense_subcategories (category_id, name, position)
            SELECT id, 'Estacionamiento', 3
            FROM expense_categories WHERE name = 'Transporte'
            ON CONFLICT (category_id, name) DO NOTHING
            """
        )
    )

    conexion.execute(
        sa.text(
            """
            UPDATE expense_subcategories s SET position = 4
            FROM expense_categories c
            WHERE c.id = s.category_id
              AND c.name = 'Transporte'
              AND s.name = 'Otro'
            """
        )
    )

    # El gasto de estacionamiento estaba en "Otro" por no existir todavia su
    # subcategoria. Se identifica por descripcion y no por monto: dos gastos
    # pueden costar lo mismo.
    conexion.execute(
        sa.text(
            """
            UPDATE expenses e SET subcategory_id = (
                SELECT s.id FROM expense_subcategories s
                JOIN expense_categories c ON c.id = s.category_id
                WHERE c.name = 'Transporte' AND s.name = 'Estacionamiento'
            )
            WHERE e.subcategory_id = (
                SELECT s.id FROM expense_subcategories s
                JOIN expense_categories c ON c.id = s.category_id
                WHERE c.name = 'Transporte' AND s.name = 'Otro'
              )
              AND e.description ILIKE '%stacionamiento%'
            """
        )
    )


def downgrade() -> None:
    conexion = op.get_bind()

    # Los gastos vuelven a "Otro" antes de borrar la subcategoria: la clave
    # foranea es RESTRICT y dejarlos apuntandole haria fallar el borrado.
    conexion.execute(
        sa.text(
            """
            UPDATE expenses e SET subcategory_id = (
                SELECT s.id FROM expense_subcategories s
                JOIN expense_categories c ON c.id = s.category_id
                WHERE c.name = 'Transporte' AND s.name = 'Otro'
            )
            WHERE e.subcategory_id = (
                SELECT s.id FROM expense_subcategories s
                JOIN expense_categories c ON c.id = s.category_id
                WHERE c.name = 'Transporte' AND s.name = 'Estacionamiento'
            )
            """
        )
    )
    conexion.execute(
        sa.text(
            """
            DELETE FROM expense_subcategories s
            USING expense_categories c
            WHERE c.id = s.category_id
              AND c.name = 'Transporte'
              AND s.name = 'Estacionamiento'
            """
        )
    )
    conexion.execute(
        sa.text(
            """
            UPDATE expense_subcategories s SET position = 3
            FROM expense_categories c
            WHERE c.id = s.category_id
              AND c.name = 'Transporte'
              AND s.name = 'Otro'
            """
        )
    )
