"""Anonimiza planillas (Excel .xlsx) y reportes (TSV/CSV) antes de compartirlos.

Reemplaza datos sensibles (proveedores, empleados, sectores, centros de costo,
cuentas...) por alias consistentes: el mismo valor recibe siempre el mismo alias
en todos los archivos y hojas, así se siguen pudiendo cruzar los datos.

La tabla de equivalencias (original -> alias) queda en tu computadora, en
`equivalencias_NO_COMPARTIR.csv`. No la subas.

Uso:
  1) Ver qué columnas y hojas hay (todas las hojas, agrupadas por encabezado, y las
     etiquetas tipo «Proveedor:»; no muestra valores, salvo con --muestra):
       python herramientas/anonimizar.py --listar pedidos.xlsx solicitudes.tsv

  2) Anonimizar indicando columna=PREFIJO (una -c por columna):
       python herramientas/anonimizar.py pedidos.xlsx solicitudes.tsv lineas.tsv distrib.tsv ^
           -c "Proveedor=PROV" -c "Solicitante=EMP" -c "Centro de Costo=CC" ^
           -c "Cuenta=CTA" -c "Sector=SEC"

     Opcional: --terminos terminos.txt  (una línea por término: PREFIJO;texto)
     para textos que aparecen sueltos dentro de celdas (por ejemplo, un nombre
     escrito en una descripción o en el encabezado de una hoja de pedido).

     Opcional: --conservar VALOR (una por valor) para dejar sin alias un valor que no es
     sensible y cuyo significado importa, por ejemplo --conservar MECANICO en la columna
     de recursos de las OT, para distinguir el trabajo propio del de un proveedor.

  Repartos de centro de costo escritos a mano («50% 4410 - 50% 4420»): los códigos pegados a
  un porcentaje reciben el alias de la columna de centro de costo (CC-001…; otro prefijo con
  --prefijo-cc). En el texto libre se reemplazan si hay dos o más porcentajes, si el código
  ya es un centro de costo conocido o si va después de «CC», «CeCo» o «centro de costo»;
  con un solo porcentaje y un número desconocido no se tocan (puede ser «IVA 21% 15000»).
  En una columna con regla se conservan los porcentajes y cada parte recibe su alias.

  En los Excel, cada fórmula se reemplaza por el valor que tenía calculado, y ese valor se
  anonimiza como cualquier otro (así no depende de hojas como «Tablas» ni quedan nombres
  dentro de las fórmulas). Con --conservar-formulas se dejan las fórmulas, sin anonimizar.

  Los archivos anonimizados quedan en la carpeta `anonimizado/`. En los Excel también se
  borran el autor y demás propiedades del archivo, y los comentarios de celda pasan por los
  mismos reemplazos (su autor recibe un alias AUT-…, o el que ya tenga en otra columna).
  De los vínculos a otros libros se borran la ruta y la copia oculta de sus datos, y los
  hipervínculos pasan a apuntar a documento_0001.pdf… (se conserva solo la extensión).
  Si después abrís el resultado en Excel, cerralo sin guardar: Excel vuelve a poner tu
  nombre en las propiedades y la ruta de tu carpeta.

  3) Chequear el resultado antes de compartirlo (muestra solo cantidades, nunca valores):
       python herramientas/anonimizar.py --chequear anonimizado
     Cuenta posibles nombres, razones sociales, correos, CUIT, rutas, números pegados a un
     porcentaje, hipervínculos, comentarios, propiedades, hojas ocultas, tablas dinámicas…
     Si encuentra equivalencias_NO_COMPARTIR.csv (u otra con --equivalencias), busca
     además cada valor original en todo el contenido del archivo. Con --ubicaciones
     muestra hoja y celda de cada hallazgo (sin el valor).

  Requiere openpyxl para los .xlsx (ya está en el entorno del proyecto).
"""
import argparse
import csv
import re
import sys
from pathlib import Path

CODIFICACIONES = ("utf-8-sig", "utf-16", "cp1252", "latin-1")
FILAS_BUSCAR_ENCABEZADO = 15
ERRORES_EXCEL = {"#REF!", "#N/A", "#VALUE!", "#DIV/0!", "#NAME?", "#NUM!", "#NULL!", "#SPILL!", "#CALC!"}


def norm(texto):
    return re.sub(r"\s+", " ", str(texto)).strip().casefold()


