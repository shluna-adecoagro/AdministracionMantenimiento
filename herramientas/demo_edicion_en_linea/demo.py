"""
Demo: edición tipo planilla con htmx para las líneas de un pedido y sus destinos.

Independiente del repo (datos en memoria, sin base), pero con las mismas reglas
que app/crud/meta/overrides/pedidos.py, más las decididas el 26/11:

  * La línea tiene un material o la descripción tal como se pidió.
  * El nº de OC se guarda sin espacios y en mayúsculas.
  * Un destino «activo» necesita el activo y uno «stock», la ubicación.
    Completar el activo o la ubicación define el tipo.
  * El sector imputado y la cuenta vacíos se completan con la sugerencia.
  * «A revisar» = destino a identificar o sin sector o sin cuenta.

  Borrador y envío a Compras (por línea):
  * Una línea nace en borrador: se edita todo, se agregan y se borran destinos,
    y la línea se puede eliminar.
  * «Enviar a Compras» congela las líneas en borrador (enviada_en). Una línea
    agregada después queda en borrador hasta el próximo envío.
  * Línea enviada: material, descripción y cantidades congeladas. La imputación
    (activo, ubicación, sector, cuenta) sigue editable. Para cambiar el reparto
    entre destinos, «Redistribuir» (el total no cambia).
  * Para pedir menos: anular (toda la línea) o cancelar una cantidad, con motivo.
    Si ya hay algo comprado, no se anula: solo se cancela lo pendiente de comprar.

Correr:  pip install flask   →   python demo.py   →   http://127.0.0.1:5001

htmx se carga desde unpkg. En la app conviene copiarlo a static/vendor/.
"""
from __future__ import annotations

import re
from dataclasses import dataclass, field
from datetime import datetime

from flask import Flask, abort, render_template, request

app = Flask(__name__)


# ---------------------------------------------------------------------------
# Datos de ejemplo (inventados)
# ---------------------------------------------------------------------------

SECTORES = {1: "Taller central", 2: "Feedlot", 3: "Agricultura"}
CUENTAS = {10: "5101 Repuestos maquinaria", 11: "5102 Lubricantes", 12: "5190 Ferretería y varios"}
MATERIALES = {
    1: {"codigo": "RE504836", "descripcion": "Filtro de aceite", "unidad": "un", "cuenta_id": 10},
    2: {"codigo": "AR26003", "descripcion": "Filtro de aire", "unidad": "un", "cuenta_id": 10},
    3: {"codigo": "TY26402", "descripcion": "Aceite Hy-Gard (tambor 208 l)", "unidad": "envases", "cuenta_id": 11},
    4: {"codigo": "BUL-M12", "descripcion": "Bulón M12 x 50", "unidad": "un", "cuenta_id": 12},
}
# cuenta_id: la del tipo de activo (la sugerencia la toma de ahí).
ACTIVOS = {
    1: {"nombre": "Tractor 1 (JD 6130J)", "sector_id": 3, "cuenta_id": 10},
    2: {"nombre": "Tractor 2 (JD 6130J)", "sector_id": 3, "cuenta_id": 10},
    3: {"nombre": "Mixer 1", "sector_id": 2, "cuenta_id": 10},
}
UBICACIONES = {1: {"nombre": "Pañol taller central", "sector_id": 1}, 2: {"nombre": "Pañol feedlot", "sector_id": 2}}
MOTIVOS = {1: "Pedido duplicado", 2: "Ya no se necesita", 3: "Se consiguió por otro canal"}

# Estado de seguimiento que se edita (anular va por su propia acción, con motivo).
ESTADOS = [("solicitado", "Solicitado"), ("en_cotizacion", "En cotización"),
           ("ofertas_cargadas", "Ofertas cargadas")]
DESTINOS = [("activo", "Activo"), ("stock", "Stock"), ("gasto_general", "Gasto general"),
            ("a_identificar", "A identificar")]
DATO_DEL_DESTINO = {"activo": "activo_id", "stock": "ubicacion_id"}


@dataclass
class Destino:
    id: int
    linea_id: int
    cantidad: float
    destino: str = "a_identificar"
    activo_id: int | None = None
    ubicacion_id: int | None = None
    sector_id: int | None = None
    cuenta_id: int | None = None

    @property
    def a_revisar(self) -> bool:
        return self.destino == "a_identificar" or self.sector_id is None or self.cuenta_id is None

    @property
    def linea(self) -> "Linea":
        return LINEAS[self.linea_id]


