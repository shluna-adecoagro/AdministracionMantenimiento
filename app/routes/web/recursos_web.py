# app/routes/web/recursos_web.py

from flask import Blueprint
from app.crud.framework import CRUDResource
from app.models.recursos_models import (
    Recurso,
    Empleado,
    Proveedor,
    ContactoProveedor,
)
from app.crud.metamodelos import ENTIDADES

recursos_web_bp = Blueprint("recursos_web", __name__)


# ============================
# Empleados (Recurso Interno)
# ============================
empleados_crud = CRUDResource(
    name="empleados", config=ENTIDADES["empleados"], blueprint=recursos_web_bp
)


# ============================
# Proveedores (Recurso Externo)
# ============================
proveedores_crud = CRUDResource(
    name="proveedores", config=ENTIDADES["proveedores"], blueprint=recursos_web_bp
)


# ============================
# Contactos de Proveedor
# ============================
contactos_proveedor_crud = CRUDResource(
    name="contactos_proveedor",
    config=ENTIDADES["contactos_proveedor"],
    blueprint=recursos_web_bp,
)
