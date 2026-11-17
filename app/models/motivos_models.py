# app/models/motivos_models.py

from app.core.db import db
from app.crud.model_mixin import ModelMixin


class MotivoOperacion(db.Model, ModelMixin):
    """Motivos que se ofrecen al confirmar un alta, una modificación o una baja."""

    __tablename__ = "motivos_operacion"
    __label_field__ = "nombre_motivo"

    motivo_operacion_id = db.Column(db.Integer, primary_key=True, autoincrement=True)
    nombre_motivo = db.Column(db.String(200), nullable=False, info={"label": "Motivo"})
    tipo_operacion = db.Column(db.String(20), nullable=False,
                               info={"label": "Operación"})  # INSERT, UPDATE, DELETE

    def __repr__(self):
        return f"<MotivoOperacion {self.nombre_motivo} ({self.tipo_operacion})>"
