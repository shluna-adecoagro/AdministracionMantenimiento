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
