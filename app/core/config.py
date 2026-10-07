import os
from dotenv import load_dotenv
from sqlalchemy.engine.url import make_url

load_dotenv()

BASE_DIR = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
INSTANCE_DIR = os.path.join(BASE_DIR, "..", "instance")
os.makedirs(INSTANCE_DIR, exist_ok=True)


def obtener_uri():
    uri_env = os.getenv("DATABASE_URL")
    if not uri_env:
        return "sqlite:///" + os.path.join(INSTANCE_DIR, "fallback.db")
    return uri_env


class Config:
    SECRET_KEY = os.getenv("SECRET_KEY", "dev-secret-key")
    SQLALCHEMY_TRACK_MODIFICATIONS = False


class DevelopmentConfig(Config):
    DEBUG = True
    SQLALCHEMY_DATABASE_URI = obtener_uri()


class ProductionConfig(Config):
    DEBUG = False
    SQLALCHEMY_DATABASE_URI = obtener_uri()


config = {
    "development": DevelopmentConfig,
    "production": ProductionConfig,
}
