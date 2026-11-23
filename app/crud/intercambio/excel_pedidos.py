# app/crud/intercambio/excel_pedidos.py
"""
Adaptador: Excel histórico de pedidos (fase 10, PR 10.6).

Lee el libro (una hoja por pedido) y lo traduce al formato interno común
(`HojaPedido` → `FilaPedido` → `Cotizacion`), sin tocar la base: las reglas de
dueño, claves e identificación las aplica app/crud/intercambio/pedidos_historicos.py.
Diseño: «Importación del Excel histórico de pedidos» en
docs/diseno_tablas_operativas.md y el análisis del Excel real en
docs/analisis_excel_pedidos.md.

Lo que resuelve este módulo:

  * Cabecera: número (el del nombre de la hoja; se avisa si «Pedido N°» no
    coincide), fecha, referencia y solicitantes.
  * Encabezado de la tabla: la fila con «Detalles» en la columna C. Las columnas
    A a F son fijas (cantidad, producto, detalles, cuenta, sector, proveedor); de
    la G en adelante se reconocen por el encabezado («IMPORTE», «PU», «OC»,
    «Recibido?», «Observaciones», «TOTAL») y cualquier otro encabezado es una
    columna de precios de un proveedor (cotización).
  * Celdas combinadas: el valor se repite en todas las filas que cubre (detalles,
    imputación, proveedor, OC, «Recibido?», observaciones).
  * Fórmulas: se usan los valores calculados que guarda el Excel; las fórmulas
    solo sirven para saber si «IMPORTE» es unitario o total (`SUM(importe)`).
  * Moneda por el formato de la celda: «$» → ARS, «[$USD]» → USD; sin símbolo,
    USD inferida, salvo que otra celda de la fila tenga «$» (ARS inferida).
  * Color de la pestaña → estado de la hoja (por tono: cualquier verde o azul es
    cerrado; amarillo o naranja, en proceso; rojo, anulado; sin color, solicitado).
  * En las hojas cerradas, la OC que el comprador escribió en una sola fila vale
    para las demás: si la hoja tiene una sola OC, para todas; si tiene varias,
    para las filas del mismo proveedor (si ese proveedor tiene una sola).
  * Lo que no se puede interpretar no se descarta: queda en `revisar` y el texto
    original, en las observaciones.
"""
from __future__ import annotations

import colorsys
import io
import re
import unicodedata
from dataclasses import dataclass, field
from datetime import date, datetime

# Estados de la hoja, por el color de la pestaña.
CERRADO, EN_PROCESO, ANULADO, SOLICITADO = "cerrado", "en_proceso", "anulado", "solicitado"

# Colores del tema de Office por defecto (si el libro no trae su tema).
_TEMA_POR_DEFECTO = ["FFFFFF", "000000", "E7E6E6", "44546A", "4472C4", "ED7D31", "A5A5A5", "FFC000",
                     "5B9BD5", "70AD47"]
_NOMBRES_TEMA = ["lt1", "dk1", "lt2", "dk2", "accent1", "accent2", "accent3", "accent4", "accent5", "accent6"]

_OC = re.compile(r"\d{6,12}")


@dataclass
class Cotizacion:
    """Un precio de un proveedor para una fila."""
    proveedor: str | None           # tal como figura (columna «PROVEEDOR» o encabezado)
    precio_unitario: float | None
    moneda: str | None              # ARS / USD
    moneda_inferida: bool
    texto: str                      # el valor original de la celda
    elegida: bool                   # es la del proveedor de la columna «PROVEEDOR»


@dataclass
class FilaPedido:
    fila: int
    cantidad: float
    producto: str
    detalles: str | None = None
    cuenta: str | None = None
    sector: str | None = None
    proveedor: str | None = None
    nro_oc: str | None = None
    oc_completada: bool = False     # la OC se tomó de otra fila de la hoja
    recibido: str | None = None
    observaciones: list[str] = field(default_factory=list)
    cotizaciones: list[Cotizacion] = field(default_factory=list)
    revisar: list[str] = field(default_factory=list)

    @property
    def recibido_ok(self) -> bool:
        return bool(self.recibido) and self.recibido.strip().lower().startswith("ok")

    @property
    def recibido_no(self) -> bool:
        """«Recibido?» dice que no llegó («NO», «KO», «falta...»)."""
        t = (self.recibido or "").strip().lower()
        return t in ("no", "ko") or t.startswith("falta")


