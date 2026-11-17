from app.core.db import db
from app.crud.audit_mixin import AuditMixin
from app.crud.model_mixin import ModelMixin
import uuid
from datetime import datetime

class Ubicacion(db.Model, ModelMixin, AuditMixin):
    __tablename__ = "ubicaciones"
    __label_field__ = "nombre_ubicacion"
    # Dentro de un sector no puede haber dos ubicaciones con el mismo nombre.
    __table_args__ = (db.UniqueConstraint("nombre_ubicacion", "sector_id"),)

    ubicacion_id = db.Column(db.Integer, primary_key=True, autoincrement=True)

    uuid = db.Column(db.String(36), default=lambda: str(uuid.uuid4()), unique=True, nullable=False)

    nombre_ubicacion = db.Column(db.String(100), nullable=False,
                             info={"label": "Nombre de la ubicación"})

    sector_id = db.Column(db.Integer, db.ForeignKey("sectores.sector_id"), nullable=True)
    # Al borrar un sector se borran sus ubicaciones (cascada), salvo que alguna
    # esté en uso (activos, stock...): en ese caso no se borra nada.
    # Ver app/crud/core/dependencias.py.
    sector = db.relationship(
        "Sector", backref=db.backref("ubicaciones", cascade="all, delete")
    )

    creado_en = db.Column(db.DateTime, default=datetime.utcnow)
    actualizado_en = db.Column(db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
