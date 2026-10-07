from flask import Blueprint
from app.crud.framework import CRUDResource
from app.crud.metamodelos import ENTIDADES

# Blueprint del módulo Sectores
sectores_web_bp = Blueprint("sectores_web", __name__)

# Registrar el recurso CRUD automáticamente
CRUDResource("sectores", ENTIDADES["sectores"], sectores_web_bp)
CRUDResource("ubicaciones", ENTIDADES["ubicaciones"], sectores_web_bp)