@dataclass
class Linea:
    id: int
    nro: int
    material_id: int | None = None
    descripcion: str | None = None
    estado: str = "solicitado"
    motivo_id: int | None = None
    nro_oc: str | None = None
    cantidad_cancelada: float = 0.0
    enviada_en: datetime | None = None
    # En la app sale de las adjudicaciones; acá se simula para probar las reglas.
    adjudicada: float = 0.0
    destinos: list[Destino] = field(default_factory=list)

    @property
    def borrador(self) -> bool:
        return self.enviada_en is None

    @property
    def anulada(self) -> bool:
        return self.estado == "anulado"

    @property
    def solicitada(self) -> float:
        return sum(d.cantidad for d in self.destinos)

    @property
    def pendiente_comprar(self) -> float:
        return max(self.solicitada - self.adjudicada - self.cantidad_cancelada, 0.0)

    @property
    def unidad(self) -> str:
        return MATERIALES[self.material_id]["unidad"] if self.material_id else "—"

    @property
    def destinos_a_revisar(self) -> int:
        return sum(d.a_revisar for d in self.destinos)

    @property
    def estado_visible(self) -> str:
        if self.anulada:
            return "Anulado"
        if self.borrador:
            return "Borrador"
        if self.adjudicada:
            return "Adjudicado"
        return dict(ESTADOS)[self.estado]


PEDIDO = {"numero": "1104", "referencia": "Filtros y aceite services", "sector_id": 3}
LINEAS: dict[int, Linea] = {}
DESTINOS_POR_ID: dict[int, Destino] = {}
_ids = {"linea": 0, "destino": 0}


def _nuevo_id(tipo):
    _ids[tipo] += 1
    return _ids[tipo]


def reiniciar_datos():
    LINEAS.clear()
    DESTINOS_POR_ID.clear()
    _ids.update(linea=0, destino=0)
    enviado = datetime(2026, 11, 24, 10, 30)
    # Enviada, con 4 de 6 ya comprados: no se anula, se puede cancelar hasta 2.
    l1 = crear_linea(material_id=1)
    agregar_destino(l1, 4, destino="activo", activo_id=1)
    agregar_destino(l1, 2, destino="activo", activo_id=3)
    l1.enviada_en, l1.estado, l1.adjudicada, l1.nro_oc = enviado, "en_cotizacion", 4, "OC450012"
    # Enviada, sin comprar todavía: se puede anular.
    l2 = crear_linea(material_id=3)
    agregar_destino(l2, 2, destino="stock", ubicacion_id=1)
    l2.enviada_en, l2.estado = enviado, "en_cotizacion"
    # Agregada después del envío: en borrador.
    l3 = crear_linea(descripcion="Grasa para rodamientos, la que usa el mixer")
    agregar_destino(l3, 5)


def estado_pedido() -> dict:
    activas = [l for l in LINEAS.values() if not l.anulada]
    sin_enviar = [l for l in activas if l.borrador]
    if not activas:
        texto = "Sin líneas"
    elif len(sin_enviar) == len(activas):
        texto = "Borrador"
    elif sin_enviar:
        n = len(sin_enviar)
        texto = f"Enviado a Compras · {n} línea{'s' if n != 1 else ''} sin enviar"
    else:
        texto = "Enviado a Compras"
    return {"texto": texto, "sin_enviar": len(sin_enviar)}


# ---------------------------------------------------------------------------
# Reglas
# ---------------------------------------------------------------------------

class ErrorCampo(Exception):
    def __init__(self, mensaje):
        super().__init__(mensaje)
        self.mensaje = mensaje


def normalizar_oc(texto):
    return re.sub(r"\s+", "", texto or "").upper() or None


def completar_destino(d: Destino):
    """Sector y cuenta vacíos ← sugerencia (activo, ubicación, pedido / tipo de activo, material)."""
    linea = LINEAS[d.linea_id]
    if d.sector_id is None:
        if d.activo_id:
            d.sector_id = ACTIVOS[d.activo_id]["sector_id"]
        elif d.ubicacion_id:
            d.sector_id = UBICACIONES[d.ubicacion_id]["sector_id"]
        else:
            d.sector_id = PEDIDO["sector_id"]
    if d.cuenta_id is None:
        if d.activo_id:
            d.cuenta_id = ACTIVOS[d.activo_id]["cuenta_id"]
        elif linea.material_id:
            d.cuenta_id = MATERIALES[linea.material_id]["cuenta_id"]


