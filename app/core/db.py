import sqlite3

from flask_sqlalchemy import SQLAlchemy
from sqlalchemy import MetaData, event
from sqlalchemy.engine import Engine

# Nombres predecibles para índices y restricciones. Las migraciones los necesitan
# para poder modificar o borrar una restricción más adelante (en SQLite, una
# restricción sin nombre no se puede tocar).
CONVENCION_NOMBRES = {
    "ix": "ix_%(column_0_label)s",
    "uq": "uq_%(table_name)s_%(column_0_name)s",
    "ck": "ck_%(table_name)s_%(constraint_name)s",
    "fk": "fk_%(table_name)s_%(column_0_name)s_%(referred_table_name)s",
    "pk": "pk_%(table_name)s",
}

# Instancia global de SQLAlchemy
db = SQLAlchemy(metadata=MetaData(naming_convention=CONVENCION_NOMBRES))


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
