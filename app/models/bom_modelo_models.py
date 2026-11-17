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

    # FK → Material
    # Sin backref: un material que figura en un BOM no se puede borrar.
    material_id = db.Column(
        db.Integer, db.ForeignKey("materiales.material_id"), nullable=False
    )
    material = db.relationship("Material", lazy="joined")

    # FK → Modelo. Al borrar el modelo se borra su BOM (cascada).
    modelo_id = db.Column(
        db.Integer, db.ForeignKey("modelos.modelo_id"), nullable=False
    )
    modelo = db.relationship(
        "Modelo", lazy="joined", backref=db.backref("bom", cascade="all, delete")
    )

    # Cantidad requerida en el BOM (opcional)
    cantidad = db.Column(db.Float, nullable=True)

    # Equivalencias (cuando el repuesto no es el original del modelo)
    es_equivalencia = db.Column(db.Boolean, default=False, nullable=False,
                                info={"label": "Es equivalencia"})
    nota_equivalencia = db.Column(db.String(300), nullable=True, info={"label": "Nota de equivalencia"})
    origen_equivalencia = db.Column(db.String(100), nullable=True, info={"label": "Origen de equivalencia"})

    creado_en = db.Column(db.DateTime, default=datetime.utcnow)
    actualizado_en = db.Column(
        db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow
    )