def validar_linea(l: Linea):
    if l.material_id is None and not (l.descripcion or "").strip():
        raise ErrorCampo("Elegí el material o escribí la descripción tal como se pidió.")


def validar_destino(d: Destino):
    if d.cantidad is None or d.cantidad <= 0:
        raise ErrorCampo("La cantidad tiene que ser mayor que cero.")
    dato = DATO_DEL_DESTINO.get(d.destino)
    if dato and getattr(d, dato) is None:
        nombre = {"activo_id": "el activo", "ubicacion_id": "la ubicación"}[dato]
        raise ErrorCampo(f"Este destino necesita {nombre}: completá esa celda y el tipo se ajusta solo.")


def crear_linea(**datos) -> Linea:
    nro = max((l.nro for l in LINEAS.values()), default=0) + 1
    linea = Linea(id=_nuevo_id("linea"), nro=nro, **datos)
    validar_linea(linea)
    LINEAS[linea.id] = linea
    return linea


def agregar_destino(linea: Linea, cantidad, **datos) -> Destino:
    d = Destino(id=_nuevo_id("destino"), linea_id=linea.id, cantidad=cantidad, **datos)
    completar_destino(d)
    validar_destino(d)
    linea.destinos.append(d)
    DESTINOS_POR_ID[d.id] = d
    return d


def eliminar_linea(l: Linea):
    if not l.borrador:
        raise ErrorCampo("La línea ya se envió a Compras: anulala o cancelá una parte, con motivo.")
    for d in l.destinos:
        DESTINOS_POR_ID.pop(d.id, None)
    del LINEAS[l.id]


def eliminar_destino(d: Destino):
    l = d.linea
    if not l.borrador:
        raise ErrorCampo("La línea ya se envió: usá «Redistribuir».")
    if len(l.destinos) == 1:
        raise ErrorCampo("Es el único destino: para sacarlo, eliminá la línea.")
    l.destinos.remove(d)
    del DESTINOS_POR_ID[d.id]


def enviar_a_compras() -> int:
    ahora = datetime.now().replace(microsecond=0)
    enviadas = [l for l in LINEAS.values() if l.borrador and not l.anulada]
    for l in enviadas:
        l.enviada_en = ahora
    return len(enviadas)


def anular_o_cancelar(l: Linea, motivo_id, cantidad) -> str:
    """
    Sin cantidad: anula la línea (solo si no hay nada comprado). Con cantidad:
    cancela esa parte, sin superar lo pendiente de comprar. Siempre con motivo.
    """
    if l.borrador:
        raise ErrorCampo("La línea está en borrador: eliminala.")
    if l.anulada:
        raise ErrorCampo("La línea ya está anulada.")
    if motivo_id is None:
        raise ErrorCampo("Elegí el motivo.")
    disponible = l.pendiente_comprar
    if cantidad is None:
        if l.adjudicada > 0:
            raise ErrorCampo(f"Ya hay {l.adjudicada:g} comprados: no se puede anular entera. "
                             f"Indicá la cantidad a cancelar (hasta {disponible:g}).")
        l.estado, l.motivo_id = "anulado", motivo_id
        return f"Línea {l.nro} anulada."
    if cantidad <= 0:
        raise ErrorCampo("La cantidad a cancelar tiene que ser mayor que cero.")
    if cantidad > disponible:
        raise ErrorCampo(f"Se puede cancelar hasta {disponible:g} (lo pendiente de comprar).")
    l.cantidad_cancelada += cantidad
    l.motivo_id = motivo_id
    return f"Línea {l.nro}: se cancelaron {cantidad:g}."


