"""Anonimiza planillas (Excel .xlsx) y reportes (TSV/CSV) antes de compartirlos.

Reemplaza datos sensibles (proveedores, empleados, sectores, centros de costo,
cuentas...) por alias consistentes: el mismo valor recibe siempre el mismo alias
en todos los archivos y hojas, así se siguen pudiendo cruzar los datos.

La tabla de equivalencias (original -> alias) queda en tu computadora, en
`equivalencias_NO_COMPARTIR.csv`. No la subas.

Uso:
  1) Ver qué columnas y hojas hay:
       python herramientas/anonimizar.py --listar pedidos.xlsx solicitudes.tsv

  2) Anonimizar indicando columna=PREFIJO (una -c por columna):
       python herramientas/anonimizar.py pedidos.xlsx solicitudes.tsv lineas.tsv distrib.tsv ^
           -c "Proveedor=PROV" -c "Solicitante=EMP" -c "Centro de Costo=CC" ^
           -c "Cuenta=CTA" -c "Sector=SEC"

     Opcional: --terminos terminos.txt  (una línea por término: PREFIJO;texto)
     para textos que aparecen sueltos dentro de celdas (por ejemplo, un nombre
     escrito en una descripción o en el encabezado de una hoja de pedido).

  Los archivos anonimizados quedan en la carpeta `anonimizado/`. En los Excel también se
  borran el autor y demás propiedades del archivo, y los comentarios de celda pasan por los
  mismos reemplazos (su autor recibe un alias AUT-…, o el que ya tenga en otra columna).
  Requiere openpyxl para los .xlsx (ya está en el entorno del proyecto).
"""
import argparse
import csv
import re
import sys
from pathlib import Path

CODIFICACIONES = ("utf-8-sig", "utf-16", "cp1252", "latin-1")
FILAS_BUSCAR_ENCABEZADO = 15


def norm(texto):
    return re.sub(r"\s+", " ", str(texto)).strip().casefold()


class Alias:
    """Asigna alias consistentes por prefijo: PROV-001, PROV-002..."""

    def __init__(self, protegidos=()):
        # Nombres de columna y etiquetas: nunca se anonimizan (son encabezados)
        self.protegidos = {norm(p).rstrip(":").strip() for p in protegidos}
        self.mapa = {}  # (prefijo, valor normalizado) -> alias
        self.originales = {}  # alias -> valor original
        self.contadores = {}
        self.por_valor = {}  # valor normalizado -> alias (para reemplazo global)

    def alias(self, prefijo, valor):
        if valor is None or str(valor).strip() == "":
            return valor
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


# ---------- TSV / CSV ----------

def procesar_tabla(ruta, reglas, terminos, alias, salida):
    filas, sep, cod = leer_tabla(ruta)
    if not filas:
        return
    cols = columnas_objetivo(filas[0], reglas)
    for fila in filas[1:]:
        for i, prefijo in cols.items():
            if i < len(fila):
                fila[i] = alias.alias(prefijo, fila[i])
    for fila in filas[1:]:
        for i, v in enumerate(fila):
            if i not in cols:
                fila[i] = aplicar_terminos(reemplazo_en_texto(reemplazo_global(v, alias), alias), terminos, alias)
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


def anonimizar_comentarios(libro, autores, terminos, alias):
    """El texto de cada comentario pasa por los mismos reemplazos que las celdas.

    Excel suele empezar el texto con «Autor:», así que el nombre del autor se reemplaza
    también dentro del texto, aunque sea corto.
    """
    lista = comentarios(libro)
    for com in lista:
        texto = com.text or ""
        for autor in sorted(autores, key=len, reverse=True):
            texto = re.sub(r"(?<!\w)" + re.escape(autor) + r"(?!\w)", autores[autor], texto, flags=re.IGNORECASE)
        com.text = aplicar_terminos(reemplazo_en_texto(texto, alias), terminos, alias)
        com.author = autores.get((com.author or "").strip(), "")
    return len(lista)


def procesar_excel(ruta, reglas, terminos, alias, salida):
    import openpyxl
    from openpyxl.cell.cell import MergedCell

    def editable(celda):
        # En un rango combinado solo la primera celda tiene valor; las demás son de solo lectura
        return not isinstance(celda, MergedCell)

    libro = openpyxl.load_workbook(ruta)
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
                        c.value = alias.alias(cols[c.column - 1], c.value)
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
                            vecina.value = alias.alias(prefijo, vecina.value)
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
                    c.value = aplicar_terminos(reemplazo_en_texto(reemplazo_global(c.value, alias), alias), terminos, alias)
    n_comentarios = anonimizar_comentarios(libro, autores, terminos, alias)
    limpiar_propiedades(libro)
    libro.save(salida / ruta.name)
    print(f"  {ruta.name}: {len(libro.worksheets)} hojas procesadas, {n_comentarios} comentarios;"
          " autor del archivo borrado")


# ---------- Listado ----------

def listar(rutas):
    for ruta in rutas:
        print(f"\n=== {ruta.name}")
        if ruta.suffix.lower() in (".xlsx", ".xlsm"):
            import openpyxl

            libro = openpyxl.load_workbook(ruta, read_only=True)
            print(f"  {len(libro.sheetnames)} hojas: {', '.join(libro.sheetnames[:10])}"
                  + (" ..." if len(libro.sheetnames) > 10 else ""))
            hoja = libro.worksheets[0]
            print(f"  Primeras filas de «{hoja.title}»:")
            for fila in hoja.iter_rows(max_row=8, values_only=True):
                print("   ", [v for v in fila if v is not None])
        else:
            filas, sep, cod = leer_tabla(ruta)
            print(f"  separador {'TAB' if sep == chr(9) else sep!r}, codificación {cod}, {len(filas) - 1} filas")
            print("  Columnas:", filas[0] if filas else "(vacío)")


def main():
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("archivos", nargs="+", type=Path)
    p.add_argument("--listar", action="store_true", help="Solo mostrar hojas y columnas")
    p.add_argument("-c", "--columna", action="append", default=[], metavar="COLUMNA=PREFIJO")
    p.add_argument("--terminos", type=Path, help="Archivo con líneas PREFIJO;texto")
    a = p.parse_args()

    faltan = [r for r in a.archivos if not r.exists()]
    if faltan:
        sys.exit(f"No existen: {', '.join(map(str, faltan))}")
    if a.listar:
        listar(a.archivos)
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
    alias = Alias(protegidos=list(reglas))
    # Primero las tablas (definen alias), después los Excel (los reutilizan)
    orden = sorted(a.archivos, key=lambda r: r.suffix.lower() in (".xlsx", ".xlsm"))
    for ruta in orden:
        if ruta.suffix.lower() in (".xlsx", ".xlsm"):
            procesar_excel(ruta, reglas, terminos, alias, salida)
        elif ruta.suffix.lower() == ".xls":
            print(f"  {ruta.name}: formato .xls viejo; guardalo como .xlsx y volvé a correr")
        else:
            procesar_tabla(ruta, reglas, terminos, alias, salida)
    alias.guardar("equivalencias_NO_COMPARTIR.csv")
    print(f"\nListo. Archivos en '{salida}/'. Equivalencias en equivalencias_NO_COMPARTIR.csv (no la subas).")
    print("Revisá los archivos anonimizados antes de compartirlos: lo que no estaba en las reglas queda igual.")


if __name__ == "__main__":
    main()
