# app/models/lecturas_medidor_models.py

import uuid
from datetime import datetime
from app.core.db import db
from app.crud.model_mixin import ModelMixin
from app.crud.audit_mixin import AuditMixin


class LecturaMedidor(db.Model, ModelMixin, AuditMixin):
    __tablename__ = "lecturas_medidor"
    __label_field__ = "fecha_lectura"

    lectura_medidor_id = db.Column(db.Integer, primary_key=True, autoincrement=True)
    uuid = db.Column(db.String(36), default=lambda: str(uuid.uuid4()), nullable=False)

    medidor_id = db.Column(
        db.Integer, db.ForeignKey("medidores.medidor_id"), nullable=False
    )
    medidor = db.relationship("Medidor", lazy="joined")

    fecha_lectura = db.Column(db.DateTime, default=datetime.utcnow, nullable=False)
    valor = db.Column(db.Float, nullable=False)

    origen = db.Column(db.String(50), default="manual")  # manual / iot / importación
    observaciones = db.Column(db.String(500), nullable=True)

    creado_en = db.Column(db.DateTime, default=datetime.utcnow)
    actualizado_en = db.Column(
        db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow
    )