def redistribuir(l: Linea, filas: list[dict]):
    """
    Reemplaza los destinos de una línea enviada por `filas`, sin cambiar el total.
    Cada fila: {"id" (o None, si es nuevo), "cantidad", "activo", "ubicacion"}.
    Una fila con cantidad vacía o 0 saca ese destino. Todo o nada.
    """
    nuevos, errores = [], []
    for n, f in enumerate(filas, start=1):
        try:
            cantidad = convertir_numero(f.get("cantidad"))
            if not cantidad:
                continue
            activo_id = buscar_por_texto(ACTIVOS, f.get("activo"), "nombre")
            ubicacion_id = buscar_por_texto(UBICACIONES, f.get("ubicacion"), "nombre")
            if activo_id and ubicacion_id:
                raise ErrorCampo("elegí el activo o la ubicación, no los dos")
            previo = DESTINOS_POR_ID.get(int(f["id"])) if str(f.get("id") or "").isdigit() else None
            if previo is not None and previo.linea_id != l.id:
                previo = None
            d = Destino(id=previo.id if previo else 0, linea_id=l.id, cantidad=cantidad)
            if activo_id:
                d.destino, d.activo_id = "activo", activo_id
            elif ubicacion_id:
                d.destino, d.ubicacion_id = "stock", ubicacion_id
            elif previo and previo.destino in ("gasto_general", "a_identificar"):
                d.destino = previo.destino
            # Si sigue apuntando a lo mismo, conserva la imputación ya corregida.
            if previo and (previo.activo_id, previo.ubicacion_id) == (d.activo_id, d.ubicacion_id):
                d.sector_id, d.cuenta_id = previo.sector_id, previo.cuenta_id
            completar_destino(d)
            validar_destino(d)
            nuevos.append(d)
        except ErrorCampo as e:
            errores.append(f"Fila {n}: {e.mensaje}")
    if errores:
        raise ErrorCampo(" · ".join(errores))
    if not nuevos:
        raise ErrorCampo("Tiene que quedar al menos un destino.")
    total = sum(d.cantidad for d in nuevos)
    if abs(total - l.solicitada) > 1e-9:
        raise ErrorCampo(f"El total tiene que seguir siendo {l.solicitada:g} (quedó {total:g}). "
                         "Para pedir menos, cancelá una parte; para pedir más, agregá una línea.")
    for d in l.destinos:
        DESTINOS_POR_ID.pop(d.id, None)
    for d in nuevos:
        if not d.id:
            d.id = _nuevo_id("destino")
        DESTINOS_POR_ID[d.id] = d
    l.destinos = nuevos


# ---------------------------------------------------------------------------
# Conversión de lo que se escribe en una celda
# ---------------------------------------------------------------------------

def buscar_por_texto(catalogo: dict, texto: str, clave: str):
    """
    El valor de un <input list=...>: «RE504836 — Filtro de aceite» o solo
    «RE504836» o el nombre. Vacío → None. Sin coincidencia → ErrorCampo.
    """
    texto = (texto or "").strip()
    if not texto:
        return None
    buscado = texto.split(" — ")[0].strip().lower()
    for id_, item in catalogo.items():
        if item[clave].lower() == buscado:
            return id_
    # Si no es exacto, vale el comienzo si es de una sola opción («Tractor 2»).
    parecidos = [id_ for id_, item in catalogo.items() if item[clave].lower().startswith(buscado)]
    if len(parecidos) == 1:
        return parecidos[0]
    raise ErrorCampo(f"No encontré «{texto}». Elegí una opción de la lista.")


def convertir_numero(texto):
    texto = (texto or "").strip().replace(",", ".")
    if not texto:
        return None
    try:
        return float(texto)
    except ValueError:
        raise ErrorCampo("Escribí un número.")


def convertir_opcion(texto, opciones):
    if texto in ("", None):
        return None
    validos = {v for v, _ in opciones} if isinstance(opciones, list) else set(map(str, opciones))
    if texto not in validos:
        raise ErrorCampo("Opción no válida.")
    return int(texto) if not isinstance(opciones, list) else texto


# ---------------------------------------------------------------------------
# Columnas de cada grilla (en la app saldrían del metamodelo)
#   editable: False = calculada; si no, `editable_si(registro)` dice si se
#   puede editar en ese registro (las congeladas se ven en gris).
# ---------------------------------------------------------------------------

def _texto_material(l):
    m = MATERIALES.get(l.material_id)
    return f"{m['codigo']} — {m['descripcion']}" if m else ""


def _si_borrador(l):
    return l.borrador and not l.anulada


def _si_enviada(l):
    return not l.borrador and not l.anulada


