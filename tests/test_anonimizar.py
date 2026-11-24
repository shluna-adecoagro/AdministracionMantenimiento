"""Tests de herramientas/anonimizar.py (script independiente de la app)."""
import csv
import importlib.util
import sys
from pathlib import Path

import openpyxl
import pytest

RUTA = Path(__file__).resolve().parent.parent / "herramientas" / "anonimizar.py"


@pytest.fixture
def anonimizar():
    spec = importlib.util.spec_from_file_location("anonimizar", RUTA)
    modulo = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(modulo)
    return modulo


def _correr(anonimizar, monkeypatch, tmp_path, *args):
    monkeypatch.chdir(tmp_path)
    monkeypatch.setattr(sys, "argv", ["anonimizar.py", *args])
    anonimizar.main()


def _hoja_pedido(ruta):
    libro = openpyxl.Workbook()
    hoja = libro.active
    hoja.title = "1104"
    hoja.append(["Pedido N°:", "1104"])
    hoja.append(["Referencia:", "Filtros"])
    hoja.append([])
    hoja.append(["Solicitante(s):", "Juan Pérez"])
    hoja.append([])
    hoja.append(["Cantidad", "Producto", "Detalles", "Imputación", None, "PROVEEDOR", "IMPORTE", "OC"])
    hoja.append([None, None, None, "Cuenta", "Sector"])
    hoja.append([2, "8605140", "Tractor de Juan Pérez", "5110", "Taller Norte", "Repuestos del Sur SA", 62.93, "100834004"])
    hoja.sheet_properties.tabColor = "00B050"
    libro.save(ruta)


def test_excel_conserva_encabezados_y_anonimiza_valores(anonimizar, monkeypatch, tmp_path):
    _hoja_pedido(tmp_path / "pedidos.xlsx")
    _correr(anonimizar, monkeypatch, tmp_path, "pedidos.xlsx",
            "-c", "PROVEEDOR=PROV", "-c", "Solicitante(s)=EMP",
            "-c", "Sector=SEC", "-c", "Cuenta=CTA")

    hoja = openpyxl.load_workbook(tmp_path / "anonimizado" / "pedidos.xlsx").active
    filas = [list(f) for f in hoja.iter_rows(values_only=True)]
    # Encabezados intactos (en una y en dos filas)
    assert filas[5][:8] == ["Cantidad", "Producto", "Detalles", "Imputación", None, "PROVEEDOR", "IMPORTE", "OC"]
    assert filas[6][3:5] == ["Cuenta", "Sector"]
    # Valores anonimizados, también dentro de un texto
    assert filas[3][1] == "EMP-001"
    assert filas[7][3:6] == ["CTA-001", "SEC-001", "PROV-001"]
    assert filas[7][2] == "Tractor de EMP-001"
    # Lo que no está en las reglas queda igual, y el color de la pestaña se conserva
    assert filas[7][1] == "8605140" and filas[7][6] == 62.93 and filas[7][7] == "100834004"
    assert hoja.sheet_properties.tabColor.rgb.endswith("00B050")


def test_alias_consistentes_entre_archivos_y_no_toca_importes(anonimizar, monkeypatch, tmp_path):
    (tmp_path / "cab.tsv").write_text(
        "Nro\tProveedor\tTotal\n101\tRepuestos del Sur SA\t5110\n", encoding="utf-8")
    (tmp_path / "dist.tsv").write_text(
        "Nro\tCentro de Costo\tCuenta\tImporte\n101\t4410\t5110\t5110\n", encoding="utf-8")
    _hoja_pedido(tmp_path / "pedidos.xlsx")
    _correr(anonimizar, monkeypatch, tmp_path, "cab.tsv", "dist.tsv", "pedidos.xlsx",
            "-c", "Proveedor=PROV", "-c", "Centro de Costo=CC", "-c", "Cuenta=CTA")

    cab = list(csv.reader((tmp_path / "anonimizado" / "cab.tsv").open(encoding="utf-8"), delimiter="\t"))
    dist = list(csv.reader((tmp_path / "anonimizado" / "dist.tsv").open(encoding="utf-8"), delimiter="\t"))
    assert cab[1] == ["101", "PROV-001", "5110"]
    assert dist[1] == ["101", "CC-001", "CTA-001", "5110"]
    hoja = openpyxl.load_workbook(tmp_path / "anonimizado" / "pedidos.xlsx").active
    assert hoja["F8"].value == "PROV-001"  # mismo proveedor, mismo alias
    equivalencias = (tmp_path / "equivalencias_NO_COMPARTIR.csv").read_text(encoding="utf-8-sig")
    assert "PROV-001;Repuestos del Sur SA" in equivalencias


