# app/models/bom_activo_models.py

import uuid
from datetime import datetime
from app.core.db import db
from app.crud.model_mixin import ModelMixin
from app.crud.audit_mixin import AuditMixin


class BOMActivo(db.Model, ModelMixin, AuditMixin):
    __tablename__ = "bom_activo"
    __label_field__ = None  # se arma con FK

    bom_activo_id = db.Column(db.Integer, primary_key=True, autoincrement=True)
    uuid = db.Column(
        db.String(36), default=lambda: str(uuid.uuid4()), unique=True, nullable=False
    )

    # FK → Activo
    # Al borrar el activo se borra su BOM (cascada).
    activo_id = db.Column(
        db.Integer, db.ForeignKey("activos.activo_id"), nullable=False
    )
    activo = db.relationship(
        "Activo", lazy="joined", backref=db.backref("bom", cascade="all, delete")
    )

    # FK → Material. Sin backref: un material que figura en un BOM no se puede borrar.
    material_id = db.Column(
        db.Integer, db.ForeignKey("materiales.material_id"), nullable=False
    )
    material = db.relationship("Material", lazy="joined", foreign_keys=[material_id])

    # Cantidad requerida en el BOM del activo
    cantidad = db.Column(db.Float, nullable=True)

    # Equivalencias específicas del activo
    es_equivalencia = db.Column(db.Boolean, default=False, nullable=False,
                                info={"label": "Es equivalencia"})
    nota_equivalencia = db.Column(db.String(300), nullable=True, info={"label": "Nota de equivalencia"})
    origen_equivalencia = db.Column(db.String(100), nullable=True, info={"label": "Origen de equivalencia"})

    # Reemplazo de material original del modelo
    reemplaza_material_modelo_id = db.Column(
        db.Integer, db.ForeignKey("materiales.material_id"), nullable=True,
        info={"label": "Reemplaza al material del modelo"},
    )
    reemplaza_material_modelo = db.relationship(
        "Material", lazy="joined", foreign_keys=[reemplaza_material_modelo_id]
    )

    creado_en = db.Column(db.DateTime, default=datetime.utcnow)
    actualizado_en = db.Column(
        db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow
    )
