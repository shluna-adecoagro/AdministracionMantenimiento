# app/core/migraciones.py
"""
Esquema de la base: migraciones con Flask-Migrate (Alembic).

Cada cambio en los modelos se registra como una migración en migrations/versions/:

    flask db migrate -m "agrega patente a activos"   # genera la migración
    flask db upgrade                                  # la aplica a la base

Así el esquema queda versionado en git y se puede aplicar igual en cualquier
base (la de desarrollo, la de producción), sin perder datos.
"""
from __future__ import annotations

import importlib
import pkgutil

from alembic.autogenerate import compare_metadata
from alembic.migration import MigrationContext
from flask import current_app
from flask_migrate import stamp, upgrade
from sqlalchemy import inspect

from app.core.db import db

TABLA_VERSION = "alembic_version"


class BaseDesactualizada(RuntimeError):
    pass


def importar_modelos():
    """Importa todos los módulos de app/models para que SQLAlchemy conozca todas las tablas."""
    import app.models as paquete

    for m in pkgutil.iter_modules(paquete.__path__):
        importlib.import_module(f"app.models.{m.name}")


def diferencias_con_modelos() -> list:
    """Diferencias entre el esquema real de la base y los modelos (vacío = coinciden)."""
    with db.engine.connect() as conexion:
        contexto = MigrationContext.configure(conexion, opts={"render_as_batch": True})
        return [
            d for d in compare_metadata(contexto, db.metadata)
            # La tabla de Alembic no es un modelo.
            if not (d[0] == "remove_table" and d[1].name == TABLA_VERSION)
        ]


def preparar_base():
    """
    Deja la base lista para usar:
      - base nueva o con migraciones previas → aplica las pendientes;
      - base creada antes de usar migraciones (con create_all) → si su esquema
        coincide con los modelos, la marca como actualizada; si no, avisa.
    """
    tablas = set(inspect(db.engine).get_table_names())
    if tablas and TABLA_VERSION not in tablas:
        diferencias = diferencias_con_modelos()
        if diferencias:
            raise BaseDesactualizada(
                "La base se creó antes de usar migraciones y su esquema no coincide con "
                f"los modelos ({len(diferencias)} diferencia/s). Si sus datos son de prueba, "
                "recreala con `flask reset-db`."
            )
        current_app.logger.warning("Base existente sin migraciones: se marca como actualizada.")
        stamp()
    upgrade()
