# Recurso es la base común (herencia) de empleados y proveedores: no tiene
# pantallas propias, se gestiona cada tipo por separado.
from app.crud.por_defecto import mantener_si_vacio
from app.models.recursos_models import ContactoProveedor, Empleado, Proveedor

OVERRIDES = {
    "empleados": {
        "model": Empleado,
        "label_singular": "empleado",
        "label_plural": "empleados",
        "genero": "m",
        "sidebar": True,
        "orden": 30,
        "listado": ["apellido", "nombre", "legajo", "puesto", "sector_id", "estado_recurso_id"],
        "clave_natural": ["apellido", "nombre"],
    },
    "proveedores": {
        "model": Proveedor,
        "label_singular": "proveedor",
        "label_plural": "proveedores",
        "genero": "m",
        "sidebar": True,
        "orden": 40,
        "clave_natural": ["razon_social"],
        # Estado obligatorio en la base, pero no hace falta enviarlo: en el alta
        # toma «Activo» (preseleccionado en el formulario) y al modificar se
        # mantiene el que tenía. Ver app/crud/por_defecto.py.
        "fields": {"estado_proveedor_id": {"required": False}},
        "completar": mantener_si_vacio("estado_proveedor_id"),
    },
    "contactos_proveedor": {
        "model": ContactoProveedor,
        "label_singular": "contacto",
        "label_plural": "contactos",
        "genero": "m",
        # Subentidad: pestaña "Contactos" del proveedor (se borran con él).
        "padre": {"entidad": "proveedores", "fk": "proveedor_id"},
        "clave_natural": ["nombre_contacto", "proveedor_id"],
        # Igual que el proveedor, con «Disponible» por defecto.
        "fields": {"estado_contacto_id": {"required": False}},
        "completar": mantener_si_vacio("estado_contacto_id"),
    },
}