COLUMNAS_LINEA = [
    {"campo": "nro", "label": "Línea", "editable": False},
    {"campo": "material_id", "label": "Material", "tipo": "lista", "lista": "dl-materiales",
     "mostrar": _texto_material, "editable_si": _si_borrador},
    {"campo": "descripcion", "label": "Descripción (como se pidió)", "tipo": "texto", "editable_si": _si_borrador},
    {"campo": "solicitada", "label": "Solicitada", "editable": False, "num": True},
    {"campo": "cantidad_cancelada", "label": "Cancelada", "editable": False, "num": True,
     "mostrar": lambda l: f"{l.cantidad_cancelada:g}" if l.cantidad_cancelada else ""},
    {"campo": "pendiente_comprar", "label": "Pend. comprar", "editable": False, "num": True},
    {"campo": "unidad", "label": "Unidad", "editable": False},
    {"campo": "estado", "label": "Estado", "tipo": "opcion", "opciones": ESTADOS,
     "mostrar": lambda l: l.estado_visible, "editable_si": lambda l: _si_enviada(l) and not l.adjudicada},
    {"campo": "motivo_id", "label": "Motivo", "editable": False,
     "mostrar": lambda l: MOTIVOS.get(l.motivo_id, "")},
    {"campo": "nro_oc", "label": "Nº de OC", "tipo": "texto", "editable_si": _si_enviada},
]

COLUMNAS_DESTINO = [
    {"campo": "cantidad", "label": "Cantidad", "tipo": "numero", "num": True,
     "editable_si": lambda d: _si_borrador(d.linea)},
    {"campo": "destino", "label": "Destino", "tipo": "opcion", "opciones": DESTINOS},
    {"campo": "activo_id", "label": "Activo", "tipo": "lista", "lista": "dl-activos",
     "mostrar": lambda d: ACTIVOS[d.activo_id]["nombre"] if d.activo_id else ""},
    {"campo": "ubicacion_id", "label": "Ubicación (taller)", "tipo": "lista", "lista": "dl-ubicaciones",
     "mostrar": lambda d: UBICACIONES[d.ubicacion_id]["nombre"] if d.ubicacion_id else ""},
    {"campo": "sector_id", "label": "Sector imputado", "tipo": "opcion",
     "opciones": [(str(k), v) for k, v in SECTORES.items()]},
    {"campo": "cuenta_id", "label": "Cuenta", "tipo": "opcion",
     "opciones": [(str(k), v) for k, v in CUENTAS.items()]},
]
for _col in COLUMNAS_DESTINO:  # nada se edita en una línea anulada
    _col.setdefault("editable_si", lambda d: not d.linea.anulada)


def es_editable(registro, col) -> bool:
    if col.get("editable") is False:
        return False
    regla = col.get("editable_si")
    return regla is None or regla(registro)


def mostrar(registro, col):
    """Texto de la celda en modo lectura."""
    if "mostrar" in col:
        return col["mostrar"](registro)
    v = getattr(registro, col["campo"])
    if col.get("tipo") == "opcion" and v is not None:
        return dict(col["opciones"]).get(str(v) if not isinstance(v, str) else v, v)
    if isinstance(v, float):
        return f"{v:g}"
    return "" if v is None else v


def valor_para_editar(registro, col):
    if col.get("tipo") == "lista":
        return col["mostrar"](registro)
    v = getattr(registro, col["campo"])
    if isinstance(v, float):
        return f"{v:g}"
    return "" if v is None else str(v)


def columna(columnas, campo, registro):
    """La columna, si se puede editar en este registro; si no, 404."""
    col = next((c for c in columnas if c["campo"] == campo), None)
    if col is None or not es_editable(registro, col):
        abort(404)
    return col


app.jinja_env.globals.update(mostrar=mostrar, valor_para_editar=valor_para_editar, es_editable=es_editable,
                             COLUMNAS_LINEA=COLUMNAS_LINEA, COLUMNAS_DESTINO=COLUMNAS_DESTINO,
                             MATERIALES=MATERIALES, ACTIVOS=ACTIVOS, UBICACIONES=UBICACIONES,
                             DESTINOS=DESTINOS, PEDIDO=PEDIDO, SECTORES=SECTORES, MOTIVOS=MOTIVOS,
                             estado_pedido=estado_pedido)
# Columnas de la tabla de líneas: las de COLUMNAS_LINEA + Envío + Destinos + Acciones.
app.jinja_env.globals["N_COLUMNAS"] = len(COLUMNAS_LINEA) + 3


