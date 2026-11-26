"""
Fixtures comunes de la suite.

Cada test corre contra una base SQLite en memoria, recién creada y con los datos
iniciales (seed). Así los tests no tocan la base real (instance/mantenimiento.db) ni
dependen unos de otros.
"""
import pytest

from app import create_app
from app.core.db import db as _db
from app.utils.seed import seed_data


@pytest.fixture
def app():
    # Config "testing": base en memoria y sin migraciones automáticas. El esquema
    # se crea directo desde los modelos (rápido); test_migraciones.py verifica
    # que las migraciones generen exactamente ese mismo esquema.
    app = create_app("testing")

    with app.app_context():
        _db.drop_all()
        _db.create_all()
        seed_data()
        yield app
        _db.session.remove()
        _db.drop_all()


@pytest.fixture
def client(app):
    return app.test_client()


@pytest.fixture
def db(app):
    return _db


# ---------------------------------------------------------------------------
# Datos de prueba
# ---------------------------------------------------------------------------

@pytest.fixture
def estado_sector_activo(db):
    from app.models.sectores_models import EstadoSector

    return EstadoSector.query.filter_by(nombre_estado_sector="Activo").one()


@pytest.fixture
def sector(db, estado_sector_activo):
    from app.models.sectores_models import Sector

    s = Sector(
        nombre_sector="Taller",
        centro_costo="CC-100",
        estado_sector_id=estado_sector_activo.estado_sector_id,
    )
    db.session.add(s)
    db.session.commit()
    return s


@pytest.fixture
def ubicacion(db, sector):
    from app.models.ubicaciones_models import Ubicacion

    u = Ubicacion(nombre_ubicacion="Galpón 1", sector_id=sector.sector_id)
    db.session.add(u)
    db.session.commit()
    return u


@pytest.fixture
def estado_cuenta_activa(db):
    from app.models.cuentas_models import EstadoCuenta

    return EstadoCuenta.query.filter_by(nombre_estado_cuenta="Activa").one()


@pytest.fixture
def cuenta(db, estado_cuenta_activa):
    from app.models.cuentas_models import Cuenta

    c = Cuenta(
        numero_cuenta="5101",
        nombre_cuenta="Repuestos",
        estado_cuenta_id=estado_cuenta_activa.estado_cuenta_id,
    )
    db.session.add(c)
    db.session.commit()
    return c


@pytest.fixture
def auditoria():
    """Devuelve los registros de auditoría de una tabla, del más viejo al más nuevo."""
    from app.models.auditoria_models import AuditLog

    def _logs(tabla):
        return (
            AuditLog.query.filter_by(TablaAfectada=tabla)
            .order_by(AuditLog.LogID)
            .all()
        )

    return _logs


@pytest.fixture
def categorias_activo(db, cuenta):
    """
    Tipos y categorías de activo (ya no los precarga el seed: cada tipo necesita
    su cuenta). Devuelve {nombre de categoría: CategoriaActivo}.
    """
    from app.models.activos_models import CategoriaActivo, TipoActivo

    categorias = {
        "Maquinaria": ["Tractor", "Pala cargadora"],
        "Vehículo": ["Pickup", "Moto"],
        "Instalación": ["Galpón"],
    }
    resultado = {}
    for tipo, nombres in categorias.items():
        t = TipoActivo(nombre_tipo=tipo, cuenta_id=cuenta.cuenta_id)
        db.session.add(t)
        db.session.flush()
        for n in nombres:
            c = CategoriaActivo(nombre_categoria=n, tipo_activo_id=t.tipo_activo_id)
            db.session.add(c)
            resultado[n] = c
    db.session.commit()
    return resultado


@pytest.fixture
def enviar(client):
    """enviar(pedido_id): «Enviar a Compras» las líneas en borrador del pedido (fase 13.2)."""
    def _enviar(pedido_id):
        r = client.post(f"/pedidos/{pedido_id}/accion/enviar_a_compras")
        assert r.status_code == 302, r.get_data(as_text=True)
    return _enviar