def test_conservar_deja_valores_sin_alias(anonimizar, monkeypatch, tmp_path):
    (tmp_path / "ots.tsv").write_text(
        "OT\tRecurso\n1\tMECANICO\n2\tTaller del Sur SA\n3\tmecanico \n", encoding="utf-8")
    (tmp_path / "lineas.tsv").write_text(
        "Nro\tProveedor\n10\tTaller del Sur SA\n", encoding="utf-8")
    _correr(anonimizar, monkeypatch, tmp_path, "ots.tsv", "lineas.tsv",
            "-c", "Recurso=PROV", "-c", "Proveedor=PROV", "--conservar", "MECANICO")

    ots = list(csv.reader((tmp_path / "anonimizado" / "ots.tsv").open(encoding="utf-8"), delimiter="\t"))
    lineas = list(csv.reader((tmp_path / "anonimizado" / "lineas.tsv").open(encoding="utf-8"), delimiter="\t"))
    assert [f[1] for f in ots[1:]] == ["MECANICO", "PROV-001", "mecanico "]
    assert lineas[1] == ["10", "PROV-001"]  # mismo proveedor en otra columna, mismo alias
    equivalencias = (tmp_path / "equivalencias_NO_COMPARTIR.csv").read_text(encoding="utf-8-sig")
    assert "MECANICO" not in equivalencias.upper()


def test_excel_con_celdas_combinadas(anonimizar, monkeypatch, tmp_path):
    # Como la planilla de solicitudes: títulos de grupo combinados arriba del encabezado
    # y valores combinados en varias filas dentro de las columnas a anonimizar
    libro = openpyxl.Workbook()
    hoja = libro.active
    hoja.title = "Enero"
    hoja.append(["Solicitud N°", "Para completar por quien solicita:", None, None, "Para completar por el comprador:"])
    hoja.append([None, "Area", "Solicitó", "Importe", "Proveedor", "Comentarios"])
    hoja.append([1, "Taller Norte", "Juan Pérez", 100, "Repuestos del Sur SA", "Pedido de Juan Pérez"])
    hoja.append([2, None, None, 50, None, None])
    hoja.merge_cells("A1:A2")
    hoja.merge_cells("B1:D1")
    hoja.merge_cells("B3:B4")
    hoja.merge_cells("C3:C4")
    hoja.merge_cells("E3:E4")
    libro.save(tmp_path / "solicitudes.xlsx")

    _correr(anonimizar, monkeypatch, tmp_path, "solicitudes.xlsx",
            "-c", "Area=A", "-c", "Solicitó=SOL", "-c", "Proveedor=PROV")

    hoja = openpyxl.load_workbook(tmp_path / "anonimizado" / "solicitudes.xlsx").active
    assert [hoja[c].value for c in ("B3", "C3", "E3", "F3")] == ["A-001", "SOL-001", "PROV-001", "Pedido de SOL-001"]
    assert hoja["D3"].value == 100 and hoja["B1"].value == "Para completar por quien solicita:"
    assert "B3:B4" in {str(r) for r in hoja.merged_cells.ranges}  # la combinación se conserva


