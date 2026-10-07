from app.core.db import db
from datetime import datetime
from app.crud.audit_mixin import AuditMixin
from app.crud.model_mixin import ModelMixin
import uuid


class TipoUnidad(db.Model, ModelMixin):
    __tablename__ = "tipos_unidad"

    tipo_unidad_id = db.Column(db.Integer, primary_key=True, autoincrement=True)
    nombre_tipo = db.Column(db.String(100), nullable=False, unique=True)

    def to_dict(self):
        return {
            "tipo_unidad_id": self.tipo_unidad_id,
            "nombre_tipo": self.nombre_tipo,
        }


class UnidadMedida(db.Model, ModelMixin, AuditMixin):
    __tablename__ = "unidades_medida"
    __label_field__ = "nombre_unidad"

    unidad_medida_id = db.Column(db.Integer, primary_key=True)
    nombre_unidad = db.Column(db.String(100), nullable=False)
    abreviatura = db.Column(db.String(20), nullable=False)
    tipo_unidad_id = db.Column(
        db.Integer, db.ForeignKey("tipos_unidad.tipo_unidad_id"), nullable=False
    )
    tipo_unidad = db.relationship("TipoUnidad", backref="unidades_medida")

    uuid = db.Column(db.String(36), default=lambda: str(uuid.uuid4()), nullable=False)
    creado_en = db.Column(db.DateTime, default=datetime.utcnow)
    actualizado_en = db.Column(
        db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow
    )
