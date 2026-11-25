"""estados de proveedor y de contacto

- Catálogos estados_proveedor (Activo, Retenido, Inactivo) y estados_contacto
  (Disponible, No disponible), informativos y editables desde Catálogos. Se
  insertan acá, completos, para que el seed no complete un catálogo a medias.
- El estado deja de estar en recursos (común a empleados y proveedores): los
  empleados siguen con estados_recurso, en su propia tabla; los proveedores
  pasan a estados_proveedor por nombre, con «Suspendido» → «Retenido».
- Contactos: estado obligatorio («Disponible» para los existentes) y la columna
  division (agregada al modelo en 8fd4255, sin migración).

Revision ID: dda0f1c78dee
Revises: 5c7c85247e05
Create Date: 2026-11-25 12:10:50.764726

"""
import uuid

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = 'dda0f1c78dee'
down_revision = '5c7c85247e05'
branch_labels = None
depends_on = None

ESTADOS_PROVEEDOR = (("Activo", "#16a34a"), ("Retenido", "#facc15"), ("Inactivo", "#dc2626"))
ESTADOS_CONTACTO = (("Disponible", "#16a34a"), ("No disponible", "#dc2626"))
# Estado de recurso → estado de proveedor (los demás nombres se mantienen).
RECURSO_A_PROVEEDOR = {"Suspendido": "Retenido"}


def _nombres_sin_equivalente(conexion, sql_origen, existentes, equivalencias):
    """Nombres de estado en uso (sql_origen) que no están entre `existentes`."""
    usados = conexion.execute(sa.text(sql_origen)).scalars().all()
    return sorted({n for n in usados if equivalencias.get(n, n) not in set(existentes)})


def _caso(columna, equivalencias):
    """CASE de SQL que traduce nombres según el diccionario."""
    ramas = " ".join(f"WHEN '{a}' THEN '{b}'" for a, b in equivalencias.items())
    return f"CASE {columna} {ramas} ELSE {columna} END"


def upgrade():
    conexion = op.get_bind()

    # Un proveedor con un estado de recurso sin equivalente (uno agregado a mano)
    # no se puede pasar solo: se frena antes de tocar nada (SQLite no deshace
    # el DDL de una migración que falla a mitad de camino).
    sin_equivalente = _nombres_sin_equivalente(
        conexion,
        "SELECT DISTINCT er.nombre_estado_recurso FROM proveedores p "
        "JOIN recursos r ON r.recurso_id = p.recurso_id "
        "JOIN estados_recurso er ON er.estado_recurso_id = r.estado_recurso_id",
        [n for n, _ in ESTADOS_PROVEEDOR],
        RECURSO_A_PROVEEDOR,
    )
    if sin_equivalente:
        raise RuntimeError(
            "Hay proveedores con estados que no existen entre los de proveedor "
            f"(Activo, Retenido, Inactivo): {', '.join(sin_equivalente)}. Cambiales "
            "el estado desde la app, o renombrá ese estado de recurso, y volvé a "
            "ejecutar flask db upgrade."
        )

    # --- Catálogos nuevos ----------------------------------------------------
    op.create_table('estados_contacto',
    sa.Column('estado_contacto_id', sa.Integer(), autoincrement=True, nullable=False),
    sa.Column('uuid', sa.String(length=36), nullable=False),
    sa.Column('nombre_estado_contacto', sa.String(length=50), nullable=False),
    sa.Column('color_badge', sa.String(length=20), nullable=False),
    sa.PrimaryKeyConstraint('estado_contacto_id', name=op.f('pk_estados_contacto')),
    sa.UniqueConstraint('nombre_estado_contacto', name=op.f('uq_estados_contacto_nombre_estado_contacto')),
    sa.UniqueConstraint('uuid', name=op.f('uq_estados_contacto_uuid'))
    )
    op.create_table('estados_proveedor',
    sa.Column('estado_proveedor_id', sa.Integer(), autoincrement=True, nullable=False),
    sa.Column('uuid', sa.String(length=36), nullable=False),
    sa.Column('nombre_estado_proveedor', sa.String(length=50), nullable=False),
    sa.Column('color_badge', sa.String(length=20), nullable=False),
    sa.PrimaryKeyConstraint('estado_proveedor_id', name=op.f('pk_estados_proveedor')),
    sa.UniqueConstraint('nombre_estado_proveedor', name=op.f('uq_estados_proveedor_nombre_estado_proveedor')),
    sa.UniqueConstraint('uuid', name=op.f('uq_estados_proveedor_uuid'))
    )
    op.bulk_insert(
        sa.table("estados_proveedor", sa.column("uuid"), sa.column("nombre_estado_proveedor"),
                 sa.column("color_badge")),
        [{"uuid": str(uuid.uuid4()), "nombre_estado_proveedor": n, "color_badge": c}
         for n, c in ESTADOS_PROVEEDOR],
    )
    op.bulk_insert(
        sa.table("estados_contacto", sa.column("uuid"), sa.column("nombre_estado_contacto"),
                 sa.column("color_badge")),
        [{"uuid": str(uuid.uuid4()), "nombre_estado_contacto": n, "color_badge": c}
         for n, c in ESTADOS_CONTACTO],
    )

    # --- Columnas nuevas, vacías; se completan y recién después son obligatorias
    with op.batch_alter_table('contactos_proveedor', schema=None) as batch_op:
        batch_op.add_column(sa.Column('division', sa.String(length=100), nullable=True))
        batch_op.add_column(sa.Column('estado_contacto_id', sa.Integer(), nullable=True))
    with op.batch_alter_table('empleados', schema=None) as batch_op:
        batch_op.add_column(sa.Column('estado_recurso_id', sa.Integer(), nullable=True))
    with op.batch_alter_table('proveedores', schema=None) as batch_op:
        batch_op.add_column(sa.Column('estado_proveedor_id', sa.Integer(), nullable=True))

    op.execute(
        "UPDATE contactos_proveedor SET estado_contacto_id = (SELECT estado_contacto_id "
        "FROM estados_contacto WHERE nombre_estado_contacto = 'Disponible')"
    )
    op.execute(
        "UPDATE empleados SET estado_recurso_id = (SELECT r.estado_recurso_id "
        "FROM recursos r WHERE r.recurso_id = empleados.recurso_id)"
    )
    op.execute(
        "UPDATE proveedores SET estado_proveedor_id = ("
        "SELECT ep.estado_proveedor_id FROM recursos r "
        "JOIN estados_recurso er ON er.estado_recurso_id = r.estado_recurso_id "
        "JOIN estados_proveedor ep ON ep.nombre_estado_proveedor = "
        f"{_caso('er.nombre_estado_recurso', RECURSO_A_PROVEEDOR)} "
        "WHERE r.recurso_id = proveedores.recurso_id)"
    )

    with op.batch_alter_table('contactos_proveedor', schema=None) as batch_op:
        batch_op.alter_column('estado_contacto_id', existing_type=sa.Integer(), nullable=False)
        batch_op.create_foreign_key(batch_op.f('fk_contactos_proveedor_estado_contacto_id_estados_contacto'), 'estados_contacto', ['estado_contacto_id'], ['estado_contacto_id'])
    with op.batch_alter_table('empleados', schema=None) as batch_op:
        batch_op.alter_column('estado_recurso_id', existing_type=sa.Integer(), nullable=False)
        batch_op.create_foreign_key(batch_op.f('fk_empleados_estado_recurso_id_estados_recurso'), 'estados_recurso', ['estado_recurso_id'], ['estado_recurso_id'])
    with op.batch_alter_table('proveedores', schema=None) as batch_op:
        batch_op.alter_column('estado_proveedor_id', existing_type=sa.Integer(), nullable=False)
        batch_op.create_foreign_key(batch_op.f('fk_proveedores_estado_proveedor_id_estados_proveedor'), 'estados_proveedor', ['estado_proveedor_id'], ['estado_proveedor_id'])

    # --- El estado sale de recursos ---------------------------------------------
    with op.batch_alter_table('recursos', schema=None) as batch_op:
        batch_op.drop_constraint(batch_op.f('fk_recursos_estado_recurso_id_estados_recurso'), type_='foreignkey')
        batch_op.drop_column('estado_recurso_id')


