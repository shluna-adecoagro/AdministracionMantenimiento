from app.core.db import db
from app.crud.audit_mixin import AuditMixin
from app.crud.model_mixin import ModelMixin
import uuid
from datetime import datetime

# Estado que toma una ubicación si no se indica otro (alta web, API, CSV o código).
ESTADO_UBICACION_POR_DEFECTO = "Operativa"


class EstadoUbicacion(ModelMixin, db.Model):
    """Si la ubicación está operativa, en mantenimiento o inactiva. Es informativo:
    ninguna regla de la app depende de él (por eso es un catálogo editable)."""

    __tablename__ = "estados_ubicacion"
    __label_field__ = "nombre_estado_ubicacion"

    estado_ubicacion_id = db.Column(db.Integer, primary_key=True, autoincrement=True)
    uuid = db.Column(db.String(36), default=lambda: str(uuid.uuid4()), unique=True, nullable=False)

    nombre_estado_ubicacion = db.Column(db.String(50), nullable=False, unique=True,
                                        info={"label": "Nombre"})
    color_badge = db.Column(db.String(20), nullable=False)


def estado_ubicacion_por_defecto(contexto):
    """
    ID de «Operativa» (o, si se renombró o borró, del primer estado cargado).

    SQLAlchemy la llama al insertar sin estado, con el contexto de ejecución: se
    consulta por su conexión porque la sesión está en pleno flush. El formulario
    de alta la llama sin contexto (None) para preseleccionar el valor.
    """
    consulta = db.select(EstadoUbicacion.estado_ubicacion_id).order_by(
        (EstadoUbicacion.nombre_estado_ubicacion != ESTADO_UBICACION_POR_DEFECTO),
        EstadoUbicacion.estado_ubicacion_id,
    ).limit(1)
    if contexto is None:
        return db.session.execute(consulta).scalar()
    return contexto.connection.execute(consulta).scalar()


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

    # Obligatorio en la base; si no se indica, «Operativa». Un estado en uso no
    # se puede borrar (relación sin backref: la FK lo impide).
    estado_ubicacion_id = db.Column(
        db.Integer,
        db.ForeignKey("estados_ubicacion.estado_ubicacion_id"),
        nullable=False,
        default=estado_ubicacion_por_defecto,
        info={"label": "Estado"},
    )
    estado = db.relationship("EstadoUbicacion")

    creado_en = db.Column(db.DateTime, default=datetime.utcnow)
    actualizado_en = db.Column(db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
