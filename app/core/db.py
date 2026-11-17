import sqlite3

from flask_sqlalchemy import SQLAlchemy
from sqlalchemy import event
from sqlalchemy.engine import Engine

# Instancia global de SQLAlchemy
db = SQLAlchemy()


@event.listens_for(Engine, "connect")
def _activar_claves_foraneas_sqlite(conexion, _registro):
    """
    SQLite no controla las claves foráneas salvo que se lo pida en cada conexión.
    Sin esto se podría, por ejemplo, borrar un sector que todavía tiene ubicaciones.
    """
    if isinstance(conexion, sqlite3.Connection):
        cursor = conexion.cursor()
        cursor.execute("PRAGMA foreign_keys=ON")
        cursor.close()
