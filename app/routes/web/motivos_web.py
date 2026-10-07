from flask import Blueprint, jsonify
from app.models.motivos_models import MotivoOperacion

motivos_web = Blueprint("motivos_web", __name__)

@motivos_web.get("/motivos/<tipo_operacion>")
def obtener_motivos_por_tipo(tipo_operacion):
    """
    Devuelve los motivos precargados según el tipo de operación:
    INSERT, UPDATE o DELETE.
    """
    motivos = (
        MotivoOperacion.query
        .filter_by(tipo_operacion=tipo_operacion.upper())
        .all()
    )

    return jsonify([
        {
            "id": m.motivo_operacion_id,
            "nombre": m.nombre_motivo
        }
        for m in motivos
    ])
