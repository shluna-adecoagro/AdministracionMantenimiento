# app/cli.py
"""
Comandos de consola: `flask --app run <comando>`.

    flask db upgrade     crea o actualiza el esquema (migraciones)
    flask db migrate -m  genera una migración después de cambiar un modelo
    flask seed           carga los catálogos iniciales (estados, motivos, tipos...)
    flask reset-db       borra la base, la recrea y carga los catálogos
    flask drop-db        borra la base
    flask inspect-db     muestra tablas, columnas y claves
    flask importar <entidad> archivo.csv [--simular]   carga datos desde CSV
    flask exportar <entidad> archivo.csv               descarga datos a CSV
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


def _spec(entidad):
    from app.crud.metamodelos import REGISTRY

    if entidad not in REGISTRY:
        disponibles = ", ".join(sorted(REGISTRY))
        raise click.BadParameter(f"«{entidad}» no existe. Disponibles: {disponibles}", param_hint="ENTIDAD")
    return REGISTRY[entidad]


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

    @app.cli.command("importar")
    @click.argument("entidad")
    @click.argument("archivo", type=click.Path(exists=True, dir_okay=False))
    @click.option("--simular", is_flag=True, help="Valida y muestra el resultado sin guardar nada.")
    @click.option("--motivo", help="Motivo para la auditoría (por defecto, el nombre del archivo).")
    @click.option("--usuario", default="importación", show_default=True,
                  help="Usuario que figura en la auditoría.")
    def importar(entidad, archivo, simular, motivo, usuario):
        """Importa un CSV: crea o actualiza registros según su clave natural."""
        from app.crud.intercambio.csv_entidades import importar as importar_csv
        from app.crud.web.textos import etiqueta_tabla

        spec = _spec(entidad)
        with open(archivo, "rb") as f:
            resultado = importar_csv(spec, f.read(), archivo, simular=simular,
                                     usuario=usuario, motivo=motivo, etiqueta_tabla=etiqueta_tabla)
        click.echo(resultado.resumen())
        if not resultado.ok:
            raise SystemExit(1)

    @app.cli.command("exportar")
    @click.argument("entidad")
    @click.argument("archivo", type=click.Path(dir_okay=False, writable=True))
    @click.option("--separador", default=";", show_default=True, help="Separador de columnas.")
    def exportar(entidad, archivo, separador):
        """Exporta una entidad a CSV (se puede volver a importar)."""
        from app.crud.intercambio.csv_entidades import exportar as exportar_csv

        with open(archivo, "wb") as f:
            f.write(exportar_csv(_spec(entidad), separador))
        click.echo(f"✔ {entidad} exportado a {archivo}")

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
