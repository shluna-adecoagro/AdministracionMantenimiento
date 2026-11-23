# app/models/documentos_models.py
"""
Documentos de proveedores y adjudicación (fase 10, PR 10.4).
Diseño: docs/diseno_tablas_operativas.md.

    documentos_proveedor ──< documento_lineas ──< adjudicaciones >── pedido_lineas

  * Un documento es una oferta, un presupuesto de trabajo, un remito o una
    factura: cabecera y líneas, tal como vienen (leídos con Copilot o cargados a
    mano). En el PR 10.4 solo las ofertas tienen circuito (se adjudican).
  * Una adjudicación vincula una línea de oferta con una línea de pedido: lo
    cotizado (cantidad adjudicada 0) o lo que se compra. Cubre una oferta que
    cotiza líneas de varios pedidos y una línea comprada a dos proveedores.

UNIDADES. La oferta y la adjudicación guardan su cantidad en la unidad de la línea
de oferta (envases, si el material es una presentación). Del lado del pedido,
todo va en la unidad de la línea de pedido: si la línea pide un genérico y se
adjudica una presentación suya, la cantidad se multiplica por el contenido del
envase (2 bidones × 20 L = 40 L). La conversión se calcula en la consulta (no se
guarda): ver `factor_conversion`.

Reglas en app/crud/meta/overrides/documentos.py.
"""
import uuid
from datetime import datetime

from sqlalchemy import String, and_, case, cast, func, select
from sqlalchemy.orm import column_property

from app.core.db import db
from app.crud.audit_mixin import AuditMixin
from app.crud.model_mixin import ModelMixin
from app.crud.origen_mixin import OrigenMixin
from app.models.materiales_models import Material
from app.models.pedidos_models import PedidoLinea
from app.models.recursos_models import Proveedor

TIPOS_DOCUMENTO = (
    {"value": "oferta", "label": "Oferta"},
    {"value": "presupuesto_trabajo", "label": "Presupuesto de trabajo"},
    {"value": "remito", "label": "Remito"},
    {"value": "factura", "label": "Factura"},
)
MONEDAS = ({"value": "ARS", "label": "ARS"}, {"value": "USD", "label": "USD"})
TIPOS_LINEA = (
    {"value": "material", "label": "Material"},
    {"value": "mano_de_obra", "label": "Mano de obra"},
    {"value": "traslado", "label": "Traslado"},
    {"value": "otro", "label": "Otro"},
)


class DocumentoProveedor(db.Model, ModelMixin, AuditMixin, OrigenMixin):
    __tablename__ = "documentos_proveedor"
    __label_field__ = "nombre"
    # Número único por proveedor y tipo, cuando está cargado.
    __table_args__ = (db.UniqueConstraint("proveedor_id", "tipo", "numero"),)

    documento_id = db.Column(db.Integer, primary_key=True, autoincrement=True)
    uuid = db.Column(db.String(36), default=lambda: str(uuid.uuid4()), unique=True, nullable=False)

    tipo = db.Column(db.String(30), nullable=False, default="oferta", info={"label": "Tipo"})

    # El proveedor identificado; mientras no se identifique, el texto tal como vino.
    # Sin backref: un proveedor con documentos no se puede borrar.
    proveedor_id = db.Column(db.Integer, db.ForeignKey("proveedores.recurso_id"), nullable=True,
                             info={"label": "Proveedor"})
    proveedor = db.relationship("Proveedor", lazy="joined")
    proveedor_texto = db.Column(db.String(200), nullable=True, info={"label": "Proveedor (como figura)"})
    proveedor_cuit = db.Column(db.String(20), nullable=True, info={"label": "CUIT (como figura)"})

    numero = db.Column(db.String(50), nullable=True, info={"label": "Número"})
    fecha = db.Column(db.Date, nullable=True, info={"label": "Fecha"})
    moneda = db.Column(db.String(3), nullable=True, info={"label": "Moneda"})
    moneda_inferida = db.Column(db.Boolean, nullable=False, default=False, info={"label": "Moneda inferida"})
    tipo_cambio = db.Column(db.Float, nullable=True, info={"label": "Tipo de cambio"})

    # Tal cual figuran en el documento.
    total_sin_iva = db.Column(db.Float, nullable=True, info={"label": "Total sin IVA"})
    descuento_global_pct = db.Column(db.Float, nullable=True, info={"label": "Descuento global (%)"})
    iva = db.Column(db.Float, nullable=True, info={"label": "IVA"})
    total = db.Column(db.Float, nullable=True, info={"label": "Total"})
    total_usd_informado = db.Column(db.Float, nullable=True, info={"label": "Total en USD informado"})

    # Para identificar el activo y la última ejecución del plan (fase 12).
    equipo_texto = db.Column(db.String(200), nullable=True, info={"label": "Equipo (como figura)"})
    horas_medidor = db.Column(db.Float, nullable=True, info={"label": "Horas del medidor"})

    plazo_entrega_dias = db.Column(db.Integer, nullable=True, info={"label": "Plazo de entrega (días)"})
    validez_hasta = db.Column(db.Date, nullable=True, info={"label": "Válida hasta"})

    # En ofertas: la OC que se emitió por ellas. En remitos y facturas: la que citan.
    nro_oc = db.Column(db.String(30), nullable=True, info={"label": "Nº de OC"})
    archivo = db.Column(db.String(300), nullable=True)

    # «La IA propone, una persona confirma.»
    revisado = db.Column(db.Boolean, nullable=False, default=False, info={"label": "Revisado"})
    motivo_revision = db.Column(db.String(500), nullable=True, info={"label": "A revisar (lectura)"})
    observaciones = db.Column(db.String(500), nullable=True)

    creado_en = db.Column(db.DateTime, default=datetime.utcnow)
    actualizado_en = db.Column(db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)