class Alias:
    """Asigna alias consistentes por prefijo: PROV-001, PROV-002..."""

    def __init__(self, protegidos=(), conservar=()):
        # Nombres de columna y etiquetas: nunca se anonimizan (son encabezados)
        self.protegidos = {norm(p).rstrip(":").strip() for p in protegidos}
        # Valores que no son sensibles y se dejan tal cual (--conservar)
        self.protegidos |= {norm(v) for v in conservar}
        self.mapa = {}  # (prefijo, valor normalizado) -> alias
        self.originales = {}  # alias -> valor original
        self.contadores = {}
        self.por_valor = {}  # valor normalizado -> alias (para reemplazo global)

    def alias(self, prefijo, valor):
        if valor is None or str(valor).strip() == "":
            return valor
        if str(valor).strip().upper() in ERRORES_EXCEL:
            return valor  # un error de fórmula no es un dato
        if isinstance(valor, (int, float)) and not isinstance(valor, bool) and valor == 0:
            return valor  # lo que da una fórmula como «=M3» con la celda de origen vacía
        if norm(valor).rstrip(":").strip() in self.protegidos:
            return valor
        clave = (prefijo, norm(valor))
        if clave not in self.mapa:
            n = self.contadores.get(prefijo, 0) + 1
            self.contadores[prefijo] = n
            nuevo = f"{prefijo}-{n:03d}"
            self.mapa[clave] = nuevo
            self.originales[nuevo] = str(valor).strip()
            self.por_valor.setdefault(norm(valor), nuevo)
        return self.mapa[clave]

    def guardar(self, ruta):
        with open(ruta, "w", newline="", encoding="utf-8-sig") as f:
            w = csv.writer(f, delimiter=";")
            w.writerow(["alias", "valor_original"])
            for a, v in sorted(self.originales.items()):
                w.writerow([a, v])


def leer_texto(ruta):
    for cod in CODIFICACIONES:
        try:
            return ruta.read_text(encoding=cod), cod
        except (UnicodeDecodeError, UnicodeError):
            continue
    sys.exit(f"No pude leer {ruta}: codificación desconocida")


def separador(ruta, texto):
    if ruta.suffix.lower() == ".tsv" or "\t" in texto.splitlines()[0]:
        return "\t"
    return ";" if texto.splitlines()[0].count(";") > texto.splitlines()[0].count(",") else ","


def leer_tabla(ruta):
    texto, cod = leer_texto(ruta)
    sep = separador(ruta, texto)
    filas = list(csv.reader(texto.splitlines(), delimiter=sep))
    return filas, sep, cod


def columnas_objetivo(encabezado, reglas):
    """Índice de columna -> prefijo, comparando nombres sin mayúsculas ni espacios extra."""
    res = {}
    for i, nombre in enumerate(encabezado):
        for col, prefijo in reglas.items():
            if norm(nombre) == norm(col):
                res[i] = prefijo
    return res


def aplicar_terminos(valor, terminos, alias):
    if not isinstance(valor, str):
        return valor
    for prefijo, termino in terminos:
        patron = re.compile(re.escape(termino), re.IGNORECASE)
        if patron.search(valor):
            valor = patron.sub(alias.alias(prefijo, termino), valor)
    return valor


def reemplazo_en_texto(valor, alias, _cache={}):
    """Nombres ya conocidos que aparecen dentro de un texto (ej.: una descripción)."""
    if not isinstance(valor, str):
        return valor
    conocidos = [(v, a) for a, v in alias.originales.items()
                 if len(v) >= 5 and re.search(r"[^\W\d_]", v)]
    if not conocidos:
        return valor
    clave = len(conocidos)
    if _cache.get("n") != clave:
        conocidos.sort(key=lambda x: -len(x[0]))
        _cache["n"] = clave
        _cache["mapa"] = {norm(v): a for v, a in conocidos}
        _cache["re"] = re.compile(
            r"(?<!\w)(" + "|".join(re.escape(v) for v, _ in conocidos) + r")(?!\w)", re.IGNORECASE)
    return _cache["re"].sub(lambda m: _cache["mapa"].get(norm(m.group(1)), m.group(1)), valor)


def reemplazo_global(valor, alias):
    """Celda cuyo contenido completo es un valor ya anonimizado en otra columna."""
    if not isinstance(valor, str) or not re.search(r"[^\W\d_]", valor):
        return valor  # solo textos con letras: no tocar importes ni cantidades
    return alias.por_valor.get(norm(valor), valor)


# ---------- Repartos de centros de costo («50% 4410 - 50% 4420») ----------

PORCENTAJE = r"(?<![\w.,])\d{1,3}(?:[.,]\d+)?\s*%"
CODIGO = r"[A-Za-z]{0,4}-?\d{3,}"
_PORCENTAJE = re.compile(PORCENTAJE)
_CODIGO = re.compile(CODIGO)
_CODIGO_DESPUES = re.compile(r"\s*(?:(?:de|del|al|a|para|en)\s+)?(?<![\w-])(" + CODIGO + r")(?![\w-])", re.IGNORECASE)
_CODIGO_ANTES = re.compile(r"(?<![\w-])(" + CODIGO + r")\s*[:=\-–]?\s*$")
_CLAVE_CC = re.compile(r"(?<!\w)(?:c\.?c\.?|ceco|centros?\s+de\s+costos?)(?![\w-])\s*(?:n[°º.]?|#|:)?\s*"
                       r"(" + CODIGO + r"(?:\s*(?:[,;/y-])\s*" + CODIGO + r")*)(?![\w-])", re.IGNORECASE)
_SEPARADORES = r"(?:\s|[,;/+\-–]|(?<![^\W\d_])(?:y|de|del|al|a|para|en)(?![^\W\d_]))*"
_PIEZA = re.compile(r"^(" + _SEPARADORES + r")(.*?)(" + _SEPARADORES + r")$", re.IGNORECASE | re.DOTALL)
_ALIAS = re.compile(r"^[A-Z]{1,8}-\d{3,}$")


