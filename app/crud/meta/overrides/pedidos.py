"""
Pedidos de materiales: cabecera, líneas y destinos (fase 10, PR 10.3).
Modelos en app/models/pedidos_models.py; diseño en docs/diseno_tablas_operativas.md.

Reglas (se verifican al guardar, en la web, la API y la importación):

  * La línea tiene un material o, si todavía no se identificó, la descripción tal
    como se pidió. Su unidad es la del material (se completa sola).
  * Al crear una línea se pide la cantidad y el destino principal: con eso se
    crea su primer destino. Para repartir entre varios destinos se usa la
    pestaña «Destinos». La cantidad solicitada es la suma de los destinos.
  * Anular una línea o cancelar parte de ella pide un motivo (de tipo «Anulación»).
  * El nº de OC se guarda sin espacios y en mayúsculas (es la llave de cruce).
  * Destino: un activo, un modelo, el stock de un taller (ubicación), gasto
    general o «a identificar». El sector imputado y la cuenta, si llegan vacíos,
    se completan con la sugerencia; si no hay de dónde, quedan «a revisar».
"""
from __future__ import annotations

import re

from app.core.db import db
from app.crud.core.coercion import ErroresValidacion
from app.models.activos_models import Activo
from app.models.marcas_modelos_models import Modelo
from app.models.motivos_models import MotivoOperacion
from app.models.pedidos_models import (
    CANALES,
    DESTINOS,
    ESTADOS_LINEA,
    PRIORIDADES,
    Pedido,
    PedidoLinea,
    PedidoLineaDestino,
)
from app.models.ubicaciones_models import Ubicacion

TIPO_MOTIVO_ANULACION = "ANULACION"
NO_SI = [{"value": False, "label": "No"}, {"value": True, "label": "Sí"}]

# Qué dato pide cada tipo de destino.
DATO_DEL_DESTINO = {"activo": "activo_id", "modelo": "modelo_id", "stock": "ubicacion_id"}


def motivos_de_anulacion():
    return MotivoOperacion.tipo_operacion == TIPO_MOTIVO_ANULACION


def normalizar_oc(texto):
    """« oc 4500 12 » → «OC450012»: sin espacios y en mayúsculas."""
    if texto is None:
        return None
    return re.sub(r"\s+", "", str(texto)).upper() or None


def _valor(datos: dict, registro, campo):
    if campo in datos:
        return datos[campo]
    return getattr(registro, campo, None) if registro is not None else None


# ---------------------------------------------------------------------------
# Sugerencias de imputación
# ---------------------------------------------------------------------------

def _cuenta_de_categoria_activo(categoria):
    tipo = categoria.tipo_activo if categoria is not None else None
    return tipo.cuenta_id if tipo is not None else None


def sector_sugerido(activo, ubicacion, linea):
    """Sector del activo; si no, el de la ubicación; si no, el del pedido."""
    if activo is not None and activo.sector_id:
        return activo.sector_id
    if ubicacion is not None and ubicacion.sector_id:
        return ubicacion.sector_id
    if linea is not None and linea.pedido is not None:
        return linea.pedido.sector_id
    return None


def cuenta_sugerida(activo, modelo, linea):
    """Cuenta del tipo de activo (del activo o del modelo); si no, la de la categoría del material."""
    if activo is not None:
        return _cuenta_de_categoria_activo(activo.categoria_activo)
    if modelo is not None:
        return _cuenta_de_categoria_activo(modelo.categoria_activo)
    material = linea.material if linea is not None else None
    if material is not None and material.categoria_material is not None:
        return material.categoria_material.cuenta_id
    return None


# ---------------------------------------------------------------------------
# Línea de pedido
# ---------------------------------------------------------------------------

def completar_linea(datos: dict, registro):
    if "nro_oc" in datos:
        datos["nro_oc"] = normalizar_oc(datos["nro_oc"])
    return datos


def al_guardar_linea(linea, operacion: str, cambiados: set):
    errores = {}
    if linea.material_id is None and not (linea.descripcion or "").strip():
        errores["material_id"] = "Elegí el material o escribí la descripción tal como se pidió."
    if linea.cantidad_cancelada is not None and linea.cantidad_cancelada < 0:
        errores["cantidad_cancelada"] = "La cantidad cancelada no puede ser negativa."
    necesita_motivo = linea.estado == "anulado" or (linea.cantidad_cancelada or 0) > 0
    if necesita_motivo and linea.motivo_operacion_id is None:
        errores["motivo_operacion_id"] = "Indicá el motivo de la anulación o la cancelación."
    if errores:
        raise ErroresValidacion(errores)

    # Primer destino, con la cantidad y el destino principal del alta.
    alta = getattr(linea, "datos_alta", None) or {}
    if operacion == "INSERT" and alta.get("cantidad") is not None:
        from app.crud.entidades import servicio

        servicio("pedido_linea_destinos", confirmar=False).crear({
            "pedido_linea_id": linea.pedido_linea_id,
            "cantidad": alta["cantidad"],
            "destino": alta.get("destino") or "a_identificar",
            "activo_id": alta.get("activo_id"),
            "modelo_id": alta.get("modelo_id"),
            "ubicacion_id": alta.get("ubicacion_id"),
        }, "Destino principal de la línea")
        db.session.refresh(linea)

    solicitada = linea.solicitada or 0
    if solicitada and (linea.cantidad_cancelada or 0) > solicitada:
        raise ErroresValidacion({"cantidad_cancelada": (
            f"No se puede cancelar más de lo solicitado ({solicitada:g})."
        )})
    return None


# ---------------------------------------------------------------------------
# Destino
# ---------------------------------------------------------------------------