@dataclass
class HojaPedido:
    hoja: str
    numero: str
    fecha: date | None
    referencia: str | None
    solicitantes: list[str]
    color: str | None               # RRGGBB, o None si la pestaña no tiene color
    estado: str
    formato: str                    # estandar / pu / proveedores / corrido
    filas: list[FilaPedido] = field(default_factory=list)
    notas: list[str] = field(default_factory=list)      # filas que no son líneas (van a observaciones)
    revisar: list[str] = field(default_factory=list)

    @property
    def clave(self) -> str:
        return f"excel_pedidos|{self.hoja}"


@dataclass
class LibroPedidos:
    hojas: list[HojaPedido]
    ignoradas: list[str]
    avisos: list[str]


# ---------------------------------------------------------------------------
# Utilidades
# ---------------------------------------------------------------------------

def normalizar(texto) -> str:
    """Minúsculas, sin acentos, sin puntuación y con un solo espacio."""
    if texto is None:
        return ""
    t = unicodedata.normalize("NFKD", str(texto))
    t = "".join(c for c in t if not unicodedata.combining(c)).lower()
    t = re.sub(r"[^\w%]+", " ", t)
    return re.sub(r"\s+", " ", t).strip()


def _texto(valor) -> str | None:
    if valor is None:
        return None
    if isinstance(valor, float) and valor.is_integer():
        valor = int(valor)
    if isinstance(valor, (datetime, date)):
        return valor.strftime("%d/%m/%Y")
    t = re.sub(r"\s+", " ", str(valor).replace("\xa0", " ")).strip()
    return t or None


def _es_numero(valor) -> bool:
    return isinstance(valor, (int, float)) and not isinstance(valor, bool)


def _es_error(valor) -> bool:
    return isinstance(valor, str) and valor.strip().startswith("#")


def numero_de_texto(texto: str) -> float | None:
    """«USD 1.429,7520» → 1429.752; «$ 35.000» → 35000; «1207727.48» → 1207727.48."""
    t = re.sub(r"(?i)usd|u\$s|\$|ars|\s", "", texto or "")
    if not re.fullmatch(r"-?[\d.,]+", t):
        return None
    if "," in t and "." in t:
        t = t.replace(".", "").replace(",", ".") if t.rfind(",") > t.rfind(".") else t.replace(",", "")
    elif "," in t:
        t = t.replace(",", ".") if len(t.split(",")[-1]) != 3 else t.replace(",", "")
    elif t.count(".") > 1 or (t.count(".") == 1 and len(t.split(".")[-1]) == 3 and len(t) > 4):
        t = t.replace(".", "")
    try:
        return float(t)
    except ValueError:
        return None


def moneda_del_formato(formato: str | None) -> str | None:
    f = formato or ""
    if "USD" in f.upper() or "U$S" in f.upper():
        return "USD"
    if "$" in f:
        return "ARS"
    return None


def oc_de_valor(valor) -> tuple[str | None, str | None]:
    """
    (nº de OC, motivo para revisar). Un número de 6 a 12 dígitos es una OC; dos
    en una celda («100777817 - 100777819»): la primera, a revisar.
    """
    if valor is None:
        return None, None
    if _es_numero(valor):
        if float(valor).is_integer() and _OC.fullmatch(str(int(valor))):
            return str(int(valor)), None
        return None, f"«OC» tiene «{_texto(valor)}», que no parece un número de OC"
    texto = _texto(valor)
    if texto is None:
        return None, None
    numeros = _OC.findall(texto)
    if len(numeros) == 1 and re.sub(r"[\s.\-]", "", texto) == numeros[0]:
        return numeros[0], None
    if len(numeros) >= 2:
        return numeros[0], f"«OC» tiene más de un número («{texto}»): se tomó el primero"
    return None, f"«OC» tiene «{texto}», que no es un número de OC"


def _hex_a_tono(rgb: str) -> str:
    r, g, b = (int(rgb[i:i + 2], 16) / 255 for i in (0, 2, 4))
    h, s, v = colorsys.rgb_to_hsv(r, g, b)
    if s < 0.2 or v < 0.15:
        return "otro"
    grados = h * 360
    if grados < 15 or grados >= 330:
        return "rojo"
    if grados < 70:
        return "amarillo"   # incluye el naranja (decidido 23/11: equivale al amarillo)
    if grados < 170:
        return "verde"
    if grados < 260:
        return "azul"
    return "otro"