def prefijo_centro_costo(reglas):
    """Prefijo de la columna de centro de costo (para reusar sus alias en los repartos)."""
    for col, prefijo in reglas.items():
        if "centro" in norm(col) and "cost" in norm(col):
            return prefijo
    return "CC"


def _es_alias(texto, alias):
    return bool(_ALIAS.match(texto)) and texto in alias.originales


def codigos_en_reparto(texto):
    """Posición de cada código pegado a un porcentaje: «50% 4410», «4410 50%», «50% del 4410»."""
    spans = set()
    for m in _PORCENTAJE.finditer(texto):
        despues = _CODIGO_DESPUES.match(texto, m.end())
        if despues:
            spans.add(despues.span(1))
        antes = _CODIGO_ANTES.search(texto[:m.start()])
        if antes:
            spans.add(antes.span(1))
    return spans


def repartos_en_texto(valor, alias, prefijo_cc):
    """Centros de costo escritos a mano dentro de un texto libre -> alias del centro de costo.

    Se reemplaza un código pegado a un porcentaje si en el texto hay al menos dos (un
    reparto: «50% 4410 - 50% 4420») o si ya es un centro de costo conocido; y siempre que
    vaya después de «CC», «CeCo» o «centro de costo». Con un solo porcentaje y un número
    desconocido no se toca (puede ser un importe: «IVA 21% 15000»).
    """
    if not isinstance(valor, str):
        return valor
    pares = codigos_en_reparto(valor)
    if len(pares) < 2:
        pares = {s for s in pares if (prefijo_cc, norm(valor[s[0]:s[1]])) in alias.mapa}
    for m in _CLAVE_CC.finditer(valor):
        inicio = m.start(1)
        pares |= {(inicio + c.start(), inicio + c.end()) for c in _CODIGO.finditer(m.group(1))}
    for ini, fin in sorted(pares, reverse=True):
        codigo = valor[ini:fin]
        if not _es_alias(codigo, alias):
            valor = valor[:ini] + alias.alias(prefijo_cc, codigo) + valor[fin:]
    return valor


def reparto_en_columna(valor, prefijo, alias, prefijo_cc):
    """Celda de una columna con regla que reparte por porcentajes: conserva la estructura.

    «50% 4410 - 50% Taller Norte» -> «50% CC-001 - 50% SEC-001»: los códigos reciben el
    alias del centro de costo (o el de la columna, si ya lo tienen ahí) y los textos el de
    la columna. Devuelve None si la celda no tiene porcentajes.
    """
    if not isinstance(valor, str) or not _PORCENTAJE.search(valor):
        return None
    piezas = re.split("(" + PORCENTAJE + ")", valor)
    for i in range(0, len(piezas), 2):
        izq, centro, der = _PIEZA.match(piezas[i]).groups()
        if not centro or _es_alias(centro, alias):
            continue
        if _CODIGO.fullmatch(centro) and (prefijo, norm(centro)) not in alias.mapa:
            centro = alias.alias(prefijo_cc, centro)
        else:
            centro = alias.alias(prefijo, centro)
        piezas[i] = izq + centro + der
    return "".join(piezas)


def valor_de_columna(valor, prefijo, alias, prefijo_cc="CC"):
    """Alias del valor de una columna con regla (o de la celda al lado de su etiqueta)."""
    reparto = reparto_en_columna(valor, prefijo, alias, prefijo_cc)
    return reparto if reparto is not None else alias.alias(prefijo, valor)


def limpiar_texto(valor, alias, terminos, prefijo_cc="CC"):
    """Reemplazos para celdas sin regla: valores conocidos, términos sueltos y repartos."""
    valor = reemplazo_en_texto(reemplazo_global(valor, alias), alias)
    return repartos_en_texto(aplicar_terminos(valor, terminos, alias), alias, prefijo_cc)


# ---------- TSV / CSV ----------

def procesar_tabla(ruta, reglas, terminos, alias, salida, prefijo_cc="CC"):
    filas, sep, cod = leer_tabla(ruta)
    if not filas:
        return
    cols = columnas_objetivo(filas[0], reglas)
    for fila in filas[1:]:
        for i, prefijo in cols.items():
            if i < len(fila):
                fila[i] = valor_de_columna(fila[i], prefijo, alias, prefijo_cc)
    for fila in filas[1:]:
        for i, v in enumerate(fila):
            if i not in cols:
                fila[i] = limpiar_texto(v, alias, terminos, prefijo_cc)
    destino = salida / ruta.name
    with open(destino, "w", newline="", encoding="utf-8") as f:
        csv.writer(f, delimiter=sep).writerows(filas)
    print(f"  {ruta.name}: columnas anonimizadas {sorted(set(cols.values())) or 'ninguna'}")


# ---------- Excel ----------

PROPIEDADES_TEXTO = ("creator", "lastModifiedBy", "title", "subject", "description",
                     "keywords", "category", "contentStatus", "identifier")


def limpiar_propiedades(libro):
    """Borra autor, último en modificar y demás textos de las propiedades del archivo."""
    from openpyxl.packaging.custom import CustomPropertyList

    for nombre in PROPIEDADES_TEXTO:
        setattr(libro.properties, nombre, None)
    libro.properties.creator = "anonimizado"
    libro.custom_doc_props = CustomPropertyList()


