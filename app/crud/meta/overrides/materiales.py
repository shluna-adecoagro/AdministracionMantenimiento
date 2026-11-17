from app.crud.meta.overrides import bom
from app.models.materiales_models import CategoriaMaterial, Material, StockMaterial, TipoMaterial

OVERRIDES = {
    "materiales": {
        "model": Material,
        "label_singular": "material",
        "label_plural": "materiales",
        "genero": "m",
        "sidebar": True,
        "orden": 20,
        "listado": [
            "codigo", "descripcion", "marca_id", "categoria_material_id",
            "tipo_material_id", "stock_total",
        ],
        "clave_natural": ["codigo"],
        "tabs_extra": [
            {"id": "compatibilidad_final", "label": "Compatibilidad final",
             "funcion": bom.compatibilidad_final},
        ],
    },
    "stock_material": {
        "model": StockMaterial,
        "label_singular": "stock",
        "label_plural": "stock por ubicación",
        "genero": "m",
        # Subentidad: pestaña del material. El sector es el de la ubicación.
        "padre": {"entidad": "materiales", "fk": "material_id"},
        "fields": {"fecha_actualizacion": {"solo_lectura": True}},
        "clave_natural": ["material_id", "ubicacion_id"],
    },
    # Catálogos (vienen de SharePoint): categorías y, dentro de cada una, sus tipos.
    "categorias_material": {
        "model": CategoriaMaterial,
        "label_singular": "categoría de material",
        "label_plural": "categorías de material",
        "genero": "f",
        "sidebar": True,
        "orden": 25,
        "clave_natural": ["nombre_categoria"],
    },
    "tipos_material": {
        "model": TipoMaterial,
        "label_singular": "tipo de material",
        "label_plural": "tipos de material",
        "genero": "m",
        "padre": {"entidad": "categorias_material", "fk": "categoria_material_id"},
        "clave_natural": ["nombre_tipo"],
    },
}
