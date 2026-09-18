"""Gastos: categorias, medios de pago y el registro

El monto va como entero: el peso chileno no tiene centavos, y usar decimales
solo invita a errores de redondeo al sumar.

La fecha del gasto (`spent_on`) es distinta de `created_at`: los gastos se
anotan de forma esporadica, a veces al dia siguiente, y si los totales usaran
la fecha de registro quedarian corridos.

Revision ID: 0007
Revises: 0006
Create Date: 2026-09-18
"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0007"
down_revision: Union[str, None] = "0006"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

# Un set corto para partir. Se agregan y renombran desde la web: pocas y
# reconocibles importa mas que exhaustivas, porque hay que elegir una en el
# momento de pagar.
CATEGORIAS = [
    ("Comida", 0),
    ("Transporte", 1),
    ("Casa", 2),
    ("Salud", 3),
    ("Ocio", 4),
    ("Otros", 5),
]

# Efectivo entra desde el principio: sin el, un pago en efectivo obliga a
# inventar un banco o a no registrar el gasto.
MEDIOS = [("Efectivo", 0)]


def _tabla_simple(nombre: str) -> None:
    op.create_table(
        nombre,
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
        sa.Column("name", sa.Text(), nullable=False),
        sa.Column("position", sa.Integer(), server_default="0", nullable=False),
        sa.PrimaryKeyConstraint("id", name=f"pk_{nombre}"),
        sa.UniqueConstraint("name", name=f"uq_{nombre}_name"),
    )


def upgrade() -> None:
    _tabla_simple("expense_categories")
    _tabla_simple("payment_methods")

    for name, position in CATEGORIAS:
        op.execute(
            sa.text(
                "INSERT INTO expense_categories (name, position) "
                "VALUES (:name, :position)"
            ).bindparams(name=name, position=position)
        )
    for name, position in MEDIOS:
        op.execute(
            sa.text(
                "INSERT INTO payment_methods (name, position) "
                "VALUES (:name, :position)"
            ).bindparams(name=name, position=position)
        )

    op.create_table(
        "expenses",
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
        # Entero: el peso chileno no tiene centavos.
        sa.Column("amount", sa.Integer(), nullable=False),
        # La fecha en que ocurrio el gasto, no la de registro.
        sa.Column(
            "spent_on", sa.Date(), server_default=sa.text("CURRENT_DATE"), nullable=False
        ),
        sa.Column("description", sa.Text(), nullable=True),
        sa.Column("category_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("payment_method_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.PrimaryKeyConstraint("id", name="pk_expenses"),
        # RESTRICT: borrar una categoria no debe llevarse gastos por delante.
        # El servicio los mueve antes.
        sa.ForeignKeyConstraint(
            ["category_id"],
            ["expense_categories.id"],
            name="fk_expenses_category",
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["payment_method_id"],
            ["payment_methods.id"],
            name="fk_expenses_payment_method",
            ondelete="RESTRICT",
        ),
        sa.CheckConstraint("amount > 0", name="ck_expenses_amount_positivo"),
    )

    # El dashboard siempre consulta por rango de fechas; id desempata para que
    # dos gastos del mismo dia queden en orden estable.
    op.create_index(
        "ix_expenses_fecha", "expenses", [sa.text("spent_on DESC"), sa.text("id DESC")]
    )
    op.create_index("ix_expenses_category", "expenses", ["category_id"])

    # updated_at lo mantiene el mismo trigger que ya usan los tickets.
    op.execute(
        """
        CREATE TRIGGER trg_expenses_updated_at
        BEFORE UPDATE ON expenses
        FOR EACH ROW
        EXECUTE FUNCTION set_updated_at();
        """
    )


def downgrade() -> None:
    op.execute("DROP TRIGGER IF EXISTS trg_expenses_updated_at ON expenses;")
    op.drop_index("ix_expenses_category", table_name="expenses")
    op.drop_index("ix_expenses_fecha", table_name="expenses")
    op.drop_table("expenses")
    op.drop_table("payment_methods")
    op.drop_table("expense_categories")