def limpiar_vinculos_externos(libro):
    """Vínculos a otros libros: borra la copia de sus datos que Excel guarda y la ruta.

    Excel guarda, invisible, una copia de las celdas que usan las fórmulas del libro
    vinculado (por ejemplo, una hoja «Tablas» con sectores y centros de costo) aunque esa
    hoja se haya borrado. Las fórmulas quedan como están; al abrir, Excel avisa que no
    encuentra el archivo vinculado.
    """
    vinculos = getattr(libro, "_external_links", [])
    for i, vinculo in enumerate(vinculos, 1):
        if vinculo.externalBook is not None:
            vinculo.externalBook.sheetDataSet = None
        if vinculo.file_link is not None:
            vinculo.file_link.Target = f"vinculo_externo_{i}.xlsx"
    return len(vinculos)


def anonimizar_hipervinculos(libro):
    """Hipervínculos: la dirección (ruta o URL, que suele tener nombres de proveedores o
    personas) pasa a `documento_0001.pdf`…, conservando la extensión; el texto que se
    muestra pasa a ser el valor ya anonimizado de la celda. Los vínculos a otra hoja del
    mismo libro no se tocan.
    """
    from urllib.parse import unquote

    n = 0
    for hoja in libro.worksheets:
        for fila in hoja.iter_rows():
            for c in fila:
                vinculo = getattr(c, "hyperlink", None)
                if not vinculo:
                    continue
                if vinculo.target:
                    n += 1
                    nombre = unquote(vinculo.target).replace("\\", "/").rsplit("/", 1)[-1]
                    extension = re.search(r"\.\w{1,5}$", nombre)
                    vinculo.target = f"documento_{n:04d}{extension.group(0).lower() if extension else ''}"
                vinculo.display = c.value if isinstance(c.value, str) else None
                vinculo.tooltip = None
    return n


def comentarios(libro):
    return [c.comment for hoja in libro.worksheets for fila in hoja.iter_rows()
            for c in fila if getattr(c, "comment", None)]


def alias_autores(libro, alias):
    """Autor de cada comentario -> alias: el que ya tenga en alguna columna, o uno AUT-…."""
    autores = {}
    for com in comentarios(libro):
        autor = (com.author or "").strip()
        if autor and autor not in autores:
            autores[autor] = alias.por_valor.get(norm(autor)) or alias.alias("AUT", autor)
    return autores


def anonimizar_comentarios(libro, autores, terminos, alias, prefijo_cc="CC"):
    """El texto de cada comentario pasa por los mismos reemplazos que las celdas.

    Excel suele empezar el texto con «Autor:», así que el nombre del autor se reemplaza
    también dentro del texto, aunque sea corto.
    """
    lista = comentarios(libro)
    for com in lista:
        texto = com.text or ""
        for autor in sorted(autores, key=len, reverse=True):
            texto = re.sub(r"(?<!\w)" + re.escape(autor) + r"(?!\w)", autores[autor], texto, flags=re.IGNORECASE)
        com.text = repartos_en_texto(aplicar_terminos(reemplazo_en_texto(texto, alias), terminos, alias),
                                     alias, prefijo_cc)
        com.author = autores.get((com.author or "").strip(), "")
    return len(lista)


def es_formula(celda):
    return celda.data_type == "f" or (isinstance(celda.value, str) and celda.value.startswith("="))


def formulas_a_valores(ruta, libro):
    """Reemplaza cada fórmula por el valor que Excel guardó la última vez que la calculó.

    Así el resultado no depende de otras hojas o libros (por ejemplo, un XLOOKUP a una hoja
    «Tablas» con los centros de costo), el valor se anonimiza como cualquier otro y no
    quedan textos sin anonimizar dentro de las fórmulas.
    """
    import openpyxl

    valores = openpyxl.load_workbook(ruta, data_only=True)
    n = 0
    for hoja in libro.worksheets:
        calculada = valores[hoja.title]
        for fila in hoja.iter_rows():
            for c in fila:
                if editable_celda(c) and es_formula(c):
                    c.value = calculada[c.coordinate].value
                    n += 1
    return n


def editable_celda(celda):
    from openpyxl.cell.cell import MergedCell

    # En un rango combinado solo la primera celda tiene valor; las demás son de solo lectura
    return not isinstance(celda, MergedCell)


