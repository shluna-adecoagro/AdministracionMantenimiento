from flask import Blueprint
from app.crud.framework import CRUDResource
from app.crud.metamodelos import ENTIDADES

# Blueprint del módulo Marcas y Modelos
marcas_modelos_web_bp = Blueprint("marcas_modelos", __name__)

# Registrar el recurso CRUD automáticamente
CRUDResource("marcas", ENTIDADES["marcas"], marcas_modelos_web_bp)
CRUDResource("modelos", ENTIDADES["modelos"], marcas_modelos_web_bp)
