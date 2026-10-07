from datetime import datetime
from app.core.db import db
import json
import hashlib

class AuditLog(db.Model):
    __tablename__ = "audit_log"

    LogID = db.Column(db.Integer, primary_key=True, autoincrement=True)

    Fecha = db.Column(db.DateTime, default=datetime.utcnow, nullable=False)
    Usuario = db.Column(db.String(150), nullable=False)

    TablaAfectada = db.Column(db.String(100), nullable=False)

    # Nuevo: UUID estable del registro auditado
    RegistroUUID = db.Column(db.String(36), nullable=False)

    # Mantener compatibilidad con registros viejos
    RegistroID = db.Column(db.String(100), nullable=True)

    TipoDeCambio = db.Column(db.String(20), nullable=False)
    Version = db.Column(db.Integer, nullable=False, default=1)

    HashRegistro = db.Column(db.String(64), nullable=False)

    EstadoAnterior = db.Column(db.JSON, nullable=True)
    EstadoActual = db.Column(db.JSON, nullable=True)

    motivo_operacion = db.Column(db.String(500), nullable=True)

    def calcular_hash(self):
        """
        Calcula el hash SHA-256 del EstadoActual.
        Si EstadoActual es None (por ejemplo en DELETE), usa EstadoAnterior.
        """
        data = self.EstadoActual or self.EstadoAnterior or {}
        json_str = json.dumps(data, sort_keys=True)
        return hashlib.sha256(json_str.encode("utf-8")).hexdigest()

    def save(self):
        """
        Calcula el hash antes de guardar.
        """
        self.HashRegistro = self.calcular_hash()
        db.session.add(self)

    def to_dict(self):
        return {
            "LogID": self.LogID,
            "Fecha": self.Fecha.isoformat(),
            "Usuario": self.Usuario,
            "TablaAfectada": self.TablaAfectada,
            "RegistroUUID": self.RegistroUUID,
            "RegistroID": self.RegistroID,
            "TipoDeCambio": self.TipoDeCambio,
            "Version": self.Version,
            "EstadoAnterior": self.EstadoAnterior,
            "EstadoActual": self.EstadoActual,
            "HashRegistro": self.HashRegistro,
            "motivo_operacion": self.motivo_operacion
        }
