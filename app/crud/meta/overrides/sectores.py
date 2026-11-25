# app/crud/meta/overrides/sectores.py
from app.models.sectores_models import Sector
from app.crud.por_defecto import mantener_si_vacio
from app.models.ubicaciones_models import Ubicacion


OVERRIDES = {
    "sectores": {
        "model": Sector,
        "label_singular": "sector",
        "label_plural": "sectores",
        "genero": "m",
        "sidebar": True,
        "orden": 60,
        "clave_natural": ["nombre_sector"],
    },
    "ubicaciones": {
        "model": Ubicacion,
        "label_singular": "ubicación",
        "label_plural": "ubicaciones",
        "genero": "f",
        # Subentidad: se gestiona desde la pestaña "Ubicaciones" del sector.
        "padre": {"entidad": "sectores", "fk": "sector_id"},
        # Una ubicación se identifica por su nombre dentro del sector.
        "clave_natural": ["nombre_ubicacion", "sector_id"],
        "fields": {
            # Obligatorio en la base, pero no hace falta enviarlo: en el alta toma
            # el valor por defecto del modelo («Operativa», preseleccionado en el
            # formulario) y al modificar se mantiene el que tenía.
            "estado_ubicacion_id": {"required": False},
        },
        "completar": mantener_si_vacio("estado_ubicacion_id"),
    },
}
