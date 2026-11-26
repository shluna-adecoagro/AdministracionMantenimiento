# app/models/recepciones_models.py
"""
Recepciones: la conformidad de lo que llegó (fase 10, PR 10.5).
Diseño: docs/diseno_tablas_operativas.md.

    pedido_linea_destinos ──< recepciones >── materiales (lo que llegó)

Una fila por entrega y por destino (admite entregas parciales). La cantidad va
en la unidad del material recibido (envases, si es una presentación); del lado
del pedido se convierte a la unidad de la línea, igual que la adjudicación.

Acá también se calculan, para la línea de pedido, lo comprado, lo recibido, los
pendientes y el ESTADO VISIBLE (ver «Estado de la línea de pedido» en el diseño):
se guarda solo lo que no deja otro rastro y lo demás sale de los datos.
"""
import uuid
from datetime import date, datetime

from sqlalchemy import and_, case, func, or_, select
from sqlalchemy.orm import column_property

from app.core.db import db
from app.crud.audit_mixin import AuditMixin
from app.crud.model_mixin import ModelMixin
from app.models.documentos_models import Adjudicacion, DocumentoLinea, DocumentoProveedor
from app.models.materiales_models import Material
from app.models.pedidos_models import ESTADOS_LINEA, PedidoLinea, PedidoLineaDestino

_EPS = 1e-9