# ---------------------------------------------------------------------------
# Guardar una celda
# ---------------------------------------------------------------------------

def guardar_celda_linea(l: Linea, campo: str, texto: str):
    anterior = {k: getattr(l, k) for k in ("material_id", "descripcion", "estado", "nro_oc")}
    try:
        if campo == "material_id":
            l.material_id = buscar_por_texto(MATERIALES, texto, "codigo")
        elif campo == "descripcion":
            l.descripcion = (texto or "").strip() or None
        elif campo == "estado":
            l.estado = convertir_opcion(texto, ESTADOS) or "solicitado"
        elif campo == "nro_oc":
            l.nro_oc = normalizar_oc(texto)
        validar_linea(l)
    except ErrorCampo:
        for k, v in anterior.items():  # todo o nada, como una transacción
            setattr(l, k, v)
        raise
    # Cambió el material: los destinos sin cuenta pueden tomar la del material.
    if campo == "material_id":
        for d in l.destinos:
            completar_destino(d)


def guardar_celda_destino(d: Destino, campo: str, texto: str):
    anterior = dict(vars(d))
    try:
        if campo == "cantidad":
            d.cantidad = convertir_numero(texto)
        elif campo == "destino":
            d.destino = convertir_opcion(texto, DESTINOS) or "a_identificar"
            # El dato que no corresponde al nuevo tipo se limpia.
            if d.destino != "activo":
                d.activo_id = None
            if d.destino != "stock":
                d.ubicacion_id = None
        elif campo == "activo_id":
            d.activo_id = buscar_por_texto(ACTIVOS, texto, "nombre")
            if d.activo_id:  # completar el activo define el tipo
                d.destino, d.ubicacion_id = "activo", None
        elif campo == "ubicacion_id":
            d.ubicacion_id = buscar_por_texto(UBICACIONES, texto, "nombre")
            if d.ubicacion_id:
                d.destino, d.activo_id = "stock", None
        elif campo == "sector_id":
            d.sector_id = convertir_opcion(texto, SECTORES)
        elif campo == "cuenta_id":
            d.cuenta_id = convertir_opcion(texto, CUENTAS)
        if campo in ("activo_id", "ubicacion_id", "destino"):
            completar_destino(d)
        validar_destino(d)
    except ErrorCampo:
        vars(d).update(anterior)
        raise


# ---------------------------------------------------------------------------
# Pegado desde Excel
# ---------------------------------------------------------------------------

def interpretar_pegado(texto: str) -> list[dict]:
    """
    Filas copiadas de una planilla (columnas separadas por tabulador):
        código o descripción | cantidad | destino (activo o pañol, opcional)
    Lo que no se reconoce queda como descripción o «a identificar», nunca se descarta.
    """
    filas = []
    for n, renglon in enumerate(texto.strip().splitlines(), start=1):
        if not renglon.strip():
            continue
        celdas = [c.strip() for c in renglon.split("\t")] + ["", "", ""]
        fila = {"n": n, "original": renglon, "material_id": None, "descripcion": None,
                "cantidad": None, "destino": "a_identificar", "activo_id": None, "ubicacion_id": None,
                "avisos": []}
        try:
            fila["material_id"] = buscar_por_texto(MATERIALES, celdas[0], "codigo")
        except ErrorCampo:
            fila["descripcion"] = celdas[0]
            fila["avisos"].append("material sin identificar")
        try:
            fila["cantidad"] = convertir_numero(celdas[1])
        except ErrorCampo:
            pass
        if not fila["cantidad"] or fila["cantidad"] <= 0:
            fila["avisos"].append("sin cantidad: no se puede cargar")
        if celdas[2]:
            for tipo, catalogo, campo in (("activo", ACTIVOS, "activo_id"), ("stock", UBICACIONES, "ubicacion_id")):
                try:
                    fila[campo] = buscar_por_texto(catalogo, celdas[2], "nombre")
                    fila["destino"] = tipo
                    break
                except ErrorCampo:
                    continue
            else:
                fila["avisos"].append(f"destino «{celdas[2]}» a identificar")
        fila["valida"] = bool(fila["cantidad"] and fila["cantidad"] > 0
                              and (fila["material_id"] or fila["descripcion"]))
        filas.append(fila)
    return filas


# ---------------------------------------------------------------------------
# Rutas
# ---------------------------------------------------------------------------

