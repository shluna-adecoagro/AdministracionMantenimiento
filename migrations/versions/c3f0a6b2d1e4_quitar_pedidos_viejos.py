"""quitar las tablas viejas de pedidos

Fase 10 (PR 10.1). Las tablas `pedidos` y `pedido_detalle` venían del modelo viejo
(`Pedido` / `PedidoDetalle`), que nunca se registró en la app. Las reemplaza el
diseño de `docs/diseno_tablas_operativas.md` (PR 10.3), que vuelve a usar el
nombre `pedidos`.

Si alguna tiene filas, la migración se detiene: no se borran datos en silencio.

Revision ID: c3f0a6b2d1e4
Revises: 84a903bf1db9
Create Date: 2026-11-23 12:00:00

"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = 'c3f0a6b2d1e4'
down_revision = '84a903bf1db9'
branch_labels = None
depends_on = None


def upgrade():
    conexion = op.get_bind()
    con_datos = [
        tabla for tabla in ("pedido_detalle", "pedidos")
        if conexion.execute(sa.text(f"SELECT COUNT(*) FROM {tabla}")).scalar()
    ]
    if con_datos:
        raise RuntimeError(
            f"Las tablas viejas de pedidos tienen datos ({', '.join(con_datos)}). "
            "Nunca se usaron desde la app: revisalas y vacialas (o recreá la base con "
            "`flask reset-db`), y volvé a ejecutar flask db upgrade."
        )
    op.drop_table('pedido_detalle')
    op.drop_table('pedidos')


def downgrade():
    op.create_table('pedidos',
    sa.Column('PedidoID', sa.Integer(), nullable=False),
    sa.Column('NumeroPedido', sa.String(length=50), nullable=True),
    sa.Column('FechaPedido', sa.Date(), nullable=False),
    sa.Column('Solicitante', sa.String(length=150), nullable=False),
    sa.Column('Referencia', sa.String(length=255), nullable=True),
    sa.Column('Origen', sa.String(length=50), nullable=False),
    sa.Column('FechaCreacion', sa.DateTime(), nullable=False),
    sa.PrimaryKeyConstraint('PedidoID', name=op.f('pk_pedidos')),
    sa.UniqueConstraint('NumeroPedido', name=op.f('uq_pedidos_NumeroPedido'))
    )
    op.create_table('pedido_detalle',
    sa.Column('DetalleID', sa.Integer(), nullable=False),
    sa.Column('PedidoID', sa.Integer(), nullable=False),
    sa.Column('Cantidad', sa.Float(), nullable=False),
    sa.Column('Descripcion', sa.String(length=500), nullable=False),
    sa.Column('LineaOriginal', sa.String(length=500), nullable=True),
    sa.ForeignKeyConstraint(['PedidoID'], ['pedidos.PedidoID'], name=op.f('fk_pedido_detalle_PedidoID_pedidos')),
    sa.PrimaryKeyConstraint('DetalleID', name=op.f('pk_pedido_detalle'))
    )
