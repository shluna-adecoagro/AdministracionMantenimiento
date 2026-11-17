from app.models.marcas_modelos_models import Marca, Modelo
from app.models.unidadmedida_models import UnidadMedida

OVERRIDES = {
    "marcas": {
        "model": Marca,
        "label_singular": "marca",
        "label_plural": "marcas",
        "genero": "f",
        "sidebar": True,
        "orden": 80,
        "clave_natural": ["nombre_marca"],
    },
    "modelos": {
        "model": Modelo,
        "label_singular": "modelo",
        "label_plural": "modelos",
        "genero": "m",
        # Subentidad: pestaña "Modelos" de la marca (se borran con ella).
        "padre": {"entidad": "marcas", "fk": "marca_id"},
        "clave_natural": ["nombre_modelo", "marca_id"],
    },
    "unidades_medida": {
        "model": UnidadMedida,
        "label_singular": "unidad de medida",
        "label_plural": "unidades de medida",
        "genero": "f",
        "sidebar": True,
        "orden": 90,
        "clave_natural": ["nombre_unidad"],
    },
}
