from flask import Blueprint, request, jsonify
from jsonschema import validate, ValidationError
from sqlalchemy.exc import SQLAlchemyError
from datetime import datetime

from app.models.auditoria_models import AuditLog
from app.core.db import db
from app.schemas import auditoria_schema

audit_bp = Blueprint("audit", __name__)


# ============================================================
# Normalización (igual que en el decorador)
# ============================================================

def normalizar_estado(data):
    if not data or "estado_sector" not in data:
        return data

    estado = data["estado_sector"]
    data = dict(data)

    data["estado_sector_id"] = estado.get("id")
    data["estado_sector"] = estado.get("nombre")

    del data["estado_sector"]
    return data


def normalizar_dict(data):
    if not data:
        return data

    data = dict(data)
    data = normalizar_estado(data)

    # eliminar claves que no deben auditarse
    for key in ["creado_en", "actualizado_en"]:
        data.pop(key, None)

    return data


# ============================================================
# CREAR LOG MANUAL
# ============================================================

@audit_bp.route("/log", methods=["POST"])
def create_audit_log():
    try:
        data = request.get_json()

        # Validación con JSON Schema
        try:
            validate(instance=data, schema=auditoria_schema)
        except ValidationError as e:
            return jsonify({
                "status": "error",
                "message": "JSON inválido según schema",
                "details": e.message
            }), 400

        # Normalizar estados
        estado_anterior = normalizar_dict(data.get("estado_anterior"))
        estado_actual = normalizar_dict(data.get("estado_actual"))

        # Manejo de versión automática
        last_log = AuditLog.query.filter_by(
            TablaAfectada=data["tabla"],
            RegistroID=data["registro_id"]
        ).order_by(AuditLog.Version.desc()).first()

        version = 1 if last_log is None else last_log.Version + 1

        log = AuditLog(
            Usuario=data["usuario"],
            TablaAfectada=data["tabla"],
            RegistroID=data["registro_id"],
            TipoDeCambio=data["tipo"],
            Version=version,
            EstadoAnterior=estado_anterior,
            EstadoActual=estado_actual,
            Fecha=datetime.utcnow()
        )

        # IMPORTANTE: calcular hash
        log.save()
        db.session.commit()

        return jsonify({
            "status": "success",
            "message": "Registro de auditoría creado correctamente",
            "log_id": log.LogID,
            "version": log.Version,
            "hash": log.HashRegistro
        }), 201

    except SQLAlchemyError as e:
        db.session.rollback()
        return jsonify({
            "status": "error",
            "message": "Error al guardar en la base de datos",
            "details": str(e)
        }), 500

    except Exception as e:
        return jsonify({
            "status": "error",
            "message": "Error inesperado",
            "details": str(e)
        }), 500


# ============================================================
# CONSULTAR AUDITORÍA POR TABLA + ID
# ============================================================

@audit_bp.route("/<tabla>/<registro_id>", methods=["GET"])
def obtener_auditoria(tabla, registro_id):
    logs = (
        AuditLog.query
        .filter_by(TablaAfectada=tabla, RegistroID=str(registro_id))
        .order_by(AuditLog.Version.desc())
        .all()
    )

    return jsonify([log.to_dict() for log in logs]), 200
