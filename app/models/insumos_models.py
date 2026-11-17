import uuid
from datetime import datetime

from sqlalchemy import func, select
from sqlalchemy.orm import column_property

from app.core.db import db
from app.crud.audit_mixin import AuditMixin
from app.crud.model_mixin import ModelMixin

# Reglas al borrar (ver app/crud/core/dependencias.py):
#   * categoría → tipos: cascada (los tipos son parte de la categoría);
#   * un insumo con stock o en algún BOM no se puede borrar;
#   * una marca, categoría, tipo o unidad usada por insumos no se puede borrar
#     (passive_deletes="all" evita que SQLAlchemy deje el insumo sin ese dato).


class CategoriaInsumo(db.Model, ModelMixin):
    __tablename__ = "categorias_insumo"
    __label_field__ = "nombre_categoria"

    categoria_insumo_id = db.Column(db.Integer, primary_key=True, autoincrement=True)
    nombre_categoria = db.Column(db.String(100), nullable=False, unique=True,
                                 info={"label": "Categoría"})


class TipoInsumo(db.Model, ModelMixin):
    __tablename__ = "tipos_insumo"
    __label_field__ = "nombre_tipo"

    tipo_insumo_id = db.Column(db.Integer, primary_key=True, autoincrement=True)
    nombre_tipo = db.Column(db.String(100), nullable=False, unique=True,
                            info={"label": "Tipo"})

    categoria_insumo_id = db.Column(
        db.Integer,
        db.ForeignKey("categorias_insumo.categoria_insumo_id"),
        nullable=False,
        info={"label": "Categoría"},
    )
    categoria = db.relationship(
        "CategoriaInsumo", backref=db.backref("tipos", cascade="all, delete")
    )


class StockInsumo(db.Model, ModelMixin, AuditMixin):
    """Cantidad de un insumo en una ubicación. El sector es el de la ubicación."""

    __tablename__ = "stock_insumo"
    # Una sola fila por insumo y ubicación.
    __table_args__ = (db.UniqueConstraint("insumo_id", "ubicacion_id"),)

    stock_insumo_id = db.Column(db.Integer, primary_key=True, autoincrement=True)

    uuid = db.Column(
        db.String(36), default=lambda: str(uuid.uuid4()), unique=True, nullable=False
    )

    insumo_id = db.Column(
        db.Integer, db.ForeignKey("insumos.insumo_id"), nullable=False
    )
    insumo = db.relationship("Insumo", backref=db.backref("stock", passive_deletes="all"))

    # passive_deletes="all": borrar una ubicación con stock se bloquea, en vez
    # de dejar el stock sin ubicación en silencio.
    ubicacion_id = db.Column(
        db.Integer, db.ForeignKey("ubicaciones.ubicacion_id"), nullable=False,
        info={"label": "Ubicación"},
    )
    ubicacion = db.relationship("Ubicacion", backref=db.backref("stock", passive_deletes="all"))

    cantidad = db.Column(db.Float, nullable=False, default=0)
    fecha_actualizacion = db.Column(db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow,
                                    info={"label": "Actualizado"})


class Insumo(db.Model, ModelMixin, AuditMixin):
    __tablename__ = "insumos"
    __label_field__ = "descripcion"

    insumo_id = db.Column(db.Integer, primary_key=True, autoincrement=True)
    uuid = db.Column(db.String(36), default=lambda: str(uuid.uuid4()), unique=True)

    codigo = db.Column(db.String(50), nullable=False, unique=True, info={"label": "Código"})
    descripcion = db.Column(db.String(200), nullable=False, info={"label": "Descripción"})

    marca_id = db.Column(db.Integer, db.ForeignKey("marcas.marca_id"), nullable=True)
    marca = db.relationship("Marca", backref=db.backref("insumos", passive_deletes="all"))

    categoria_insumo_id = db.Column(
        db.Integer,
        db.ForeignKey("categorias_insumo.categoria_insumo_id"),
        nullable=False,
        info={"label": "Categoría"},
    )
    categoria_insumo = db.relationship(
        "CategoriaInsumo", backref=db.backref("insumos", passive_deletes="all")
    )

    tipo_insumo_id = db.Column(
        db.Integer, db.ForeignKey("tipos_insumo.tipo_insumo_id"), nullable=True,
        info={"label": "Tipo"},
    )
    tipo_insumo = db.relationship(
        "TipoInsumo", backref=db.backref("insumos", passive_deletes="all")
    )

    presentacion_cantidad = db.Column(db.Float, nullable=True,
                                      info={"label": "Cantidad por presentación"})

    unidad_medida_id = db.Column(
        db.Integer, db.ForeignKey("unidades_medida.unidad_medida_id"), nullable=True,
        info={"label": "Unidad de medida"},
    )
    unidad_medida = db.relationship(
        "UnidadMedida", backref=db.backref("insumos", passive_deletes="all")
    )

    cantidad_minima = db.Column(db.Float, nullable=True, info={"label": "Stock mínimo"})

    observaciones = db.Column(db.String(300), nullable=True)
    detalles_tecnicos = db.Column(db.JSON, nullable=True)

    # Foto del insumo
    foto = db.Column(db.String(300), nullable=True)

    # Suma del stock en todas las ubicaciones (se calcula en la consulta).
    stock_total = column_property(
        select(func.coalesce(func.sum(StockInsumo.cantidad), 0.0))
        .where(StockInsumo.insumo_id == insumo_id)
        .correlate_except(StockInsumo)
        .scalar_subquery(),
        info={"label": "Stock total"},
    )

    creado_en = db.Column(db.DateTime, default=datetime.utcnow)
    actualizado_en = db.Column(
        db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow
    )
