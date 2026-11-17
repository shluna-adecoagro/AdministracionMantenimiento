from app.core.db import db
from app.crud.audit_mixin import AuditMixin
from app.crud.model_mixin import ModelMixin
import uuid

class EstadoCuenta(ModelMixin, db.Model):
    __tablename__ = "estados_cuenta"
    __label_field__ = "nombre_estado_cuenta"

    estado_cuenta_id = db.Column(db.Integer, primary_key=True)
    uuid = db.Column(db.String(36), default=lambda: str(uuid.uuid4()), unique=True, nullable=False)
    nombre_estado_cuenta = db.Column(db.String(50), nullable=False)
    color_badge = db.Column(db.String(20), nullable=False)


class Cuenta(ModelMixin, AuditMixin, db.Model):
    __tablename__ = "cuentas"
    __label_field__ = "nombre_cuenta"

    cuenta_id = db.Column(db.Integer, autoincrement=True, primary_key=True)
    uuid = db.Column(db.String(36), default=lambda: str(uuid.uuid4()), unique=True, nullable=False)
    numero_cuenta = db.Column(db.String(50), nullable=False, unique=True,
                              info={"label": "Número de cuenta"})
    nombre_cuenta = db.Column(db.String(120), nullable=False,
                              info={"label": "Nombre de cuenta"})

    estado_cuenta_id = db.Column(
        db.Integer,
        db.ForeignKey("estados_cuenta.estado_cuenta_id"),
        nullable=False,
        info={"label": "Estado"},
    )
    estado = db.relationship("EstadoCuenta", backref="cuentas")
