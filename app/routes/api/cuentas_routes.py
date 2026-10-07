from flask import Blueprint, request, jsonify
from app.models.cuentas_models import Cuenta, db
from app.utils.json_validator import validar_cuenta
from app.utils.auditoria_decorator import auditar_cambios
from sqlalchemy.exc import IntegrityError

cuentas_bp = Blueprint("cuentas", __name__)

# CREATE
@cuentas_bp.route("/cuentas", methods=["POST"])
@auditar_cambios("INSERT", modelo=Cuenta)
def crear_cuenta():
    data = request.json
    validar_cuenta(data)

    cuenta = Cuenta(**data)
    db.session.add(cuenta)

    try:
        db.session.commit()
    except IntegrityError:
        db.session.rollback()
        return jsonify({"error": "El nombre de la cuenta ya existe"}), 400

    return jsonify(cuenta.to_dict()), 201


# UPDATE
@cuentas_bp.route("/cuentas/<int:id>", methods=["PUT"])
@auditar_cambios("UPDATE", modelo=Cuenta)
def actualizar_cuenta(id):
    cuenta = Cuenta.query.get_or_404(id)
    data = request.json
    validar_cuenta(data)

    for key, value in data.items():
        setattr(cuenta, key, value)

    try:
        db.session.commit()
    except IntegrityError:
        db.session.rollback()
        return jsonify({"error": "El nombre de la cuenta ya existe"}), 400

    return jsonify(cuenta.to_dict()), 200


# DELETE
@cuentas_bp.route("/cuentas/<int:id>", methods=["DELETE"])
@auditar_cambios("DELETE", modelo=Cuenta)
def eliminar_cuenta(id):
    cuenta = Cuenta.query.get_or_404(id)
    db.session.delete(cuenta)
    db.session.commit()
    return jsonify({"status": "ok"}), 200


# LIST
@cuentas_bp.route("/cuentas", methods=["GET"])
@auditar_cambios("SELECT", modelo=Cuenta)
def listar_cuentas():
    cuentas = Cuenta.query.all()
    return jsonify([c.to_dict() for c in cuentas])