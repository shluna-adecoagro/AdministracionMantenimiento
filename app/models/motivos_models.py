# app/models/motivos_models.py

from app.core.db import db

class MotivoOperacion(db.Model):
    __tablename__ = "motivos_operacion"

    motivo_operacion_id = db.Column(db.Integer, primary_key=True, autoincrement=True)
    nombre_motivo = db.Column(db.String(200), nullable=False)
    tipo_operacion = db.Column(db.String(20), nullable=False)  # INSERT, UPDATE, DELETE

    def __repr__(self):
        return f"<MotivoOperacion {self.nombre_motivo} ({self.tipo_operacion})>"
