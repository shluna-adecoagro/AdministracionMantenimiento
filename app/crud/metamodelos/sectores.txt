# app/crud/metamodelos/sectores.py

from app.models.sectores_models import Sector, EstadoSector
from app.models.ubicaciones_models import Ubicacion

ENTIDAD_SECTORES = {
    "model": Sector,
    "pk": "sector_id",
    "label_singular": "sector",
    "label_plural": "sectores",
    "genero": "m",
    "bp_name": "sectores_web",
    "es_subentidad": False,
    "template_detalle": "crud/detalle_entidad.html",
    "fields": {
        "nombre_sector": {
            "label": "Nombre del Sector",
            "tipo": "text",
            "required": True,
        },
        "centro_costo": {
            "label": "Centro de Costo",
            "tipo": "text",
            "required": True,
        },
        "estado_sector_id": {
            "label": "Estado",
            "tipo": "fk",
            "fk_model": EstadoSector,
            "fk_label": "nombre_estado_sector",
            "relacion": "estado",
            "required": True,
            "es_estado": True,
        },
    },
    "listado": {"columns": ["nombre_sector", "centro_costo", "estado_sector_id"]},
    "filtros": {"campos": ["nombre_sector", "centro_costo", "estado_sector_id"]},
    "auditoria": {
        "enabled": True,
        "ignore_fields": ["uuid", "creado_en", "actualizado_en"],
    },
    "mostrar_en_sidebar": True,
    "orden": 60,
    # ⭐ SUBENTIDAD UBICACIONES
    "subentidades": [
        {
            "entidad": "ubicaciones",
            "label": "Ubicaciones",
            "label_singular": "ubicación",
            "label_plural": "ubicaciones",
            "fk": "sector_id",
            "template_listado": "crud/listado_subentidad.html",
            "campos_listado": ["nombre_ubicacion"],
        }
    ],
}

ENTIDAD_UBICACIONES = {
    "model": Ubicacion,
    "pk": "ubicacion_id",
    "label_singular": "ubicación",
    "label_plural": "ubicaciones",
    "genero": "f",
    "bp_name": "sectores_web",
    # ⭐ MARCAR COMO SUBENTIDAD
    "es_subentidad": True,
    "entidad_padre": "sectores",
    "fk_padre": "sector_id",
    "template_detalle": "crud/detalle_subentidad.html",
    "template_listado": "crud/listado_subentidad.html",
    "fields": {
        "sector_id": {
            "label": "Sector",
            "tipo": "fk",
            "fk_model": Sector,
            "fk_label": "nombre_sector",
            "relacion": "sector",
            "required": False,
        },
        "nombre_ubicacion": {
            "label": "Nombre de la ubicación",
            "tipo": "text",
            "required": True,
        },
    },
    "listado": {"columns": ["nombre_ubicacion", "sector_id"]},
    "filtros": {"campos": ["nombre_ubicacion", "sector_id"]},
    "auditoria": {
        "enabled": True,
        "ignore_fields": ["uuid", "creado_en", "actualizado_en"],
    },
    "mostrar_en_sidebar": False,
}
