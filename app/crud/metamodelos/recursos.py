# app/crud/metamodelos/recursos.py

from app.models.recursos_models import (
    Recurso,
    Empleado,
    Proveedor,
    EstadoRecurso,
    ContactoProveedor,
)

from app.models.sectores_models import Sector

ENTIDAD_RECURSOS = {
    "model": Recurso,
    "pk": "recurso_id",
    "label_singular": "recurso",
    "label_plural": "recursos",
    "genero": "m",
    "bp_name": "recursos_web",
    "es_subentidad": False,
    "template_detalle": "crud/detalle_entidad.html",
    "fields": {
        "tipo_recurso": {"tipo": "string", "label": "Tipo"},
        "estado_recurso_id": {
            "tipo": "fk",
            "label": "Estado",
            "fk_model": EstadoRecurso,
            "fk_label": "nombre_estado_recurso",
            "es_estado": True,
        },
    },
    "listado": {"columns": ["tipo_recurso", "estado_recurso_id"]},
    "filtros": {"campos": ["tipo_recurso", "estado_recurso_id"]},
    "auditoria": {"enabled": True},
    "mostrar_en_sidebar": False,
}

ENTIDAD_EMPLEADOS = {
    "model": Empleado,
    "pk": "recurso_id",
    "label_singular": "empleado",
    "label_plural": "empleados",
    "genero": "m",
    "bp_name": "recursos_web",
    "es_subentidad": False,
    "template_detalle": "crud/detalle_entidad.html",
    "fields": {
        "nombre": {"tipo": "text", "label": "Nombre"},
        "apellido": {"tipo": "text", "label": "Apellido"},
        "legajo": {"tipo": "text", "label": "Legajo"},
        "puesto": {"tipo": "text", "label": "Puesto"},
        "sector_id": {
            "tipo": "fk",
            "label": "Sector",
            "fk_model": Sector,
            "fk_label": "nombre_sector",
        },
        "estado_recurso_id": {
            "tipo": "fk",
            "label": "Estado",
            "fk_model": EstadoRecurso,
            "fk_label": "nombre_estado_recurso",
            "es_estado": True,
        },
    },
    "listado": {
        "columns": [
            "nombre",
            "apellido",
            "legajo",
            "puesto",
            "sector_id",
            "estado_recurso_id",
        ]
    },
    "filtros": {
        "campos": [
            "nombre",
            "apellido",
            "legajo",
            "puesto",
            "sector_id",
            "estado_recurso_id",
        ]
    },
    "auditoria": {"enabled": True},
    "mostrar_en_sidebar": True,
    "orden": 30,
}

ENTIDAD_PROVEEDORES = {
    "model": Proveedor,
    "pk": "recurso_id",
    "label_singular": "proveedor",
    "label_plural": "proveedores",
    "genero": "m",
    "bp_name": "recursos_web",
    "es_subentidad": False,
    "template_detalle": "crud/detalle_entidad.html",
    "fields": {
        "razon_social": {"tipo": "text", "label": "Razón social"},
        "cuit": {"tipo": "text", "label": "CUIT"},
        "direccion": {"tipo": "text", "label": "Dirección"},
        "estado_recurso_id": {
            "tipo": "fk",
            "label": "Estado",
            "fk_model": EstadoRecurso,
            "fk_label": "nombre_estado_recurso",
            "es_estado": True,
        },
    },
    "listado": {"columns": ["razon_social", "cuit", "direccion", "estado_recurso_id"]},
    "filtros": {"campos": ["razon_social", "cuit", "direccion", "estado_recurso_id"]},
    "auditoria": {"enabled": True},
    "mostrar_en_sidebar": True,
    "orden": 40,
    # SUBENTIDADES AUTOMÁTICAS
    "subentidades": [
        {
            "entidad": "contactos_proveedor",
            "label": "Contactos",
            "fk": "proveedor_id",
            "template_listado": "crud/listado_subentidad.html",
            "campos_listado": ["nombre_contacto"],
        }
    ],
}

ENTIDAD_CONTACTOS_PROVEEDOR = {
    "model": ContactoProveedor,
    "pk": "contacto_id",
    "label_singular": "contacto de proveedor",
    "label_plural": "contactos de proveedor",
    "genero": "m",
    "bp_name": "recursos_web",
    "es_subentidad": True,
    "entidad_padre": "proveedores",
    "fk_padre": "proveedor_id",
    "template_detalle": "crud/detalle_subentidad.html",
    "template_listado": "crud/listado_subentidad.html",
    "fields": {
        "proveedor_id": {
            "tipo": "fk",
            "label": "Proveedor",
            "fk_model": Proveedor,
            "fk_label": "razon_social",
        },
        "nombre_contacto": {"tipo": "text", "label": "Nombre"},
        "email": {"tipo": "text", "label": "Email"},
        "telefono": {"tipo": "text", "label": "Teléfono"},
        "tipo_contacto": {"tipo": "text", "label": "Tipo de contacto"},
    },
    "listado": {
        "columns": [
            "nombre_contacto",
            "email",
            "telefono",
            "tipo_contacto",
            "proveedor_id",
        ]
    },
    "filtros": {
        "campos": [
            "nombre_contacto",
            "email",
            "telefono",
            "tipo_contacto",
            "proveedor_id",
        ]
    },
    "auditoria": {"enabled": False},  # NO historial en subentidades
    "mostrar_en_sidebar": False,
}