class DocumentoLinea(db.Model, ModelMixin, AuditMixin, OrigenMixin):
    __tablename__ = "documento_lineas"
    __label_field__ = "nombre"
    __table_args__ = (db.UniqueConstraint("documento_id", "nro_linea"),)
    __calculados__ = {"se_cuenta_en": "Se cuenta en"}

    documento_linea_id = db.Column(db.Integer, primary_key=True, autoincrement=True)
    uuid = db.Column(db.String(36), default=lambda: str(uuid.uuid4()), unique=True, nullable=False)

    # Al borrar el documento se borran sus líneas (y sus adjudicaciones).
    documento_id = db.Column(db.Integer, db.ForeignKey("documentos_proveedor.documento_id"), nullable=False,
                             info={"label": "Documento"})
    documento = db.relationship(
        "DocumentoProveedor", lazy="joined",
        backref=db.backref("lineas", cascade="all, delete", order_by="DocumentoLinea.nro_linea"),
    )
    nro_linea = db.Column(db.Integer, nullable=False, info={"label": "Línea"})
    tipo_linea = db.Column(db.String(20), nullable=False, default="material", info={"label": "Tipo de línea"})

    # Sin backref: un material ofertado no se puede borrar. Nunca un genérico.
    material_id = db.Column(db.Integer, db.ForeignKey("materiales.material_id"), nullable=True,
                            info={"label": "Material"})
    material = db.relationship("Material", lazy="joined")
    codigo_proveedor = db.Column(db.String(100), nullable=True, info={"label": "Código del proveedor"})
    descripcion_proveedor = db.Column(db.String(300), nullable=True, info={"label": "Descripción del proveedor"})

    # Si el material es una presentación, en envases.
    cantidad = db.Column(db.Float, nullable=False, info={"label": "Cantidad (envases, si es una presentación)"})
    udm_texto = db.Column(db.String(30), nullable=True, info={"label": "Unidad (como figura)"})
    # La del material (se completa sola).
    unidad_medida_id = db.Column(db.Integer, db.ForeignKey("unidades_medida.unidad_medida_id"), nullable=True,
                                 info={"label": "Unidad"})
    unidad_medida = db.relationship("UnidadMedida")

    # Sin IVA. El precio unitario es el neto, después de todos los descuentos.
    precio_lista = db.Column(db.Float, nullable=True, info={"label": "Precio de lista"})
    descuento_pct = db.Column(db.Float, nullable=True, info={"label": "Descuento (%)"})
    precio_unitario = db.Column(db.Float, nullable=False, info={"label": "Precio unitario (neto)"})

    activo_id = db.Column(db.Integer, db.ForeignKey("activos.activo_id"), nullable=True, info={"label": "Activo"})
    activo = db.relationship("Activo")
    confianza = db.Column(db.Float, nullable=True, info={"label": "Confianza"})
    motivo_revision = db.Column(db.String(300), nullable=True, info={"label": "A revisar (lectura)"})

    creado_en = db.Column(db.DateTime, default=datetime.utcnow)
    actualizado_en = db.Column(db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    subtotal = column_property(cantidad * precio_unitario, info={"label": "Subtotal"})

    @property
    def se_cuenta_en(self) -> str | None:
        m = self.material
        if m is not None and m.material_generico_id is not None:
            contenido = f"{m.presentacion_cantidad:g} {m.unidad_medida.abreviatura}" if m.unidad_medida else ""
            return f"envases ({contenido})".replace(" ()", "")
        if self.unidad_medida is not None:
            return self.unidad_medida.nombre_unidad
        return self.udm_texto


class Adjudicacion(db.Model, ModelMixin, AuditMixin):
    __tablename__ = "adjudicaciones"
    __label_field__ = None
    __table_args__ = (db.UniqueConstraint("documento_linea_id", "pedido_linea_id"),)

    adjudicacion_id = db.Column(db.Integer, primary_key=True, autoincrement=True)
    uuid = db.Column(db.String(36), default=lambda: str(uuid.uuid4()), unique=True, nullable=False)

    # Al borrar la línea de la oferta se borran sus adjudicaciones.
    documento_linea_id = db.Column(db.Integer, db.ForeignKey("documento_lineas.documento_linea_id"),
                                   nullable=False, info={"label": "Línea de la oferta"})
    documento_linea = db.relationship(
        "DocumentoLinea", lazy="joined", backref=db.backref("adjudicaciones", cascade="all, delete"))
    # Sin backref: una línea de pedido con adjudicaciones no se puede borrar.
    pedido_linea_id = db.Column(db.Integer, db.ForeignKey("pedido_lineas.pedido_linea_id"),
                                nullable=False, info={"label": "Línea de pedido"})
    pedido_linea = db.relationship("PedidoLinea", lazy="joined")

    # En la unidad de la línea de oferta (envases, si es una presentación).
    cantidad_ofertada = db.Column(db.Float, nullable=True, info={"label": "Cantidad ofertada"})
    cantidad_adjudicada = db.Column(db.Float, nullable=False, default=0,
                                    info={"label": "Cantidad adjudicada (0 = cotizado)"})

    creado_en = db.Column(db.DateTime, default=datetime.utcnow)
    actualizado_en = db.Column(db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)


# ---------------------------------------------------------------------------
# Conversión de unidades (línea de oferta → línea de pedido)
# ---------------------------------------------------------------------------

_dl = DocumentoLinea.__table__.alias("conv_dl")
_pl = PedidoLinea.__table__.alias("conv_pl")
_mat_dl = Material.__table__.alias("conv_mat_dl")
_mat_pl = Material.__table__.alias("conv_mat_pl")


def factor_conversion(tabla_adjudicaciones):
    """
    Cuánto vale 1 unidad de la línea de oferta en la unidad de la línea de pedido,
    para una fila de `tabla_adjudicaciones`: el contenido del envase si la línea
    de pedido pide un genérico y la oferta es una presentación suya; si no, 1.
    """
    return (
        select(func.coalesce(case(
            (and_(_mat_pl.c.es_generico.is_(True), _mat_dl.c.material_generico_id == _mat_pl.c.material_id),
             _mat_dl.c.presentacion_cantidad),
            else_=1.0,
        ), 1.0))
        .select_from(
            _dl.outerjoin(_mat_dl, _mat_dl.c.material_id == _dl.c.material_id),
        )
        .join(_pl, _pl.c.pedido_linea_id == tabla_adjudicaciones.c.pedido_linea_id)
        .outerjoin(_mat_pl, _mat_pl.c.material_id == _pl.c.material_id)
        .where(_dl.c.documento_linea_id == tabla_adjudicaciones.c.documento_linea_id)
        .correlate(tabla_adjudicaciones)
        .scalar_subquery()
    )


_adj = Adjudicacion.__table__

# En la adjudicación: la adjudicada convertida a la unidad de la línea de pedido.
Adjudicacion.adjudicada_en_pedido = column_property(
    Adjudicacion.cantidad_adjudicada * factor_conversion(_adj),
    info={"label": "Adjudicada (unidad del pedido)"},
)

# En la línea de oferta: lo adjudicado (en su unidad).
DocumentoLinea.adjudicada = column_property(
    select(func.coalesce(func.sum(_adj.c.cantidad_adjudicada), 0.0))
    .where(_adj.c.documento_linea_id == DocumentoLinea.documento_linea_id)
    .correlate_except(_adj)
    .scalar_subquery(),
    info={"label": "Adjudicada"},
)

# En la línea de pedido: ofertada y adjudicada, en su unidad.
_adj_o = _adj.alias("ofertas_pl")
_dl_o = DocumentoLinea.__table__.alias("ofertas_dl")
PedidoLinea.ofertada = column_property(
    select(func.coalesce(func.sum(
        func.coalesce(_adj_o.c.cantidad_ofertada, _dl_o.c.cantidad) * factor_conversion(_adj_o)
    ), 0.0))
    .select_from(_adj_o.join(_dl_o, _dl_o.c.documento_linea_id == _adj_o.c.documento_linea_id))
    .where(_adj_o.c.pedido_linea_id == PedidoLinea.pedido_linea_id)
    .correlate_except(_adj_o, _dl_o)
    .scalar_subquery(),
    info={"label": "Ofertada"},
)
_adj_a = _adj.alias("adjudicadas_pl")
PedidoLinea.adjudicada = column_property(
    select(func.coalesce(func.sum(_adj_a.c.cantidad_adjudicada * factor_conversion(_adj_a)), 0.0))
    .where(_adj_a.c.pedido_linea_id == PedidoLinea.pedido_linea_id)
    .correlate_except(_adj_a)
    .scalar_subquery(),
    info={"label": "Adjudicada"},
)
# «Pendiente de comprar», «comprado», lo recibido y el estado visible de la línea
# de pedido están en app/models/recepciones_models.py (dependen de las recepciones).

# En el documento: total de sus líneas, diferencia con el total sin IVA (control
# de carga) y total adjudicado.
_dl_t = DocumentoLinea.__table__.alias("totales_dl")
DocumentoProveedor.total_lineas = column_property(
    select(func.coalesce(func.sum(_dl_t.c.cantidad * _dl_t.c.precio_unitario), 0.0))
    .where(_dl_t.c.documento_id == DocumentoProveedor.documento_id)
    .correlate_except(_dl_t)
    .scalar_subquery(),
    info={"label": "Total de líneas"},
)
DocumentoProveedor.diferencia = column_property(
    DocumentoProveedor.total_sin_iva - DocumentoProveedor.total_lineas.expression,
    info={"label": "Diferencia con el total sin IVA"},
)
_dl_a = DocumentoLinea.__table__.alias("adjudicado_dl")
_adj_d = _adj.alias("adjudicado_adj")
DocumentoProveedor.total_adjudicado = column_property(
    select(func.coalesce(func.sum(_adj_d.c.cantidad_adjudicada * _dl_a.c.precio_unitario), 0.0))
    .select_from(_adj_d.join(_dl_a, _dl_a.c.documento_linea_id == _adj_d.c.documento_linea_id))
    .where(_dl_a.c.documento_id == DocumentoProveedor.documento_id)
    .correlate_except(_adj_d, _dl_a)
    .scalar_subquery(),
    info={"label": "Total adjudicado"},
)

# ---------------------------------------------------------------------------
# Cómo se muestran
# ---------------------------------------------------------------------------

_TIPO_TEXTO = case(*[(DocumentoProveedor.tipo == o["value"], o["label"]) for o in TIPOS_DOCUMENTO],
                   else_=DocumentoProveedor.tipo)

# «Oferta 0003-00013508 — Venturino SA» (sin número: la fecha).
DocumentoProveedor.nombre = column_property(
    _TIPO_TEXTO + " "
    + func.coalesce(DocumentoProveedor.numero, cast(DocumentoProveedor.fecha, String), "s/n")
    + " — "
    + func.coalesce(
        select(Proveedor.razon_social)
        .where(Proveedor.recurso_id == DocumentoProveedor.proveedor_id)
        .correlate_except(Proveedor)
        .scalar_subquery(),
        DocumentoProveedor.proveedor_texto,
        "?",
    ),
    info={"label": "Documento"},
)

_doc_n = DocumentoProveedor.__table__.alias("nombre_doc")
_prov_n = Proveedor.__table__.alias("nombre_prov")
_mat_n = Material.__table__.alias("nombre_mat")
# «0003-00013508 / 2 — RE504836 — Filtro de aceite» (o la descripción del proveedor).
DocumentoLinea.nombre = column_property(
    select(
        func.coalesce(_doc_n.c.numero, cast(_doc_n.c.fecha, String), "s/n")
        + " / " + cast(DocumentoLinea.nro_linea, String) + " — "
        + func.coalesce(
            select(_mat_n.c.codigo + " — " + _mat_n.c.descripcion)
            .where(_mat_n.c.material_id == DocumentoLinea.material_id)
            .correlate_except(_mat_n)
            .scalar_subquery(),
            DocumentoLinea.descripcion_proveedor,
            "",
        )
        + " (" + func.coalesce(
            select(_prov_n.c.razon_social).where(_prov_n.c.recurso_id == _doc_n.c.proveedor_id)
            .correlate_except(_prov_n).scalar_subquery(),
            _doc_n.c.proveedor_texto, "?",
        ) + ")"
    )
    .where(_doc_n.c.documento_id == DocumentoLinea.documento_id)
    .correlate_except(_doc_n)
    .scalar_subquery(),
    info={"label": "Línea de documento"},
)

# A revisar: una línea de material sin el material identificado.
DocumentoLinea.a_revisar = column_property(
    case((and_(DocumentoLinea.tipo_linea == "material", DocumentoLinea.material_id.is_(None)), "Sí"), else_="No"),
    info={"label": "A revisar"},
)

