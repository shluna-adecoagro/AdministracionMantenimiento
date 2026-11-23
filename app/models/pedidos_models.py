# app/models/pedidos_models.py
"""
Pedidos de materiales (fase 10, PR 10.3). Diseño: docs/diseno_tablas_operativas.md.

    pedidos ──< pedido_lineas ──< pedido_linea_destinos

  * El pedido es la cabecera (número de la serie del Excel, fecha, quién y para
    qué sector). Su estado no se guarda: es el resumen de sus líneas.
  * La línea es lo que se compra y se cotiza: un material (o la descripción tal
    como se pidió) y su estado de seguimiento.
  * El destino dice adónde va y quién paga (activo, modelo, stock de un taller o
    gasto general, con sector imputado y cuenta). La cantidad solicitada de la
    línea es la suma de sus destinos (calculada, sin columna).

Todas las cantidades del lado del pedido están en la unidad de la línea: la del
material o, si el material es una presentación, envases de esa presentación.

Las reglas (sugerencias de imputación, primer destino, motivo de anulación)
están en app/crud/meta/overrides/pedidos.py.
"""
import uuid
from datetime import date, datetime

from sqlalchemy import String, cast, func, select
from sqlalchemy.orm import column_property

from app.core.db import db
from app.crud.audit_mixin import AuditMixin
from app.crud.model_mixin import ModelMixin
from app.crud.origen_mixin import OrigenMixin

# Estados de flujo: opciones fijas en código (las reglas dependen de ellos).
CANALES = (
    {"value": "whatsapp", "label": "WhatsApp"},
    {"value": "mail", "label": "Mail"},
    {"value": "site", "label": "Site"},
    {"value": "app", "label": "App"},
)
PRIORIDADES = (
    {"value": "normal", "label": "Normal"},
    {"value": "urgente", "label": "Urgente"},
)
# Estados que se guardan; el resto (adjudicado, OC emitida, recibido, cerrado)
# se calcula a partir de los datos (PR 10.4 y 10.5).
ESTADOS_LINEA = (
    {"value": "solicitado", "label": "Solicitado"},
    {"value": "en_cotizacion", "label": "En cotización"},
    {"value": "ofertas_cargadas", "label": "Ofertas cargadas"},
    {"value": "anulado", "label": "Anulado"},
)
DESTINOS = (
    {"value": "activo", "label": "Activo"},
    {"value": "modelo", "label": "Modelo"},
    {"value": "stock", "label": "Stock"},
    {"value": "gasto_general", "label": "Gasto general"},
    {"value": "a_identificar", "label": "A identificar"},
)

_ESTADO_PLURAL = {
    "solicitado": ("solicitada", "solicitadas"),
    "en_cotizacion": ("en cotización", "en cotización"),
    "ofertas_cargadas": ("con ofertas cargadas", "con ofertas cargadas"),
    "anulado": ("anulada", "anuladas"),
}


