# app/routes/web/unidades_medida_web.py

from flask import Blueprint
from app.crud.framework import CRUDResource
from app.crud.metamodelos import ENTIDADES

# Registrar el recurso CRUD automáticamente
unidades_medida_web_bp = Blueprint("unidades_medida_web", __name__)
CRUDResource("unidades_medida", ENTIDADES["unidades_medida"], unidades_medida_web_bp)