ESTADO_POR_TONO = {"verde": CERRADO, "azul": CERRADO, "amarillo": EN_PROCESO, "rojo": ANULADO}


def _colores_tema(libro) -> list[str]:
    tema = getattr(libro, "loaded_theme", None)
    if not tema:
        return _TEMA_POR_DEFECTO
    xml = tema.decode("utf-8", "ignore") if isinstance(tema, bytes) else str(tema)
    colores = []
    for i, nombre in enumerate(_NOMBRES_TEMA):
        m = re.search(rf"<a:{nombre}>.*?(?:srgbClr val|lastClr)=\"([0-9A-Fa-f]{{6}})\"", xml, re.S)
        colores.append(m.group(1).upper() if m else _TEMA_POR_DEFECTO[i])
    return colores


def color_de_pestana(hoja, tema: list[str]) -> str | None:
    c = hoja.sheet_properties.tabColor
    if c is None:
        return None
    if c.type == "rgb" and isinstance(c.rgb, str):
        return c.rgb[-6:].upper()
    if c.type == "theme" and c.theme is not None and c.theme < len(tema):
        return tema[c.theme]
    if c.type == "indexed" and c.indexed is not None:
        from openpyxl.styles.colors import COLOR_INDEX

        if c.indexed < len(COLOR_INDEX):
            return COLOR_INDEX[c.indexed][-6:].upper()
    return None


# ---------------------------------------------------------------------------
# Lectura
# ---------------------------------------------------------------------------

def _rol(encabezado: str) -> str:
    n = normalizar(encabezado)
    if n.startswith("importe"):
        return "importe"
    if n in ("pu", "p u", "precio unitario"):
        return "pu"
    if n == "oc":
        return "oc"
    if n.startswith("recibido"):
        return "recibido"
    if n.startswith("observaci"):
        return "observaciones"
    if n == "total":
        return "total"
    return "proveedor"


def _mismo_proveedor(encabezado: str | None, proveedor: str | None) -> bool:
    """«PROV-034 L.» es el mismo que «PROV-034»; «PROV-154 sin iva», que «PROV-154»."""
    a, b = normalizar(encabezado), normalizar(proveedor)
    if not a or not b:
        return False
    return a == b or a.startswith(b + " ") or b.startswith(a + " ")


def leer_libro(contenido: bytes) -> LibroPedidos:
    import openpyxl

    valores = openpyxl.load_workbook(io.BytesIO(contenido), data_only=True)
    formulas = openpyxl.load_workbook(io.BytesIO(contenido), data_only=False)
    tema = _colores_tema(formulas)
    hojas, ignoradas, avisos = [], [], []
    for hv in valores.worksheets:
        if normalizar(hv.title).startswith("plantilla"):
            ignoradas.append(hv.title)
            continue
        hoja = leer_hoja(hv, formulas[hv.title], tema)
        if hoja is None:
            ignoradas.append(hv.title)
            avisos.append(f"«{hv.title}»: no tiene la tabla del pedido (falta el encabezado «Detalles»); "
                          "no se importó.")
            continue
        hojas.append(hoja)
    vistos: dict[str, str] = {}
    for h in hojas:
        if h.numero in vistos:
            avisos.append(f"«{h.hoja}» y «{vistos[h.numero]}» tienen el mismo número de pedido ({h.numero}): "
                          "se importa solo la primera.")
        else:
            vistos[h.numero] = h.hoja
    return LibroPedidos(hojas=[h for h in hojas if vistos[h.numero] == h.hoja], ignoradas=ignoradas,
                        avisos=avisos)