def procesar_excel(ruta, reglas, terminos, alias, salida, conservar_formulas=False, prefijo_cc="CC"):
    import openpyxl

    editable = editable_celda
    libro = openpyxl.load_workbook(ruta)
    n_formulas = 0 if conservar_formulas else formulas_a_valores(ruta, libro)
    for hoja in libro.worksheets:
        # Busca una fila de encabezado con alguna de las columnas pedidas
        cols, fila_enc = {}, None
        for fila in hoja.iter_rows(min_row=1, max_row=FILAS_BUSCAR_ENCABEZADO):
            encontrado = columnas_objetivo([c.value or "" for c in fila], reglas)
            if encontrado:
                cols, fila_enc = encontrado, fila[0].row
                break
        inicio_datos = fila_enc + 1 if fila_enc else None
        if fila_enc:
            # Encabezados en dos filas (por ejemplo, «Imputación» arriba y «Cuenta» / «Sector» abajo)
            siguiente = [c.value or "" for c in next(hoja.iter_rows(min_row=fila_enc + 1, max_row=fila_enc + 1))]
            extra = columnas_objetivo(siguiente, reglas)
            if extra:
                cols.update(extra)
                inicio_datos = fila_enc + 2
            for fila in hoja.iter_rows(min_row=inicio_datos):
                for c in fila:
                    if c.column - 1 in cols and editable(c) and not str(c.value or "").startswith("="):
                        c.value = valor_de_columna(c.value, cols[c.column - 1], alias, prefijo_cc)
        # Etiquetas tipo "Proveedor:" con el valor en la celda de al lado
        for fila in hoja.iter_rows():
            if fila and fila_enc and fila[0].row in (fila_enc - 1, fila_enc, fila_enc + 1):
                continue
            for c in fila:
                etiqueta = norm(str(c.value or "")).rstrip(":").strip()
                for col, prefijo in reglas.items():
                    if etiqueta == norm(col) and c.column < hoja.max_column:
                        vecina = hoja.cell(row=c.row, column=c.column + 1)
                        if (editable(vecina) and vecina.value not in (None, "")
                                and not str(vecina.value).startswith("=")):
                            vecina.value = valor_de_columna(vecina.value, prefijo, alias, prefijo_cc)
    # Autores de comentarios: después de las columnas (para reusar sus alias) y antes de la
    # segunda pasada (para que sus nombres también se reemplacen dentro de las celdas)
    autores = alias_autores(libro, alias)
    # Segunda pasada: valores ya conocidos y términos sueltos en cualquier celda
    for hoja in libro.worksheets:
        for fila in hoja.iter_rows():
            for c in fila:
                if isinstance(c.value, str) and c.value.startswith("="):
                    continue
                if c.value is not None and editable(c):
                    c.value = limpiar_texto(c.value, alias, terminos, prefijo_cc)
    n_comentarios = anonimizar_comentarios(libro, autores, terminos, alias, prefijo_cc)
    limpiar_propiedades(libro)
    n_vinculos = limpiar_vinculos_externos(libro)
    n_hipervinculos = anonimizar_hipervinculos(libro)
    libro.save(salida / ruta.name)
    formulas = f"{n_formulas} fórmulas pasadas a valor" if not conservar_formulas else "fórmulas conservadas"
    print(f"  {ruta.name}: {len(libro.worksheets)} hojas procesadas, {formulas}, {n_comentarios} comentarios,"
          f" {n_hipervinculos} hipervínculos, {n_vinculos} vínculos externos; autor del archivo borrado")


# ---------- Listado ----------

def encabezado_probable(filas):
    """Fila con más títulos (textos cortos, sin números) entre las primeras: (n° de fila, títulos)."""
    mejor = (None, [])
    for n, fila in enumerate(filas, 1):
        titulos = [str(v).strip() for v in fila
                   if isinstance(v, str) and re.search(r"[^\W\d_]", v) and len(v.strip()) <= 40]
        if len(titulos) >= 3 and len(titulos) > len(mejor[1]):
            mejor = (n, titulos)
    return mejor


def rangos(numeros):
    """[2, 3, 4, 7] -> «2-4, 7»."""
    partes, inicio = [], None
    for i, n in enumerate(numeros):
        if inicio is None:
            inicio = n
        if i + 1 == len(numeros) or numeros[i + 1] != n + 1:
            partes.append(str(inicio) if inicio == n else f"{inicio}-{n}")
            inicio = None
    return ", ".join(partes)


def resumen_hojas(libro):
    """Todas las hojas, agrupadas por encabezado, más las etiquetas («Proveedor:»). Sin valores."""
    grupos, etiquetas, ocultas = {}, {}, []
    for i, hoja in enumerate(libro.worksheets, 1):
        if getattr(hoja, "sheet_state", "visible") != "visible":
            ocultas.append(i)
        filas = list(hoja.iter_rows(max_row=FILAS_BUSCAR_ENCABEZADO, values_only=True))
        fila_enc, titulos = encabezado_probable(filas)
        grupos.setdefault((fila_enc, tuple(titulos)), []).append(i)
        for fila in filas:
            for v in fila:
                if isinstance(v, str) and v.strip().endswith(":") and len(v.strip()) <= 40:
                    etiquetas[v.strip()] = etiquetas.get(v.strip(), 0) + 1
    print(f"  {len(libro.worksheets)} hojas" + (f" (ocultas: {rangos(ocultas)})" if ocultas else ""))
    print(f"  Encabezados (fila con más títulos entre las primeras {FILAS_BUSCAR_ENCABEZADO}):")
    for (fila_enc, titulos), hojas in sorted(grupos.items(), key=lambda g: -len(g[1])):
        donde = f"fila {fila_enc}: " + " | ".join(titulos) if fila_enc else "(sin encabezado reconocible)"
        print(f"    {len(hojas):>4} hojas  {donde}")
        print(f"               hojas n° {rangos(hojas)}")
    if etiquetas:
        print("  Etiquetas (texto que termina en «:», con el valor en la celda de al lado):")
        print("    " + ", ".join(f"{e} ({n})" for e, n in sorted(etiquetas.items(), key=lambda x: -x[1])))


