"""Migraciones (Flask-Migrate / Alembic) y preparación de la base."""
import pytest
from alembic.script import ScriptDirectory
from flask_migrate import downgrade, upgrade
from sqlalchemy import inspect

from app import CARPETA_MIGRACIONES, create_app
from app.core.db import db
from app.core.migraciones import BaseDesactualizada, diferencias_con_modelos, preparar_base


@pytest.fixture
def app_archivo(tmp_path):
    """App de prueba sobre un archivo SQLite vacío (las migraciones necesitan uno real)."""
    def _crear(**config):
        uri = f"sqlite:///{tmp_path / 'prueba.db'}"
        return create_app("testing", {"SQLALCHEMY_DATABASE_URI": uri, **config})
    return _crear


def tablas():
    return set(inspect(db.engine).get_table_names())


def test_una_sola_cabeza_de_migraciones():
    from alembic.config import Config

    cfg = Config()
    cfg.set_main_option("script_location", CARPETA_MIGRACIONES)
    assert len(ScriptDirectory.from_config(cfg).get_heads()) == 1


def test_migraciones_generan_el_mismo_esquema_que_los_modelos(app_archivo):
    """Si falla: se cambió un modelo sin generar la migración (flask db migrate)."""
    with app_archivo().app_context():
        upgrade()
        assert diferencias_con_modelos() == []


def test_se_pueden_deshacer(app_archivo):
    with app_archivo().app_context():
        upgrade()
        downgrade(revision="base")
        assert tablas() <= {"alembic_version"}
        upgrade()
        assert "sectores" in tablas()


def test_base_vieja_sin_migraciones_se_adopta(app_archivo):
    """Una base creada con create_all (antes de la Fase 5) se marca como actualizada."""
    with app_archivo().app_context():
        db.create_all()
        preparar_base()
        assert "alembic_version" in tablas()
        assert diferencias_con_modelos() == []


def test_base_vieja_distinta_no_se_toca(app_archivo):
    with app_archivo().app_context():
        db.create_all()
        db.metadata.tables["ubicaciones"].drop(db.engine)
        with pytest.raises(BaseDesactualizada, match="reset-db"):
            preparar_base()


def test_en_desarrollo_la_base_se_prepara_sola(app_archivo):
    from app.models.sectores_models import EstadoSector

    app = app_archivo(AUTO_MIGRATE=True)
    assert app.test_client().get("/sectores").status_code == 200
    with app.app_context():
        assert "alembic_version" in tablas()
        assert EstadoSector.query.count() == 2  # catálogos cargados


def test_produccion_no_migra_sola():
    from app.core.config import ProductionConfig

    assert ProductionConfig.AUTO_MIGRATE is False


def test_reset_db(app_archivo):
    from app.models.sectores_models import EstadoSector

    app = app_archivo()
    resultado = app.test_cli_runner().invoke(args=["reset-db", "--yes"])
    assert resultado.exit_code == 0, resultado.output
    with app.app_context():
        assert "sectores" in tablas()
        assert EstadoSector.query.count() == 2


def test_reset_db_pide_confirmacion(app_archivo):
    resultado = app_archivo().test_cli_runner().invoke(args=["reset-db"], input="n\n")
    assert resultado.exit_code != 0


