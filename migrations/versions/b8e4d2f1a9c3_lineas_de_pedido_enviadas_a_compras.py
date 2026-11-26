"""líneas de pedido enviadas a Compras

pedido_lineas.enviada_en (fase 13.2): vacía = borrador; la pone «Enviar a
Compras». Las líneas que ya existen (el histórico y las cargadas antes de esta
fase) quedan enviadas, con la fecha de su pedido (decidido 26/11).

Revision ID: b8e4d2f1a9c3
Revises: 1d89261de669
Create Date: 2026-11-26 10:00:00

"""
from datetime import datetime, time

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = 'b8e4d2f1a9c3'
down_revision = '1d89261de669'
branch_labels = None
depends_on = None


def upgrade():
    with op.batch_alter_table('pedido_lineas', schema=None) as batch_op:
        batch_op.add_column(sa.Column('enviada_en', sa.DateTime(), nullable=True))

    # Las líneas existentes, enviadas con la fecha de su pedido.
    pedidos = sa.table('pedidos', sa.column('pedido_id', sa.Integer), sa.column('fecha_pedido', sa.Date))
    lineas = sa.table('pedido_lineas', sa.column('pedido_id', sa.Integer), sa.column('enviada_en', sa.DateTime))
    conexion = op.get_bind()
    for pedido_id, fecha in conexion.execute(sa.select(pedidos.c.pedido_id, pedidos.c.fecha_pedido)).all():
        if isinstance(fecha, str):  # SQLite sin tipos
            fecha = datetime.strptime(fecha[:10], "%Y-%m-%d").date()
        enviada = datetime.combine(fecha, time()) if fecha else datetime.now().replace(microsecond=0)
        conexion.execute(lineas.update().where(lineas.c.pedido_id == pedido_id).values(enviada_en=enviada))


def downgrade():
    with op.batch_alter_table('pedido_lineas', schema=None) as batch_op:
        batch_op.drop_column('enviada_en')
