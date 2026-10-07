# app/crud/metamodelos/activos.py

from app.models.activos_models import (
    Activo,
    CategoriaActivo,
    TipoActivo,
    EstadoActivo,
)
from app.models.marcas_modelos_models import Marca, Modelo
from app.models.ubicaciones_models import Ubicacion
from app.models.medidores_models import Medidor
from app.models.lecturas_medidores_models import LecturaMedidor
from app.models.unidadmedida_models import UnidadMedida
from app.models.sectores_models import Sector
from app.models.recursos_models import Empleado

ENTIDAD_ACTIVOS = {
    "model": Activo,
    "pk": "activo_id",
    "label_singular": "activo",
    "label_plural": "activos",
    "genero": "m",
    "bp_name": "activos",
    "es_subentidad": False,
    "template_detalle": "crud/detalle_entidad.html",
    "fields": {
        "tipo_activo_id": {
            "label": "Tipo de activo",
            "tipo": "fk",
            "fk_model": TipoActivo,
            "fk_label": "nombre_tipo",
            "relacion": "tipo_activo",
            "required": True,
        },
        "categoria_activo_id": {
            "label": "Categoría",
            "tipo": "fk",
            "fk_model": CategoriaActivo,
            "fk_label": "nombre_categoria",
            "relacion": "categoria_activo",
            "required": True,
        },
        "marca_id": {
            "label": "Marca",
            "tipo": "fk",
            "fk_model": Marca,
            "fk_label": "nombre_marca",
            "relacion": "marca",
            "required": False,
        },
        "modelo_id": {
            "label": "Modelo",
            "tipo": "fk",
            "fk_model": Modelo,
            "fk_label": "nombre_modelo",
            "relacion": "modelo",
            "required": False,
        },
        "patente": {"label": "Patente", "tipo": "text"},
        "descripcion": {"label": "Descripción", "tipo": "text", "required": True},
        "nro_serie_chasis": {"label": "Nro. serie chasis", "tipo": "text"},
        "nro_motor": {"label": "Nro. motor", "tipo": "text"},
        "año": {"label": "Año", "tipo": "number"},
        "observacion": {"label": "Observación", "tipo": "textarea"},
        "codigo_brescia": {"label": "Código Brescia", "tipo": "text"},
        "sector_id": {
            "label": "Sector asignado",
            "tipo": "fk",
            "fk_model": Sector,
            "fk_label": "nombre_sector",
            "relacion": "sector",
            "required": False,
        },
        "usuario_asignado": {
            "label": "Usuario asignado",
            "tipo": "datalist",
            "fk_model": Empleado,
            "fk_label": "nombre_completo",
            "required": False,
        },
        "ubicacion_id": {
            "label": "Ubicación",
            "tipo": "fk",
            "fk_model": Ubicacion,
            "fk_label": "nombre_ubicacion",
            "relacion": "ubicacion",
            "required": False,
        },
        "estado_activo_id": {
            "label": "Estado",
            "tipo": "fk",
            "fk_model": EstadoActivo,
            "fk_label": "nombre_estado",
            "relacion": "estado_activo",
            "es_estado": True,
            "required": True,
        },
        "foto_path": {
            "label": "Foto",
            "tipo": "file",
            "required": False,
            "subcarpeta": "fotos",  # opcional
        },
    },
    "listado": {
        "columns": [
            "patente",
            "descripcion",
            "tipo_activo_id",
            "categoria_activo_id",
            "nro_serie_chasis",
            "marca_id",
            "modelo_id",
            "sector_id",
            "estado_activo_id",
        ]
    },
    "filtros": {
        "campos": [
            "patente",
            "descripcion",
            "tipo_activo_id",
            "categoria_activo_id",
            "marca_id",
            "modelo_id",
            "nro_serie_chasis",
            "sector_id",
            "estado_activo_id",
        ]
    },
    "auditoria": {
        "enabled": True,
        "ignore_fields": ["uuid", "creado_en", "actualizado_en"],
    },
    "mostrar_en_sidebar": True,
    "orden": 10,
    "subentidades": [
        {
            "entidad": "medidores",
            "label": "Medidores",
            "label_singular": "medidor",
            "label_plural": "medidores",
            "fk": "activo_id",
            "template_listado": "crud/listado_subentidad.html",
            "campos_listado": ["nombre_medidor", "nombre_unidad", "valor_actual"],
        },
        {
            "entidad": "bom_activo",
            "label": "BOM del activo",
            "fk": "activo_id",
            "template_listado": "crud/listado_subentidad.html",
            "campos_listado": ["insumo_id", "cantidad", "es_equivalencia"],
        },
    ],
    "tabs_extra": [
        {
            "id": "bom_modelo",
            "label": "BOM del modelo",
            "endpoint": "activos.bom_modelo_por_activo",
        },
        {
            "id": "bom_final",
            "label": "BOM final",
            "endpoint": "activos.bom_final",
        },
    ],
}