def listar(rutas, muestra=False):
    for ruta in rutas:
        print(f"\n=== {ruta.name}")
        if ruta.suffix.lower() in (".xlsx", ".xlsm"):
            import openpyxl

            libro = openpyxl.load_workbook(ruta, read_only=True)
            resumen_hojas(libro)
            if muestra:
                hoja = libro.worksheets[0]
                print(f"  Primeras filas de la hoja 1 (con valores reales, no compartir):")
                for fila in hoja.iter_rows(max_row=8, values_only=True):
                    print("   ", [v for v in fila if v is not None])
        else:
            filas, sep, cod = leer_tabla(ruta)
            print(f"  separador {'TAB' if sep == chr(9) else sep!r}, codificación {cod}, {len(filas) - 1} filas")
            print("  Columnas:", filas[0] if filas else "(vacío)")


# ---------- Chequeo (solo cantidades) ----------

_PALABRA_NOMBRE = r"[A-ZÁÉÍÓÚÑ][a-záéíóúüñ]{2,}"
CHEQUEOS_TEXTO = {
    "posibles nombres de personas (dos palabras con mayúscula: «Juan Pérez»)":
        re.compile(rf"(?<!\w){_PALABRA_NOMBRE}(?:\s+{_PALABRA_NOMBRE})+(?!\w)"),
    "posibles razones sociales (SA, SRL, SAS, S.A.…)":
        re.compile(r"\w\s+(?:S\.?\s?A\.?(?:\s?[CI]\.?){0,3}|S\.?R\.?L\.?|S\.?A\.?S\.?|S\.?H\.?|Hnos\.?)(?![\w.])"),
    "correos electrónicos": re.compile(r"[\w.+-]+@[\w-]+\.\w+"),
    "posibles CUIT/CUIL": re.compile(r"(?<!\d)(?:20|23|24|27|30|33|34)-?\d{8}-?\d(?!\d)"),
    "rutas de archivo o direcciones web": re.compile(r"[A-Za-z]:[\\/]|\\\\\w|https?://|www\.|file:/", re.IGNORECASE),
}
CATEGORIA_REPARTOS = "números pegados a un porcentaje («50% 4410»; o un importe: «IVA 21% 15000»)"
ORIGINALES = ("valores originales en celdas: con letras",
              "valores originales en celdas: solo números (pueden ser importes)",
              "valores originales en todo el archivo: con letras",
              "valores originales en todo el archivo: solo números")
ORDEN_EXCEL = ("hojas", "hojas ocultas (también se anonimizan)", "fórmulas",
               *CHEQUEOS_TEXTO, CATEGORIA_REPARTOS,
               "hipervínculos a archivos o webs", "  de esos, sin anonimizar",
               "comentarios", "  de esos, con autor sin anonimizar",
               "propiedades del archivo con texto (autor, título…)",
               "vínculos a otros libros", "  de esos, con copia de datos guardada",
               "nombres definidos (rangos con nombre)", "listas desplegables con opciones escritas",
               "hojas con encabezado o pie de página de impresión",
               "tablas dinámicas (guardan una copia de los datos)",
               "gráficos (guardan una copia de los datos)", "imágenes")
ORDEN_TABLA = ("filas", *CHEQUEOS_TEXTO, CATEGORIA_REPARTOS)
MAX_UBICACIONES = 20


class Hallazgos:
    def __init__(self, categorias=()):
        self.datos = {c: [] for c in categorias}  # categoría -> ubicaciones (sin valores)

    def agregar(self, categoria, ubicacion="", n=1):
        self.datos.setdefault(categoria, []).extend([ubicacion] * n)

    def mostrar(self, ubicaciones):
        for categoria, lugares in self.datos.items():
            print(f"  {len(lugares):>6}  {categoria}")
            lugares = [u for u in dict.fromkeys(lugares) if u]
            if ubicaciones and lugares:
                print("          " + ", ".join(lugares[:MAX_UBICACIONES])
                      + (f" … (+{len(lugares) - MAX_UBICACIONES})" if len(lugares) > MAX_UBICACIONES else ""))


def cargar_originales(ruta):
    """Valores originales de la tabla de equivalencias (para buscarlos en el resultado)."""
    if not ruta or not Path(ruta).exists():
        return []
    texto, _ = leer_texto(Path(ruta))
    filas = list(csv.reader(texto.splitlines(), delimiter=";"))[1:]
    return sorted({f[1].strip() for f in filas if len(f) > 1 and len(f[1].strip()) >= 3}, key=len, reverse=True)


def patron_originales(originales):
    if not originales:
        return None
    partes = (r"\s+".join(re.escape(p) for p in o.split()) for o in originales)
    return re.compile(r"(?<!\w)(?:" + "|".join(partes) + r")(?!\w)", re.IGNORECASE)


