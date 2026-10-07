# app/crud/metamodelos/insumos.py

from app.models.insumos_models import Insumo, CategoriaInsumo, TipoInsumo, StockInsumo
from app.models.marcas_modelos_models import Marca
from app.models.unidadmedida_models import UnidadMedida
from app.models.sectores_models import Sector
from app.models.ubicaciones_models import Ubicacion

# ============================================================
# INSUMOS (Entidad principal)
# ============================================================
ENTIDAD_INSUMOS = {
    "model": Insumo,
    "pk": "insumo_id",
    "label_singular": "insumo",
    "label_plural": "insumos",
    "genero": "m",
    "bp_name": "insumos",
    "fields": {
        "codigo": {"label": "Código", "tipo": "text", "required": True},
        "descripcion": {"label": "Descripción", "tipo": "text", "required": True},
        "marca_id": {
            "label": "Marca",
            "tipo": "fk",
            "fk_model": Marca,
            "fk_label": "nombre_marca",
            "relacion": "marca",
        },
        "categoria_insumo_id": {
            "label": "Categoría",
            "tipo": "fk",
            "fk_model": CategoriaInsumo,
            "fk_label": "nombre_categoria",
            "relacion": "categoria_insumo",
            "required": True,
        },
        "tipo_insumo_id": {
            "label": "Tipo",
            "tipo": "fk",
            "fk_model": TipoInsumo,
            "fk_label": "nombre_tipo",
            "relacion": "tipo_insumo",
        },
        "presentacion_cantidad": {
            "label": "Cantidad por presentación",
            "tipo": "number",
        },
        "unidad_medida_id": {
            "label": "Unidad de medida",
            "tipo": "fk",
            "fk_model": UnidadMedida,
            "fk_label": "nombre_unidad",
        },
        "cantidad_minima": {"label": "Stock mínimo", "tipo": "number"},
        "observaciones": {"label": "Observaciones", "tipo": "textarea"},
        "foto": {"label": "Foto", "tipo": "file", "subcarpeta": "fotos"},
        "stock_total": {"label": "Stock total", "tipo": "number", "virtual": True},
    },
    "listado": {
        "columns": [
            "codigo",
            "descripcion",
            "marca_id",
            "categoria_insumo_id",
            "tipo_insumo_id",
            "stock_total",
        ]
    },
    "filtros": {
        "campos": [
            "codigo",
            "descripcion",
            "marca_id",
            "categoria_insumo_id",
            "tipo_insumo_id",
        ]
    },
    "auditoria": {
        "enabled": True,
        "ignore_fields": ["uuid", "creado_en", "actualizado_en"],
    },
    "mostrar_en_sidebar": True,
    "orden": 20,
    "subentidades": [
        {
            "entidad": "stock_insumo",
            "label": "Stock por ubicación",
            "label_singular": "stock",
            "label_plural": "stock",
            "fk": "insumo_id",
            "template_listado": "crud/listado_subentidad.html",
            "campos_listado": ["ubicacion_id", "cantidad"],
        },
        {
            "entidad": "bom_modelo",
            "label": "Modelos compatibles",
            "fk": "insumo_id",
            "template_listado": "crud/listado_subentidad.html",
            "campos_listado": ["modelo_id", "es_equivalencia"],
        },
        {
            "entidad": "bom_activo",
            "label": "Activos compatibles",
            "fk": "insumo_id",
            "template_listado": "crud/listado_subentidad.html",
            "campos_listado": ["activo_id", "es_equivalencia"],
        },
    ],
    "tabs_extra": [
        {
            "label": "Compatibilidad final",
            "endpoint": "insumos.compatibilidad_final",
        }
    ],
}

ENTIDAD_STOCK_INSUMO = {
    "model": StockInsumo,
    "pk": "stock_insumo_id",
    "label_singular": "stock",
    "label_plural": "stock",
    "genero": "m",
    "bp_name": "insumos",
    "es_subentidad": True,
    "entidad_padre": "insumos",
    "fk_padre": "insumo_id",
    "template_detalle": "crud/detalle_subentidad.html",
    "template_listado": "crud/listado_subentidad.html",
    "fields": {
        "insumo_id": {
            "label": "Insumo",
            "tipo": "fk",
            "fk_model": Insumo,
            "fk_label": "descripcion",
            "relacion": "insumo",
            "required": True,
        },
        "sector_id": {
            "label": "Sector",
            "tipo": "fk",
            "fk_model": Sector,
            "fk_label": "nombre_sector",
            "relacion": "sector",
            "required": True,
        },
        "ubicacion_id": {
            "label": "Ubicación",
            "tipo": "fk",
            "fk_model": Ubicacion,
            "fk_label": "nombre_ubicacion",
            "relacion": "ubicacion",
            "required": True,
        },
        "cantidad": {"label": "Cantidad", "tipo": "number", "required": True},
    },
    "listado": {"columns": ["ubicacion_id", "cantidad"]},
    "filtros": {"campos": ["ubicacion_id", "cantidad"]},
    "auditoria": {
        "enabled": True,
        "ignore_fields": ["uuid", "creado_en", "actualizado_en"],
    },
    # Subentidad → no mostrar en sidebar
    "mostrar_en_sidebar": False,
}
