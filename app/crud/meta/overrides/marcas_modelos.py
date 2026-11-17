from app.models.marcas_modelos_models import Marca, Modelo

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
}
