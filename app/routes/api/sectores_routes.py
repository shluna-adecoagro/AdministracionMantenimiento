from flask import Blueprint, request, jsonify
from app.models.sectores_models import Sector, EstadoSector
from app.core.db import db
from app.utils.json_validator import validar_sector
from app.utils.auditoria_decorator import auditar_cambios
from sqlalchemy.exc import IntegrityError

sectores_bp = Blueprint("sectores", __name__)

# ============================================================
# CREATE
# ============================================================

@sectores_bp.route("/", methods=["POST"])
@auditar_cambios("INSERT", modelo=Sector)
def crear_sector():
    data = request.json
    validar_sector(data)

    # Validar FK
    estado_id = data.get("estado_sector_id")
    estado = EstadoSector.query.get(estado_id)
    if not estado:
        return jsonify({"error": "Estado inválido"}), 400

    sector = Sector(
        nombre_sector=data["nombre_sector"],
        centro_costo=data["centro_costo"],
        estado_sector_id=estado_id
    )

    db.session.add(sector)

    try:
        db.session.commit()
    except IntegrityError as e:
        db.session.rollback()
        if "UNIQUE" in str(e.orig):
            return jsonify({"error": "El nombre del sector ya existe"}), 400
        return jsonify({"error": "Error de integridad"}), 400

    return jsonify(sector.to_dict()), 201


# ============================================================
# UPDATE
# ============================================================

@sectores_bp.route("/<int:id>", methods=["PUT"])
@auditar_cambios("UPDATE", modelo=Sector)
def actualizar_sector(id):
    sector = Sector.query.get_or_404(id)
    data = request.json
    validar_sector(data)

    # Validar FK
    estado_id = data.get("estado_sector_id")
    estado = EstadoSector.query.get(estado_id)
    if not estado:
        return jsonify({"error": "Estado inválido"}), 400

    sector.nombre_sector = data["nombre_sector"]
    sector.centro_costo = data["centro_costo"]
    sector.estado_sector_id = estado_id

    try:
        db.session.commit()
    except IntegrityError as e:
        db.session.rollback()
        if "UNIQUE" in str(e.orig):
            return jsonify({"error": "El nombre del sector ya existe"}), 400
        return jsonify({"error": "Error de integridad"}), 400

    return jsonify(sector.to_dict()), 200


# ============================================================
# DELETE
# ============================================================

@sectores_bp.route("/<int:id>", methods=["DELETE"])
@auditar_cambios("DELETE", modelo=Sector)
def eliminar_sector(id):
    sector = Sector.query.get_or_404(id)
    db.session.delete(sector)
    db.session.commit()
    return jsonify({"status": "ok"}), 200


# ============================================================
# LIST
# ============================================================

@sectores_bp.route("/", methods=["GET"])
def listar_sectores():
    sectores = Sector.query.all()
    return jsonify([s.to_dict() for s in sectores])
