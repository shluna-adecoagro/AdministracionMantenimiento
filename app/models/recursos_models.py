from app import db
from app.crud.model_mixin import ModelMixin
from app.crud.audit_mixin import AuditMixin
import uuid

class EstadoRecurso(ModelMixin, db.Model):
    __tablename__ = "estados_recurso"
    __label_field__ = "nombre_estado_recurso"

    estado_recurso_id = db.Column(db.Integer, primary_key=True)
    uuid = db.Column(db.String(36), default=lambda: str(uuid.uuid4()), unique=True, nullable=False)

    nombre_estado_recurso = db.Column(db.String(50), nullable=False)
    color_badge = db.Column(db.String(20), nullable=False)

class Recurso(ModelMixin, AuditMixin, db.Model):
    __tablename__ = "recursos"

    recurso_id = db.Column(db.Integer, autoincrement=True, primary_key=True)
    uuid = db.Column(db.String(36), default=lambda: str(uuid.uuid4()), unique=True)
    tipo_recurso = db.Column(db.String(20), nullable=False)  # interno / proveedor
    estado_recurso_id = db.Column(db.Integer, db.ForeignKey("estados_recurso.estado_recurso_id"), nullable=False)
    estado = db.relationship("EstadoRecurso", lazy="joined")

    __mapper_args__ = {
        "polymorphic_on": tipo_recurso,
        "polymorphic_identity": "recurso"
    }


class Empleado(Recurso):
    __tablename__ = "empleados"
    __label_field__ = "nombre_completo"

    recurso_id = db.Column(db.Integer, db.ForeignKey("recursos.recurso_id"), primary_key=True)

    nombre = db.Column(db.String(100), nullable=False)
    apellido = db.Column(db.String(100), nullable=False)
    legajo = db.Column(db.String(50))
    sector_id = db.Column(db.Integer, db.ForeignKey("sectores.sector_id"))
    puesto = db.Column(db.String(100))

    @property
    def nombre_completo(self):
        return f"{self.nombre} {self.apellido}"

    __mapper_args__ = {
        "polymorphic_identity": "interno"
    }



class Proveedor(Recurso):
    __tablename__ = "proveedores"
    __label_field__ = "razon_social"

    recurso_id = db.Column(db.Integer, db.ForeignKey("recursos.recurso_id"), primary_key=True)

    razon_social = db.Column(db.String(150), nullable=False)
    cuit = db.Column(db.String(20))
    direccion = db.Column(db.String(200))

    contactos = db.relationship("ContactoProveedor", back_populates="proveedor", cascade="all, delete-orphan")

    __mapper_args__ = {
        "polymorphic_identity": "proveedor"
    }

class ContactoProveedor(db.Model, ModelMixin):
    __tablename__ = "contactos_proveedor"
    __label_field__ = "nombre_contacto"

    contacto_id = db.Column(db.Integer, autoincrement=True, primary_key=True)

    uuid = db.Column(db.String(36), default=lambda: str(uuid.uuid4()), unique=True, nullable=False)

    proveedor_id = db.Column(db.Integer, db.ForeignKey("proveedores.recurso_id"), nullable=False)

    nombre_contacto = db.Column(db.String(100), nullable=False)
    email = db.Column(db.String(100))
    telefono = db.Column(db.String(50))
    tipo_contacto = db.Column(db.String(50))

    proveedor = db.relationship("Proveedor", back_populates="contactos")

