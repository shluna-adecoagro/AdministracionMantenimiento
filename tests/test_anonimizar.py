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