class Pedido(db.Model, ModelMixin, AuditMixin, OrigenMixin):
    __tablename__ = "pedidos"
    __label_field__ = "numero"
    __calculados__ = {"resumen": "Resumen"}

    pedido_id = db.Column(db.Integer, primary_key=True, autoincrement=True)
    uuid = db.Column(db.String(36), default=lambda: str(uuid.uuid4()), unique=True, nullable=False)

    # Sigue la serie del Excel (1104, 1107...): si se deja vacío, se numera solo.
    numero = db.Column(db.String(20), nullable=False, unique=True, info={"label": "Número"})
    fecha_pedido = db.Column(db.Date, nullable=False, default=date.today, info={"label": "Fecha del pedido"})
    referencia = db.Column(db.String(150), nullable=True, info={"label": "Referencia"})

    # Sin backref: un empleado o un sector con pedidos no se puede borrar.
    solicitante_id = db.Column(db.Integer, db.ForeignKey("empleados.recurso_id"), nullable=True,
                               info={"label": "Solicitante"})
    solicitante = db.relationship("Empleado")
    solicitante_texto = db.Column(db.String(150), nullable=True, info={"label": "Solicitante (texto)"})
    sector_id = db.Column(db.Integer, db.ForeignKey("sectores.sector_id"), nullable=True,
                          info={"label": "Sector que pide"})
    sector = db.relationship("Sector")

    canal = db.Column(db.String(20), nullable=True, info={"label": "Canal"})
    prioridad = db.Column(db.String(20), nullable=False, default="normal", info={"label": "Prioridad"})
    fecha_requerida = db.Column(db.Date, nullable=True, info={"label": "Fecha requerida"})
    observaciones = db.Column(db.String(300), nullable=True)

    creado_en = db.Column(db.DateTime, default=datetime.utcnow)
    actualizado_en = db.Column(db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    @property
    def resumen(self) -> str:
        """«5 líneas: 3 en cotización, 2 solicitadas» (hasta el PR 10.5, por estado guardado)."""
        lineas = self.lineas
        if not lineas:
            return "Sin líneas"
        conteo: dict[str, int] = {}
        for linea in lineas:
            conteo[linea.estado] = conteo.get(linea.estado, 0) + 1
        partes = []
        for opcion in ESTADOS_LINEA:
            n = conteo.get(opcion["value"])
            if n:
                singular, plural = _ESTADO_PLURAL[opcion["value"]]
                partes.append(f"{n} {singular if n == 1 else plural}")
        total = len(lineas)
        return f"{total} línea{'s' if total != 1 else ''}: {', '.join(partes)}"


class PedidoLinea(db.Model, ModelMixin, AuditMixin, OrigenMixin):
    __tablename__ = "pedido_lineas"
    __label_field__ = "nombre"
    __table_args__ = (db.UniqueConstraint("pedido_id", "nro_linea"),)
    __calculados__ = {"se_cuenta_en": "Se cuenta en"}

    pedido_linea_id = db.Column(db.Integer, primary_key=True, autoincrement=True)
    uuid = db.Column(db.String(36), default=lambda: str(uuid.uuid4()), unique=True, nullable=False)

    # Al borrar el pedido se borran sus líneas.
    pedido_id = db.Column(db.Integer, db.ForeignKey("pedidos.pedido_id"), nullable=False,
                          info={"label": "Pedido"})
    pedido = db.relationship("Pedido", lazy="joined",
                             backref=db.backref("lineas", cascade="all, delete",
                                                order_by="PedidoLinea.nro_linea"))
    # Se numera sola dentro del pedido.
    nro_linea = db.Column(db.Integer, nullable=False, info={"label": "Línea"})

    # El material, si se identificó; si no, la descripción tal como se pidió.
    # Sin backref: un material pedido no se puede borrar.
    material_id = db.Column(db.Integer, db.ForeignKey("materiales.material_id"), nullable=True,
                            info={"label": "Material"})
    material = db.relationship("Material", lazy="joined")
    descripcion = db.Column(db.String(200), nullable=True, info={"label": "Descripción (como se pidió)"})
    # La del material (se completa sola); a mano solo si no hay material.
    unidad_medida_id = db.Column(db.Integer, db.ForeignKey("unidades_medida.unidad_medida_id"),
                                 nullable=True, info={"label": "Unidad"})
    unidad_medida = db.relationship("UnidadMedida")

    estado = db.Column(db.String(20), nullable=False, default="solicitado", info={"label": "Estado"})
    # Cierre manual del histórico: cerrada sin registro de recepción.
    sin_conformidad = db.Column(db.Boolean, nullable=False, default=False, info={"label": "Sin conformidad"})
    cantidad_cancelada = db.Column(db.Float, nullable=False, default=0, info={"label": "Cantidad cancelada"})
    # Motivo de la anulación o la cancelación (motivos de tipo «Anulación»).
    motivo_operacion_id = db.Column(db.Integer, db.ForeignKey("motivos_operacion.motivo_operacion_id"),
                                    nullable=True, info={"label": "Motivo de anulación"})
    motivo = db.relationship("MotivoOperacion")
    # OC con la que se compró (sin espacios y en mayúsculas: es la llave de cruce).
    nro_oc = db.Column(db.String(30), nullable=True, info={"label": "Nº de OC"})
    observaciones = db.Column(db.String(300), nullable=True)

    creado_en = db.Column(db.DateTime, default=datetime.utcnow)
    actualizado_en = db.Column(db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    @property
    def se_cuenta_en(self) -> str | None:
        """Unidad de las cantidades: envases si el material es una presentación."""
        m = self.material
        if m is not None and m.material_generico_id is not None:
            contenido = f"{m.presentacion_cantidad:g} {m.unidad_medida.abreviatura}" if m.unidad_medida else ""
            return f"envases ({contenido})".replace(" ()", "")
        u = self.unidad_medida
        return u.nombre_unidad if u is not None else None


class PedidoLineaDestino(db.Model, ModelMixin, AuditMixin, OrigenMixin):
    __tablename__ = "pedido_linea_destinos"
    __label_field__ = None

    pedido_linea_destino_id = db.Column(db.Integer, primary_key=True, autoincrement=True)
    uuid = db.Column(db.String(36), default=lambda: str(uuid.uuid4()), unique=True, nullable=False)

    # Al borrar la línea se borran sus destinos.
    pedido_linea_id = db.Column(db.Integer, db.ForeignKey("pedido_lineas.pedido_linea_id"), nullable=False,
                                info={"label": "Línea"})
    pedido_linea = db.relationship("PedidoLinea", lazy="joined",
                                   backref=db.backref("destinos", cascade="all, delete"))

    cantidad = db.Column(db.Float, nullable=False)
    destino = db.Column(db.String(20), nullable=False, default="a_identificar", info={"label": "Destino"})

    # Sin backref: un activo, modelo, ubicación, sector o cuenta usados en un
    # destino no se pueden borrar.
    activo_id = db.Column(db.Integer, db.ForeignKey("activos.activo_id"), nullable=True, info={"label": "Activo"})
    activo = db.relationship("Activo")
    modelo_id = db.Column(db.Integer, db.ForeignKey("modelos.modelo_id"), nullable=True, info={"label": "Modelo"})
    modelo = db.relationship("Modelo")
    ubicacion_id = db.Column(db.Integer, db.ForeignKey("ubicaciones.ubicacion_id"), nullable=True,
                             info={"label": "Ubicación (taller que recibe)"})
    ubicacion = db.relationship("Ubicacion")
    detalle_texto = db.Column(db.String(300), nullable=True, info={"label": "Detalle (como se pidió)"})

    # Quién paga y a qué cuenta. Si llegan vacíos se completan con la sugerencia;
    # si no hay de dónde sugerir, quedan vacíos y el destino figura «a revisar».
    sector_imputado_id = db.Column(db.Integer, db.ForeignKey("sectores.sector_id"), nullable=True,
                                   info={"label": "Sector imputado"})
    sector_imputado = db.relationship("Sector")
    cuenta_id = db.Column(db.Integer, db.ForeignKey("cuentas.cuenta_id"), nullable=True,
                          info={"label": "Cuenta"})
    cuenta = db.relationship("Cuenta")

    creado_en = db.Column(db.DateTime, default=datetime.utcnow)
    actualizado_en = db.Column(db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    # «A revisar»: falta identificar el destino, el sector imputado o la cuenta.
    a_revisar = column_property(
        db.case(
            (db.or_(destino == "a_identificar", sector_imputado_id.is_(None), cuenta_id.is_(None)), "Sí"),
            else_="No",
        ),
        info={"label": "A revisar"},
    )


# Cantidad solicitada: la suma de los destinos (sin columna).
PedidoLinea.solicitada = column_property(
    select(func.coalesce(func.sum(PedidoLineaDestino.cantidad), 0.0))
    .where(PedidoLineaDestino.pedido_linea_id == PedidoLinea.pedido_linea_id)
    .correlate_except(PedidoLineaDestino)
    .scalar_subquery(),
    info={"label": "Solicitada"},
)

# Cómo se muestra una línea: «1104 / 2 — RE504836 — Filtro de aceite».
from app.models.materiales_models import Material  # noqa: E402

PedidoLinea.nombre = column_property(
    select(
        Pedido.numero + " / " + cast(PedidoLinea.nro_linea, String) + " — "
        + func.coalesce(
            select(Material.codigo + " — " + Material.descripcion)
            .where(Material.material_id == PedidoLinea.material_id)
            .correlate_except(Material)
            .scalar_subquery(),
            PedidoLinea.descripcion,
            "",
        )
    )
    .where(Pedido.pedido_id == PedidoLinea.pedido_id)
    .correlate_except(Pedido)
    .scalar_subquery(),
    info={"label": "Línea de pedido"},
)