def test_excel_borra_autor_del_archivo_y_anonimiza_comentarios(anonimizar, monkeypatch, tmp_path):
    from openpyxl.comments import Comment

    libro = openpyxl.Workbook()
    hoja = libro.active
    hoja.append(["Solicitó", "Proveedor", "Importe"])
    hoja.append(["Juan Pérez", "Repuestos del Sur SA", 100])
    hoja.append([None, None, None, "Ver con Ana Gómez"])
    hoja["C2"].comment = Comment("Ana Gómez:\nConfirmar con Repuestos del Sur SA", "Ana Gómez")
    hoja["A2"].comment = Comment("Juan Pérez:\nOK", "Juan Pérez")
    libro.properties.creator = "Juan Pérez"
    libro.properties.lastModifiedBy = "Ana Gómez"
    libro.properties.title = "Compras de Ana Gómez"
    libro.save(tmp_path / "solicitudes.xlsx")

    _correr(anonimizar, monkeypatch, tmp_path, "solicitudes.xlsx", "-c", "Solicitó=SOL", "-c", "Proveedor=PROV")

    libro = openpyxl.load_workbook(tmp_path / "anonimizado" / "solicitudes.xlsx")
    hoja = libro.active
    assert libro.properties.creator == "anonimizado"
    assert libro.properties.lastModifiedBy is None and libro.properties.title is None
    # Autor sin alias previo -> AUT-…; autor que ya figura en una columna -> el mismo alias
    assert hoja["C2"].comment.author == "AUT-001"
    assert hoja["C2"].comment.text == "AUT-001:\nConfirmar con PROV-001"
    assert hoja["A2"].comment.author == "SOL-001"
    assert hoja["A2"].comment.text == "SOL-001:\nOK"
    assert hoja["D3"].value == "Ver con AUT-001"  # nombre del autor dentro de una celda
    equivalencias = (tmp_path / "equivalencias_NO_COMPARTIR.csv").read_text(encoding="utf-8-sig")
    assert "AUT-001;Ana Gómez" in equivalencias
    # Nada del original queda en el archivo (celdas, comentarios ni propiedades)
    import zipfile
    with zipfile.ZipFile(tmp_path / "anonimizado" / "solicitudes.xlsx") as z:
        contenido = "".join(z.read(n).decode("utf-8", "ignore") for n in z.namelist())
    for original in ("Juan Pérez", "Ana Gómez", "Repuestos del Sur SA"):
        assert original not in contenido


def test_excel_borra_datos_guardados_de_vinculos_externos(anonimizar, monkeypatch, tmp_path):
    # Copia oculta de una hoja «Tablas» de otro libro, como la que guarda Excel para las fórmulas
    from openpyxl.packaging.relationship import Relationship
    from openpyxl.workbook.external_link.external import (
        ExternalBook, ExternalCell, ExternalLink, ExternalRow, ExternalSheetData,
        ExternalSheetDataSet, ExternalSheetNames)

    libro = openpyxl.Workbook()
    hoja = libro.active
    hoja.append(["Area", "Centro de costo"])
    hoja.append(["Sector Uno", "=_xlfn.XLOOKUP(A2,[1]Tablas!$A:$A,[1]Tablas!$B:$B)"])
    datos = ExternalSheetDataSet(sheetData=[ExternalSheetData(sheetId=0, row=[
        ExternalRow(r=3, cell=[ExternalCell(r="A3", t="str", v="Sector Uno"), ExternalCell(r="B3", v="9001")])])])
    vinculo = ExternalLink(externalBook=ExternalBook(
        sheetNames=ExternalSheetNames(sheetName=["Tablas"]), sheetDataSet=datos, id="rId1"))
    vinculo.file_link = Relationship(
        type="externalLinkPath", Target="file:///C:/Users/jperez/Compras/Mantenimiento.xlsx", TargetMode="External")
    libro._external_links.append(vinculo)
    libro.save(tmp_path / "solicitudes.xlsx")

    # Con las fórmulas conservadas el vínculo sigue en uso: hay que limpiarlo
    _correr(anonimizar, monkeypatch, tmp_path, "solicitudes.xlsx", "-c", "Area=A", "--conservar-formulas")

    import zipfile
    with zipfile.ZipFile(tmp_path / "solicitudes.xlsx") as z:  # el original sí los tenía
        assert any("9001" in z.read(n).decode("utf-8", "ignore") for n in z.namelist())
    with zipfile.ZipFile(tmp_path / "anonimizado" / "solicitudes.xlsx") as z:
        contenido = "".join(z.read(n).decode("utf-8", "ignore") for n in z.namelist())
    for original in ("Sector Uno", "9001", "jperez"):
        assert original not in contenido
    hoja = openpyxl.load_workbook(tmp_path / "anonimizado" / "solicitudes.xlsx").active
    assert hoja["A2"].value == "A-001" and hoja["B2"].value.startswith("=_xlfn.XLOOKUP")


