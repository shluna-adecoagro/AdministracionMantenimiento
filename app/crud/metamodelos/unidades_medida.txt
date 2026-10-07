# app/crud/metamodelos/unidades_medida.py

from app.models.unidadmedida_models import UnidadMedida, TipoUnidad

ENTIDAD_UNIDADES_MEDIDA = {
    "model": UnidadMedida,
    "pk": "unidad_medida_id",
    "label_singular": "unidad de medida",
    "label_plural": "unidades de medida",
    "genero": "f",
    "bp_name": "unidades_medida_web",
    "es_subentidad": False,
    "template_detalle": "crud/detalle_entidad.html",
    "template_listado": "crud/listado_entidad.html",
    "fields": {
        "nombre_unidad": {"tipo": "text", "label": "Nombre", "required": True},
        "abreviatura": {"tipo": "text", "label": "Abreviatura", "required": True},
        "tipo_unidad_id": {
            "label": "Tipo",
            "tipo": "fk",
            "fk_model": TipoUnidad,
            "fk_label": "nombre_tipo",
            "relacion": "tipo_unidad",
            "required": False,
        },
    },
    "listado": {"columns": ["nombre_unidad", "abreviatura", "tipo_unidad_id"]},
    "filtros": {"campos": ["nombre_unidad", "abreviatura", "tipo_unidad_id"]},
    "auditoria": {
        "enabled": True,
        "ignore_fields": ["uuid", "creado_en", "actualizado_en"],
    },
    "mostrar_en_sidebar": True,
    "orden": 90,
}
