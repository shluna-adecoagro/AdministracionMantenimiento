"""líneas de pedido sin material del maestro

pedido_lineas.sin_material_maestro (fase 13.6): la línea no tiene ni va a tener
material del maestro (ferretería, insumos que no se cargan): sale de la cola
«Líneas sin material». Las líneas existentes quedan en No.

Revision ID: c1d7e3a9b5f2
Revises: b8e4d2f1a9c3
Create Date: 2026-11-27 10:00:00

"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = 'c1d7e3a9b5f2'
down_revision = 'b8e4d2f1a9c3'
branch_labels = None
depends_on = None


def upgrade():
    with op.batch_alter_table('pedido_lineas', schema=None) as batch_op:
        batch_op.add_column(sa.Column('sin_material_maestro', sa.Boolean(), nullable=False,
                                      server_default=sa.false()))


def downgrade():
    with op.batch_alter_table('pedido_lineas', schema=None) as batch_op:
        batch_op.drop_column('sin_material_maestro')
