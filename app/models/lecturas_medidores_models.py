# app/models/lecturas_medidor_models.py

import uuid
from datetime import datetime

from sqlalchemy import func, select
from sqlalchemy.orm import column_property

from app.core.db import db
from app.crud.model_mixin import ModelMixin
from app.crud.audit_mixin import AuditMixin
from app.models.medidores_models import Medidor


class LecturaMedidor(db.Model, ModelMixin, AuditMixin):
    __tablename__ = "lecturas_medidor"
    __label_field__ = "fecha_lectura"

    lectura_medidor_id = db.Column(db.Integer, primary_key=True, autoincrement=True)
    uuid = db.Column(db.String(36), default=lambda: str(uuid.uuid4()), nullable=False)

    # Sin backref: un medidor con lecturas no se puede borrar (son historial).
    medidor_id = db.Column(
        db.Integer, db.ForeignKey("medidores.medidor_id"), nullable=False,
        info={"label": "Medidor"},
    )
    medidor = db.relationship("Medidor", lazy="joined")

    fecha_lectura = db.Column(db.DateTime, default=datetime.utcnow, nullable=False,
                              info={"label": "Fecha"})
    valor = db.Column(db.Float, nullable=False)

    origen = db.Column(db.String(50), default="manual")  # manual / iot / importacion
    observaciones = db.Column(db.String(500), nullable=True)

    creado_en = db.Column(db.DateTime, default=datetime.utcnow)
    actualizado_en = db.Column(
        db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow
    )


# Valor actual del medidor: el de su lectura más reciente o, si todavía no
# tiene lecturas, el valor inicial. Se calcula en la consulta (no se guarda),
# así nunca puede quedar desactualizado.
_ultima_lectura = (
    select(LecturaMedidor.valor)
    .where(LecturaMedidor.medidor_id == Medidor.medidor_id)
    .order_by(LecturaMedidor.fecha_lectura.desc(), LecturaMedidor.lectura_medidor_id.desc())
    .limit(1)
    .correlate_except(LecturaMedidor)
    .scalar_subquery()
)
Medidor.valor_actual = column_property(
    func.coalesce(_ultima_lectura, Medidor.valor_inicial),
    info={"label": "Valor actual"},
)
