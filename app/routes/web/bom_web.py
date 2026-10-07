# app/routes/web/bom_web.py

from flask import Blueprint, render_template
from app.models.bom_modelo_models import BOMModelo
from app.models.bom_activo_models import BOMActivo
from app.models.marcas_modelos_models import Modelo
from app.models.activos_models import Activo
from app.models.insumos_models import Insumo

bom_web_bp = Blueprint("bom", __name__)


# ============================================================
# 1) Vista global del BOM por modelo
# ============================================================
@bom_web_bp.route("/bom/modelos")
def bom_por_modelos():
    registros = BOMModelo.query.all()
    registros = [r.to_dict() for r in registros]

    return render_template(
        "crud/listado_entidad.html",
        titulo="BOM por modelo",
        registros=registros,
        columns=["modelo_id", "insumo_id", "cantidad", "es_equivalencia"],
        endpoint_base="bom.bom_por_modelos",
    )


# ============================================================
# 2) Vista global del BOM por activo
# ============================================================
@bom_web_bp.route("/bom/activos")
def bom_por_activos():
    registros = BOMActivo.query.all()
    registros = [r.to_dict() for r in registros]

    return render_template(
        "crud/listado_entidad.html",
        titulo="BOM por activo",
        registros=registros,
        columns=["activo_id", "insumo_id", "cantidad", "es_equivalencia"],
        endpoint_base="bom.bom_por_activos",
    )


# ============================================================
# 3) Vista combinada (modelo + activo)
# ============================================================
@bom_web_bp.route("/bom/combinado")
def bom_combinado():
    bom_modelo = [r.to_dict() for r in BOMModelo.query.all()]
    bom_activo = [r.to_dict() for r in BOMActivo.query.all()]

    registros = bom_modelo + bom_activo

    return render_template(
        "crud/listado_entidad.html",
        titulo="BOM combinado",
        registros=registros,
        columns=["modelo_id", "activo_id", "insumo_id", "es_equivalencia"],
        endpoint_base="bom.bom_combinado",
    )
