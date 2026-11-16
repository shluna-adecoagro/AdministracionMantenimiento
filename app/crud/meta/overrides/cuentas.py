# app/crud/meta/overrides/cuentas.py
from app.models.cuentas_models import Cuenta

OVERRIDES = {
    "cuentas": {
        "model": Cuenta,
        "label_singular": "cuenta",
        "label_plural": "cuentas",
        "genero": "f",
        "sidebar": True,
        "orden": 70,
    },
}
