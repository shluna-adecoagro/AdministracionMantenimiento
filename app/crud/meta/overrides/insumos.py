from app.crud.meta.overrides import bom
from app.models.insumos_models import CategoriaInsumo, Insumo, StockInsumo, TipoInsumo

OVERRIDES = {
    "insumos": {
        "model": Insumo,
        "label_singular": "insumo",
        "label_plural": "insumos",
        "genero": "m",
        "sidebar": True,
        "orden": 20,
        "listado": [
            "codigo", "descripcion", "marca_id", "categoria_insumo_id",
            "tipo_insumo_id", "stock_total",
        ],
        "clave_natural": ["codigo"],
        "tabs_extra": [
            {"id": "compatibilidad_final", "label": "Compatibilidad final",
             "funcion": bom.compatibilidad_final},
        ],
    },
    "stock_insumo": {
        "model": StockInsumo,
        "label_singular": "stock",
        "label_plural": "stock por ubicación",
        "genero": "m",
        # Subentidad: pestaña del insumo. El sector es el de la ubicación.
        "padre": {"entidad": "insumos", "fk": "insumo_id"},
        "fields": {"fecha_actualizacion": {"solo_lectura": True}},
        "clave_natural": ["insumo_id", "ubicacion_id"],
    },
    # Catálogos (vienen de SharePoint): categorías y, dentro de cada una, sus tipos.
    "categorias_insumo": {
        "model": CategoriaInsumo,
        "label_singular": "categoría de insumo",
        "label_plural": "categorías de insumo",
        "genero": "f",
        "sidebar": True,
        "orden": 25,
        "clave_natural": ["nombre_categoria"],
    },
    "tipos_insumo": {
        "model": TipoInsumo,
        "label_singular": "tipo de insumo",
        "label_plural": "tipos de insumo",
        "genero": "m",
        "padre": {"entidad": "categorias_insumo", "fk": "categoria_insumo_id"},
        "clave_natural": ["nombre_tipo"],
    },
}