def test_excel_anonimiza_hipervinculos(anonimizar, monkeypatch, tmp_path):
    from openpyxl.worksheet.hyperlink import Hyperlink

    libro = openpyxl.Workbook()
    hoja = libro.active
    hoja.title = "Enero"
    hoja.append(["Proveedor", "Descripción"])
    hoja.append(["Repuestos del Sur SA", "Presupuesto de Juan Pérez"])
    hoja.append(["Repuestos del Sur SA", "Ver enero"])
    hoja["B2"].hyperlink = "Carpeta compras\\Repuestos del Sur SA\\Presupuesto Juan Pérez.PDF"
    hoja["B2"].hyperlink.display = "Presupuesto de Juan Pérez"
    hoja["B2"].hyperlink.tooltip = "Juan Pérez"
    hoja["B3"].hyperlink = Hyperlink(ref="B3", location="'Enero'!A1", display="Ver enero")
    libro.save(tmp_path / "solicitudes.xlsx")

    (tmp_path / "terminos.txt").write_text("EMP;Juan Pérez\n", encoding="utf-8")
    _correr(anonimizar, monkeypatch, tmp_path, "solicitudes.xlsx", "-c", "Proveedor=PROV",
            "--terminos", "terminos.txt")

    hoja = openpyxl.load_workbook(tmp_path / "anonimizado" / "solicitudes.xlsx").active
    assert hoja["B2"].value == "Presupuesto de EMP-001"
    assert hoja["B2"].hyperlink.target == "documento_0001.pdf"
    assert hoja["B3"].hyperlink.location == "'Enero'!A1"  # vínculo interno, intacto
    import zipfile
    with zipfile.ZipFile(tmp_path / "anonimizado" / "solicitudes.xlsx") as z:
        contenido = "".join(z.read(n).decode("utf-8", "ignore") for n in z.namelist())
    for original in ("Juan Pérez", "Repuestos del Sur", "Carpeta compras"):
        assert original not in contenido


def _con_valores_calculados(ruta, valores):
    """openpyxl no guarda el valor calculado de una fórmula: se lo agrega como haría Excel."""
    import re
    import zipfile

    with zipfile.ZipFile(ruta) as z:
        partes = {n: z.read(n) for n in z.namelist()}
    xml = partes["xl/worksheets/sheet1.xml"].decode("utf-8")
    for celda, (tipo, valor) in valores.items():
        xml, n = re.subn(rf'<c r="{celda}"([^>]*)><f>(.*?)</f><v\s*/?>(</v>)?',
                         rf'<c r="{celda}"\1 t="{tipo}"><f>\2</f><v>{valor}</v>', xml)
        assert n == 1, celda
    partes["xl/worksheets/sheet1.xml"] = xml.encode("utf-8")
    with zipfile.ZipFile(ruta, "w") as z:
        for nombre, datos in partes.items():
            z.writestr(nombre, datos)