@app.get("/")
def pedido():
    return render_template("pedido.html", lineas=list(LINEAS.values()))


def _cuerpo(aviso):
    return render_template("_cuerpo_lineas.html", lineas=list(LINEAS.values()), aviso=aviso)


# --- Línea ---------------------------------------------------------------

@app.get("/lineas/<int:id>/fila")
def fila_linea(id):
    return render_template("_fila_linea.html", l=LINEAS.get(id) or abort(404))


@app.get("/lineas/<int:id>/celda/<campo>")
def editar_celda_linea(id, campo):
    l = LINEAS.get(id) or abort(404)
    col = columna(COLUMNAS_LINEA, campo, l)
    return render_template("_celda_edicion.html", r=l, col=col, valor=valor_para_editar(l, col),
                           url=f"/lineas/{id}/celda/{campo}", url_cancelar=f"/lineas/{id}/fila")


@app.post("/lineas/<int:id>/celda/<campo>")
def guardar_linea(id, campo):
    l = LINEAS.get(id) or abort(404)
    columna(COLUMNAS_LINEA, campo, l)
    texto = request.form.get("valor", "")
    try:
        guardar_celda_linea(l, campo, texto)
    except ErrorCampo as e:
        # La fila con esa celda todavía en edición y el error. 422: htmx la
        # reemplaza igual (ver responseHandling en base.html).
        return render_template("_fila_linea.html", l=l, editar=campo, valor=texto, error=e.mensaje), 422
    # Se devuelve la fila entera: las columnas calculadas (unidad, solicitada) se actualizan.
    return render_template("_fila_linea.html", l=l, foco=campo)


@app.post("/lineas")
def nueva_linea():
    f = request.form
    try:
        material_id = buscar_por_texto(MATERIALES, f.get("material", ""), "codigo")
        descripcion = None
    except ErrorCampo:
        material_id, descripcion = None, (f.get("material") or "").strip() or None
    try:
        cantidad = convertir_numero(f.get("cantidad"))
        linea = crear_linea(material_id=material_id, descripcion=descripcion)
        try:
            agregar_destino(linea, cantidad)
        except ErrorCampo:
            del LINEAS[linea.id]
            raise
    except ErrorCampo as e:
        return render_template("_fila_nueva.html", error=e.mensaje, form=f), 422
    return render_template("_fila_nueva.html", nueva=linea, form={}, oob_estado=True)


@app.delete("/lineas/<int:id>")
def borrar_linea(id):
    l = LINEAS.get(id) or abort(404)
    try:
        eliminar_linea(l)
    except ErrorCampo as e:
        # La fila queda: sin reemplazo, solo el aviso fuera de banda.
        return render_template("_avisos.html", error=e.mensaje), 422, {"HX-Reswap": "none"}
    # Contenido principal vacío (la fila desaparece) + la fila de destinos y el estado, fuera de banda.
    return render_template("_linea_eliminada.html", id=id)


@app.get("/lineas/<int:id>/anular")
def form_anular(id):
    l = LINEAS.get(id) or abort(404)
    return render_template("_anular.html", l=l)


@app.post("/lineas/<int:id>/anular")
def anular(id):
    l = LINEAS.get(id) or abort(404)
    f = request.form
    try:
        motivo_id = convertir_opcion(f.get("motivo_id", ""), MOTIVOS)
        cantidad = convertir_numero(f.get("cantidad"))
        aviso = anular_o_cancelar(l, motivo_id, cantidad)
    except ErrorCampo as e:
        return render_template("_anular.html", l=l, error=e.mensaje, form=f), 422
    return render_template("_anulada.html", l=l, aviso=aviso)


@app.post("/enviar")
def enviar():
    n = enviar_a_compras()
    aviso = f"Se enviaron {n} línea{'s' if n != 1 else ''} a Compras." if n else "No había líneas sin enviar."
    return _cuerpo(aviso)


# --- Destinos ------------------------------------------------------------

@app.get("/lineas/<int:id>/destinos")
def destinos(id):
    return render_template("_destinos.html", l=LINEAS.get(id) or abort(404))


@app.get("/destinos/<int:id>/fila")
def fila_destino(id):
    return render_template("_fila_destino.html", d=DESTINOS_POR_ID.get(id) or abort(404))


