# app/models/activos_models.py

from app.core.db import db
from datetime import datetime

from sqlalchemy import select
from sqlalchemy.orm import column_property

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

    nombre_estado = db.Column(db.String(50), nullable=False, info={"label": "Nombre"})
    color_badge = db.Column(db.String(20), nullable=False)


class TipoActivo(db.Model, ModelMixin):
    __tablename__ = "tipos_activo"
    __label_field__ = "nombre_tipo"

    tipo_activo_id = db.Column(db.Integer, primary_key=True, autoincrement=True)
    nombre_tipo = db.Column(db.String(50), nullable=False, unique=True, info={"label": "Nombre"})

    # Cuenta a la que se imputan los gastos de los activos de este tipo.
    # Sin backref: una cuenta usada por un tipo no se puede borrar.
    cuenta_id = db.Column(db.Integer, db.ForeignKey("cuentas.cuenta_id"), nullable=False,
                          info={"label": "Cuenta de imputación"})
    cuenta = db.relationship("Cuenta")


class CategoriaActivo(db.Model, ModelMixin):
    __tablename__ = "categorias_activo"
    __label_field__ = "nombre_categoria"

    categoria_activo_id = db.Column(db.Integer, primary_key=True, autoincrement=True)
    nombre_categoria = db.Column(db.String(100), nullable=False, info={"label": "Nombre"})

    # FK → TipoActivo. Sin backref: un tipo con categorías no se puede borrar.
    tipo_activo_id = db.Column(
        db.Integer, db.ForeignKey("tipos_activo.tipo_activo_id"), nullable=False,
        info={"label": "Tipo de activo"},
    )
    tipo_activo = db.relationship("TipoActivo", lazy="joined")


class Activo(db.Model, ModelMixin, AuditMixin):
    """
    Un equipo, vehículo o instalación.

    Marca y sector se guardan aunque se puedan deducir del modelo y de la
    ubicación: un activo puede tener marca sin modelo conocido, o sector sin
    ubicación precisa. Cuando están los dos, el sistema verifica que coincidan
    (y si falta la marca o el sector, los completa). Ver FieldSpec.depende_de.
    """

    __tablename__ = "activos"
    __label_field__ = "descripcion"

    activo_id = db.Column(db.Integer, primary_key=True, autoincrement=True)
    uuid = db.Column(
        db.String(36), default=lambda: str(uuid.uuid4()), unique=True, nullable=False
    )

    # Identifica al activo (también fuera de la base, ej: en SharePoint).
    numero_activo = db.Column(db.String(50), nullable=False, unique=True,
                              info={"label": "Número de activo"})
    descripcion = db.Column(db.String(200), nullable=False, info={"label": "Descripción"})

    # FK → CategoriaActivo (el tipo de activo es el de la categoría)
    categoria_activo_id = db.Column(
        db.Integer,
        db.ForeignKey("categorias_activo.categoria_activo_id"),
        nullable=False,
        info={"label": "Categoría"},
    )
    categoria_activo = db.relationship("CategoriaActivo", lazy="joined")

    # Tipo de activo: el de la categoría (se calcula, no se guarda). En el
    # formulario aparece como filtro de las categorías.
    tipo_activo_id = column_property(
        select(CategoriaActivo.tipo_activo_id)
        .where(CategoriaActivo.categoria_activo_id == categoria_activo_id)
        .correlate_except(CategoriaActivo)
        .scalar_subquery(),
        info={"label": "Tipo de activo"},
    )

    observaciones = db.Column(db.String(300), nullable=True)

    # FK → Marca / Modelo (el modelo pertenece a la marca)
    marca_id = db.Column(db.Integer, db.ForeignKey("marcas.marca_id"), nullable=True)
    marca = db.relationship("Marca", lazy="joined")

    modelo_id = db.Column(db.Integer, db.ForeignKey("modelos.modelo_id"), nullable=True)
    modelo = db.relationship("Modelo", lazy="joined")

    # Únicos cuando están cargados (puede haber varios activos sin dato).
    numero_serie = db.Column(db.String(100), nullable=True, unique=True,
                             info={"label": "Número de serie"})
    numero_motor = db.Column(db.String(100), nullable=True, unique=True,
                             info={"label": "Número de motor"})

    año = db.Column(db.Integer, nullable=True)

    # FK → Sector / Ubicación (la ubicación pertenece al sector).
    # Sin backref: un sector o ubicación con activos no se puede borrar.
    sector_id = db.Column(
        db.Integer, db.ForeignKey("sectores.sector_id"), nullable=True,
        info={"label": "Sector asignado"},
    )
    sector = db.relationship("Sector", lazy="joined")

    ubicacion_id = db.Column(
        db.Integer, db.ForeignKey("ubicaciones.ubicacion_id"), nullable=True,
        info={"label": "Ubicación asignada"},
    )
    ubicacion = db.relationship("Ubicacion", lazy="joined")

    # Texto libre, con los empleados como sugerencias (puede ser alguien que no
    # está cargado como empleado).
    usuario_asignado = db.Column(db.String(150), nullable=True)

    codigo_carga_gasoil = db.Column(db.String(50), nullable=True,
                                    info={"label": "Código de carga de gasoil"})

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