def test_excel_reemplaza_formulas_por_su_valor_anonimizado(anonimizar, monkeypatch, tmp_path):
    # Centro de costo calculado con un XLOOKUP a una hoja «Tablas» (que se borró antes de compartir)
    libro = openpyxl.Workbook()
    hoja = libro.active
    hoja.append(["Area", "Centro de costo", "Proveedor sugerido", "Proveedor"])
    hoja.append(["Sector Uno", '=_xlfn.XLOOKUP(A2,Tablas!A:A,Tablas!B:B,"Seleccionar área")',
                 "Repuestos del Sur SA", "=C2"])
    hoja.append(["Sector Dos", '=_xlfn.XLOOKUP(A3,Tablas!A:A,Tablas!B:B,"Seleccionar área")', None, "=C3"])
    libro.save(tmp_path / "solicitudes.xlsx")
    _con_valores_calculados(tmp_path / "solicitudes.xlsx", {
        "B2": ("n", "9001"), "D2": ("str", "Repuestos del Sur SA"), "B3": ("e", "#REF!"), "D3": ("n", "0")})
    reglas = ("-c", "Area=A", "-c", "Centro de costo=CC", "-c", "Proveedor sugerido=PROV", "-c", "Proveedor=PROV")

    _correr(anonimizar, monkeypatch, tmp_path, "solicitudes.xlsx", *reglas)

    hoja = openpyxl.load_workbook(tmp_path / "anonimizado" / "solicitudes.xlsx").active
    assert [c.value for c in hoja[2]] == ["A-001", "CC-001", "PROV-001", "PROV-001"]
    assert [c.value for c in hoja[3]] == ["A-002", "#REF!", None, 0]  # error y cero, sin alias
    import zipfile
    with zipfile.ZipFile(tmp_path / "anonimizado" / "solicitudes.xlsx") as z:
        contenido = "".join(z.read(n).decode("utf-8", "ignore") for n in z.namelist())
    assert "<f>" not in contenido and "Tablas" not in contenido and "9001" not in contenido

    # Con --conservar-formulas quedan como estaban
    _correr(anonimizar, monkeypatch, tmp_path, "solicitudes.xlsx", *reglas, "--conservar-formulas")
    hoja = openpyxl.load_workbook(tmp_path / "anonimizado" / "solicitudes.xlsx").active
    assert hoja["B2"].value.startswith("=_xlfn.XLOOKUP") and hoja["D2"].value == "=C2"


def test_repartos_de_centro_de_costo_en_texto_libre(anonimizar, monkeypatch, tmp_path):
    libro = openpyxl.Workbook()
    hoja = libro.active
    hoja.append(["Detalles", "Sector", "Centro de Costo", "Importe", "Observaciones"])
    hoja.append(["Imputar 50% 4410 - 50% 4420", "40% 4410, 60% Taller Norte", 4410, 100, "IVA 21% 15000"])
    hoja.append(["100% 4410", "Taller Norte", 4430, 200, "cargar a CC 4430/4440"])
    hoja.append(["4410 30% y 4499 70%", None, None, 300, "100% 8888"])
    libro.save(tmp_path / "pedidos.xlsx")

    _correr(anonimizar, monkeypatch, tmp_path, "pedidos.xlsx",
            "-c", "Sector=SEC", "-c", "Centro de Costo=CC")

    filas = [list(f) for f in openpyxl.load_workbook(tmp_path / "anonimizado" / "pedidos.xlsx").active
             .iter_rows(min_row=2, values_only=True)]
    # Dos o más porcentajes: reparto; los códigos reciben el alias de la columna de centro de costo
    assert filas[0][0] == "Imputar 50% CC-001 - 50% CC-003"
    assert filas[2][0] == "CC-001 30% y CC-005 70%"
    # En la columna con regla se conserva el reparto: código -> CC, texto -> alias de la columna
    assert filas[0][1] == "40% CC-001, 60% SEC-001" and filas[1][1] == "SEC-001"
    # Un solo porcentaje: solo si el código ya es un centro de costo conocido
    assert filas[1][0] == "100% CC-001"
    assert filas[0][4] == "IVA 21% 15000" and filas[2][4] == "100% 8888"
    # Después de «CC»: siempre, aunque sean varios
    assert filas[1][4] == "cargar a CC CC-002/CC-004"
    assert [f[3] for f in filas] == [100, 200, 300]
    equivalencias = (tmp_path / "equivalencias_NO_COMPARTIR.csv").read_text(encoding="utf-8-sig")
    assert "CC-003;4420" in equivalencias and "8888" not in equivalencias
    assert "15000" not in equivalencias


def test_repartos_en_tsv_con_prefijo_de_la_columna_de_centro_de_costo(anonimizar, monkeypatch, tmp_path):
    (tmp_path / "dist.tsv").write_text(
        "Nro\tCentro de Costo\tComentario\n101\t4410\t50% 4410 - 50% 4420\n", encoding="utf-8")
    _correr(anonimizar, monkeypatch, tmp_path, "dist.tsv", "-c", "Centro de Costo=CECO")

    dist = list(csv.reader((tmp_path / "anonimizado" / "dist.tsv").open(encoding="utf-8"), delimiter="\t"))
    assert dist[1] == ["101", "CECO-001", "50% CECO-001 - 50% CECO-002"]


