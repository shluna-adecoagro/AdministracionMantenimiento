import os

from dotenv import load_dotenv

load_dotenv()

BASE_DIR = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
INSTANCE_DIR = os.path.abspath(os.path.join(BASE_DIR, "..", "instance"))
os.makedirs(INSTANCE_DIR, exist_ok=True)

BASE_POR_DEFECTO = os.path.join(INSTANCE_DIR, "mantenimiento.db")


def obtener_uri():
    """DATABASE_URL del entorno (.env) o, si no está, instance/mantenimiento.db."""
    return os.getenv("DATABASE_URL") or "sqlite:///" + BASE_POR_DEFECTO


class Config:
    SECRET_KEY = os.getenv("SECRET_KEY", "dev-secret-key")
    SQLALCHEMY_TRACK_MODIFICATIONS = False
    # Al arrancar, aplicar las migraciones pendientes y cargar los catálogos
    # iniciales (estados, motivos...). Cómodo en desarrollo; en producción
    # conviene correr `flask db upgrade` a mano, como paso del despliegue.
    AUTO_MIGRATE = False


class DevelopmentConfig(Config):
    DEBUG = True
    SQLALCHEMY_DATABASE_URI = obtener_uri()
    AUTO_MIGRATE = True


class ProductionConfig(Config):
    DEBUG = False
    SQLALCHEMY_DATABASE_URI = obtener_uri()


class TestingConfig(Config):
    TESTING = True
    SQLALCHEMY_DATABASE_URI = "sqlite://"  # en memoria


config = {
    "development": DevelopmentConfig,
    "production": ProductionConfig,
    "testing": TestingConfig,
}