class Recepcion(db.Model, ModelMixin, AuditMixin):
    __tablename__ = "recepciones"
    __label_field__ = None
    __calculados__ = {"se_cuenta_en": "Se cuenta en"}

    recepcion_id = db.Column(db.Integer, primary_key=True, autoincrement=True)
    uuid = db.Column(db.String(36), default=lambda: str(uuid.uuid4()), unique=True, nullable=False)

    # Sin cascada: un destino con recepciones no se puede borrar (es historial).
    pedido_linea_destino_id = db.Column(
        db.Integer, db.ForeignKey("pedido_linea_destinos.pedido_linea_destino_id"), nullable=False,
        info={"label": "Destino"},
    )
    destino = db.relationship("PedidoLineaDestino", lazy="joined",
                              backref=db.backref("recepciones", passive_deletes="all"))
    fecha = db.Column(db.Date, nullable=False, default=date.today, info={"label": "Fecha"})

    # Lo que llegó: siempre una presentación (o un material concreto), nunca un
    # genérico. Si se deja vacío, el adjudicado. Sin backref: no se puede borrar.
    material_id = db.Column(db.Integer, db.ForeignKey("materiales.material_id"), nullable=False,
                            info={"label": "Material recibido"})
    material = db.relationship("Material", lazy="joined")
    # En la unidad del material recibido. Si se deja vacía, lo pendiente del destino.
    cantidad = db.Column(db.Float, nullable=False, info={"label": "Cantidad (envases, si es una presentación)"})

    recibido_por_id = db.Column(db.Integer, db.ForeignKey("empleados.recurso_id"), nullable=True,
                                info={"label": "Recibido por"})
    recibido_por = db.relationship("Empleado")
    # Línea del remito, si se cargó (sin backref: una línea de remito recibida no se borra).
    documento_linea_id = db.Column(db.Integer, db.ForeignKey("documento_lineas.documento_linea_id"),
                                   nullable=True, info={"label": "Línea del remito"})
    documento_linea = db.relationship("DocumentoLinea")
    observaciones = db.Column(db.String(300), nullable=True, info={"label": "Observaciones (faltantes, roturas)"})

    creado_en = db.Column(db.DateTime, default=datetime.utcnow)
    actualizado_en = db.Column(db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    @property
    def se_cuenta_en(self) -> str | None:
        m = self.material
        if m is None:
            return None
        if m.material_generico_id is not None:
            contenido = f"{m.presentacion_cantidad:g} {m.unidad_medida.abreviatura}" if m.unidad_medida else ""
            return f"envases ({contenido})".replace(" ()", "")
        return m.unidad_medida.nombre_unidad if m.unidad_medida else None


# ---------------------------------------------------------------------------
# Conversión: material recibido → unidad de la línea de pedido
# ---------------------------------------------------------------------------

_rec = Recepcion.__table__
_d = PedidoLineaDestino.__table__.alias("conv_rec_destino")
_l = PedidoLinea.__table__.alias("conv_rec_linea")
_m_rec = Material.__table__.alias("conv_rec_mat")
_m_lin = Material.__table__.alias("conv_rec_mat_linea")


def factor_recepcion(tabla):
    """Contenido del envase si la línea pide un genérico y llegó una presentación suya; si no, 1."""
    return (
        select(func.coalesce(case(
            (and_(_m_lin.c.es_generico.is_(True), _m_rec.c.material_generico_id == _m_lin.c.material_id),
             _m_rec.c.presentacion_cantidad),
            else_=1.0,
        ), 1.0))
        .select_from(_m_rec)
        .join(_d, _d.c.pedido_linea_destino_id == tabla.c.pedido_linea_destino_id)
        .join(_l, _l.c.pedido_linea_id == _d.c.pedido_linea_id)
        .outerjoin(_m_lin, _m_lin.c.material_id == _l.c.material_id)
        .where(_m_rec.c.material_id == tabla.c.material_id)
        .correlate(tabla)
        .scalar_subquery()
    )


Recepcion.recibida_en_linea = column_property(
    Recepcion.cantidad * factor_recepcion(_rec),
    info={"label": "Recibida (unidad del pedido)"},
)


# ---------------------------------------------------------------------------
# Línea de pedido: comprado, recibido, pendientes y estado visible
# ---------------------------------------------------------------------------

_r = _rec.alias("recibida_rec")
_dr = PedidoLineaDestino.__table__.alias("recibida_destino")
PedidoLinea.recibida = column_property(
    select(func.coalesce(func.sum(_r.c.cantidad * factor_recepcion(_r)), 0.0))
    .select_from(_r.join(_dr, _dr.c.pedido_linea_destino_id == _r.c.pedido_linea_destino_id))
    .where(_dr.c.pedido_linea_id == PedidoLinea.pedido_linea_id)
    .correlate_except(_r, _dr)
    .scalar_subquery(),
    info={"label": "Recibida"},
)

_adj = Adjudicacion.__table__
_adj_hay = _adj.alias("hay_adj")
_hay_adjudicaciones = (
    select(_adj_hay.c.adjudicacion_id)
    .where(_adj_hay.c.pedido_linea_id == PedidoLinea.pedido_linea_id)
    .correlate_except(_adj_hay)
    .exists()
)

# Comprado: lo adjudicado si hay adjudicaciones; si no (compra directa o
# histórico), lo solicitado menos lo cancelado, pero solo si ya hay OC o
# recepciones (si no, todavía no se compró nada).
_solicitada = PedidoLinea.solicitada.expression
_adjudicada = PedidoLinea.adjudicada.expression
_recibida = PedidoLinea.recibida.expression
PedidoLinea.comprado = column_property(
    case(
        (_hay_adjudicaciones, _adjudicada),
        (or_(PedidoLinea.nro_oc.isnot(None), _recibida > 0), _solicitada - PedidoLinea.cantidad_cancelada),
        else_=0.0,
    ),
    info={"label": "Comprada"},
)
_comprado = PedidoLinea.comprado.expression
PedidoLinea.pendiente_comprar = column_property(
    _solicitada - PedidoLinea.cantidad_cancelada - _comprado,
    info={"label": "Pendiente de comprar"},
)
PedidoLinea.pendiente_recibir = column_property(
    _comprado - _recibida,
    info={"label": "Pendiente de recibir"},
)

# ¿Tiene OC? La propia, o la de una oferta adjudicada (con cantidad).
_dl = DocumentoLinea.__table__.alias("oc_dl")
_doc = DocumentoProveedor.__table__.alias("oc_doc")
_adj_oc = _adj.alias("oc_adj")
_tiene_oc = or_(
    PedidoLinea.nro_oc.isnot(None),
    select(_adj_oc.c.adjudicacion_id)
    .select_from(_adj_oc.join(_dl, _dl.c.documento_linea_id == _adj_oc.c.documento_linea_id)
                 .join(_doc, _doc.c.documento_id == _dl.c.documento_id))
    .where(_adj_oc.c.pedido_linea_id == PedidoLinea.pedido_linea_id,
           _adj_oc.c.cantidad_adjudicada > 0, _doc.c.nro_oc.isnot(None))
    .correlate_except(_adj_oc, _dl, _doc)
    .exists(),
)

_pend_comprar = PedidoLinea.pendiente_comprar.expression
_pend_recibir = PedidoLinea.pendiente_recibir.expression
_GUARDADO = case(*[(PedidoLinea.estado == o["value"], o["label"]) for o in ESTADOS_LINEA],
                 else_=PedidoLinea.estado)

# Estado visible, en orden de prioridad («Borrador»: todavía no se envió a
# Compras). Es el que se muestra; el guardado solo
# cuenta mientras no haya datos posteriores (adjudicaciones, OC, recepciones).
PedidoLinea.estado_visible = column_property(
    case(
        (PedidoLinea.estado == "anulado", "Anulado"),
        (PedidoLinea.enviada_en.is_(None), "Borrador"),
        (PedidoLinea.sin_conformidad.is_(True), "Cerrado"),
        (and_(_solicitada > 0, _pend_comprar <= _EPS, _pend_recibir <= _EPS), "Cerrado"),
        (and_(_recibida > 0, _pend_recibir <= _EPS), "Recibido"),
        (_recibida > 0, "Recibido parcial"),
        (_tiene_oc, "OC emitida"),
        (_adjudicada > 0, "Adjudicado"),
        else_=_GUARDADO,
    ),
    info={"label": "Estado"},
)

# Salteo: la línea avanzó (adjudicada o más) sin haber pasado por «en cotización».
PedidoLinea.estado_salteado = column_property(
    case(
        (and_(PedidoLinea.estado == "solicitado",
              PedidoLinea.estado_visible.expression.notin_(["Solicitado", "Anulado"])), "Sí"),
        else_="No",
    ),
    info={"label": "Salteó estados"},
)
