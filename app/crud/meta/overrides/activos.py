from app.crud.meta.overrides import bom, preventivos
from app.models.activos_models import Activo
from app.models.lecturas_medidores_models import LecturaMedidor
from app.models.medidores_models import Medidor
from app.models.recursos_models import Empleado

OVERRIDES = {
    "activos": {
        "model": Activo,
        "label_singular": "activo",
        "label_plural": "activos",
        "genero": "m",
        "sidebar": True,
        "orden": 10,
        "fields": {
            # Texto libre, con los empleados como sugerencias.
            "usuario_asignado": {"tipo": "datalist", "fk_model": Empleado, "fk_label": "nombre_completo"},
        },
        "listado": [
            "numero_activo", "descripcion", "sector_id", "usuario_asignado", "estado_activo_id",
        ],
        "filtros": [
            "numero_activo", "descripcion", "numero_serie", "numero_motor", "usuario_asignado",
            "codigo_carga_gasoil", "tipo_activo_id", "categoria_activo_id", "marca_id", "modelo_id",
            "sector_id", "ubicacion_id", "estado_activo_id",
        ],
        "clave_natural": ["numero_activo"],
        "excluir": ["etiqueta"],  # es número + descripción, que ya se muestran
        # BOM: al crear el activo (o asignarle modelo, si su BOM está vacío) se
        # copia el del modelo; la acción trae los materiales nuevos del modelo.
        "al_guardar": bom.al_guardar_activo,
        "acciones": [bom.ACCION_TRAER_DEL_MODELO],
    },
    "medidores": {
        "model": Medidor,
        "label_singular": "medidor",
        "label_plural": "medidores",
        "genero": "m",
        # Subentidad: pestaña "Medidores" del activo. Un activo con medidores no
        # se puede borrar.
        "padre": {"entidad": "activos", "fk": "activo_id"},
        "fields": {
            # Solo las unidades que dicen qué instrumento las mide (horas → horómetro).
            "unidad_medida_id": {"fk_filtro": preventivos.unidades_de_medidor},
        },
        "listado": ["nombre_medidor", "activo_id", "tipo_medidor", "unidad_medida_id", "valor_actual"],
        "clave_natural": ["nombre_medidor", "activo_id"],
    },
    "lecturas_medidor": {
        "model": LecturaMedidor,
        "label_singular": "lectura",
        "label_plural": "lecturas",
        "genero": "f",
        # Subentidad: pestaña "Lecturas" del medidor. La última lectura define
        # el valor actual del medidor.
        "padre": {"entidad": "medidores", "fk": "medidor_id"},
        "fields": {
            "origen": {
                "tipo": "select",
                "required": True,
                "options": [
                    {"value": "manual", "label": "Manual"},
                    {"value": "iot", "label": "IoT"},
                    {"value": "importacion", "label": "Importación"},
                ],
            },
        },
        "listado": ["medidor_id", "fecha_lectura", "valor", "origen"],
        "clave_natural": ["medidor_id", "fecha_lectura"],
    },
}
