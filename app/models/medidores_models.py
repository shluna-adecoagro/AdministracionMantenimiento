# app/models/medidores_models.py

import uuid
from datetime import datetime
from app.core.db import db
from app.crud.model_mixin import ModelMixin
from app.crud.audit_mixin import AuditMixin


class Medidor(db.Model, ModelMixin, AuditMixin):
    __tablename__ = "medidores"
    __label_field__ = "nombre_medidor"

    medidor_id = db.Column(db.Integer, primary_key=True, autoincrement=True)
    uuid = db.Column(db.String(36), default=lambda: str(uuid.uuid4()), nullable=False)

    nombre_medidor = db.Column(db.String(100), nullable=False)

    # FK → Unidad de medida
    unidad_medida_id = db.Column(
        db.Integer, db.ForeignKey("unidades_medida.unidad_medida_id"), nullable=False
    )
    unidad_medida = db.relationship("UnidadMedida", lazy="joined")

    # FK → Activo
    activo_id = db.Column(
        db.Integer, db.ForeignKey("activos.activo_id"), nullable=False
    )
    activo = db.relationship("Activo", lazy="joined")

    valor_inicial = db.Column(db.Float, default=0)
    valor_actual = db.Column(db.Float, default=0)

    creado_en = db.Column(db.DateTime, default=datetime.utcnow)
    actualizado_en = db.Column(
        db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow
    )
