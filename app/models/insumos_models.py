from app.core.db import db
from app.crud.audit_mixin import AuditMixin
from app.crud.model_mixin import ModelMixin
import uuid
from datetime import datetime


class CategoriaInsumo(db.Model, ModelMixin):
    __tablename__ = "categorias_insumo"

    categoria_insumo_id = db.Column(db.Integer, primary_key=True, autoincrement=True)
    nombre_categoria = db.Column(db.String(100), nullable=False, unique=True)

    def to_dict(self):
        return {
            "categoria_insumo_id": self.categoria_insumo_id,
            "nombre_categoria": self.nombre_categoria,
        }


class TipoInsumo(db.Model, ModelMixin):
    __tablename__ = "tipos_insumo"

    tipo_insumo_id = db.Column(db.Integer, primary_key=True, autoincrement=True)
    nombre_tipo = db.Column(db.String(100), nullable=False, unique=True)

    categoria_insumo_id = db.Column(
        db.Integer,
        db.ForeignKey("categorias_insumo.categoria_insumo_id"),
        nullable=False,
    )
    categoria = db.relationship("CategoriaInsumo", backref="tipos")

    def to_dict(self):
        return {
            "tipo_insumo_id": self.tipo_insumo_id,
            "nombre_tipo": self.nombre_tipo,
            "categoria_insumo_id": self.categoria_insumo_id,
            "categoria": self.categoria.nombre_categoria if self.categoria else None,
        }


class StockInsumo(db.Model, ModelMixin, AuditMixin):
    __tablename__ = "stock_insumo"

    stock_insumo_id = db.Column(db.Integer, primary_key=True, autoincrement=True)

    uuid = db.Column(
        db.String(36), default=lambda: str(uuid.uuid4()), unique=True, nullable=False
    )

    insumo_id = db.Column(
        db.Integer, db.ForeignKey("insumos.insumo_id"), nullable=False
    )
    insumo = db.relationship("Insumo", backref="stock")

    sector_id = db.Column(
        db.Integer, db.ForeignKey("sectores.sector_id"), nullable=True
    )
    # passive_deletes="all": borrar un sector o una ubicación con stock se
    # bloquea, en vez de dejar el stock sin sector/ubicación en silencio.
    sector = db.relationship("Sector", backref=db.backref("stock", passive_deletes="all"))

    ubicacion_id = db.Column(
        db.Integer, db.ForeignKey("ubicaciones.ubicacion_id"), nullable=False
    )
    ubicacion = db.relationship("Ubicacion", backref=db.backref("stock", passive_deletes="all"))

    cantidad = db.Column(db.Float, nullable=False, default=0)
    fecha_actualizacion = db.Column(db.DateTime, default=datetime.utcnow)

    def to_dict(self):
        return {
            "stock_insumo_id": self.stock_insumo_id,
            "insumo_id": self.insumo_id,
            "ubicacion_id": self.ubicacion_id,
            "sector_id": self.sector_id,
            "cantidad": self.cantidad,
            "fecha_actualizacion": self.fecha_actualizacion.isoformat(),
        }


class Insumo(db.Model, ModelMixin, AuditMixin):
    __tablename__ = "insumos"

    insumo_id = db.Column(db.Integer, primary_key=True, autoincrement=True)
    uuid = db.Column(db.String(36), default=lambda: str(uuid.uuid4()), unique=True)

    codigo = db.Column(db.String(50), nullable=False, unique=True)
    descripcion = db.Column(db.String(200), nullable=False)

    # FK a marcas (ya existe)
    marca_id = db.Column(db.Integer, db.ForeignKey("marcas.marca_id"), nullable=True)
    marca = db.relationship("Marca", backref="insumos")

    # FK a categoría
    categoria_insumo_id = db.Column(
        db.Integer,
        db.ForeignKey("categorias_insumo.categoria_insumo_id"),
        nullable=False,
    )
    categoria_insumo = db.relationship("CategoriaInsumo", backref="insumos")

    # FK a tipo
    tipo_insumo_id = db.Column(
        db.Integer, db.ForeignKey("tipos_insumo.tipo_insumo_id"), nullable=True
    )
    tipo_insumo = db.relationship("TipoInsumo", backref="insumos")

    presentacion_cantidad = db.Column(db.Float, nullable=True)

    unidad_medida_id = db.Column(
        db.Integer, db.ForeignKey("unidades_medida.unidad_medida_id"), nullable=True
    )
    unidad_medida = db.relationship("UnidadMedida", backref="insumos")

    cantidad_minima = db.Column(db.Float, nullable=True)

    observaciones = db.Column(db.String(300), nullable=True)
    detalles_tecnicos = db.Column(db.JSON, nullable=True)

    # Foto del insumo
    foto = db.Column(db.String(300), nullable=True)

    creado_en = db.Column(db.DateTime, default=datetime.utcnow)
    actualizado_en = db.Column(
        db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow
    )

    def to_dict(self):
        data = {
            "insumo_id": self.insumo_id,
            "uuid": self.uuid,
            "codigo": self.codigo,
            "descripcion": self.descripcion,
            "marca_id": self.marca_id,
            "marca": self.marca.nombre_marca if self.marca else None,
            "categoria_insumo_id": self.categoria_insumo_id,
            "categoria_insumo": (
                self.categoria_insumo.nombre_categoria
                if self.categoria_insumo
                else None
            ),
            "tipo_insumo_id": self.tipo_insumo_id,
            "tipo_insumo": self.tipo_insumo.nombre_tipo if self.tipo_insumo else None,
            "presentacion_cantidad": self.presentacion_cantidad,
            "unidad_medida": self.unidad_medida,
            "cantidad_minima": self.cantidad_minima,
            "observaciones": self.observaciones,
            "detalles_tecnicos": self.detalles_tecnicos,
            "foto": self.foto,
            "creado_en": self.creado_en.isoformat(),
            "actualizado_en": self.actualizado_en.isoformat(),
        }

        # Campo calculado
        from app.services.stock_service import StockService

        data["stock_total"] = StockService.obtener_stock_total(self.insumo_id)

        return data
