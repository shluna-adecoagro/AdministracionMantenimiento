# app/routes/web/insumos_web.py

from flask import Blueprint, render_template
from app.crud.framework import CRUDResource
from app.crud.metamodelos import ENTIDADES
from app.models.insumos_models import Insumo
from app.models.bom_modelo_models import BOMModelo
from app.models.bom_activo_models import BOMActivo

insumos_web_bp = Blueprint("insumos", __name__)

CRUDResource("insumos", ENTIDADES["insumos"], insumos_web_bp)

CRUDResource("stock_insumo", ENTIDADES["stock_insumo"], insumos_web_bp)


@insumos_web_bp.route("/insumos/<int:id>/compatibilidad_final")
def compatibilidad_final(id):
    insumo = Insumo.query.get_or_404(id)

    # Compatibilidad por modelo
    bom_modelo = BOMModelo.query.filter_by(insumo_id=id).all()

    # Compatibilidad por activo
    bom_activo = BOMActivo.query.filter_by(insumo_id=id).all()

    # Convertir a dict
    modelos = [b.to_dict() for b in bom_modelo]
    activos = [b.to_dict() for b in bom_activo]

    # Combinar
    compatibilidad = modelos + activos

    return render_template(
        "crud/listado_subentidad.html",
        titulo="Compatibilidad final",
        registros=compatibilidad,
        columns=["modelo_id", "activo_id", "es_equivalencia"],
        padre_id=id,
        entidad_padre="insumos",
        entidad_padre_endpoint="insumos.insumos_detalle",
        endpoint_base="insumos.compatibilidad_final",
        es_subentidad=True,
    )
