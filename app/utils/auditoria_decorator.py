from functools import wraps
from flask import request
from app.models.auditoria_models import AuditLog
from app.core.db import db

IGNORAR = {"creado_en", "actualizado_en"}

def normalizar_estado(data):
    """
    Convierte el estado anidado en valores simples:
    - estado_sector_id
    - estado_sector (nombre)
    Elimina el color.
    """
    if not data or "estado_sector" not in data:
        return data

    estado = data["estado_sector"]
    data = dict(data)  # copiar

    # Aplanar
    data["estado_sector_id"] = estado.get("id")
    data["estado_sector"] = estado.get("nombre")

    # Eliminar objeto anidado
    del data["estado_sector"]

    return data


def normalizar_dict(data):
    """
    Normaliza el dict completo antes de auditar:
    - Aplana estado
    - Elimina claves ignoradas
    """
    if not data:
        return data

    data = dict(data)

    # Aplanar estado
    data = normalizar_estado(data)

    # Eliminar claves ignoradas
    for key in list(data.keys()):
        if key in IGNORAR:
            del data[key]

    return data


def calcular_diff(antes, despues):
    if antes is None:
        return {"nuevo_registro": despues}
    if despues is None:
        return {"registro_eliminado": antes}

    diff = {}
    for key in set(antes.keys()).union(despues.keys()):
        if antes.get(key) != despues.get(key):
            diff[key] = {
                "antes": antes.get(key),
                "despues": despues.get(key)
            }
    return diff


def auditar_cambios(tipo_cambio, modelo):
    def decorator(func):
        @wraps(func)
        def wrapper(*args, **kwargs):
            usuario = request.headers.get("X-Usuario", "desconocido")
            pk_name = modelo.__mapper__.primary_key[0].name

            # Estado anterior
            estado_anterior = None
            if tipo_cambio in ["UPDATE", "DELETE"]:
                registro = modelo.query.get(kwargs.get("id"))
                if registro:
                    estado_anterior = normalizar_dict(registro.to_dict())

            # Ejecutar la función original
            resultado = func(*args, **kwargs)

            # Si hubo error, no auditar
            if isinstance(resultado, tuple) and resultado[1] >= 400:
                return resultado

            # Estado actual
            if tipo_cambio == "INSERT":
                registro_actual = modelo.query.order_by(
                    modelo.__table__.c[pk_name].desc()
                ).first()
                estado_actual = normalizar_dict(registro_actual.to_dict()) if registro_actual else None

            elif tipo_cambio == "UPDATE":
                registro_actual = modelo.query.get(kwargs.get("id"))
                estado_actual = normalizar_dict(registro_actual.to_dict()) if registro_actual else None

            elif tipo_cambio == "DELETE":
                estado_actual = None

            # Calcular diff
            diff = calcular_diff(estado_anterior, estado_actual)

            # Obtener ID del registro
            registro_id = (
                estado_actual.get(pk_name)
                if estado_actual else estado_anterior.get(pk_name)
            )

            # Obtener última versión
            ultimo = (
                AuditLog.query
                .filter_by(TablaAfectada=modelo.__tablename__, RegistroID=str(registro_id))
                .order_by(AuditLog.Version.desc())
                .first()
            )
            version = (ultimo.Version + 1) if ultimo else 1

            # Crear log
            log = AuditLog(
                Usuario=usuario,
                TablaAfectada=modelo.__tablename__,
                RegistroID=str(registro_id),
                TipoDeCambio=tipo_cambio,
                EstadoAnterior=estado_anterior,
                EstadoActual=estado_actual,
                Version=version
            )

            log.save()  # calcula hash
            db.session.commit()

            return resultado
        return wrapper
    return decorator
