from app.core.db import db
from datetime import datetime
from app.crud.audit_mixin import AuditMixin
from app.crud.model_mixin import ModelMixin
import uuid


class TipoUnidad(db.Model, ModelMixin):
    __tablename__ = "tipos_unidad"
    __label_field__ = "nombre_tipo"

    tipo_unidad_id = db.Column(db.Integer, primary_key=True, autoincrement=True)
    nombre_tipo = db.Column(db.String(100), nullable=False, unique=True, info={"label": "Nombre"})


class UnidadMedida(db.Model, ModelMixin, AuditMixin):
    __tablename__ = "unidades_medida"
    __label_field__ = "nombre_unidad"

    unidad_medida_id = db.Column(db.Integer, primary_key=True)
    nombre_unidad = db.Column(db.String(100), nullable=False,
                              info={"label": "Nombre"})
    abreviatura = db.Column(db.String(20), nullable=False)
    # Qué instrumento mide en esta unidad (horas → «Horómetro», km → «Odómetro»).
    # Solo las unidades con tipo de medidor se ofrecen en los medidores y en el
    # período por uso de los planes preventivos.
    tipo_medidor = db.Column(db.String(50), nullable=True, info={"label": "Tipo de medidor"})
    tipo_unidad_id = db.Column(
        db.Integer, db.ForeignKey("tipos_unidad.tipo_unidad_id"), nullable=False,
        info={"label": "Tipo"},
    )
    # Un tipo de unidad en uso no se puede borrar.
    tipo_unidad = db.relationship(
        "TipoUnidad", backref=db.backref("unidades_medida", passive_deletes="all")
    )

    uuid = db.Column(db.String(36), default=lambda: str(uuid.uuid4()), nullable=False)
    creado_en = db.Column(db.DateTime, default=datetime.utcnow)
    actualizado_en = db.Column(
        db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow
    )
