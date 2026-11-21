from app.crud.meta.overrides import preventivos
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
        # Subentidad: pestaña "Modelos" de la marca (se borran con ella) y de la
        # categoría de activo (una categoría con modelos no se borra).
        "padre": [
            {"entidad": "marcas", "fk": "marca_id"},
            {"entidad": "categorias_activo", "fk": "categoria_activo_id"},
        ],
        "clave_natural": ["nombre_modelo", "marca_id"],
        # Cambiar la categoría: sus activos y sus planes tienen que acompañarla.
        "al_guardar": preventivos.al_guardar_modelo,
    },
}
