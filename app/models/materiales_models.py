import uuid
from datetime import datetime

from sqlalchemy import func, select
from sqlalchemy.orm import column_property

from app.core.db import db
from app.crud.audit_mixin import AuditMixin
from app.crud.model_mixin import ModelMixin

# Reglas al borrar (ver app/crud/core/dependencias.py):
#   * categoría → tipos: cascada (los tipos son parte de la categoría);
#   * un material con stock o en algún BOM no se puede borrar;
#   * una marca, categoría, tipo o unidad usada por materiales no se puede borrar
#     (passive_deletes="all" evita que SQLAlchemy deje el material sin ese dato).


class CategoriaMaterial(db.Model, ModelMixin):
    __tablename__ = "categorias_material"
    __label_field__ = "nombre_categoria"

    categoria_material_id = db.Column(db.Integer, primary_key=True, autoincrement=True)
    nombre_categoria = db.Column(db.String(100), nullable=False, unique=True,
                                 info={"label": "Categoría"})

    # Cuenta que se sugiere al comprar sin activo (para stock o gasto general).
    # Sin backref: una cuenta usada por una categoría no se puede borrar.
    cuenta_id = db.Column(db.Integer, db.ForeignKey("cuentas.cuenta_id"), nullable=True,
                          info={"label": "Cuenta de imputación"})
    cuenta = db.relationship("Cuenta")


class TipoMaterial(db.Model, ModelMixin):
    __tablename__ = "tipos_material"
    __label_field__ = "nombre_tipo"

    tipo_material_id = db.Column(db.Integer, primary_key=True, autoincrement=True)
    nombre_tipo = db.Column(db.String(100), nullable=False, unique=True,
                            info={"label": "Tipo"})

    categoria_material_id = db.Column(
        db.Integer,
        db.ForeignKey("categorias_material.categoria_material_id"),
        nullable=False,
        info={"label": "Categoría"},
    )
    categoria = db.relationship(
        "CategoriaMaterial", backref=db.backref("tipos", cascade="all, delete")
    )


class StockMaterial(db.Model, ModelMixin, AuditMixin):
    """Cantidad de un material en una ubicación. El sector es el de la ubicación."""

    __tablename__ = "stock_material"
    # Una sola fila por material y ubicación.
    __table_args__ = (db.UniqueConstraint("material_id", "ubicacion_id"),)

    stock_material_id = db.Column(db.Integer, primary_key=True, autoincrement=True)

    uuid = db.Column(
        db.String(36), default=lambda: str(uuid.uuid4()), unique=True, nullable=False
    )

    material_id = db.Column(
        db.Integer, db.ForeignKey("materiales.material_id"), nullable=False
    )
    material = db.relationship("Material", backref=db.backref("stock", passive_deletes="all"))

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


class Material(db.Model, ModelMixin, AuditMixin):
    __tablename__ = "materiales"
    # Se muestra como «RE504836 — Filtro de aceite» (las descripciones se repiten).
    __label_field__ = "etiqueta"
    # Al importar, una FK a un material se reconoce también por el código o por la
    # descripción (si no se repite).
    __buscar_por__ = ("codigo", "descripcion")

    material_id = db.Column(db.Integer, primary_key=True, autoincrement=True)
    uuid = db.Column(db.String(36), default=lambda: str(uuid.uuid4()), unique=True)

    # Número de parte (código del fabricante). Los genéricos usan el prefijo GEN-.
    codigo = db.Column(db.String(50), nullable=False, unique=True, info={"label": "Código"})
    descripcion = db.Column(db.String(200), nullable=False, info={"label": "Descripción"})
    # Código en el ERP (EAM / SAP). Vacío = NULL: la unicidad solo controla los cargados.
    codigo_erp = db.Column(db.String(50), nullable=True, unique=True, info={"label": "Código ERP"})

    # Genérico y presentaciones. El genérico («Aceite 15W-40», en litros, sin
    # envase) agrupa las presentaciones comprables («bidón 20 L»: unidad L,
    # presentación 20), que apuntan a él. El BOM y los planes pueden usar el
    # genérico; ofertas, stock y recepciones, siempre la presentación. Reglas en
    # app/crud/meta/overrides/materiales.py.
    es_generico = db.Column(db.Boolean, nullable=False, default=False, info={"label": "Es genérico"})
    # Sin backref: un genérico con presentaciones no se puede borrar.
    material_generico_id = db.Column(
        db.Integer, db.ForeignKey("materiales.material_id"), nullable=True,
        info={"label": "Genérico"},
    )
    material_generico = db.relationship(
        "Material", remote_side=[material_id], foreign_keys=[material_generico_id],
    )

    # Lo caro, lo crítico y lo que se usa en los services. El resto se da por
    # consumido al recibirlo.
    controla_stock = db.Column(db.Boolean, nullable=False, default=False, info={"label": "Controla stock"})

    marca_id = db.Column(db.Integer, db.ForeignKey("marcas.marca_id"), nullable=True)
    marca = db.relationship("Marca", backref=db.backref("materiales", passive_deletes="all"))

    categoria_material_id = db.Column(
        db.Integer,
        db.ForeignKey("categorias_material.categoria_material_id"),
        nullable=False,
        info={"label": "Categoría"},
    )
    categoria_material = db.relationship(
        "CategoriaMaterial", backref=db.backref("materiales", passive_deletes="all")
    )

    tipo_material_id = db.Column(
        db.Integer, db.ForeignKey("tipos_material.tipo_material_id"), nullable=True,
        info={"label": "Tipo"},
    )
    tipo_material = db.relationship(
        "TipoMaterial", backref=db.backref("materiales", passive_deletes="all")
    )

    # Contenido de cada envase, en la unidad de medida (bidón de 20 L → 20).
    presentacion_cantidad = db.Column(db.Float, nullable=True,
                                      info={"label": "Contenido por envase"})

    unidad_medida_id = db.Column(
        db.Integer, db.ForeignKey("unidades_medida.unidad_medida_id"), nullable=True,
        info={"label": "Unidad de medida"},
    )
    unidad_medida = db.relationship(
        "UnidadMedida", backref=db.backref("materiales", passive_deletes="all")
    )

    cantidad_minima = db.Column(db.Float, nullable=True, info={"label": "Stock mínimo"})

    observaciones = db.Column(db.String(300), nullable=True)
    detalles_tecnicos = db.Column(db.JSON, nullable=True)

    # Foto del material
    foto = db.Column(db.String(300), nullable=True)

    # Cómo se muestra en selects, listados y exportaciones.
    etiqueta = column_property(codigo + " — " + descripcion, info={"label": "Material"})

    # Suma del stock en todas las ubicaciones (se calcula en la consulta).
    stock_total = column_property(
        select(func.coalesce(func.sum(StockMaterial.cantidad), 0.0))
        .where(StockMaterial.material_id == material_id)
        .correlate_except(StockMaterial)
        .scalar_subquery(),
        info={"label": "Stock total"},
    )

    creado_en = db.Column(db.DateTime, default=datetime.utcnow)
    actualizado_en = db.Column(
        db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow
    )