def test_fase_7_conserva_los_datos(app_archivo):
    """
    Con datos reales: las tablas referenciadas (modelos, medidores) se recrean sin
    romper las claves foráneas, el stock repetido se suma y el BOM vacío pasa a "No".
    """
    from sqlalchemy import text

    sql = [
        "INSERT INTO estados_sector VALUES (1, 'e', 'Activo', '#000')",
        "INSERT INTO sectores (sector_id, uuid, nombre_sector, centro_costo, estado_sector_id) VALUES (1, 's', 'Taller', 'CC', 1)",
        "INSERT INTO ubicaciones (ubicacion_id, uuid, nombre_ubicacion, sector_id) VALUES (1, 'u', 'Galpón', 1)",
        "INSERT INTO categorias_insumo VALUES (1, 'Filtros')",
        "INSERT INTO insumos (insumo_id, uuid, codigo, descripcion, categoria_insumo_id) VALUES (1, 'i', 'F-1', 'Filtro', 1)",
        "INSERT INTO stock_insumo (stock_insumo_id, uuid, insumo_id, sector_id, ubicacion_id, cantidad) VALUES (1, 'a', 1, 1, 1, 2), (2, 'b', 1, 1, 1, 3)",
        "INSERT INTO marcas (marca_id, uuid, nombre_marca) VALUES (1, 'm', 'Marca')",
        "INSERT INTO modelos (modelo_id, uuid, nombre_modelo, marca_id) VALUES (1, 'mo', 'Modelo', 1)",
        "INSERT INTO bom_modelo (bom_modelo_id, uuid, insumo_id, modelo_id) VALUES (1, 'bm', 1, 1)",
    ]
    with app_archivo().app_context():
        upgrade(revision="2e78b97a2c67")
        with db.engine.begin() as c:
            for s in sql:
                c.execute(text(s))
        upgrade()
        with db.engine.connect() as c:
            assert c.execute(text("SELECT stock_insumo_id, cantidad FROM stock_insumo")).all() == [(1, 5.0)]
            assert c.execute(text("SELECT es_equivalencia FROM bom_modelo")).scalar_one() in (0, False)
            assert c.execute(text("SELECT count(*) FROM bom_modelo")).scalar_one() == 1
        downgrade(revision="2e78b97a2c67")
        with db.engine.connect() as c:
            assert c.execute(text("SELECT sector_id FROM stock_insumo")).scalar_one() == 1


_ACTIVOS_BASE = [
    "INSERT INTO tipos_activo VALUES (1, 'Vehículo')",
    "INSERT INTO categorias_activo (categoria_activo_id, nombre_categoria, tipo_activo_id) VALUES (1, 'Pickup', 1)",
    "INSERT INTO estados_activo VALUES (1, 'e', 'Activo', '#000')",
]


def _activo(id_, patente, serie=None, brescia=None):
    valores = ", ".join("NULL" if v is None else f"'{v}'" for v in (patente, serie, brescia))
    return ("INSERT INTO activos (activo_id, uuid, tipo_activo_id, categoria_activo_id, estado_activo_id, "
            f"descripcion, patente, nro_serie_chasis, codigo_brescia) VALUES ({id_}, 'u{id_}', 1, 1, 1, 'X', {valores})")


def test_activos_nuevo_diseno_conserva_los_datos(app_archivo):
    from sqlalchemy import text

    with app_archivo().app_context():
        upgrade(revision="9ad78721c603")
        with db.engine.begin() as c:
            for s in _ACTIVOS_BASE + [_activo(1, "AB123CD", "S-1", "G-77"), _activo(2, None), _activo(3, "", "")]:
                c.execute(text(s))
        upgrade()
        with db.engine.connect() as c:
            filas = c.execute(text(
                "SELECT activo_id, numero_activo, numero_serie, codigo_carga_gasoil FROM activos ORDER BY activo_id"
            )).all()
        assert filas == [(1, "AB123CD", "S-1", "G-77"), (2, "ACT-2", None, None), (3, "ACT-3", None, None)]

        downgrade(revision="9ad78721c603")
        with db.engine.connect() as c:
            assert c.execute(text("SELECT patente, tipo_activo_id FROM activos WHERE activo_id = 1")).one() == ("AB123CD", 1)


def test_activos_repetidos_frenan_la_migracion(app_archivo):
    from sqlalchemy import text

    with app_archivo().app_context():
        upgrade(revision="9ad78721c603")
        with db.engine.begin() as c:
            for s in _ACTIVOS_BASE + [_activo(1, "AB123CD"), _activo(2, "AB123CD")]:
                c.execute(text(s))
        # Flask-Migrate informa el error («AB123CD» (2 activos)) y termina.
        with pytest.raises(SystemExit):
            upgrade()
        with db.engine.connect() as c:
            assert c.execute(text("SELECT count(*) FROM activos WHERE patente = 'AB123CD'")).scalar_one() == 2
