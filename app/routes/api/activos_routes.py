from flask import Blueprint, request, jsonify
from app.models.activos_models import Activo, db
from app.utils.json_validator import validar_activo
from app.utils.auditoria_decorator import auditar_cambios

activos_bp = Blueprint("activos", __name__)

# CREATE
@activos_bp.route("/activos", methods=["POST"])
@auditar_cambios("INSERT", modelo=Activo)
def crear_activo():
    data = request.json
    validar_activo(data)

    activo = Activo(**data)
    db.session.add(activo)
    db.session.commit()

    return jsonify(activo.to_dict()), 201


# UPDATE
@activos_bp.route("/activos/<int:id>", methods=["PUT"])
@auditar_cambios("UPDATE", modelo=Activo)
def actualizar_activo(id):
    activo = Activo.query.get_or_404(id)
    data = request.json
    validar_activo(data)

    for key, value in data.items():
        setattr(activo, key, value)

    db.session.commit()
    return jsonify(activo.to_dict()), 200


# DELETE
@activos_bp.route("/activos/<int:id>", methods=["DELETE"])
@auditar_cambios("DELETE", modelo=Activo)
def eliminar_activo(id):
    activo = Activo.query.get_or_404(id)
    db.session.delete(activo)
    db.session.commit()
    return jsonify({"status": "ok"}), 200


# LIST
@activos_bp.route("/activos", methods=["GET"])
def listar_activos():
    activos = Activo.query.all()
    return jsonify([a.to_dict() for a in activos])
