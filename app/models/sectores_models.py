from app.core.db import db
from datetime import datetime
from app.crud.audit_mixin import AuditMixin
from app.crud.model_mixin import ModelMixin
import uuid

class EstadoSector(ModelMixin, db.Model):
    __tablename__ = "estados_sector"
    __label_field__ = "nombre_estado_sector"

    estado_sector_id = db.Column(db.Integer, primary_key=True, autoincrement=True)
    uuid = db.Column(db.String(36), default=lambda: str(uuid.uuid4()), unique=True, nullable=False)

    nombre_estado_sector = db.Column(db.String(50), nullable=False, info={"label": "Nombre"})
    color_badge = db.Column(db.String(20), nullable=False)


class Sector(ModelMixin, AuditMixin, db.Model):
    __tablename__ = "sectores"
    __label_field__ = "nombre_sector"

    sector_id = db.Column(db.Integer, autoincrement=True, primary_key=True)
    uuid = db.Column(db.String(36), default=lambda: str(uuid.uuid4()), unique=True, nullable=False)

    nombre_sector = db.Column(db.String(150), nullable=False, unique=True,
                            info={"label": "Nombre del Sector"})
    centro_costo = db.Column(db.String(100), nullable=False,
                            info={"label": "Centro de Costo"})
    estado_sector_id = db.Column(
        db.Integer,
        db.ForeignKey("estados_sector.estado_sector_id"),
        nullable=False,
        info={"label": "Estado"},
    )
    
    estado = db.relationship("EstadoSector")

    creado_en = db.Column(db.DateTime, default=datetime.utcnow)
    actualizado_en = db.Column(db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