# ============================
# SUBENTIDAD: MEDIDORES
# ============================

ENTIDAD_MEDIDORES = {
    "model": Medidor,
    "pk": "medidor_id",
    "label_singular": "medidor",
    "label_plural": "medidores",
    "genero": "m",
    "bp_name": "activos",
    "es_subentidad": True,
    "entidad_padre": "activos",
    "fk_padre": "activo_id",
    "template_detalle": "crud/detalle_entidad.html",
    "template_listado": "crud/listado_entidad.html",
    "fields": {
        "nombre_medidor": {"tipo": "text", "label": "Nombre", "required": True},
        "unidad_medida_id": {
            "tipo": "fk",
            "label": "Unidad de medida",
            "fk_model": UnidadMedida,
        },
        "valor_inicial": {"tipo": "number", "label": "Valor inicial"},
        "valor_actual": {"tipo": "number", "label": "Valor actual"},
    },
    "listado": {"columns": ["nombre_medidor", "unidad_medida_id", "valor_actual"]},
    "filtros": {"campos": ["nombre_medidor"]},
    "subentidades": [
        {
            "entidad": "lecturas_medidor",
            "label": "Lecturas",
            "label_singular": "lectura",
            "label_plural": "lecturas",
            "fk": "medidor_id",
            "pk": "lectura_medidor_id",
            "template_listado": "crud/listado_subentidad.html",
            "campos_listado": ["fecha_lectura", "valor", "origen"],
        }
    ],
}

ENTIDAD_LECTURAS_MEDIDOR = {
    "model": LecturaMedidor,
    "pk": "lectura_medidor_id",
    "label_singular": "lectura",
    "label_plural": "lecturas",
    "genero": "f",
    "bp_name": "lecturas",
    "es_subentidad": True,
    "entidad_padre": "medidores",
    "fk_padre": "medidor_id",
    "template_detalle": "crud/detalle_subentidad.html",
    "template_listado": "crud/listado_subentidad.html",
    "fields": {
        "medidor_id": {
            "label": "Medidor",
            "tipo": "fk",
            "fk_model": Medidor,
            "fk_label": "nombre_medidor",
            "relacion": "medidor",
            "required": True,
            "oculto": True,  # opcional, para no mostrarlo en el formulario
        },
        "fecha_lectura": {"tipo": "date", "label": "Fecha", "required": True},
        "valor": {"tipo": "number", "label": "Valor", "required": True},
        "origen": {
            "tipo": "select",
            "label": "Origen",
            "options": [
                {"value": "manual", "label": "Manual"},
                {"value": "iot", "label": "IoT"},
                {"value": "importacion", "label": "Importación"},
            ],
        },
        "observaciones": {"tipo": "textarea", "label": "Observaciones"},
    },
    "listado": {"columns": ["fecha_lectura", "valor", "origen"]},
    "filtros": {"campos": ["fecha_lectura", "valor", "origen"]},
}
