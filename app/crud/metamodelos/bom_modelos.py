# app/crud/metamodelos/bom_modelos.py

from app.models.bom_modelo_models import BOMModelo
from app.models.insumos_models import Insumo
from app.models.marcas_modelos_models import Modelo

# Metamodelo BOMModelo
ENTIDAD_BOM_MODELOS = {
    "model": BOMModelo,
    "pk": "bom_modelo_id",
    "label_singular": "Compatibilidad de modelo",
    "label_plural": "Compatibilidades de modelo",
    "genero": "f",
    # Blueprint donde vive esta entidad
    # Podés elegir "modelos" o crear uno específico "bom"
    "bp_name": "activos",  # se registra en activos_web_bp
    # Campos del formulario
    "fields": {
        "insumo_id": {
            "tipo": "fk",
            "label": "Insumo",
            "fk_model": Insumo,
            "required": True,
        },
        "modelo_id": {
            "tipo": "fk",
            "label": "Modelo",
            "fk_model": Modelo,
            "required": True,
        },
        "cantidad": {
            "tipo": "number",
            "label": "Cantidad",
            "required": False,
        },
        "es_equivalencia": {
            "tipo": "select",
            "label": "Es equivalencia",
            "options": [
                {"value": False, "label": "No"},
                {"value": True, "label": "Sí"},
            ],
            "required": True,
        },
        "nota_equivalencia": {
            "tipo": "textarea",
            "label": "Nota de equivalencia",
            "required": False,
        },
        "origen_equivalencia": {
            "tipo": "text",
            "label": "Origen de equivalencia",
            "required": False,
        },
    },
    # Listado
    "listado": {
        "columns": [
            "insumo_id",
            "modelo_id",
            "cantidad",
            "es_equivalencia",
        ]
    },
    # Filtros
    "filtros": {"campos": ["insumo_id", "modelo_id"]},
    # Auditoría
    "audit": {"enabled": True, "ignore_fields": []},
    # Subentidad: BOMModelo es subentidad de Modelo
    "es_subentidad": False,
}
