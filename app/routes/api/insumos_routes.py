from flask import Blueprint, request, jsonify
from app.models.insumos_models import Insumo, db
from app.utils.json_validator import validar_insumo
from app.utils.auditoria_decorator import auditar_cambios

insumos_bp = Blueprint("insumos", __name__)

# CREATE
@insumos_bp.route("/insumos", methods=["POST"])
@auditar_cambios("INSERT", modelo=Insumo)
def crear_insumo():
    data = request.json
    validar_insumo(data)

    insumo = Insumo(**data)
    db.session.add(insumo)
    db.session.commit()

    return jsonify(insumo.to_dict()), 201


# UPDATE
@insumos_bp.route("/insumos/<int:id>", methods=["PUT"])
@auditar_cambios("UPDATE", modelo=Insumo)
def actualizar_insumo(id):
    insumo = Insumo.query.get_or_404(id)
    data = request.json
    validar_insumo(data)

    for key, value in data.items():
        setattr(insumo, key, value)

    db.session.commit()
    return jsonify(insumo.to_dict()), 200


# DELETE
@insumos_bp.route("/insumos/<int:id>", methods=["DELETE"])
@auditar_cambios("DELETE", modelo=Insumo)
def eliminar_insumo(id):
    insumo = Insumo.query.get_or_404(id)
    db.session.delete(insumo)
    db.session.commit()
    return jsonify({"status": "ok"}), 200


# LIST
@insumos_bp.route("/insumos", methods=["GET"])
@auditar_cambios("SELECT", modelo=Insumo)
def listar_insumos():
    insumos = Insumo.query.all()
    return jsonify([i.to_dict() for i in insumos])