def revisar_texto(texto, donde, hallazgos, patron):
    """Chequeos de una celda de texto: nombres, razones sociales, repartos y valores originales."""
    for categoria, regex in CHEQUEOS_TEXTO.items():
        if regex.search(texto):
            hallazgos.agregar(categoria, donde)
    if any(not _ALIAS.match(texto[i:j]) for i, j in codigos_en_reparto(texto)):
        hallazgos.agregar(CATEGORIA_REPARTOS, donde)
    if patron:
        for m in patron.finditer(texto):
            letras = bool(re.search(r"[^\W\d_]", m.group(0)))
            hallazgos.agregar("valores originales en celdas: con letras" if letras
                              else "valores originales en celdas: solo números (pueden ser importes)", donde)


def chequear_excel(ruta, hallazgos, patron):
    import html
    import zipfile

    import openpyxl

    libro = openpyxl.load_workbook(ruta)
    hallazgos.agregar("hojas", n=len(libro.worksheets))
    for i, hoja in enumerate(libro.worksheets, 1):
        if hoja.sheet_state != "visible":
            hallazgos.agregar("hojas ocultas (también se anonimizan)", f"hoja {i}")
        revisar_texto(hoja.title, f"nombre de la hoja {i}", hallazgos, None)
        for fila in hoja.iter_rows():
            for c in fila:
                donde = f"hoja {i} {c.coordinate}"
                if es_formula(c):
                    hallazgos.agregar("fórmulas", donde)
                elif isinstance(c.value, str):
                    revisar_texto(c.value, donde, hallazgos, patron)
                vinculo = getattr(c, "hyperlink", None)
                if vinculo and vinculo.target:
                    hallazgos.agregar("hipervínculos a archivos o webs", donde)
                    if not re.fullmatch(r"documento_\d{4}(\.\w{1,5})?", vinculo.target):
                        hallazgos.agregar("  de esos, sin anonimizar", donde)
                if getattr(c, "comment", None):
                    hallazgos.agregar("comentarios", donde)
                    if c.comment.author and not _ALIAS.match(c.comment.author):
                        hallazgos.agregar("  de esos, con autor sin anonimizar", donde)
                    revisar_texto(c.comment.text or "", f"comentario {donde}", hallazgos, patron)
        for dv in hoja.data_validations.dataValidation:
            if dv.type == "list" and str(dv.formula1 or "").startswith('"'):
                hallazgos.agregar("listas desplegables con opciones escritas", f"hoja {i}")
        hallazgos.agregar("nombres definidos (rangos con nombre)", f"hoja {i}", n=len(hoja.defined_names))
    hallazgos.agregar("nombres definidos (rangos con nombre)", "libro", n=len(libro.defined_names))
    props = libro.properties
    n_props = sum(1 for nombre in PROPIEDADES_TEXTO if getattr(props, nombre)
                  and not (nombre == "creator" and props.creator == "anonimizado"))
    hallazgos.agregar("propiedades del archivo con texto (autor, título…)", n=n_props + len(libro.custom_doc_props))
    for v in getattr(libro, "_external_links", []):
        hallazgos.agregar("vínculos a otros libros")
        if v.externalBook is not None and v.externalBook.sheetDataSet is not None:
            hallazgos.agregar("  de esos, con copia de datos guardada")

    with zipfile.ZipFile(ruta) as z:
        nombres = z.namelist()
        partes = {n: html.unescape(z.read(n).decode("utf-8", "ignore")) for n in nombres
                  if n.endswith((".xml", ".rels", ".vml"))}
    encabezados = sum(1 for n, x in partes.items() if n.startswith("xl/worksheets/")
                      and re.search(r"<(?:odd|even|first)(?:Header|Footer)>[^<]", x))
    hallazgos.agregar("hojas con encabezado o pie de página de impresión", n=encabezados)
    hallazgos.agregar("tablas dinámicas (guardan una copia de los datos)",
                      n=sum(1 for n in nombres if n.startswith("xl/pivotCache/pivotCacheDefinition")))
    hallazgos.agregar("gráficos (guardan una copia de los datos)", n=sum(1 for n in nombres if n.startswith("xl/charts/chart")))
    hallazgos.agregar("imágenes", n=sum(1 for n in nombres if n.startswith("xl/media/")))
    if patron:
        for nombre, texto in partes.items():
            for m in patron.finditer(texto):
                letras = bool(re.search(r"[^\W\d_]", m.group(0)))
                hallazgos.agregar("valores originales en todo el archivo: con letras" if letras
                                  else "valores originales en todo el archivo: solo números", nombre)


def chequear_tabla(ruta, hallazgos, patron):
    filas, _, _ = leer_tabla(ruta)
    hallazgos.agregar("filas", n=max(len(filas) - 1, 0))
    for n, fila in enumerate(filas[1:], 2):
        for j, v in enumerate(fila, 1):
            revisar_texto(v, f"fila {n} col {j}", hallazgos, patron)


def expandir(rutas):
    """Carpetas -> sus .xlsx, .xlsm, .tsv, .csv y .txt (en Windows el * no se expande solo)."""
    res = []
    for r in rutas:
        if r.is_dir():
            res += sorted(x for x in r.iterdir() if x.suffix.lower() in (".xlsx", ".xlsm", ".tsv", ".csv", ".txt")
                          and not x.name.startswith(("~$", "equivalencias")))
        else:
            res.append(r)
    return res


