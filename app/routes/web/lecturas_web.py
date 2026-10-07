# app/routes/web/lecturas_web.py

from flask import Blueprint
from app.crud.framework import CRUDResource
from app.crud.metamodelos import ENTIDADES

lecturas_web = Blueprint("lecturas", __name__)

CRUDResource("lecturas_medidor", ENTIDADES["lecturas_medidor"], lecturas_web)
