# app/models/activos_models.py

from app.core.db import db
from datetime import datetime
from app.crud.audit_mixin import AuditMixin
from app.crud.model_mixin import ModelMixin
import uuid


class EstadoActivo(db.Model, ModelMixin):
    __tablename__ = "estados_activo"
    __label_field__ = "nombre_estado"

    estado_activo_id = db.Column(db.Integer, primary_key=True, autoincrement=True)
    uuid = db.Column(
        db.String(36), default=lambda: str(uuid.uuid4()), unique=True, nullable=False
    )

    nombre_estado = db.Column(db.String(50), nullable=False)
    color_badge = db.Column(db.String(20), nullable=False)


class TipoActivo(db.Model, ModelMixin):
    __tablename__ = "tipos_activo"
    __label_field__ = "nombre_tipo"

    tipo_activo_id = db.Column(db.Integer, primary_key=True, autoincrement=True)
    nombre_tipo = db.Column(db.String(50), nullable=False, unique=True)


class CategoriaActivo(db.Model, ModelMixin, AuditMixin):
    __tablename__ = "categorias_activo"
    __label_field__ = "nombre_categoria"

    categoria_activo_id = db.Column(db.Integer, primary_key=True, autoincrement=True)
    nombre_categoria = db.Column(db.String(100), nullable=False)

    # FK → TipoActivo
    tipo_activo_id = db.Column(
        db.Integer, db.ForeignKey("tipos_activo.tipo_activo_id"), nullable=False
    )
    tipo_activo = db.relationship("TipoActivo", lazy="joined")


class Activo(db.Model, ModelMixin, AuditMixin):
    __tablename__ = "activos"

    activo_id = db.Column(db.Integer, primary_key=True, autoincrement=True)
    uuid = db.Column(
        db.String(36), default=lambda: str(uuid.uuid4()), unique=True, nullable=False
    )

    # FK → TipoActivo
    tipo_activo_id = db.Column(
        db.Integer, db.ForeignKey("tipos_activo.tipo_activo_id"), nullable=False
    )
    tipo_activo = db.relationship("TipoActivo", lazy="joined")

    # FK → CategoriaActivo
    categoria_activo_id = db.Column(
        db.Integer,
        db.ForeignKey("categorias_activo.categoria_activo_id"),
        nullable=False,
    )
    categoria_activo = db.relationship("CategoriaActivo", lazy="joined")

    # FK → Marca
    marca_id = db.Column(db.Integer, db.ForeignKey("marcas.marca_id"), nullable=True)
    marca = db.relationship("Marca", lazy="joined")

    # FK → Modelo
    modelo_id = db.Column(db.Integer, db.ForeignKey("modelos.modelo_id"), nullable=True)
    modelo = db.relationship("Modelo", lazy="joined")

    patente = db.Column(db.String(50), nullable=True)
    descripcion = db.Column(db.String(200), nullable=False)

    nro_serie_chasis = db.Column(db.String(100), nullable=True)
    nro_motor = db.Column(db.String(100), nullable=True)

    año = db.Column(db.Integer, nullable=True)
    observacion = db.Column(db.String(300), nullable=True)
    codigo_brescia = db.Column(db.String(50), nullable=True)

    # FK → Sector
    sector_id = db.Column(
        db.Integer, db.ForeignKey("sectores.sector_id"), nullable=True
    )
    sector = db.relationship("Sector", lazy="joined")

    usuario_asignado = db.Column(db.String(150), nullable=True)

    # FK → Ubicacion
    ubicacion_id = db.Column(
        db.Integer, db.ForeignKey("ubicaciones.ubicacion_id"), nullable=True
    )
    ubicacion = db.relationship("Ubicacion", lazy="joined") 

    # FK → EstadoActivo
    estado_activo_id = db.Column(
        db.Integer, db.ForeignKey("estados_activo.estado_activo_id"), nullable=False
    )
    estado_activo = db.relationship("EstadoActivo", lazy="joined")

    foto_path = db.Column(db.String(300), nullable=True)
    detalles_tecnicos = db.Column(db.JSON, nullable=True)

    creado_en = db.Column(db.DateTime, default=datetime.utcnow)
    actualizado_en = db.Column(
        db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow
    )

    def to_dict(self):
        return {
            "activo_id": self.activo_id,
            "uuid": self.uuid,
            "tipo_activo_id": self.tipo_activo_id,
            "categoria_activo_id": self.categoria_activo_id,
            "marca_id": self.marca_id,
            "modelo_id": self.modelo_id,
            "patente": self.patente,
            "descripcion": self.descripcion,
            "nro_serie_chasis": self.nro_serie_chasis,
            "nro_motor": self.nro_motor,
            "año": self.año,
            "observacion": self.observacion,
            "codigo_brescia": self.codigo_brescia,
            "sector_id": self.sector_id,
            "usuario_asignado": self.usuario_asignado,
            "ubicacion_id": self.ubicacion_id,
            "estado_activo_id": self.estado_activo_id,
            "foto_path": self.foto_path,
            "detalles_tecnicos": self.detalles_tecnicos,
            "creado_en": self.creado_en.isoformat(),
            "actualizado_en": self.actualizado_en.isoformat(),
        }
