"""
Catálogos: listas de valores que usan los datos maestros (estados, tipos,
categorías, unidades, motivos). Van en la sección «Catálogos» del menú.

Los valores iniciales se cargan con app/utils/seed.py (salvo los tipos y
categorías de activo, que los carga el usuario con su cuenta); desde acá se
pueden agregar, renombrar o cambiar de color. Un valor en uso no se puede borrar.
"""
from app.models.activos_models import CategoriaActivo, EstadoActivo, TipoActivo
from app.models.cuentas_models import EstadoCuenta
from app.models.motivos_models import MotivoOperacion
from app.models.recursos_models import EstadoContacto, EstadoProveedor, EstadoRecurso
from app.models.sectores_models import EstadoSector
from app.models.ubicaciones_models import EstadoUbicacion
from app.models.unidadmedida_models import TipoUnidad, UnidadMedida

# Tipos de medidor que se sugieren al cargar una unidad (además de los ya usados).
TIPOS_MEDIDOR = ("Horómetro", "Odómetro", "Caudalímetro", "Contador de arranques")


def _estado(model, nombre_campo, de, orden):
    return {
        "model": model,
        "label_singular": f"estado de {de}",
        "label_plural": f"estados de {de}",
        "genero": "m",
        "sidebar": True,
        "grupo": "catalogos",
        "orden": orden,
        "clave_natural": [nombre_campo],
    }


OVERRIDES = {
    # --- Activos ----------------------------------------------------------
    "estados_activo": _estado(EstadoActivo, "nombre_estado", "activo", 110),
    "tipos_activo": {
        "model": TipoActivo,
        "label_singular": "tipo de activo",
        "label_plural": "tipos de activo",
        "genero": "m",
        "sidebar": True,
        "grupo": "catalogos",
        "orden": 120,
        # Cada tipo se imputa a una cuenta (obligatoria). También aparece como pestaña de la cuenta («qué tipos se imputan acá»).
        "padre": {"entidad": "cuentas", "fk": "cuenta_id"},
        "clave_natural": ["nombre_tipo"],
    },
    "categorias_activo": {
        "model": CategoriaActivo,
        "label_singular": "categoría de activo",
        "label_plural": "categorías de activo",
        "genero": "f",
        # Pestaña del tipo de activo (ej: Maquinaria → Tractor, Pala cargadora...).
        "padre": {"entidad": "tipos_activo", "fk": "tipo_activo_id"},
        "clave_natural": ["nombre_categoria"],
    },
    # --- Materiales (las categorías y tipos están en materiales.py) -------
    "tipos_unidad": {
        "model": TipoUnidad,
        "label_singular": "tipo de unidad",
        "label_plural": "tipos de unidad",
        "genero": "m",
        "sidebar": True,
        "grupo": "catalogos",
        "orden": 150,
        "clave_natural": ["nombre_tipo"],
    },
    "unidades_medida": {
        "model": UnidadMedida,
        "label_singular": "unidad de medida",
        "label_plural": "unidades de medida",
        "genero": "f",
        "sidebar": True,
        "grupo": "catalogos",
        "orden": 140,
        # También aparece como pestaña del tipo de unidad (ej: Tiempo → horas, días).
        "padre": {"entidad": "tipos_unidad", "fk": "tipo_unidad_id"},
        "fields": {
            # Texto libre, con sugerencias: los tipos habituales y los ya cargados.
            "tipo_medidor": {
                "tipo": "datalist", "fk_model": UnidadMedida, "fk_label": "tipo_medidor",
                "options": [{"value": t, "label": t} for t in TIPOS_MEDIDOR],
            },
        },
        "clave_natural": ["nombre_unidad"],
    },
    # --- Otros -------------------------------------------------------------
    "estados_sector": _estado(EstadoSector, "nombre_estado_sector", "sector", 160),
    "estados_ubicacion": _estado(EstadoUbicacion, "nombre_estado_ubicacion", "ubicación", 165),
    "estados_cuenta": _estado(EstadoCuenta, "nombre_estado_cuenta", "cuenta", 170),
    "estados_recurso": _estado(EstadoRecurso, "nombre_estado_recurso", "recurso", 180),
    "estados_proveedor": _estado(EstadoProveedor, "nombre_estado_proveedor", "proveedor", 182),
    "estados_contacto": _estado(EstadoContacto, "nombre_estado_contacto", "contacto", 184),
    "motivos_operacion": {
        "model": MotivoOperacion,
        "label_singular": "motivo de operación",
        "label_plural": "motivos de operación",
        "genero": "m",
        "sidebar": True,
        "grupo": "catalogos",
        "orden": 190,
        "fields": {
            "tipo_operacion": {
                "tipo": "select",
                "options": [
                    {"value": "INSERT", "label": "Alta"},
                    {"value": "UPDATE", "label": "Modificación"},
                    {"value": "DELETE", "label": "Baja"},
                    # Para anular o cancelar una línea de pedido (no es un motivo de auditoría).
                    {"value": "ANULACION", "label": "Anulación"},
                ],
            },
        },
        "clave_natural": ["nombre_motivo", "tipo_operacion"],
    },
}
