"""activos: nuevo diseño

Renombres (se conservan los datos):
    patente          → numero_activo (obligatorio y único; los activos sin
                       patente reciben "ACT-<id>")
    codigo_brescia   → codigo_carga_gasoil
    nro_serie_chasis → numero_serie (único)
    nro_motor        → numero_motor (único)
    observacion      → observaciones

Se quita tipo_activo_id: es el de la categoría.

Si hay números de activo, de serie o de motor repetidos, la migración se
detiene y los lista (hay que corregirlos antes, no se elige uno al azar).

Revision ID: 7e5ba69e230b
Revises: 9ad78721c603
Create Date: 2026-11-17 14:22:27.078244

"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = '7e5ba69e230b'
down_revision = '9ad78721c603'
branch_labels = None
depends_on = None


RENOMBRES = [
    ("patente", "numero_activo", sa.String(50)),
    ("codigo_brescia", "codigo_carga_gasoil", sa.String(50)),
    ("nro_serie_chasis", "numero_serie", sa.String(100)),
    ("nro_motor", "numero_motor", sa.String(100)),
    ("observacion", "observaciones", sa.String(300)),
]
UNICOS = ("numero_activo", "numero_serie", "numero_motor")


def _preparar_datos():
    c = op.get_bind()
    # Vacíos → NULL (para los únicos, "" contaría como un valor repetido).
    for col in ("patente", "nro_serie_chasis", "nro_motor"):
        c.execute(sa.text(f"UPDATE activos SET {col} = NULL WHERE TRIM({col}) = ''"))
    c.execute(sa.text(
        "UPDATE activos SET patente = 'ACT-' || CAST(activo_id AS VARCHAR(20)) WHERE patente IS NULL"
    ))

    repetidos = []
    for col, nombre in (("patente", "número de activo (patente)"),
                        ("nro_serie_chasis", "número de serie"),
                        ("nro_motor", "número de motor")):
        filas = c.execute(sa.text(
            f"SELECT {col}, COUNT(*) FROM activos WHERE {col} IS NOT NULL "
            f"GROUP BY {col} HAVING COUNT(*) > 1"
        )).all()
        repetidos += [f"{nombre} «{v}» ({n} activos)" for v, n in filas]
    if repetidos:
        raise RuntimeError(
            "No se puede migrar activos: hay valores que deben ser únicos y están repetidos: "
            + "; ".join(repetidos) + ". Corregilos y volvé a ejecutar flask db upgrade."
        )


def upgrade():
    _preparar_datos()
    with op.batch_alter_table('activos', schema=None) as batch_op:
        for viejo, nuevo, tipo in RENOMBRES:
            batch_op.alter_column(viejo, new_column_name=nuevo, existing_type=tipo,
                                  nullable=False if nuevo == "numero_activo" else None)
    # En otro bloque: las restricciones necesitan las columnas ya renombradas.
    with op.batch_alter_table('activos', schema=None) as batch_op:
        for col in UNICOS:
            batch_op.create_unique_constraint(batch_op.f(f'uq_activos_{col}'), [col])
        batch_op.drop_constraint(batch_op.f('fk_activos_tipo_activo_id_tipos_activo'), type_='foreignkey')
        batch_op.drop_column('tipo_activo_id')


def downgrade():
    with op.batch_alter_table('activos', schema=None) as batch_op:
        batch_op.add_column(sa.Column('tipo_activo_id', sa.INTEGER(), nullable=True))
    # El tipo es el de la categoría.
    op.execute(
        "UPDATE activos SET tipo_activo_id = (SELECT c.tipo_activo_id FROM categorias_activo c "
        "WHERE c.categoria_activo_id = activos.categoria_activo_id)"
    )
    with op.batch_alter_table('activos', schema=None) as batch_op:
        batch_op.alter_column('tipo_activo_id', existing_type=sa.INTEGER(), nullable=False)
        batch_op.create_foreign_key(batch_op.f('fk_activos_tipo_activo_id_tipos_activo'),
                                    'tipos_activo', ['tipo_activo_id'], ['tipo_activo_id'])
        for col in UNICOS:
            batch_op.drop_constraint(batch_op.f(f'uq_activos_{col}'), type_='unique')
    with op.batch_alter_table('activos', schema=None) as batch_op:
        for viejo, nuevo, tipo in RENOMBRES:
            batch_op.alter_column(nuevo, new_column_name=viejo, existing_type=tipo,
                                  nullable=True if nuevo == "numero_activo" else None)