def leer_hoja(hv, hf, tema) -> HojaPedido | None:
    """`hv`: la hoja con valores; `hf`: la misma con fórmulas."""
    fila_enc = next((r for r in range(1, 16) if normalizar(hv.cell(r, 3).value) == "detalles"), None)
    if fila_enc is None:
        return None

    revisar: list[str] = []
    # Número: el del nombre de la hoja (decidido 23/11). El sufijo va a observaciones.
    m = re.match(r"(?i)\s*pedido\s*n?\D{0,3}?(\d+)\s*[-–]?\s*(.*)$", hv.title)
    numero_b1 = _texto(hv["B1"].value)
    notas: list[str] = []
    if m:
        numero = m.group(1)
        if m.group(2).strip():
            notas.append(f"Nombre de la hoja: «{hv.title}»")
    else:
        numero = re.sub(r"\D", "", numero_b1 or "") or hv.title
        revisar.append(f"el nombre de la hoja no tiene el número de pedido; se usó «Pedido N°» ({numero})")
    if m and numero_b1 and re.sub(r"\D", "", numero_b1) != numero:
        revisar.append(f"«Pedido N°» dice {numero_b1} y la hoja, {numero}: se usó el de la hoja")

    fecha = hv["E1"].value
    if isinstance(fecha, datetime):
        fecha = fecha.date()
    elif not isinstance(fecha, date):
        if fecha is not None:
            revisar.append(f"la fecha «{_texto(fecha)}» no es una fecha")
        fecha = None
    solicitantes = [t for t in (_texto(hv.cell(r, 2).value) for r in range(4, fila_enc)) if t]

    color = color_de_pestana(hv, tema)
    if color is None:
        estado = SOLICITADO
    else:
        estado = ESTADO_POR_TONO.get(_hex_a_tono(color))
        if estado is None:
            estado = SOLICITADO
            revisar.append(f"el color de la pestaña ({color}) no corresponde a ningún estado: quedó «solicitado»")

    # Columnas de la G en adelante, por su encabezado (fila del encabezado o la siguiente).
    columnas: dict[int, tuple[str, str]] = {}
    for c in range(7, hv.max_column + 1):
        enc = _texto(hv.cell(fila_enc, c).value) or _texto(hv.cell(fila_enc + 1, c).value)
        if enc:
            columnas[c] = (_rol(enc), enc)
    por_rol: dict[str, list[int]] = {}
    for c, (rol, _) in columnas.items():
        por_rol.setdefault(rol, []).append(c)
    col = {rol: cs[0] for rol, cs in por_rol.items() if rol != "proveedor"}
    cols_proveedor = por_rol.get("proveedor", [])

    inicio = fila_enc + 2 if normalizar(hv.cell(fila_enc + 1, 4).value) == "cuenta" else fila_enc + 1

    # Celdas combinadas: el valor de la primera celda vale para todas.
    combinadas: dict[tuple[int, int], tuple[int, int]] = {}
    for rango in hv.merged_cells.ranges:
        if rango.max_row < inicio:
            continue
        for r in range(rango.min_row, rango.max_row + 1):
            for c in range(rango.min_col, rango.max_col + 1):
                combinadas[(r, c)] = (rango.min_row, rango.min_col)
    repetir = {3, 4, 5, 6} | {col[r] for r in ("oc", "recibido", "observaciones") if r in col}

    def celda(r, c):
        if c in repetir and (r, c) in combinadas:
            r, c = combinadas[(r, c)]
        return hv.cell(r, c)

    # Formato de la hoja.
    duplicados = [rol for rol, cs in por_rol.items() if rol != "proveedor" and len(cs) > 1]
    corrida = bool(duplicados) or "oc" not in col
    if not corrida:
        # Contenido: la «OC» tiene que tener números de OC (o estar vacía) y «PROVEEDOR», no.
        ocs_en_oc = ocs_fuera = 0
        for r in range(inicio, hv.max_row + 1):
            if _OC.fullmatch(_texto(celda(r, col["oc"]).value) or ""):
                ocs_en_oc += 1
            if _OC.fullmatch(_texto(celda(r, 6).value) or ""):
                ocs_fuera += 1
        corrida = ocs_fuera > ocs_en_oc
    if corrida:
        formato = "corrido"
        revisar.append("los encabezados de la tabla no coinciden con su contenido (columnas corridas): "
                       "precios, proveedor y OC quedaron sin interpretar, con el texto original en las observaciones")
    elif "importe" not in col and "pu" not in col:
        formato = "proveedores" if cols_proveedor else "estandar"
    else:
        formato = "pu" if "pu" in col else "estandar"

    # ¿«IMPORTE» es el unitario o el total de la línea?
    col_precio = col.get("pu") or col.get("importe")
    importe_es_total = False
    if formato == "estandar" and col_precio:
        letra = hv.cell(1, col_precio).column_letter
        for r in range(inicio, hf.max_row + 1):
            f = hf.cell(r, col_precio).value
            if isinstance(f, str) and re.match(rf"(?i)=\s*SUM\(\s*\$?{letra}\$?\d", f):
                importe_es_total = True
                break

    hoja = HojaPedido(hoja=hv.title, numero=numero, fecha=fecha, referencia=_texto(hv["B2"].value),
                      solicitantes=solicitantes, color=color, estado=estado, formato=formato,
                      notas=notas, revisar=revisar)

    for r in range(inicio, hv.max_row + 1):
        a, b = hv.cell(r, 1).value, hv.cell(r, 2).value
        textos = [t for t in (_texto(hv.cell(r, c).value) for c in range(1, hv.max_column + 1)) if t]
        if not textos:
            continue
        producto = _texto(b)
        # Totales, errores y filas sin producto: se ignoran. Un total es un número
        # suelto en «Producto»; con cantidad, el número es un código (8605140).
        if producto is None or _es_error(b):
            continue
        if (_es_numero(b) or numero_de_texto(producto) is not None) and not (_es_numero(a) and a > 0):
            continue
        cantidad, motivo = None, None
        if _es_numero(a) and a > 0:
            cantidad = float(a)
        else:
            # La cantidad dentro del texto: «2 tambor plus 50», «40m» en la columna Cantidad.
            texto_a = _texto(a) if not _es_error(a) else None
            m_a = re.match(r"^(\d+(?:[.,]\d+)?)\s*([a-zA-Z]{0,3})$", texto_a or "")
            m_b = re.match(r"^(\d+(?:[.,]\d+)?)\s+(\S.*)$", producto)
            if m_a and float(m_a.group(1).replace(",", ".")) > 0:
                cantidad = float(m_a.group(1).replace(",", "."))
                motivo = f"la cantidad venía como texto («{texto_a}»)"
            elif texto_a is None and m_b and float(m_b.group(1).replace(",", ".")) > 0:
                cantidad = float(m_b.group(1).replace(",", "."))
                producto = m_b.group(2)
                motivo = f"la cantidad salió del texto del producto («{_texto(b)}»)"
        if cantidad is None:
            hoja.notas.append(f"Fila {r}: " + " | ".join(textos))
            continue

        fila = FilaPedido(fila=r, cantidad=cantidad, producto=producto,
                          detalles=_texto(celda(r, 3).value), cuenta=_texto(celda(r, 4).value),
                          sector=_texto(celda(r, 5).value))
        if motivo:
            fila.revisar.append(motivo)
        if "observaciones" in col and not corrida:
            obs = _texto(celda(r, col["observaciones"]).value)
            if obs:
                fila.observaciones.append(obs)

        if corrida:
            crudo = [f"{hv.cell(fila_enc, c).column_letter}: {t}" for c in range(6, hv.max_column + 1)
                     if (t := _texto(celda(r, c).value))]
            if crudo:
                fila.observaciones.append("Sin interpretar (columnas corridas): " + "; ".join(crudo))
            hoja.filas.append(fila)
            continue

        fila.proveedor = _texto(celda(r, 6).value)
        if "recibido" in col:
            fila.recibido = _texto(celda(r, col["recibido"]).value)
            if fila.recibido:
                fila.observaciones.append(f"Recibido?: {fila.recibido}")
            if fila.recibido_no:
                fila.revisar.append(f"«Recibido?» dice «{fila.recibido}»")
        fila.nro_oc, motivo_oc = oc_de_valor(celda(r, col["oc"]).value)
        if motivo_oc:
            fila.revisar.append(motivo_oc)
            fila.observaciones.append(f"OC: {_texto(celda(r, col['oc']).value)}")

        # Precios: el de la columna de precio (del proveedor elegido) y los de las
        # columnas de otros proveedores.
        celdas_precio = [c for c in ([col_precio] if col_precio else []) + cols_proveedor]
        hay_pesos = any(moneda_del_formato(hv.cell(r, c).number_format) == "ARS" for c in celdas_precio)

        def cotizacion(c, proveedor, elegida, es_total=False):
            v = hv.cell(r, c).value
            if v is None or _es_error(v):
                return None
            texto = _texto(v)
            if _es_numero(v):
                precio = float(v)
                moneda = moneda_del_formato(hv.cell(r, c).number_format)
                inferida = moneda is None
                if moneda is None:
                    moneda = "ARS" if hay_pesos else "USD"
            else:
                precio = numero_de_texto(texto)
                moneda = "USD" if re.search(r"(?i)usd|u\$s", texto) else ("ARS" if "$" in texto else None)
                inferida = moneda is None
                if precio is None:
                    fila.observaciones.append(f"Precio de {proveedor or 'proveedor sin nombre'}: {texto}")
                    fila.revisar.append(f"un precio no se pudo leer («{texto}»)")
                    return None
                if moneda is None:
                    moneda = "ARS" if hay_pesos else "USD"
            if precio <= 0:
                return None
            if es_total:
                precio = precio / cantidad
            return Cotizacion(proveedor=proveedor, precio_unitario=precio, moneda=moneda,
                              moneda_inferida=inferida, texto=texto, elegida=elegida)

        if col_precio:
            cot = cotizacion(col_precio, fila.proveedor, True, importe_es_total)
            if cot is not None:
                fila.cotizaciones.append(cot)
        for c in cols_proveedor:
            enc = columnas[c][1]
            elegida = _mismo_proveedor(enc, fila.proveedor)
            if elegida and any(x.elegida for x in fila.cotizaciones):
                continue  # el precio del elegido ya salió de la columna de precio
            cot = cotizacion(c, enc, elegida)
            if cot is None:
                continue
            # La columna del elegido escrita con otro nombre: mismo precio que «IMPORTE».
            if any(x.elegida and abs(x.precio_unitario - cot.precio_unitario) < 0.01 for x in fila.cotizaciones):
                continue
            fila.cotizaciones.append(cot)
        if fila.proveedor and fila.cotizaciones and not any(x.elegida for x in fila.cotizaciones):
            if formato == "proveedores":
                fila.revisar.append(f"el proveedor «{fila.proveedor}» no coincide con ninguna columna de precios")
        hoja.filas.append(fila)

    if hoja.estado == CERRADO and hoja.formato != "corrido":
        completar_oc(hoja)
    return hoja