@app.get("/destinos/<int:id>/celda/<campo>")
def editar_celda_destino(id, campo):
    d = DESTINOS_POR_ID.get(id) or abort(404)
    col = columna(COLUMNAS_DESTINO, campo, d)
    return render_template("_celda_edicion.html", r=d, col=col, valor=valor_para_editar(d, col),
                           url=f"/destinos/{id}/celda/{campo}", url_cancelar=f"/destinos/{id}/fila")


@app.post("/destinos/<int:id>/celda/<campo>")
def guardar_destino(id, campo):
    d = DESTINOS_POR_ID.get(id) or abort(404)
    columna(COLUMNAS_DESTINO, campo, d)
    texto = request.form.get("valor", "")
    try:
        guardar_celda_destino(d, campo, texto)
    except ErrorCampo as e:
        return render_template("_fila_destino.html", d=d, editar=campo, valor=texto, error=e.mensaje), 422
    # La fila del destino y, fuera de banda, la fila de su línea (solicitada, «a revisar»).
    return render_template("_fila_destino.html", d=d, foco=campo, oob_linea=d.linea)


@app.post("/lineas/<int:id>/destinos")
def nuevo_destino(id):
    l = LINEAS.get(id) or abort(404)
    if not _si_borrador(l):
        abort(404)
    try:
        agregar_destino(l, convertir_numero(request.form.get("cantidad")))
    except ErrorCampo as e:
        return render_template("_destinos.html", l=l, error=e.mensaje), 422
    return render_template("_destinos.html", l=l, oob_linea=l)


@app.delete("/destinos/<int:id>")
def borrar_destino(id):
    d = DESTINOS_POR_ID.get(id) or abort(404)
    l = d.linea
    try:
        eliminar_destino(d)
    except ErrorCampo as e:
        return render_template("_destinos.html", l=l, error=e.mensaje), 422
    return render_template("_destinos.html", l=l, oob_linea=l)


@app.get("/lineas/<int:id>/redistribuir")
def form_redistribuir(id):
    l = LINEAS.get(id) or abort(404)
    if not _si_enviada(l):
        abort(404)
    filas = [{"id": d.id, "cantidad": f"{d.cantidad:g}",
              "activo": ACTIVOS[d.activo_id]["nombre"] if d.activo_id else "",
              "ubicacion": UBICACIONES[d.ubicacion_id]["nombre"] if d.ubicacion_id else "",
              "otro": dict(DESTINOS)[d.destino] if not (d.activo_id or d.ubicacion_id) else ""}
             for d in l.destinos]
    return render_template("_redistribuir.html", l=l, filas=filas)


@app.post("/lineas/<int:id>/redistribuir")
def guardar_redistribucion(id):
    l = LINEAS.get(id) or abort(404)
    if not _si_enviada(l):
        abort(404)
    f = request.form
    filas = [{"id": i, "cantidad": c, "activo": a, "ubicacion": u, "otro": ""}
             for i, c, a, u in zip(f.getlist("id"), f.getlist("cantidad"), f.getlist("activo"),
                                   f.getlist("ubicacion"))]
    try:
        redistribuir(l, filas)
    except ErrorCampo as e:
        return render_template("_redistribuir.html", l=l, filas=filas, error=e.mensaje), 422
    return render_template("_destinos.html", l=l, oob_linea=l, aviso="Destinos redistribuidos.")


# --- Pegado --------------------------------------------------------------

@app.post("/pegar")
def pegar():
    filas = interpretar_pegado(request.form.get("texto", ""))
    return render_template("_pegado.html", filas=filas, texto=request.form.get("texto", ""))


@app.post("/pegar/confirmar")
def confirmar_pegado():
    # Las filas no válidas (sin cantidad) se informan en la vista previa y no se cargan.
    nuevas = [f for f in interpretar_pegado(request.form.get("texto", "")) if f["valida"]]
    for f in nuevas:
        linea = crear_linea(material_id=f["material_id"], descripcion=f["descripcion"])
        agregar_destino(linea, f["cantidad"], destino=f["destino"],
                        activo_id=f["activo_id"], ubicacion_id=f["ubicacion_id"])
    return _cuerpo(f"Se agregaron {len(nuevas)} líneas (en borrador).")


@app.post("/reiniciar")
def reiniciar():
    reiniciar_datos()
    return _cuerpo("Datos reiniciados.")


reiniciar_datos()

if __name__ == "__main__":
    app.run(debug=True, port=5001)
