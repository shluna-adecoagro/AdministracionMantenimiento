# app/models/medidores_models.py

import uuid
from datetime import datetime

from sqlalchemy import select
from sqlalchemy.orm import column_property

from app.core.db import db
from app.crud.model_mixin import ModelMixin
from app.crud.audit_mixin import AuditMixin
from app.models.unidadmedida_models import UnidadMedida


class Medidor(db.Model, ModelMixin, AuditMixin):
    __tablename__ = "medidores"
    __label_field__ = "nombre_medidor"

    medidor_id = db.Column(db.Integer, primary_key=True, autoincrement=True)
    uuid = db.Column(db.String(36), default=lambda: str(uuid.uuid4()), nullable=False)

    nombre_medidor = db.Column(db.String(100), nullable=False, info={"label": "Nombre"})

    # FK → Unidad de medida
    unidad_medida_id = db.Column(
        db.Integer, db.ForeignKey("unidades_medida.unidad_medida_id"), nullable=False,
        info={"label": "Unidad de medida"},
    )
    unidad_medida = db.relationship("UnidadMedida", lazy="joined")

    # Qué mide (horómetro, odómetro...): el tipo de medidor de su unidad.
    tipo_medidor = column_property(
        select(UnidadMedida.tipo_medidor)
        .where(UnidadMedida.unidad_medida_id == unidad_medida_id)
        .correlate_except(UnidadMedida)
        .scalar_subquery(),
        info={"label": "Tipo de medidor"},
    )

    # FK → Activo. Sin backref: un activo con medidores no se puede borrar
    # (las lecturas son historial; para retirarlo se usa el estado "Baja").
    activo_id = db.Column(
        db.Integer, db.ForeignKey("activos.activo_id"), nullable=False,
        info={"label": "Activo"},
    )
    activo = db.relationship("Activo", lazy="joined")

    valor_inicial = db.Column(db.Float, default=0, info={"label": "Valor inicial"})

    # valor_actual: calculado a partir de la última lectura (ver
    # lecturas_medidores_models.py, donde se define porque necesita LecturaMedidor).

    creado_en = db.Column(db.DateTime, default=datetime.utcnow)
    actualizado_en = db.Column(
        db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow
    )