def completar_oc(hoja: HojaPedido) -> None:
    """
    En una hoja cerrada, la OC escrita en una fila vale para las demás (decidido
    23/11): con una sola OC en la hoja, para todas; con varias, para las del
    mismo proveedor si ese proveedor tiene una sola. Si no se puede decidir, la
    fila queda sin OC y a revisar.
    """
    ocs = {f.nro_oc for f in hoja.filas if f.nro_oc}
    if not ocs:
        return
    por_proveedor: dict[str, set[str]] = {}
    for f in hoja.filas:
        if f.nro_oc and f.proveedor:
            por_proveedor.setdefault(normalizar(f.proveedor), set()).add(f.nro_oc)
    for f in hoja.filas:
        if f.nro_oc:
            continue
        if len(ocs) == 1:
            f.nro_oc = next(iter(ocs))
        else:
            del_proveedor = por_proveedor.get(normalizar(f.proveedor), set()) if f.proveedor else set()
            if len(del_proveedor) != 1:
                f.revisar.append("la hoja tiene varias OC y no se pudo deducir cuál corresponde a esta línea")
                continue
            f.nro_oc = next(iter(del_proveedor))
        f.oc_completada = True

    # Una OC es de un solo proveedor: la fila sin proveedor toma el de su OC (si
    # en la hoja esa OC tiene uno solo), y con él se sabe qué precio se eligió.
    proveedores_de_oc: dict[str, set[str]] = {}
    nombre: dict[str, str] = {}
    for f in hoja.filas:
        if f.nro_oc and f.proveedor:
            proveedores_de_oc.setdefault(f.nro_oc, set()).add(normalizar(f.proveedor))
            nombre.setdefault(normalizar(f.proveedor), f.proveedor)
    for f in hoja.filas:
        if f.proveedor or not f.nro_oc or len(proveedores_de_oc.get(f.nro_oc, ())) != 1:
            continue
        f.proveedor = nombre[next(iter(proveedores_de_oc[f.nro_oc]))]
        for cot in f.cotizaciones:
            if cot.elegida and cot.proveedor is None:
                cot.proveedor = f.proveedor  # el precio de la columna «IMPORTE»
            elif _mismo_proveedor(cot.proveedor, f.proveedor):
                cot.elegida = True           # una columna por proveedor
