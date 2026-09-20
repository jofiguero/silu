"""Subcategorias de gasto

Cada gasto pasa a tener categoria y subcategoria. La pareja se amarra con una
clave foranea COMPUESTA contra (id, category_id) de la subcategoria: asi la
base impide guardar "Alimento > Cine" aunque falle una validacion del codigo.
Una FK simple no podria garantizarlo.

Ademas reemplaza la taxonomia inicial por la definitiva y reclasifica los
gastos existentes.

Revision ID: 0008
Revises: 0007
Create Date: 2026-09-20
"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0008"
down_revision: Union[str, None] = "0007"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

# Cada categoria trae un "Otro"/"Otros": con la subcategoria obligatoria,
# siempre tiene que haber donde caer o el formulario dejaria atascado.
TAXONOMIA = {
    "Alimento": ["Restaurant", "Casino", "Chuchería", "Otro"],
    "Ocio": ["Cine", "Otros"],
    "Compras": ["Ropa", "Tecnología", "Libro", "Regalo", "Suscripción", "Otro"],
    "Extras": ["Transporte", "Invitación", "Salud", "Trámites", "Otro"],
}

# Adonde va cada gasto ya registrado. Las categorias viejas que no aparecen
# aqui no tienen gastos y se eliminan sin mas.
RECLASIFICACION = [
    # (categoria vieja, categoria nueva, subcategoria nueva)
    ("Comida", "Alimento", "Restaurant"),
    ("Ocio", "Ocio", "Otros"),
    ("Transporte", "Extras", "Transporte"),
]


def upgrade() -> None:
    op.create_table(
        "expense_subcategories",
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
        sa.Column("category_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("name", sa.Text(), nullable=False),
        sa.Column("position", sa.Integer(), server_default="0", nullable=False),
        sa.PrimaryKeyConstraint("id", name="pk_expense_subcategories"),
        sa.ForeignKeyConstraint(
            ["category_id"],
            ["expense_categories.id"],
            name="fk_subcategories_category",
            # CASCADE: una subcategoria sin su categoria no significa nada. El
            # servicio igual impide borrar una categoria con gastos.
            ondelete="CASCADE",
        ),
        # El nombre es unico dentro de su categoria, no globalmente: "Otro"
        # existe en varias.
        sa.UniqueConstraint("category_id", "name", name="uq_subcategory_nombre"),
        # Destino de la FK compuesta de expenses. Postgres exige un indice
        # unico sobre las columnas referenciadas.
        sa.UniqueConstraint("id", "category_id", name="uq_subcategory_con_categoria"),
    )

    conexion = op.get_bind()

    # --- Taxonomia definitiva ---

    # Comida se renombra en vez de recrearse: asi sus gastos siguen apuntando a
    # la misma fila y no hay que moverlos.
    conexion.execute(
        sa.text("UPDATE expense_categories SET name = 'Alimento' WHERE name = 'Comida'")
    )

    for posicion, (categoria, subs) in enumerate(TAXONOMIA.items()):
        conexion.execute(
            sa.text(
                """
                INSERT INTO expense_categories (name, position)
                VALUES (:name, :position)
                ON CONFLICT (name) DO UPDATE SET position = EXCLUDED.position
                """
            ).bindparams(name=categoria, position=posicion)
        )
        for orden, sub in enumerate(subs):
            conexion.execute(
                sa.text(
                    """
                    INSERT INTO expense_subcategories (category_id, name, position)
                    SELECT id, :sub, :orden FROM expense_categories WHERE name = :cat
                    """
                ).bindparams(sub=sub, orden=orden, cat=categoria)
            )

    # --- Reclasificacion de lo ya registrado ---

    op.add_column(
        "expenses",
        sa.Column("subcategory_id", postgresql.UUID(as_uuid=True), nullable=True),
    )

    for vieja, nueva, sub in RECLASIFICACION:
        conexion.execute(
            sa.text(
                """
                UPDATE expenses SET
                    category_id = (
                        SELECT id FROM expense_categories WHERE name = :nueva
                    ),
                    subcategory_id = (
                        SELECT s.id FROM expense_subcategories s
                        JOIN expense_categories c ON c.id = s.category_id
                        WHERE c.name = :nueva AND s.name = :sub
                    )
                WHERE category_id = (
                    SELECT id FROM expense_categories WHERE name = :vieja
                )
                """
            ).bindparams(vieja=vieja, nueva=nueva, sub=sub)
        )

    # Red de seguridad: si quedara algun gasto sin subcategoria, va al "Otro"
    # de su categoria antes de exigir NOT NULL.
    conexion.execute(
        sa.text(
            """
            UPDATE expenses e SET subcategory_id = (
                SELECT s.id FROM expense_subcategories s
                WHERE s.category_id = e.category_id
                ORDER BY s.position DESC LIMIT 1
            )
            WHERE e.subcategory_id IS NULL
            """
        )
    )

    op.alter_column("expenses", "subcategory_id", nullable=False)
    op.create_foreign_key(
        "fk_expenses_subcategory",
        "expenses",
        "expense_subcategories",
        ["subcategory_id", "category_id"],
        ["id", "category_id"],
        ondelete="RESTRICT",
    )
    op.create_index("ix_expenses_subcategory", "expenses", ["subcategory_id"])

    # Las categorias viejas que ya no existen en la taxonomia y quedaron sin
    # gastos.
    conexion.execute(
        sa.text(
            """
            DELETE FROM expense_categories
            WHERE name NOT IN :vigentes
              AND id NOT IN (SELECT category_id FROM expenses)
            """
        ).bindparams(sa.bindparam("vigentes", tuple(TAXONOMIA), expanding=False))
    )


def downgrade() -> None:
    """Deja los gastos en su categoria actual, sin subcategoria.

    No restituye la taxonomia anterior: esa informacion se pierde al aplicar la
    migracion.
    """
    op.drop_index("ix_expenses_subcategory", table_name="expenses")
    op.drop_constraint("fk_expenses_subcategory", "expenses", type_="foreignkey")
    op.drop_column("expenses", "subcategory_id")
    op.drop_table("expense_subcategories")
