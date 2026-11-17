# app/cli.py
"""
Comandos de consola: `flask --app run <comando>`.

    flask db upgrade     crea o actualiza el esquema (migraciones)
    flask db migrate -m  genera una migración después de cambiar un modelo
    flask seed           carga los catálogos iniciales (estados, motivos, tipos...)
    flask reset-db       borra la base, la recrea y carga los catálogos
    flask drop-db        borra la base
    flask inspect-db     muestra tablas, columnas y claves
"""
import os

import click
from flask import current_app
from flask_migrate import upgrade
from sqlalchemy import inspect, text
from sqlalchemy.engine.url import make_url

from app.core.db import db
from app.core.migraciones import TABLA_VERSION


def _archivo_sqlite():
    url = make_url(current_app.config["SQLALCHEMY_DATABASE_URI"])
    if url.get_backend_name() == "sqlite" and url.database not in (None, "", ":memory:"):
        return url.database
    return None


def _borrar_base():
    db.session.remove()
    archivo = _archivo_sqlite()
    if archivo:
        db.engine.dispose()
        if os.path.exists(archivo):
            os.remove(archivo)
        click.echo(f"✔ Archivo eliminado: {archivo}")
    else:
        db.drop_all()
        with db.engine.begin() as conexion:
            conexion.execute(text(f"DROP TABLE IF EXISTS {TABLA_VERSION}"))
        click.echo("✔ Tablas eliminadas.")


def registrar_comandos(app):
    @app.cli.command("seed")
    def seed():
        """Carga los catálogos iniciales (solo en tablas vacías)."""
        from app.utils.seed import seed_data

        seed_data()
        click.echo("✔ Catálogos cargados.")

    @app.cli.command("reset-db")
    @click.confirmation_option(prompt="Se borran TODOS los datos. ¿Continuar?")
    def reset_db():
        """Borra la base, aplica las migraciones y carga los catálogos."""
        from app.utils.seed import seed_data

        click.echo(f"Base: {current_app.config['SQLALCHEMY_DATABASE_URI']}")
        _borrar_base()
        upgrade()
        click.echo("✔ Esquema creado (migraciones aplicadas).")
        seed_data()
        click.echo("✔ Catálogos cargados.")

    @app.cli.command("drop-db")
    @click.confirmation_option(prompt="Se borran TODOS los datos. ¿Continuar?")
    def drop_db():
        """Borra la base."""
        _borrar_base()

    @app.cli.command("inspect-db")
    def inspect_db():
        """Muestra tablas, columnas, tipos, PK y FK."""
        inspector = inspect(db.engine)
        for tabla in inspector.get_table_names():
            click.echo(f"\n🟦 {tabla}")
            for col in inspector.get_columns(tabla):
                nulo = "NULL" if col["nullable"] else "NOT NULL"
                click.echo(f"   • {col['name']} ({col['type']}) {nulo}")
            pk = inspector.get_pk_constraint(tabla).get("constrained_columns")
            if pk:
                click.echo(f"   🔑 PK: {pk}")
            for fk in inspector.get_foreign_keys(tabla):
                click.echo(f"   🔗 {fk['constrained_columns']} → {fk['referred_table']}.{fk['referred_columns']}")