def downgrade():
    conexion = op.get_bind()
    proveedor_a_recurso = {b: a for a, b in RECURSO_A_PROVEEDOR.items()}
    sin_equivalente = _nombres_sin_equivalente(
        conexion,
        "SELECT DISTINCT ep.nombre_estado_proveedor FROM proveedores p "
        "JOIN estados_proveedor ep ON ep.estado_proveedor_id = p.estado_proveedor_id",
        conexion.execute(sa.text("SELECT nombre_estado_recurso FROM estados_recurso")).scalars().all(),
        proveedor_a_recurso,
    )
    if sin_equivalente:
        raise RuntimeError(
            "Hay proveedores con estados que no existen entre los de recurso: "
            f"{', '.join(sin_equivalente)}. Cambiales el estado y volvé a intentar."
        )

    with op.batch_alter_table('recursos', schema=None) as batch_op:
        batch_op.add_column(sa.Column('estado_recurso_id', sa.INTEGER(), nullable=True))
    op.execute(
        "UPDATE recursos SET estado_recurso_id = (SELECT e.estado_recurso_id "
        "FROM empleados e WHERE e.recurso_id = recursos.recurso_id) "
        "WHERE recurso_id IN (SELECT recurso_id FROM empleados)"
    )
    op.execute(
        "UPDATE recursos SET estado_recurso_id = ("
        "SELECT er.estado_recurso_id FROM proveedores p "
        "JOIN estados_proveedor ep ON ep.estado_proveedor_id = p.estado_proveedor_id "
        "JOIN estados_recurso er ON er.nombre_estado_recurso = "
        f"{_caso('ep.nombre_estado_proveedor', proveedor_a_recurso)} "
        "WHERE p.recurso_id = recursos.recurso_id) "
        "WHERE recurso_id IN (SELECT recurso_id FROM proveedores)"
    )
    with op.batch_alter_table('recursos', schema=None) as batch_op:
        batch_op.alter_column('estado_recurso_id', existing_type=sa.INTEGER(), nullable=False)
        batch_op.create_foreign_key(batch_op.f('fk_recursos_estado_recurso_id_estados_recurso'), 'estados_recurso', ['estado_recurso_id'], ['estado_recurso_id'])

    with op.batch_alter_table('proveedores', schema=None) as batch_op:
        batch_op.drop_constraint(batch_op.f('fk_proveedores_estado_proveedor_id_estados_proveedor'), type_='foreignkey')
        batch_op.drop_column('estado_proveedor_id')

    with op.batch_alter_table('empleados', schema=None) as batch_op:
        batch_op.drop_constraint(batch_op.f('fk_empleados_estado_recurso_id_estados_recurso'), type_='foreignkey')
        batch_op.drop_column('estado_recurso_id')

    with op.batch_alter_table('contactos_proveedor', schema=None) as batch_op:
        batch_op.drop_constraint(batch_op.f('fk_contactos_proveedor_estado_contacto_id_estados_contacto'), type_='foreignkey')
        batch_op.drop_column('estado_contacto_id')
        batch_op.drop_column('division')

    op.drop_table('estados_proveedor')
    op.drop_table('estados_contacto')
