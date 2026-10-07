from app.core.db import db
from app.crud.audit_mixin import AuditMixin
from app.crud.model_mixin import ModelMixin
import uuid
from datetime import datetime

class Ubicacion(db.Model, ModelMixin, AuditMixin):
    __tablename__ = "ubicaciones"

    ubicacion_id = db.Column(db.Integer, primary_key=True, autoincrement=True)

    uuid = db.Column(db.String(36), default=lambda: str(uuid.uuid4()), unique=True, nullable=False)

    nombre_ubicacion = db.Column(db.String(100), nullable=False)

    sector_id = db.Column(db.Integer, db.ForeignKey("sectores.sector_id"), nullable=True)
    sector = db.relationship("Sector", backref="ubicaciones")

    creado_en = db.Column(db.DateTime, default=datetime.utcnow)
    actualizado_en = db.Column(db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    def to_dict(self):
        return {
            "ubicacion_id": self.ubicacion_id,
            "uuid": self.uuid,
            "nombre_ubicacion": self.nombre_ubicacion,
            "sector_id": self.sector_id,
            "sector": self.sector.nombre_sector if self.sector else None,
            "creado_en": self.creado_en.isoformat() if self.creado_en else None,
            "actualizado_en": self.actualizado_en.isoformat() if self.actualizado_en else None
        }
