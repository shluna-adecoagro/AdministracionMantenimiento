# app/crud/metamodelos/bom_modelos.py

from app.models.bom_activo_models import BOMActivo
from app.models.activos_models import Activo
from app.models.insumos_models import Insumo

# Metamodelo BOMActivo
ENTIDAD_BOM_ACTIVOS = {
    "model": BOMActivo,
    "pk": "bom_activo_id",
    "label_singular": "BOM del activo",
    "label_plural": "BOM del activo",
    "genero": "m",
    # Este blueprint es importante: BOMActivo vive dentro de "activos"
    "bp_name": "activos",
    # Campos del formulario
    "fields": {
        "activo_id": {
            "tipo": "fk",
            "label": "Activo",
            "fk_model": Activo,
            "required": True,
        },
        "insumo_id": {
            "tipo": "fk",
            "label": "Insumo",
            "fk_model": Insumo,
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
        "reemplaza_insumo_modelo_id": {
            "tipo": "fk",
            "label": "Reemplaza insumo del modelo",
            "fk_model": Insumo,
            "required": False,
        },
    },
    # Listado
    "listado": {
        "columns": [
            "insumo_id",
            "cantidad",
            "es_equivalencia",
            "reemplaza_insumo_modelo_id",
        ]
    },
    # Filtros
    "filtros": {"campos": ["insumo_id", "activo_id"]},
    # Auditoría
    "audit": {"enabled": True, "ignore_fields": []},
    # Subentidad: BOMActivo es subentidad de Activo
    "es_subentidad": False,
}
