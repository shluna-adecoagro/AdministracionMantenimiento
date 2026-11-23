# app/audit/registrar.py

from app.models.auditoria_models import AuditLog
from app.core.db import db
from datetime import date, datetime


IGNORAR_CAMPOS_GLOBALES = {
    "creado_en",
    "actualizado_en",
    "created_at",
    "updated_at",
    "fecha_creacion",
    "fecha_modificacion",
}


def clean_dict(data, ignore_fields=None):

    """
    Limpia el dict antes de guardarlo en auditoría:
    - elimina campos datetime (no serializables) y pasa las fechas (date) a texto ISO
    - elimina campos globales que no deben auditarse
    """
    if data is None:
        return None

    limpio = {}

    for k, v in data.items():

        # Ignorar campos globales
        if k in IGNORAR_CAMPOS_GLOBALES:
            continue

        # Ignorar campos específicos del metamodelo
        if ignore_fields and k in ignore_fields:
            continue

        # Ignorar datetime (no serializable)
        if isinstance(v, datetime):
            continue

        # Una fecha sin hora (ej: fecha del pedido) sí se audita, como texto ISO.
        if isinstance(v, date):
            v = v.isoformat()

        limpio[k] = v

    return limpio


def registrar_cambio(
    tabla,
    registro_uuid,
    tipo,
    estado_anterior,
    estado_actual,
    motivo_operacion,
    usuario="sistema",
    registro_id=None,
    ignore_fields=None
):

    """
    Registra un cambio en la tabla de auditoría.
    Ahora usa UUID como identificador estable del registro.
    """

    # Obtener última versión del registro auditado
    ultimo = (
        AuditLog.query
        .filter_by(TablaAfectada=tabla, RegistroUUID=str(registro_uuid))
        .order_by(AuditLog.Version.desc())
        .first()
    )
    version = (ultimo.Version + 1) if ultimo else 1

    log = AuditLog(
        Usuario=usuario,
        TablaAfectada=tabla,

        # Identidad real del registro
        RegistroUUID=str(registro_uuid),

        # Compatibilidad con auditorías viejas
        RegistroID=str(registro_id) if registro_id is not None else None,

        TipoDeCambio=tipo,
        Version=version,
        EstadoAnterior=clean_dict(estado_anterior, ignore_fields),
        EstadoActual=clean_dict(estado_actual, ignore_fields),
        motivo_operacion=motivo_operacion
    )

    log.save()
