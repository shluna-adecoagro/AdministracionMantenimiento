from flask import Blueprint
from app.crud.framework import CRUDResource
from app.crud.metamodelos import ENTIDADES

cuentas_bp = Blueprint("cuentas", __name__)

CRUDResource("cuentas", ENTIDADES["cuentas"], cuentas_bp)