def test_listar_muestra_todas_las_hojas_sin_valores(anonimizar, monkeypatch, tmp_path, capsys):
    _hoja_pedido(tmp_path / "pedidos.xlsx")
    libro = openpyxl.load_workbook(tmp_path / "pedidos.xlsx")
    for nombre in ("1105", "1106"):
        libro.copy_worksheet(libro["1104"]).title = nombre
    libro.create_sheet("Tablas").append(["Área", "Centro de costo", "Responsable"])
    libro["Tablas"].sheet_state = "hidden"
    libro.save(tmp_path / "pedidos.xlsx")

    _correr(anonimizar, monkeypatch, tmp_path, "pedidos.xlsx", "--listar")

    salida = capsys.readouterr().out
    assert "4 hojas (ocultas: 4)" in salida
    assert "3 hojas  fila 6: Cantidad | Producto | Detalles | Imputación | PROVEEDOR | IMPORTE | OC" in salida
    assert "hojas n° 1-3" in salida and "Área | Centro de costo | Responsable" in salida
    assert "Solicitante(s): (3)" in salida
    for valor in ("Juan Pérez", "Repuestos del Sur", "Filtros", "8605140"):
        assert valor not in salida

    _correr(anonimizar, monkeypatch, tmp_path, "pedidos.xlsx", "--listar", "--muestra")
    assert "Juan Pérez" in capsys.readouterr().out


def test_chequear_muestra_solo_cantidades(anonimizar, monkeypatch, tmp_path, capsys):
    from openpyxl.comments import Comment

    libro = openpyxl.Workbook()
    hoja = libro.active
    hoja.append(["Solicitó", "Proveedor", "Detalles"])
    hoja.append(["Pedro Ramírez", "Repuestos del Sur SA", "50% 7710 - 50% 7720, ver jperez@empresa.com"])
    hoja["C2"].hyperlink = "C:\\Compras\\Repuestos del Sur SA\\presupuesto.pdf"
    hoja["A2"].comment = Comment("Ana Gómez: ok", "Ana Gómez")
    libro.save(tmp_path / "solicitudes.xlsx")

    def chequear(*args):
        _correr(anonimizar, monkeypatch, tmp_path, "--chequear", *args)
        salida = capsys.readouterr().out
        for valor in ("Pedro Ramírez", "Repuestos del Sur", "7710", "jperez", "Ana Gómez", "Compras"):  # no los de los rótulos
            assert valor not in salida
        return {linea[8:].strip(): int(linea[:8]) for linea in salida.splitlines()
                if linea[:8].strip().isdigit()}

    # Antes de anonimizar, sin tabla de equivalencias
    antes = chequear("solicitudes.xlsx")
    nombres, razones, correos = list(anonimizar.CHEQUEOS_TEXTO)[:3]
    assert (antes[nombres], antes[razones], antes[correos]) == (2, 1, 1)  # nombres: celda A2 y comentario
    assert antes[anonimizar.CATEGORIA_REPARTOS] == 1
    assert antes["hipervínculos a archivos o webs"] == 1 and antes["de esos, sin anonimizar"] == 1
    assert antes["de esos, con autor sin anonimizar"] == 1
    assert not any(c.startswith("valores originales") for c in antes)

    _correr(anonimizar, monkeypatch, tmp_path, "solicitudes.xlsx", "-c", "Solicitó=SOL", "-c", "Proveedor=PROV",
            "--terminos", str(_terminos(tmp_path)))
    capsys.readouterr()
    # El original contra la tabla de equivalencias: encuentra los valores
    original = chequear("solicitudes.xlsx")
    assert original["valores originales en celdas: con letras"] >= 2
    assert original["valores originales en todo el archivo: con letras"] >= 3
    # El resultado (pasando la carpeta, como en Windows): no queda nada
    despues = chequear("anonimizado", "--ubicaciones")
    for categoria, n in despues.items():
        if categoria not in ("hojas", "comentarios", "hipervínculos a archivos o webs"):
            assert n == 0, categoria


def _terminos(tmp_path):
    ruta = tmp_path / "terminos.txt"
    ruta.write_text("EMP;Ana Gómez\nMAIL;jperez@empresa.com\n", encoding="utf-8")
    return ruta
