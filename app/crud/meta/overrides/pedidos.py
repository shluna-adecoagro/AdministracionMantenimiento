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
    destino (un activo, un modelo, una ubicación o, vacío, «a identificar»).
  * Destino: un activo, un modelo, el stock de un taller (ubicación), gasto
    general o «a identificar». El sector imputado y la cuenta, si llegan vacíos,
    se completan con la sugerencia; si no hay de dónde, quedan «a revisar».
  * Tipo de destino (fase 13.4): completar el activo o el modelo lo define;
    completar la ubicación, solo si estaba «a identificar» (pasa a «stock»): en
    los demás, la ubicación es el taller que recibe. Cambiar el tipo limpia el
    activo o el modelo que ya no corresponde (la ubicación, nunca). Si cambia a
    qué apunta el destino, el sector imputado y la cuenta se vuelven a sugerir
    (salvo que se cambien en la misma operación).
  * Destinos en la pestaña «Líneas» del pedido (fase 13.4): subgrilla bajo cada
    línea. En borrador se agregan y se sacan (menos el último); en una línea
    enviada, «Redistribuir» cambia todos juntos sin cambiar el total.
"""
from __future__ import annotations

import re
from datetime import datetime

from sqlalchemy import and_, select

from app.core.db import db
from app.crud.core.coercion import ErroresValidacion
from app.crud.core.interpretes import CodigoEnTexto, FkEntre, FkOTexto
from app.crud.introspect import normalizar_texto
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

# El destino escrito en una sola celda (alta rápida de líneas y de destinos, y
# «Redistribuir»): un activo, un modelo o una ubicación (stock); vacío, «a identificar».
DESTINO_EN_TEXTO = FkEntre(
    {"activo_id": {"destino": "activo"}, "modelo_id": {"destino": "modelo"},
     "ubicacion_id": {"destino": "stock"}},
    vacio={"destino": "a_identificar"},
)
MOTIVO_REDISTRIBUCION = "Redistribución"


def aviso_linea_repetida(datos, pedido_id):
    """
    «Pegar líneas»: aviso (no bloquea) si el pedido ya tiene una línea no anulada
    del mismo material, o con la misma descripción, y la misma cantidad. Pegar
    dos veces el mismo mensaje duplicaría las líneas. Incluye las que se acaban
    de agregar en el mismo pegado (ya están en la transacción).
    """
    material, texto = datos.get("material_id"), normalizar_texto(datos.get("descripcion"))
    filas = (db.session.query(PedidoLinea.nro_linea, PedidoLinea.material_id, PedidoLinea.descripcion,
                              PedidoLinea.solicitada)
             .filter(PedidoLinea.pedido_id == pedido_id, PedidoLinea.estado != "anulado")
             .order_by(PedidoLinea.nro_linea))
    for nro, material_linea, descripcion, solicitada in filas:
        igual = (material is not None and material_linea == material) or (
            texto and normalizar_texto(descripcion) == texto)
        if igual and solicitada is not None and float(solicitada) == float(datos.get("cantidad") or 0):
            return f"Igual a la línea {nro} del pedido (mismo material o descripción y cantidad)."
    return None


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
    linea = d.pedido_linea
    if linea.enviada_en is not None:
        return f"{ENVIADA}: no se sacan destinos sueltos (usá «Redistribuir»)"
    if len(linea.destinos) <= 1:
        return "es el único destino de la línea: para sacarlo, eliminá la línea"
    return True


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


# ---------------------------------------------------------------------------
# Redistribuir (fase 13.4): todos los destinos de una línea enviada juntos
# ---------------------------------------------------------------------------

def _clave_destino(d) -> tuple:
    """A qué apunta un destino, como lo escribe la celda «Destino» (DESTINO_EN_TEXTO)."""
    if d.destino == "activo":
        return ("activo_id", d.activo_id)
    if d.destino == "modelo":
        return ("modelo_id", d.modelo_id)
    if d.ubicacion_id is not None:
        return ("ubicacion_id", d.ubicacion_id)
    return (None, None)


def _clave_fila(fila: dict) -> tuple:
    for campo in _APUNTA:
        if fila.get(campo) is not None:
            return (campo, fila[campo])
    return (None, None)


def _texto_destino(d) -> str:
    """El texto de la celda «Destino» para un destino existente."""
    from app.crud.entidades import REGISTRY

    campo, id_ = _clave_destino(d)
    if campo is None:
        return ""
    return DESTINO_EN_TEXTO.texto_de(REGISTRY["pedido_linea_destinos"], campo, id_) or ""


def _nota_destino(d) -> str:
    etiqueta = next((o["label"] for o in DESTINOS if o["value"] == d.destino), d.destino)
    partes = [etiqueta]
    if d.destino in ("activo", "modelo") and d.ubicacion is not None:
        partes.append(f"recibe {d.ubicacion.nombre_ubicacion}")
    if d.sector_imputado is not None:
        partes.append(f"imputado a {d.sector_imputado.nombre_sector}")
    if (d.recibida or 0) > _EPS:
        partes.append(f"recibido {d.recibida:g} (no baja de eso)")
    if d.comprada_corregida is not None:
        partes.append(f"comprada corregida {d.comprada_corregida:g}")
    return " · ".join(partes)


def filas_de_redistribuir(linea) -> list[dict]:
    """Las filas iniciales del formulario: un destino por fila, con lo que no se ve en las celdas."""
    return [{"id": d.pedido_linea_destino_id, "cantidad": f"{d.cantidad:g}", "destino": _texto_destino(d),
             "_nota": _nota_destino(d)}
            for d in sorted(linea.destinos, key=lambda d: d.pedido_linea_destino_id)]


def _redistribuible(linea):
    return linea.enviada_en is not None and linea.estado != "anulado" and not linea.sin_conformidad


def redistribuir(linea, filas: list[dict]):
    """
    Reemplaza el reparto de una línea enviada por `filas` (todo o nada, sin
    cambiar el total). Cada fila: {"id" (el destino, o None si es nuevo),
    "fila" (su número), "cantidad", y el destino: activo, modelo o ubicación}.
    Una fila sin cantidad (o en 0) saca ese destino.

      * Un destino con recepciones no se saca ni baja de lo recibido.
      * Un destino que sigue apuntando a lo mismo conserva su tipo, su sector y
        su cuenta; si cambia, se vuelven a sugerir (completar_destino).
      * Si un destino baja de su «comprada (corregida)», o se saca, la corrección
        se limpia y lo comprado vuelve a repartirse en proporción (con aviso).
    """
    from app.crud.entidades import servicio

    previos = {d.pedido_linea_destino_id: d for d in linea.destinos}
    errores, quedan = {}, []
    for f in filas:
        clave = f"fila_{f['fila']}"
        previo = previos.get(f.get("id")) if f.get("id") is not None else None
        if f.get("id") is not None and previo is None:
            errores[clave] = "El destino no es de esta línea (recargá la página)."
            continue
        cantidad = f.get("cantidad")
        if cantidad is None or abs(cantidad) <= _EPS:
            continue  # sin cantidad: se saca (o era una fila vacía)
        if cantidad < 0:
            errores[clave] = "La cantidad no puede ser negativa."
            continue
        if previo is not None and cantidad < (previo.recibida or 0) - _EPS:
            errores[clave] = f"Ya se recibieron {previo.recibida:g}: la cantidad no puede bajar de eso."
            continue
        quedan.append((previo, f))

    siguen = {id(p) for p, _ in quedan if p is not None}
    sacados = [d for d in previos.values() if id(d) not in siguen]
    for d in sacados:
        if (d.recibida or 0) > _EPS:
            n = next((f["fila"] for f in filas if f.get("id") == d.pedido_linea_destino_id), None)
            texto = (f"Ya se recibieron {d.recibida:g}: este destino no se saca "
                     "(su cantidad no puede bajar de lo recibido).")
            if n is not None:
                errores.setdefault(f"fila_{n}", texto)
            else:
                errores.setdefault("_general", f"«{_texto_destino(d) or 'A identificar'}»: {texto}")
    if errores:
        raise ErroresValidacion(errores)
    if not quedan:
        raise ErroresValidacion({"_general": "Tiene que quedar al menos un destino."})
    total, solicitada = sum(f["cantidad"] for _, f in quedan), linea.solicitada or 0
    if abs(total - solicitada) > _EPS:
        raise ErroresValidacion({"_general": (
            f"El total tiene que seguir siendo {solicitada:g} (quedó {total:g}). Para pedir menos, "
            "cancelá una parte; para pedir más, agregá una línea nueva.")})

    # Las reglas de la línea enviada (cantidades congeladas, sin destinos sueltos)
    # son justamente las que «Redistribuir» levanta: las de arriba las reemplazan.
    s = servicio("pedido_linea_destinos", confirmar=False, reglas_de_edicion=False)
    corregidos = 0
    for previo, f in quedan:
        datos = {"cantidad": f["cantidad"]}
        if previo is None or _clave_fila(f) != _clave_destino(previo):
            # Apunta a otro: el tipo nuevo limpia el activo o el modelo que no
            # corresponde (completar_destino); la ubicación (taller que recibe) queda.
            datos["destino"] = f.get("destino") or "a_identificar"
            datos.update({c: f[c] for c in _APUNTA if f.get(c) is not None})
        if previo is None:
            s.crear({"pedido_linea_id": linea.pedido_linea_id, **datos}, MOTIVO_REDISTRIBUCION)
            continue
        if previo.comprada_corregida is not None and f["cantidad"] < previo.comprada_corregida - _EPS:
            datos["comprada_corregida"] = None
            corregidos += 1
        s.actualizar(previo, datos, MOTIVO_REDISTRIBUCION)
    for d in sacados:
        if d.comprada_corregida is not None:
            corregidos += 1
        s.eliminar(d, MOTIVO_REDISTRIBUCION)
    db.session.flush()
    db.session.refresh(linea)

    mensajes = [("ok", f"Línea {linea.nro_linea}: destinos redistribuidos.")]
    if corregidos:
        mensajes.append(("aviso", (
            f"Se limpi{'ó' if corregidos == 1 else 'aron'} {corregidos} «comprada (corregida)» (el destino "
            f"bajó de ese valor o se sacó): lo comprado vuelve a repartirse en proporción a las cantidades.")))
    return mensajes


ACCION_REDISTRIBUIR = {
    "id": "redistribuir",
    "label": "Redistribuir",
    "funcion": redistribuir,
    "seccion": "pedido_linea_destinos",
    "visible": _redistribuible,
    "ayuda": ("Cambiá cuánto va a cada activo, modelo o taller, todos los destinos juntos. El total tiene que "
              "seguir igual; una fila sin cantidad saca ese destino. Un destino con recepciones no baja de lo "
              "recibido."),
    "filas": {
        "entidad": "pedido_linea_destinos",
        "celdas": [
            {"nombre": "cantidad", "label": "Cantidad", "sumar": True},
            {"nombre": "destino", "label": "Destino: activo, modelo o ubicación (vacío: a identificar)",
             "interprete": DESTINO_EN_TEXTO},
        ],
        "iniciales": filas_de_redistribuir,
        "total": lambda linea: linea.solicitada or 0,
    },
}


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
    # Identificar el material saca la marca «sin material del maestro» (fase 13.6).
    if datos.get("material_id") is not None and "sin_material_maestro" not in datos:
        datos["sin_material_maestro"] = False
    return datos


def al_guardar_linea(linea, operacion: str, cambiados: set):
    errores = {}
    if linea.material_id is None and not (linea.descripcion or "").strip():
        errores["material_id"] = "Elegí el material o escribí la descripción tal como se pidió."
    if linea.sin_material_maestro and linea.material_id is not None:
        errores["sin_material_maestro"] = "La línea ya tiene el material identificado."
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

_APUNTA = ("activo_id", "modelo_id", "ubicacion_id")


def _tipo_de_destino(datos: dict, registro, cambia) -> str | None:
    """
    El tipo que corresponde (decidido 26/11): el elegido, si se cambió (o, en un
    alta, si no es «a identificar»); si no, el que define el dato completado: el
    activo o el modelo, siempre; la ubicación, solo si estaba «a identificar».
    """
    actual = _valor(datos, registro, "destino")
    if cambia("destino") and (registro is not None or actual not in (None, "a_identificar")):
        return actual
    if cambia("activo_id") and datos["activo_id"] is not None:
        return "activo"
    if cambia("modelo_id") and datos["modelo_id"] is not None:
        return "modelo"
    if cambia("ubicacion_id") and datos["ubicacion_id"] is not None and actual in (None, "a_identificar"):
        return "stock"
    return actual


def completar_destino(datos: dict, registro):
    """
    Tipo de destino según el dato completado (y limpia el activo o el modelo que
    ya no corresponde) y sector imputado y cuenta sugeridos: si están vacíos o
    si cambió a qué apunta el destino (salvo que se cambien en la misma operación).
    """
    def cambia(campo):
        return campo in datos and (registro is None or datos[campo] != getattr(registro, campo))

    tipo = _tipo_de_destino(datos, registro, cambia)
    if tipo is not None and tipo != _valor(datos, registro, "destino"):
        datos["destino"] = tipo
    # Cambiar el tipo limpia lo que ya no corresponde. La ubicación queda: en un
    # activo, un modelo o un gasto general es el taller que recibe.
    for otro_tipo, campo in (("activo", "activo_id"), ("modelo", "modelo_id")):
        if tipo != otro_tipo and _valor(datos, registro, campo) is not None:
            datos[campo] = None

    def obj(model, campo):
        v = _valor(datos, registro, campo)
        return db.session.get(model, v) if v is not None else None

    activo, modelo, ubicacion = obj(Activo, "activo_id"), obj(Modelo, "modelo_id"), obj(Ubicacion, "ubicacion_id")
    linea = obj(PedidoLinea, "pedido_linea_id")
    # Si cambió a qué apunta, la imputación anterior era la de otro destino.
    apunta_a_otro = registro is not None and any(cambia(c) for c in _APUNTA)
    for campo, sugerencia in (("sector_imputado_id", lambda: sector_sugerido(activo, ubicacion, linea)),
                              ("cuenta_id", lambda: cuenta_sugerida(activo, modelo, linea))):
        if apunta_a_otro and not cambia(campo):
            datos[campo] = sugerencia()
        elif _valor(datos, registro, campo) is None:
            sugerido = sugerencia()
            if sugerido is not None:
                datos[campo] = sugerido
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
# Colas de «a revisar» (fase 13.6). Nunca entran las líneas anuladas; las
# cerradas, solo si se pide (son casi todas del histórico).
# ---------------------------------------------------------------------------

def _linea_no_anulada():
    return PedidoLinea.estado_visible != "Anulado"


def _linea_abierta():
    return PedidoLinea.estado_visible != "Cerrado"


def _de_lineas(condicion):
    """Destinos cuya línea cumple la condición."""
    return PedidoLineaDestino.pedido_linea_id.in_(select(PedidoLinea.pedido_linea_id).where(condicion))


def _con_texto(columna):
    return and_(columna.is_not(None), columna != "")


COLA_DESTINOS = {
    "id": "a_revisar",
    "label": "Destinos a revisar",
    "condicion": lambda: and_(PedidoLineaDestino.a_revisar == "Sí", _de_lineas(_linea_no_anulada())),
    "por_defecto": lambda: _de_lineas(_linea_abierta()),
    "label_todas": "Incluir los de líneas cerradas",
    "columnas": ["pedido_linea_id", "detalle_texto", "cantidad", "destino", "activo_id", "modelo_id",
                 "ubicacion_id", "sector_imputado_id", "cuenta_id"],
    "ayuda": ("Destinos «a identificar», o sin sector imputado o sin cuenta. Completar el activo, el modelo "
              "o la ubicación define el tipo de destino y sugiere el sector y la cuenta. Para repartir "
              "entre varios destinos: «Destinos de la línea» (en borrador) o «Redistribuir» (enviada)."),
    "orden": 10,
}
COLA_SIN_MATERIAL = {
    "id": "sin_material",
    "label": "Líneas sin material",
    "condicion": lambda: and_(PedidoLinea.material_id.is_(None), PedidoLinea.sin_material_maestro.is_(False),
                              _linea_no_anulada()),
    "por_defecto": _linea_abierta,
    "label_todas": "Incluir las cerradas",
    "columnas": ["pedido_id", "nro_linea", "descripcion", "solicitada", "se_cuenta_en", "estado_visible",
                 "material_id", "sin_material_maestro"],
    "edicion_en_linea": ["material_id", "descripcion", "sin_material_maestro"],
    "ayuda": ("Líneas sin el material del maestro identificado. Elegí el material por código o descripción; "
              "si no está ni va a estar en el maestro (ferretería, insumos), marcá «Sin material del "
              "maestro» y sale de la cola. En una línea enviada el material se completa, pero no se cambia."),
    "orden": 20,
}
COLA_LINEAS_IMPORTACION = {
    "id": "importacion",
    "label": "Líneas a revisar (importación)",
    "condicion": lambda: and_(_con_texto(PedidoLinea.motivo_revision), _linea_no_anulada()),
    "por_defecto": _linea_abierta,
    "label_todas": "Incluir las cerradas",
    "columnas": ["pedido_id", "nro_linea", "material_id", "descripcion", "solicitada", "estado_visible",
                 "nro_oc", "observaciones", "motivo_revision"],
    "edicion_en_linea": ["material_id", "nro_oc", "observaciones", "motivo_revision"],
    "ayuda": ("Lo que la importación del histórico no pudo interpretar. Corregí lo que haga falta y borrá "
              "el texto de «A revisar (importación)»: la línea sale de la cola."),
    "orden": 30,
}
COLA_PEDIDOS_IMPORTACION = {
    "id": "importacion",
    "label": "Pedidos a revisar (importación)",
    "condicion": lambda: _con_texto(Pedido.motivo_revision),
    "columnas": ["numero", "fecha_pedido", "referencia", "resumen", "observaciones", "motivo_revision"],
    "edicion_en_linea": ["referencia", "observaciones", "motivo_revision"],
    "ayuda": ("Lo que la importación del histórico no pudo interpretar en la hoja del pedido. Corregí lo que "
              "haga falta y borrá el texto de «A revisar (importación)»: el pedido sale de la cola."),
    "orden": 40,
}

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
        "colas": [COLA_PEDIDOS_IMPORTACION],
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
            "sin_material_maestro": {"required": False, "options": NO_SI},
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
        # El destino es un activo, un modelo o una ubicación (stock); vacío, «a
        # identificar». Gasto general se elige en el destino (subgrilla).
        "alta_en_linea": [
            {"nombre": "material", "label": "Material (código o descripción) o texto tal como se pidió",
             "columnas": ["material_id", "descripcion"],
             "interprete": FkOTexto("material_id", "descripcion")},
            {"nombre": "cantidad", "label": "Cantidad", "columnas": ["solicitada"]},
            {"nombre": "destino", "label": "Destino: activo, modelo o ubicación (vacío: a identificar)",
             "columnas": ["adjudicada", "recibida", "pendiente_comprar", "pendiente_recibir", "se_cuenta_en"],
             "interprete": DESTINO_EN_TEXTO, "repetir": True},
        ],
        # «Pegar líneas» (fase 13.5): un renglón por línea, «cantidad código o
        # descripción», copiado de un mail o de WhatsApp. El material se reconoce
        # solo por un código exacto; el destino no se adivina: queda «a
        # identificar» (y la línea, a revisar) hasta que el gestor lo complete.
        "pegado_en_linea": {
            "label": "Pegar líneas",
            "cantidad": "cantidad",
            "texto": CodigoEnTexto("material_id", "descripcion", "codigo"),
            "datos": {"destino": "a_identificar"},
            "aviso": aviso_linea_repetida,
        },
        # Los destinos de cada línea se despliegan debajo de ella (fase 13.4).
        "subgrillas": ["pedido_linea_destinos"],
        "acciones": [ACCION_ANULAR, ACCION_REDISTRIBUIR],
        "colas": [COLA_SIN_MATERIAL, COLA_LINEAS_IMPORTACION],
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
        # Grilla (fase 13.4): en la subgrilla de cada línea y en la pestaña
        # «Destinos» de la línea. Completar el activo, el modelo o la ubicación
        # define el tipo (completar_destino).
        "edicion_en_linea": ["cantidad", "destino", "activo_id", "modelo_id", "ubicacion_id",
                             "sector_imputado_id", "cuenta_id"],
        # Alta rápida: en borrador (en una línea enviada no se agregan destinos
        # sueltos: la fila no se muestra, por creable_si).
        "alta_en_linea": [
            {"nombre": "cantidad", "label": "Cantidad", "columnas": ["cantidad"]},
            {"nombre": "destino", "label": "Destino: activo, modelo o ubicación (vacío: a identificar)",
             "columnas": ["destino", "activo_id", "modelo_id", "ubicacion_id"], "interprete": DESTINO_EN_TEXTO},
        ],
        # Línea enviada: cantidades congeladas y sin destinos sueltos (la
        # imputación sigue editable); se cambian todas juntas con «Redistribuir».
        "editable_si": {"cantidad": destino_en_borrador},
        "creable_si": destino_creable,
        "eliminable_si": destino_eliminable,
        "colas": [COLA_DESTINOS],
    },
}
