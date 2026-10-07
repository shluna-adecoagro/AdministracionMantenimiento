# app/crud/metamodelos/marcas_modelos.py

from app.models.marcas_modelos_models import Marca, Modelo

ENTIDAD_MARCAS = {
    "model": Marca,
    "pk": "marca_id",
    "label_singular": "marca",
    "label_plural": "marcas",
    "genero": "f",
    "bp_name": "marcas_modelos",
    "es_subentidad": False,
    "template_detalle": "crud/detalle_entidad.html",
    "fields": {
        "nombre_marca": {"tipo": "text", "label": "Nombre de la marca"},
    },
    "listado": {"columns": ["nombre_marca"]},
    "filtros": {"campos": ["nombre_marca"]},
    "auditoria": {"enabled": True},
    "mostrar_en_sidebar": True,
    "orden": 80,
    # ⭐ SUBENTIDAD MODELOS
    "subentidades": [
        {
            "entidad": "modelos",
            "label": "Modelos",
            "label_singular": "modelo",
            "label_plural": "modelos",
            "fk": "marca_id",
            "template_listado": "crud/listado_subentidad.html",
            "campos_listado": ["nombre_modelo"],
        }
    ],
}

ENTIDAD_MODELOS = {
    "model": Modelo,
    "pk": "modelo_id",
    "label_singular": "modelo",
    "label_plural": "modelos",
    "genero": "m",
    "bp_name": "marcas_modelos",
    # ⭐ MARCAR COMO SUBENTIDAD
    "es_subentidad": True,
    "entidad_padre": "marcas",
    "fk_padre": "marca_id",
    "template_detalle": "crud/detalle_subentidad.html",
    "template_listado": "crud/listado_subentidad.html",
    "fields": {
        "marca_id": {
            "tipo": "fk",
            "label": "Marca",
            "fk_model": Marca,
            "fk_label": "nombre_marca",
            "relacion": "marca",
        },
        "nombre_modelo": {
            "tipo": "text",
            "label": "Nombre del modelo",
            "required": True,
        },
    },
    "listado": {"columns": ["nombre_modelo", "marca_id"]},
    "filtros": {"campos": ["nombre_modelo", "marca_id"]},
    "auditoria": {"enabled": True},
    "mostrar_en_sidebar": False,
    "subentidades": [
        {
            "entidad": "bom_modelo",
            "label": "BOM",
            "fk": "modelo_id",
            "template_listado": "crud/listado_subentidad.html",
            "campos_listado": ["insumo_id", "cantidad", "es_equivalencia"],
        }
    ],
}
