# app/models/bom_modelo_models.py

import uuid
from datetime import datetime
from app.core.db import db
from app.crud.model_mixin import ModelMixin
from app.crud.audit_mixin import AuditMixin


class BOMModelo(db.Model, ModelMixin, AuditMixin):
    __tablename__ = "bom_modelo"
    __label_field__ = None  # no hay un label único, se arma con FK

    bom_modelo_id = db.Column(db.Integer, primary_key=True, autoincrement=True)
    uuid = db.Column(
        db.String(36), default=lambda: str(uuid.uuid4()), unique=True, nullable=False
    )

    # FK → Insumo
    insumo_id = db.Column(
        db.Integer, db.ForeignKey("insumos.insumo_id"), nullable=False
    )
    insumo = db.relationship("Insumo", lazy="joined")

    # FK → Modelo
    modelo_id = db.Column(
        db.Integer, db.ForeignKey("modelos.modelo_id"), nullable=False
    )
    modelo = db.relationship("Modelo", lazy="joined")

    # Cantidad requerida en el BOM (opcional)
    cantidad = db.Column(db.Float, nullable=True)

    # Equivalencias (cuando el repuesto no es el original del modelo)
    es_equivalencia = db.Column(db.Boolean, default=False)
    nota_equivalencia = db.Column(db.String(300), nullable=True)
    origen_equivalencia = db.Column(db.String(100), nullable=True)

    creado_en = db.Column(db.DateTime, default=datetime.utcnow)
    actualizado_en = db.Column(
        db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow
    )

    def to_dict(self):
        return {
            "bom_modelo_id": self.bom_modelo_id,
            "uuid": self.uuid,
            "insumo_id": self.insumo_id,
            "insumo": self.insumo.descripcion if self.insumo else None,
            "modelo_id": self.modelo_id,
            "modelo": self.modelo.nombre_modelo if self.modelo else None,
            "marca": self.modelo.marca.nombre_marca if self.modelo else None,
            "cantidad": self.cantidad,
            "es_equivalencia": self.es_equivalencia,
            "nota_equivalencia": self.nota_equivalencia,
            "origen_equivalencia": self.origen_equivalencia,
            "creado_en": self.creado_en.isoformat(),
            "actualizado_en": self.actualizado_en.isoformat(),
        }
