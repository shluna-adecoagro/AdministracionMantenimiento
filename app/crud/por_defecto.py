"""
Valor por defecto de una FK obligatoria a un catálogo (ej: el estado «Operativa»
de una ubicación, «Activo» de un proveedor).

Se usa en dos lugares:

  * en el modelo, como `default` de la columna:

        estado_proveedor_id = db.Column(
            db.Integer, db.ForeignKey("estados_proveedor.estado_proveedor_id"),
            nullable=False,
            default=id_por_nombre("estados_proveedor", "estado_proveedor_id",
                                  "nombre_estado_proveedor", "Activo"),
        )

    Así lo completan la API, el CSV y las altas desde el código, y el formulario
    de alta lo preselecciona (ver VistasEntidad._valores_por_defecto).

  * en el override, con `"completar": mantener_si_vacio("estado_proveedor_id")`
    y `"fields": {"estado_proveedor_id": {"required": False}}`: al modificar,
    un valor vacío (PUT de la API sin el campo, CSV sin la columna) mantiene el
    que tenía en lugar de intentar vaciar una columna obligatoria.
"""
from app.core.db import db


def id_por_nombre(tabla: str, columna_id: str, columna_nombre: str, nombre: str):
    """
    Función para `default=`: el ID del valor `nombre` del catálogo o, si se
    renombró o se borró, el del primer valor cargado (None si está vacío).

    SQLAlchemy la llama al insertar con el contexto de ejecución: se consulta por
    su conexión porque la sesión está en pleno flush. El formulario de alta la
    llama con None y entonces se usa la sesión.
    """
    def por_defecto(contexto):
        t = db.metadata.tables[tabla]
        consulta = (
            db.select(t.c[columna_id])
            .order_by(t.c[columna_nombre] != nombre, t.c[columna_id])
            .limit(1)
        )
        conexion = db.session if contexto is None else contexto.connection
        return conexion.execute(consulta).scalar()

    por_defecto.__name__ = f"{tabla}_por_defecto"
    por_defecto.__doc__ = f"ID de «{nombre}» en {tabla} (o del primer valor)."
    return por_defecto


def mantener_si_vacio(*campos):
    """`completar` para el override: en una modificación, los campos que llegan
    vacíos conservan el valor que tenía el registro."""
    def completar(datos, registro):
        if registro is not None:
            for campo in campos:
                if datos.get(campo) in (None, ""):
                    datos[campo] = getattr(registro, campo)
        return datos

    return completar
