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
  * Borrador y envío (fase 13.2): la línea nace en borrador; «Enviar a Compras»
    (acción del pedido) pone `enviada_en`. En borrador se edita todo y se puede
    eliminar; enviada, el material (salvo completarlo si estaba vacío), la
    descripción y las cantidades de los destinos quedan congelados, no se
    agregan ni sacan destinos y no se elimina: se anula o se cancela una parte,
    con motivo (no se anula entera si ya hay algo comprado). El estado de
    seguimiento solo se edita en líneas enviadas, sin compras.
  * Alta rápida (fase 13.3): la última fila de la pestaña «Líneas» crea una línea
    con el material (o la descripción, si no se reconoce), la cantidad y el
    destino (un activo, una ubicación o, vacío, «a identificar»).
  * Destino: un activo, un modelo, el stock de un taller (ubicación), gasto
    general o «a identificar». El sector imputado y la cuenta, si llegan vacíos,
    se completan con la sugerencia; si no hay de dónde, quedan «a revisar».
"""
from __future__ import annotations

import re
from datetime import datetime

from app.core.db import db
from app.crud.core.coercion import ErroresValidacion
from app.crud.core.interpretes import FkEntre, FkOTexto
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
# Lo comprado, recibido, pendientes y estado visible de la línea se definen ahí.
import app.models.recepciones_models  # noqa: E402,F401

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
# Borrador y envío a Compras (fase 13.2): qué se puede editar según la línea
# ---------------------------------------------------------------------------

ENVIADA = "la línea ya se envió a Compras"
_EPS = 1e-9


def en_borrador(linea):
    return True if linea.enviada_en is None else ENVIADA


def enviada(linea):
    return True if linea.enviada_en is not None else "la línea está en borrador"


def material_editable(linea):
    """En borrador, siempre; enviada, solo para completarlo (identificar el material)."""
    if linea.enviada_en is None or linea.material_id is None:
        return True
    return f"{ENVIADA} (solo se puede completar si está vacío)"


def estado_editable(linea):
    """El estado de seguimiento: en líneas enviadas, abiertas y sin compras."""
    if linea.enviada_en is None:
        return "la línea está en borrador (el estado se sigue después de enviarla)"
    if linea.estado == "anulado":
        return "la línea está anulada"
    if linea.sin_conformidad:
        return "la línea está cerrada"
    if (linea.comprado or 0) > _EPS:
        return "ya hay compras: el estado sale de las adjudicaciones, la OC y las recepciones"
    return True


def linea_eliminable(linea):
    return True if linea.enviada_en is None else f"{ENVIADA}: anulala o cancelá una parte, con motivo"


def pedido_eliminable(pedido):
    enviadas = sum(1 for linea in pedido.lineas if linea.enviada_en is not None)
    if not enviadas:
        return True
    return f"tiene {enviadas} línea{'s' if enviadas != 1 else ''} enviada{'s' if enviadas != 1 else ''} a Compras"


def destino_en_borrador(d):
    return en_borrador(d.pedido_linea)


def destino_eliminable(d):
    if d.pedido_linea.enviada_en is None:
        return True
    return f"{ENVIADA}: no se sacan destinos sueltos"


def destino_creable(datos):
    linea = db.session.get(PedidoLinea, datos.get("pedido_linea_id")) if datos.get("pedido_linea_id") else None
    if linea is None or linea.enviada_en is None:
        return True
    return (f"La línea {linea.nombre} ya se envió a Compras: no se le agregan destinos sueltos. "
            "Para pedir más, agregá una línea nueva al pedido.")


def _lineas_para_enviar(pedido):
    return [linea for linea in pedido.lineas if linea.enviada_en is None and linea.estado != "anulado"]


def enviar_a_compras(pedido):
    """Pone `enviada_en` en las líneas en borrador no anuladas. Avisa los destinos «a revisar»."""
    from app.crud.entidades import servicio

    s = servicio("pedido_lineas", confirmar=False)
    ahora = datetime.now().replace(microsecond=0)
    lineas = _lineas_para_enviar(pedido)
    a_revisar = 0
    for linea in lineas:
        s.actualizar(linea, {"enviada_en": ahora}, "Enviar a Compras")
        if any(d.a_revisar == "Sí" for d in linea.destinos):
            a_revisar += 1
    n = len(lineas)
    mensajes = [("ok", f"Se envi{'ó' if n == 1 else 'aron'} {n} línea{'s' if n != 1 else ''} a Compras.")]
    if a_revisar:
        mensajes.append(("aviso", (
            f"{a_revisar} línea{'s' if a_revisar != 1 else ''} tiene{'n' if a_revisar != 1 else ''} destinos "
            "a revisar (a identificar, o sin sector imputado o cuenta). La imputación se puede completar igual.")))
    return mensajes


def anular_o_cancelar(linea, datos):
    """
    Sin cantidad: anula la línea entera (si no hay nada comprado). Con cantidad:
    la suma a la cancelada. Siempre con motivo. Las reglas las aplica el
    servicio (editable_si y al_guardar_linea); acá se adelanta el aviso de que
    con compras no se anula entera, con lo que se puede cancelar.
    """
    from app.crud.entidades import servicio

    motivo = db.session.get(MotivoOperacion, datos["motivo_operacion_id"])
    texto = motivo.nombre_motivo if motivo is not None else "Anulación"
    s = servicio("pedido_lineas", confirmar=False)
    cantidad = datos.get("cantidad")
    comprado = linea.comprado or 0
    if cantidad is None and comprado > _EPS:
        raise ErroresValidacion({"cantidad": (
            f"Ya hay {comprado:g} comprados: la línea no se anula entera. Indicá la cantidad a cancelar "
            f"(hasta {max(linea.pendiente_comprar or 0, 0):g}, lo pendiente de comprar).")})
    if cantidad is None:
        s.actualizar(linea, {"estado": "anulado", "motivo_operacion_id": datos["motivo_operacion_id"]},
                     f"Anulación: {texto}")
        return f"Línea {linea.nro_linea} anulada."
    if cantidad <= 0:
        raise ErroresValidacion({"cantidad": "La cantidad a cancelar tiene que ser mayor que cero."})
    s.actualizar(linea, {"cantidad_cancelada": (linea.cantidad_cancelada or 0) + cantidad,
                         "motivo_operacion_id": datos["motivo_operacion_id"]},
                 f"Cancelación de {cantidad:g}: {texto}")
    return f"Línea {linea.nro_linea}: se cancelaron {cantidad:g}."


def _anulable(linea):
    return linea.enviada_en is not None and linea.estado != "anulado" and not linea.sin_conformidad


ACCION_ENVIAR = {
    "id": "enviar_a_compras",
    "label": "Enviar a Compras",
    "funcion": enviar_a_compras,
    "seccion": "pedido_lineas",
    "confirmar": ("¿Enviar a Compras las líneas en borrador? Después no se pueden cambiar su material, "
                  "su descripción ni sus cantidades (la imputación, sí)."),
    "visible": lambda pedido: bool(_lineas_para_enviar(pedido)),
}

ACCION_ANULAR = {
    "id": "anular_o_cancelar",
    "label": "Anular o cancelar",
    "funcion": anular_o_cancelar,
    "en_fila": True,
    "visible": _anulable,
    "ayuda": ("Sin cantidad se anula la línea entera (solo si todavía no se compró nada). Con cantidad, "
              "se cancela esa parte, hasta lo pendiente de comprar."),
    "campos": {
        "motivo_operacion_id": {"label": "Motivo", "tipo": "fk", "fk_model": MotivoOperacion,
                                "fk_filtro": motivos_de_anulacion, "required": True},
        "cantidad": {"label": "Cantidad a cancelar (vacío: anular la línea entera)", "tipo": "number"},
    },
}


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
    if getattr(linea, "reglas_de_edicion", True) and "estado" in cambiados and linea.estado == "anulado":
        if linea.enviada_en is None:
            errores["estado"] = "Una línea en borrador no se anula: eliminala."
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
    if getattr(linea, "reglas_de_edicion", True):
        _verificar_cancelacion(linea, cambiados)
    return None


def _verificar_cancelacion(linea, cambiados):
    """
    No se cancela más de lo pendiente de comprar. (Que no se anule entera una
    línea con compras lo asegura editable_si del estado: con compras, no cambia.)
    """
    comprado = linea.comprado or 0
    if "cantidad_cancelada" in cambiados and (linea.pendiente_comprar or 0) < -_EPS:
        hasta = max((linea.solicitada or 0) - comprado, 0)
        raise ErroresValidacion({"cantidad_cancelada": (
            f"Se puede cancelar hasta {hasta:g} en total (lo pendiente de comprar; ya hay {comprado:g} comprados).")})


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
    if d.comprada_corregida is not None and d.comprada_corregida < 0:
        errores["comprada_corregida"] = "La cantidad comprada no puede ser negativa."
    dato = DATO_DEL_DESTINO.get(d.destino)
    if dato and getattr(d, dato) is None:
        etiqueta = next(o["label"] for o in DESTINOS if o["value"] == d.destino).lower()
        nombre = {"activo_id": "el activo", "modelo_id": "el modelo", "ubicacion_id": "la ubicación (taller que recibe)"}
        errores[dato] = f"Un destino «{etiqueta}» necesita {nombre[dato]}."
    if errores:
        raise ErroresValidacion(errores)
    return None


def _tab_recepciones(linea):
    from app.crud.meta.overrides.recepciones import tab_recepciones_de_la_linea

    return tab_recepciones_de_la_linea(linea)


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
                    "prioridad", "observaciones", "motivo_revision", "origen"],
        # El número identifica al pedido (también en el Excel histórico).
        "clave_natural": ["numero"],
        "acciones": [ACCION_ENVIAR],
        "eliminable_si": pedido_eliminable,
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
            # El que se guarda (lo marca una persona). El que se ve es «Estado» (calculado).
            "sin_conformidad": {"required": False, "options": NO_SI},
            "cantidad_cancelada": {"required": False},
            "motivo_operacion_id": {"fk_filtro": motivos_de_anulacion},
            # Anular va por su acción, que pide el motivo: la grilla no lo ofrece.
            "estado": {"tipo": "select", "options": ESTADOS_LINEA, "required": False,
                       "label": "Estado de seguimiento", "excluir_en_linea": ("anulado",)},
            # La pone «Enviar a Compras» (o la importación del histórico).
            "enviada_en": {"solo_lectura": True},
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
        "listado": ["pedido_id", "nro_linea", "material_id", "descripcion", "solicitada", "adjudicada",
                    "recibida", "pendiente_comprar", "pendiente_recibir", "se_cuenta_en", "estado_visible",
                    "nro_oc"],
        "filtros": ["material_id", "descripcion", "estado", "nro_oc", "observaciones", "motivo_revision",
                    "origen"],
        "clave_natural": ["pedido_id", "nro_linea"],
        # Grilla de la pestaña «Líneas» del pedido (fase 13). El estado de
        # seguimiento se edita sobre la columna «Estado» (el visible).
        "edicion_en_linea": ["material_id", "descripcion", ("estado", "estado_visible"), "nro_oc"],
        # Borrador y envío (fase 13.2).
        "editable_si": {
            "material_id": material_editable,
            "descripcion": en_borrador,
            "estado": estado_editable,
            "cantidad_cancelada": enviada,
            "motivo_operacion_id": enviada,
            "nro_oc": enviada,
        },
        "eliminable_si": linea_eliminable,
        # Alta rápida (fase 13.3): última fila de la pestaña «Líneas» del pedido.
        # El destino es un activo o una ubicación (stock); vacío, «a identificar».
        # Modelo y gasto general se eligen en el destino (subgrilla, PR 13.4).
        "alta_en_linea": [
            {"nombre": "material", "label": "Material (código o descripción) o texto tal como se pidió",
             "columnas": ["material_id", "descripcion"],
             "interprete": FkOTexto("material_id", "descripcion")},
            {"nombre": "cantidad", "label": "Cantidad", "columnas": ["solicitada"]},
            {"nombre": "destino", "label": "Destino: activo o ubicación (vacío: a identificar)",
             "columnas": ["adjudicada", "recibida", "pendiente_comprar", "pendiente_recibir", "se_cuenta_en"],
             "interprete": FkEntre({"activo_id": {"destino": "activo"}, "ubicacion_id": {"destino": "stock"}},
                                   vacio={"destino": "a_identificar"}),
             "repetir": True},
        ],
        "acciones": [ACCION_ANULAR],
        "tabs_extra": [{"id": "recepciones_linea", "label": "Recepciones", "funcion": _tab_recepciones}],
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
        "excluir": ["nombre"],
        "listado": ["pedido_linea_id", "cantidad", "destino", "activo_id", "modelo_id", "ubicacion_id",
                    "sector_imputado_id", "cuenta_id", "comprada", "recibida", "pendiente_recibir", "a_revisar"],
        "completar": completar_destino,
        "al_guardar": al_guardar_destino,
        # Línea enviada: cantidades congeladas y sin destinos sueltos (la
        # imputación sigue editable). «Redistribuir» llega en el PR 13.4.
        "editable_si": {"cantidad": destino_en_borrador},
        "creable_si": destino_creable,
        "eliminable_si": destino_eliminable,
    },
}
