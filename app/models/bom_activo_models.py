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

    # FK → Insumo. Sin backref: un insumo que figura en un BOM no se puede borrar.
    insumo_id = db.Column(
        db.Integer, db.ForeignKey("insumos.insumo_id"), nullable=False
    )
    insumo = db.relationship("Insumo", lazy="joined", foreign_keys=[insumo_id])

    # Cantidad requerida en el BOM del activo
    cantidad = db.Column(db.Float, nullable=True)

    # Equivalencias específicas del activo
    es_equivalencia = db.Column(db.Boolean, default=False, nullable=False,
                                info={"label": "Es equivalencia"})
    nota_equivalencia = db.Column(db.String(300), nullable=True, info={"label": "Nota de equivalencia"})
    origen_equivalencia = db.Column(db.String(100), nullable=True, info={"label": "Origen de equivalencia"})

    # Reemplazo de insumo original del modelo
    reemplaza_insumo_modelo_id = db.Column(
        db.Integer, db.ForeignKey("insumos.insumo_id"), nullable=True,
        info={"label": "Reemplaza al insumo del modelo"},
    )
    reemplaza_insumo_modelo = db.relationship(
        "Insumo", lazy="joined", foreign_keys=[reemplaza_insumo_modelo_id]
    )

    creado_en = db.Column(db.DateTime, default=datetime.utcnow)
    actualizado_en = db.Column(
        db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow
    )

    def to_dict(self):
        return {
            "bom_activo_id": self.bom_activo_id,
            "uuid": self.uuid,
            "activo_id": self.activo_id,
            "activo": self.activo.descripcion if self.activo else None,
            "insumo_id": self.insumo_id,
            "insumo": self.insumo.descripcion if self.insumo else None,
            "cantidad": self.cantidad,
            "es_equivalencia": self.es_equivalencia,
            "nota_equivalencia": self.nota_equivalencia,
            "origen_equivalencia": self.origen_equivalencia,
            "reemplaza_insumo_modelo_id": self.reemplaza_insumo_modelo_id,
            "reemplaza_insumo_modelo": (
                self.reemplaza_insumo_modelo.descripcion
                if self.reemplaza_insumo_modelo
                else None
            ),
            "creado_en": self.creado_en.isoformat(),
            "actualizado_en": self.actualizado_en.isoformat(),
        }