def completar_destino(datos: dict, registro):
    """Completa el sector imputado y la cuenta vacíos con la sugerencia."""
    def obj(model, campo):
        v = _valor(datos, registro, campo)
        return db.session.get(model, v) if v is not None else None

    activo, modelo, ubicacion = obj(Activo, "activo_id"), obj(Modelo, "modelo_id"), obj(Ubicacion, "ubicacion_id")
    linea = obj(PedidoLinea, "pedido_linea_id")
    if _valor(datos, registro, "sector_imputado_id") is None:
        sugerido = sector_sugerido(activo, ubicacion, linea)
        if sugerido is not None:
            datos["sector_imputado_id"] = sugerido
    if _valor(datos, registro, "cuenta_id") is None:
        sugerida = cuenta_sugerida(activo, modelo, linea)
        if sugerida is not None:
            datos["cuenta_id"] = sugerida
    return datos


def al_guardar_destino(d, operacion: str, cambiados: set):
    errores = {}
    if d.cantidad is None or d.cantidad <= 0:
        errores["cantidad"] = "La cantidad tiene que ser mayor que cero."
    dato = DATO_DEL_DESTINO.get(d.destino)
    if dato and getattr(d, dato) is None:
        etiqueta = next(o["label"] for o in DESTINOS if o["value"] == d.destino).lower()
        nombre = {"activo_id": "el activo", "modelo_id": "el modelo", "ubicacion_id": "la ubicación (taller que recibe)"}
        errores[dato] = f"Un destino «{etiqueta}» necesita {nombre[dato]}."
    if errores:
        raise ErroresValidacion(errores)
    return None


# ---------------------------------------------------------------------------
# Entidades
# ---------------------------------------------------------------------------

OVERRIDES = {
    "pedidos": {
        "model": Pedido,
        "label_singular": "pedido",
        "label_plural": "pedidos",
        "genero": "m",
        "sidebar": True,
        "grupo": "operativos",
        "orden": 10,
        "fields": {
            "numero": {"numeracion": "{n}"},
            "canal": {"tipo": "select", "options": CANALES},
            "prioridad": {"tipo": "select", "options": PRIORIDADES, "required": False},
            # Se puede pedir para otro sector: el solicitante no filtra ni corrige el sector.
            "solicitante_id": {"depende_de": None},
        },
        "listado": ["numero", "fecha_pedido", "referencia", "sector_id", "prioridad", "resumen"],
        "filtros": ["numero", "referencia", "solicitante_texto", "solicitante_id", "sector_id", "canal",
                    "prioridad", "observaciones"],
        # El número identifica al pedido (también en el Excel histórico).
        "clave_natural": ["numero"],
    },
    "pedido_lineas": {
        "model": PedidoLinea,
        "label_singular": "línea de pedido",
        "label_plural": "líneas de pedido",
        "genero": "f",
        "padre": [
            {"entidad": "pedidos", "fk": "pedido_id", "label": "Líneas"},
            {"entidad": "materiales", "fk": "material_id", "label": "Pedidos"},
        ],
        "fields": {
            "nro_linea": {"numeracion": "{n}", "numeracion_por": "pedido_id"},
            "estado": {"tipo": "select", "options": ESTADOS_LINEA, "required": False},
            "sin_conformidad": {"required": False, "options": NO_SI},
            "cantidad_cancelada": {"required": False},
            "motivo_operacion_id": {"fk_filtro": motivos_de_anulacion},
        },
        # Solo en el alta: con esto se crea el primer destino.
        "campos_alta": {
            "cantidad": {"label": "Cantidad", "tipo": "number", "required": True},
            "destino": {"label": "Destino", "tipo": "select", "options": DESTINOS, "required": True},
            "activo_id": {"label": "Activo", "tipo": "fk", "fk_model": Activo},
            "modelo_id": {"label": "Modelo", "tipo": "fk", "fk_model": Modelo},
            "ubicacion_id": {"label": "Ubicación (taller que recibe)", "tipo": "fk", "fk_model": Ubicacion},
        },
        # En el alta, la cantidad y el destino van junto al material.
        "orden_campos": ["pedido_id", "nro_linea", "material_id", "descripcion", "unidad_medida_id",
                         "cantidad", "destino", "activo_id", "modelo_id", "ubicacion_id"],
        "excluir": ["nombre"],
        "listado": ["pedido_id", "nro_linea", "material_id", "descripcion", "solicitada", "se_cuenta_en",
                    "estado", "nro_oc"],
        "filtros": ["material_id", "descripcion", "estado", "nro_oc", "observaciones"],
        "clave_natural": ["pedido_id", "nro_linea"],
        "completar": completar_linea,
        "al_guardar": al_guardar_linea,
    },
    "pedido_linea_destinos": {
        "model": PedidoLineaDestino,
        "label_singular": "destino",
        "label_plural": "destinos de pedidos",
        "genero": "m",
        "padre": [
            {"entidad": "pedido_lineas", "fk": "pedido_linea_id", "label": "Destinos"},
            {"entidad": "activos", "fk": "activo_id", "label": "Pedidos"},
        ],
        "fields": {
            "destino": {"tipo": "select", "options": DESTINOS, "required": False},
            # El activo y la ubicación no filtran ni corrigen el sector imputado:
            # quien paga puede ser otro sector (préstamos de activos).
            "activo_id": {"depende_de": None},
            "ubicacion_id": {"depende_de": None},
        },
        "listado": ["pedido_linea_id", "cantidad", "destino", "activo_id", "modelo_id", "ubicacion_id",
                    "sector_imputado_id", "cuenta_id", "a_revisar"],
        "completar": completar_destino,
        "al_guardar": al_guardar_destino,
    },
}
