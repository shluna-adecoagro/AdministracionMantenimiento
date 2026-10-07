# app/crud/metamodelos/cuentas.py

from app.models.cuentas_models import Cuenta, EstadoCuenta

ENTIDAD_CUENTAS = {
    "model": Cuenta,
    "pk": "cuenta_id",
    "label_singular": "cuenta",
    "label_plural": "cuentas",
    "genero": "f",
    "bp_name": "cuentas",
    "es_subentidad": False,
    "template_detalle": "crud/detalle_entidad.html",
    "fields": {
        "numero_cuenta": {
            "label": "Número de cuenta",
            "tipo": "text",
            "required": True,
        },
        "nombre_cuenta": {
            "label": "Nombre de cuenta",
            "tipo": "text",
            "required": True,
        },
        "estado_cuenta_id": {
            "label": "Estado",
            "tipo": "fk",
            "fk_model": EstadoCuenta,
            "required": True,
            "es_estado": True,
        },
    },
    "listado": {"columns": ["numero_cuenta", "nombre_cuenta", "estado_cuenta_id"]},
    "filtros": {"campos": ["numero_cuenta", "nombre_cuenta", "estado_cuenta_id"]},
    "auditoria": {"enabled": True, "ignore_fields": ["uuid"]},
    "mostrar_en_sidebar": True,
    "orden": 70,
}