def chequear(rutas, ruta_equivalencias, ubicaciones=False):
    """Cuenta lo que podría quedar sin anonimizar. Muestra cantidades y, si se pide, celdas; nunca valores."""
    originales = cargar_originales(ruta_equivalencias)
    patron = patron_originales(originales)
    if originales:
        print(f"Buscando también los {len(originales)} valores originales de {ruta_equivalencias}.")
    else:
        print("Sin tabla de equivalencias: no se buscan los valores originales (ver --equivalencias).")
    for ruta in expandir(rutas):
        excel = ruta.suffix.lower() in (".xlsx", ".xlsm")
        orden = ORDEN_EXCEL if excel else ORDEN_TABLA
        if patron:
            orden += ORIGINALES if excel else ORIGINALES[:2]
        hallazgos = Hallazgos(orden)
        print(f"\n=== {ruta.name}")
        if excel:
            chequear_excel(ruta, hallazgos, patron)
        else:
            chequear_tabla(ruta, hallazgos, patron)
        hallazgos.mostrar(ubicaciones)
    print("\nSolo cantidades: se puede compartir. Las categorías «posibles…» incluyen falsos positivos.")


def main():
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("archivos", nargs="+", type=Path)
    p.add_argument("--listar", action="store_true",
                   help="Solo mostrar hojas, encabezados y etiquetas (sin valores)")
    p.add_argument("--muestra", action="store_true",
                   help="Con --listar, mostrar también las primeras filas de la hoja 1 (con valores reales)")
    p.add_argument("--chequear", action="store_true",
                   help="Contar lo que podría quedar sin anonimizar (solo cantidades, sin valores)")
    p.add_argument("--equivalencias", type=Path, default=Path("equivalencias_NO_COMPARTIR.csv"),
                   help="Con --chequear, tabla cuyos valores originales se buscan en los archivos")
    p.add_argument("--ubicaciones", action="store_true",
                   help="Con --chequear, mostrar también hoja y celda de cada hallazgo (sin valores)")
    p.add_argument("--prefijo-cc", metavar="PREFIJO",
                   help="Prefijo para los centros de costo de los repartos «50%% 4410 - 50%% 4420» "
                        "(por defecto, el de la columna de centro de costo, o CC)")
    p.add_argument("-c", "--columna", action="append", default=[], metavar="COLUMNA=PREFIJO")
    p.add_argument("--terminos", type=Path, help="Archivo con líneas PREFIJO;texto")
    p.add_argument("--conservar", action="append", default=[], metavar="VALOR",
                   help="Valor que se deja sin alias (no es sensible), p. ej. MECANICO")
    p.add_argument("--conservar-formulas", action="store_true",
                   help="No reemplazar las fórmulas por su valor (el texto de las fórmulas no se anonimiza)")
    a = p.parse_args()

    faltan = [r for r in a.archivos if not r.exists()]
    if faltan:
        sys.exit(f"No existen: {', '.join(map(str, faltan))}")
    if a.listar:
        listar(expandir(a.archivos), a.muestra)
        return
    if a.chequear:
        chequear(a.archivos, a.equivalencias, a.ubicaciones)
        return
    reglas = {}
    for regla in a.columna:
        if "=" not in regla:
            sys.exit(f"Regla inválida: {regla!r} (formato COLUMNA=PREFIJO)")
        col, prefijo = regla.rsplit("=", 1)
        reglas[col.strip()] = prefijo.strip().upper()
    terminos = []
    if a.terminos:
        texto, _ = leer_texto(a.terminos)
        for linea in texto.splitlines():
            if ";" in linea:
                prefijo, termino = linea.split(";", 1)
                if termino.strip():
                    terminos.append((prefijo.strip().upper(), termino.strip()))
    if not reglas and not terminos:
        sys.exit("Indicá al menos una columna (-c) o un archivo de términos (--terminos)")

    salida = Path("anonimizado")
    salida.mkdir(exist_ok=True)
    alias = Alias(protegidos=list(reglas), conservar=a.conservar)
    prefijo_cc = (a.prefijo_cc or prefijo_centro_costo(reglas)).upper()
    # Primero las tablas (definen alias), después los Excel (los reutilizan)
    orden = sorted(a.archivos, key=lambda r: r.suffix.lower() in (".xlsx", ".xlsm"))
    for ruta in orden:
        if ruta.suffix.lower() in (".xlsx", ".xlsm"):
            procesar_excel(ruta, reglas, terminos, alias, salida, a.conservar_formulas, prefijo_cc)
        elif ruta.suffix.lower() == ".xls":
            print(f"  {ruta.name}: formato .xls viejo; guardalo como .xlsx y volvé a correr")
        else:
            procesar_tabla(ruta, reglas, terminos, alias, salida, prefijo_cc)
    alias.guardar("equivalencias_NO_COMPARTIR.csv")
    print(f"\nListo. Archivos en '{salida}/'. Equivalencias en equivalencias_NO_COMPARTIR.csv (no la subas).")
    print("Revisá los archivos anonimizados antes de compartirlos: lo que no estaba en las reglas queda igual.")


if __name__ == "__main__":
    main()
