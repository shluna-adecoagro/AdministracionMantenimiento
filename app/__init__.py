import os

from flask import Flask, jsonify
from flask_cors import CORS
from flask_migrate import Migrate

from app.core.config import config
from app.core.db import db
from app.core.migraciones import importar_modelos, preparar_base

# Blueprints
## API
from app.routes.api.auditoria_routes import audit_bp

## Web
from app.routes.web.index_web import index_web_bp
from app.routes.web.motivos_web import motivos_web


from app.utils.json_validator import JSONValidationError


CARPETA_MIGRACIONES = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "migrations")


def create_app(env="development", config_extra=None):

    app = Flask(
        __name__,
        instance_relative_config=True,
        template_folder="templates",
        static_folder="static",
    )
    app.config.from_object(config[env])
    app.config.update(config_extra or {})

    # ============================
    # Base de datos
    # ============================
    db.init_app(app)
    importar_modelos()
    # render_as_batch: SQLite no admite ALTER TABLE completo; Alembic recrea la tabla.
    Migrate(app, db, directory=CARPETA_MIGRACIONES, render_as_batch=True)
    CORS(app)

    # ============================
    # Registrar API REST
    # ============================
    app.register_blueprint(audit_bp, url_prefix="/api/auditoria")

    # ============================
    # Registrar frontend
    # ============================
    app.register_blueprint(index_web_bp)
    app.register_blueprint(motivos_web)

    # Pantallas CRUD generadas desde el registry
    from app.crud.metamodelos import REGISTRY
    from app.crud.web.views import registrar_web

    registrar_web(app, REGISTRY)

    # API REST generada desde el registry: /api/<entidad>, /api/docs
    from app.crud.api.views import registrar_api

    registrar_api(app, REGISTRY)

    # ============================
    # Filtros de plantilla
    # ============================
    from app.crud.introspect import inicial as _inicial

    app.add_template_filter(_inicial, "inicial")

    @app.template_filter("mostrar")
    def mostrar(valor):
        """Valor para mostrar en una celda: None (dato vacío) se ve como un guion."""
        return "—" if valor is None or valor == "" else valor

    # ============================
    # Manejo de errores JSON
    # ============================
    @app.errorhandler(JSONValidationError)
    def manejar_error_json(e):
        return (
            jsonify({"status": "error", "message": "JSON inválido", "details": str(e)}),
            400,
        )

    # ============================
    # Comandos de consola (flask --app run ...)
    # ============================
    from app.cli import registrar_comandos

    registrar_comandos(app)

    # ============================
    # Preparar la base al primer pedido (solo con AUTO_MIGRATE, en desarrollo):
    # aplica migraciones pendientes y carga catálogos en tablas vacías.
    # ============================
    app.base_preparada = not app.config.get("AUTO_MIGRATE")

    @app.before_request
    def _preparar_base():
        if app.base_preparada:
            return
        from app.utils.seed import seed_data

        preparar_base()
        seed_data()
        app.base_preparada = True
        app.logger.info("Base lista: %s", app.config["SQLALCHEMY_DATABASE_URI"])

    # ============================
    # Sidebar dinámico
    # ============================
    menu = [
        {"name": n, "label": _inicial(s.label_plural), "url": f"/{n}"}
        for n, s in sorted(REGISTRY.items(), key=lambda par: par[1].orden)
        if s.sidebar
    ]

    @app.context_processor
    def inject_sidebar_entities():
        return {"sidebar_items": menu}

    return app
