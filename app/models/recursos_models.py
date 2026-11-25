from app import db
from app.crud.model_mixin import ModelMixin
from app.crud.audit_mixin import AuditMixin
from app.crud.por_defecto import id_por_nombre
import uuid

class EstadoRecurso(ModelMixin, db.Model):
    """Estados de los empleados (el nombre de la tabla es anterior a que los
    proveedores tuvieran su propio catálogo, estados_proveedor)."""

    __tablename__ = "estados_recurso"
    __label_field__ = "nombre_estado_recurso"

    estado_recurso_id = db.Column(db.Integer, primary_key=True)
    uuid = db.Column(db.String(36), default=lambda: str(uuid.uuid4()), unique=True, nullable=False)

    nombre_estado_recurso = db.Column(db.String(50), nullable=False, info={"label": "Nombre"})
    color_badge = db.Column(db.String(20), nullable=False)

class Recurso(ModelMixin, AuditMixin, db.Model):
    __tablename__ = "recursos"

    recurso_id = db.Column(db.Integer, autoincrement=True, primary_key=True)
    uuid = db.Column(db.String(36), default=lambda: str(uuid.uuid4()), unique=True)
    tipo_recurso = db.Column(db.String(20), nullable=False)  # interno / proveedor
    # El estado no está acá: cada tipo tiene el suyo (empleados → estados_recurso,
    # proveedores → estados_proveedor).

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
    legajo = db.Column(db.String(50), info={"label": "Legajo"})
    # Sin backref: un sector con empleados no se puede borrar.
    sector_id = db.Column(db.Integer, db.ForeignKey("sectores.sector_id"))
    sector = db.relationship("Sector")
    puesto = db.Column(db.String(100), info={"label": "Puesto"})
    telefono = db.Column(db.String(50), info={"label": "Teléfono"})
    email = db.Column(db.String(100), info={"label": "Email"})
    estado_recurso_id = db.Column(db.Integer, db.ForeignKey("estados_recurso.estado_recurso_id"), nullable=False,
                                  info={"label": "Estado"})
    estado = db.relationship("EstadoRecurso", lazy="joined")

    @property
    def nombre_completo(self):
        return f"{self.nombre} {self.apellido}"

    __mapper_args__ = {
        "polymorphic_identity": "interno"
    }



class EstadoProveedor(ModelMixin, db.Model):
    """Activo, Retenido o Inactivo. Por ahora es informativo; está previsto que
    «Retenido» impida adjudicarle ofertas y emitirle OC (ver
    docs/diseno_tablas_operativas.md)."""

    __tablename__ = "estados_proveedor"
    __label_field__ = "nombre_estado_proveedor"

    estado_proveedor_id = db.Column(db.Integer, primary_key=True, autoincrement=True)
    uuid = db.Column(db.String(36), default=lambda: str(uuid.uuid4()), unique=True, nullable=False)

    nombre_estado_proveedor = db.Column(db.String(50), nullable=False, unique=True,
                                        info={"label": "Nombre"})
    color_badge = db.Column(db.String(20), nullable=False)


class EstadoContacto(ModelMixin, db.Model):
    """Disponible o No disponible. Informativo."""

    __tablename__ = "estados_contacto"
    __label_field__ = "nombre_estado_contacto"

    estado_contacto_id = db.Column(db.Integer, primary_key=True, autoincrement=True)
    uuid = db.Column(db.String(36), default=lambda: str(uuid.uuid4()), unique=True, nullable=False)

    nombre_estado_contacto = db.Column(db.String(50), nullable=False, unique=True,
                                       info={"label": "Nombre"})
    color_badge = db.Column(db.String(20), nullable=False)


class Proveedor(Recurso):
    __tablename__ = "proveedores"
    __label_field__ = "razon_social"

    recurso_id = db.Column(db.Integer, db.ForeignKey("recursos.recurso_id"), primary_key=True)

    razon_social = db.Column(db.String(150), nullable=False, info={"label": "Razón social"})
    cuit = db.Column(db.String(20), info={"label": "CUIT"})
    # Código del proveedor en el ERP (figura en la OC). Vacío = NULL.
    codigo_erp = db.Column(db.String(50), nullable=True, unique=True, info={"label": "Código ERP"})
    direccion = db.Column(db.String(200), info={"label": "Dirección"})
    telefono = db.Column(db.String(50), info={"label": "Teléfono"})
    email = db.Column(db.String(100), info={"label": "Email"})
    # Obligatorio; si no se indica, «Activo». Un estado en uso no se puede borrar.
    estado_proveedor_id = db.Column(
        db.Integer,
        db.ForeignKey("estados_proveedor.estado_proveedor_id"),
        nullable=False,
        default=id_por_nombre("estados_proveedor", "estado_proveedor_id",
                              "nombre_estado_proveedor", "Activo"),
        info={"label": "Estado"},
    )
    estado = db.relationship("EstadoProveedor", lazy="joined")

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

    nombre_contacto = db.Column(db.String(100), nullable=False, info={"label": "Nombre"})
    division = db.Column(db.String(100), nullable=True, info={"label": "División"})
    email = db.Column(db.String(100), info={"label": "Email"})
    telefono = db.Column(db.String(50), info={"label": "Teléfono"})
    tipo_contacto = db.Column(db.String(50))
    # Obligatorio; si no se indica, «Disponible».
    estado_contacto_id = db.Column(
        db.Integer,
        db.ForeignKey("estados_contacto.estado_contacto_id"),
        nullable=False,
        default=id_por_nombre("estados_contacto", "estado_contacto_id",
                              "nombre_estado_contacto", "Disponible"),
        info={"label": "Estado"},
    )
    estado = db.relationship("EstadoContacto")

    proveedor = db.relationship("Proveedor", back_populates="contactos")

