# app/routes/web/activos_web.py

from flask import Blueprint, render_template
from app.crud.framework import CRUDResource
from app.crud.metamodelos import ENTIDADES
from app.models.activos_models import Activo
from app.models.bom_modelo_models import BOMModelo
from app.models.bom_activo_models import BOMActivo

# Blueprint del módulo Activos
activos_web_bp = Blueprint("activos", __name__)

# Entidad principal
CRUDResource("activos", ENTIDADES["activos"], activos_web_bp)

# SUBENTIDAD: Medidores (se registra en el blueprint del padre)
CRUDResource("medidores", ENTIDADES["medidores"], activos_web_bp)

CRUDResource("bom_activo", ENTIDADES["bom_activo"], activos_web_bp)

CRUDResource("bom_modelo", ENTIDADES["bom_modelo"], activos_web_bp)


@activos_web_bp.route("/activos/<int:id>/bom_modelo")
def bom_modelo_por_activo(id):
    activo = Activo.query.get_or_404(id)

    # BOM del modelo
    bom_modelo = BOMModelo.query.filter_by(modelo_id=activo.modelo_id).all()

    # Convertir a dict
    registros = [b.to_dict() for b in bom_modelo]

    return render_template(
        "crud/listado_subentidad.html",
        titulo="BOM del modelo",
        registros=registros,
        columns=["insumo_id", "cantidad", "es_equivalencia"],
        padre_id=id,
        entidad_padre="activos",
        entidad_padre_endpoint="activos.activos_detalle",
        endpoint_base="activos.bom_modelo_por_activo",
        es_subentidad=True,
    )


@activos_web_bp.route("/activos/<int:id>/bom_final")
def bom_final(id):
    activo = Activo.query.get_or_404(id)

    # BOM original del modelo
    bom_modelo = BOMModelo.query.filter_by(modelo_id=activo.modelo_id).all()

    # BOM específico del activo
    bom_activo = BOMActivo.query.filter_by(activo_id=id).all()

    # Convertir a dict
    bom_modelo_dict = [b.to_dict() for b in bom_modelo]
    bom_activo_dict = [b.to_dict() for b in bom_activo]

    # Combinar (activo tiene prioridad)
    bom_final = bom_modelo_dict.copy()

    for b in bom_activo_dict:
        bom_final.append(b)

    return render_template(
        "crud/listado_subentidad.html",
        titulo="BOM final",
        registros=bom_final,
        columns=["insumo_id", "cantidad", "es_equivalencia"],
        padre_id=id,
        entidad_padre="activos",
        entidad_padre_endpoint="activos.activos_detalle",
        endpoint_base="activos.bom_final",
        es_subentidad=True,
    )
