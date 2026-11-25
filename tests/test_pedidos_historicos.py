"""
Fase 10, PR 10.6: importación del Excel histórico de pedidos.

Los libros de prueba se arman en memoria con openpyxl, con el formato del Excel
real (docs/analisis_excel_pedidos.md): cabecera en A1:E4, encabezado de la tabla
en las filas 6 y 7, datos desde la fila 8.
"""
import csv
import io
from datetime import datetime

import openpyxl
import pytest
from openpyxl.styles.colors import Color

from app.crud.intercambio.excel_pedidos import (
    ANULADO,
    CERRADO,
    EN_PROCESO,
    SOLICITADO,
    leer_libro,
    numero_de_texto,
    oc_de_valor,
)
from app.crud.intercambio.pedidos_historicos import (
    COLUMNAS_PENDIENTES,
    MOTIVO_ANULACION_HISTORICO,
    importar_pedidos_historicos,
    porcentajes,
    repartir,
)
from app.models.activos_models import Activo, EstadoActivo
from app.models.documentos_models import Adjudicacion, DocumentoLinea, DocumentoProveedor
from app.models.marcas_modelos_models import Marca, Modelo
from app.models.materiales_models import CategoriaMaterial, Material
from app.models.pedidos_models import Pedido, PedidoLinea, PedidoLineaDestino
from app.models.recursos_models import Proveedor

PESOS = '_-"$"\\ * #,##0.00_-;\\-"$"\\ * #,##0.00_-;_-"$"\\ * "-"??_-;_-@_-'
DOLARES = '_-[$USD]\\ * #,##0.00_-;\\-[$USD]\\ * #,##0.00_-;_-[$USD]\\ * "-"??_-;_-@_-'
# Color del tema. En el Excel real, el verde de la mayoría de las pestañas es accent6
# (70AD47); openpyxl guarda el tema de Office 2007, donde el verde es accent3 (9BBB59)
# y accent6 es naranja: el color se resuelve con el tema del propio libro.
VERDE_TEMA = Color(theme=6)
NARANJA_TEMA = Color(theme=9)
ESTANDAR = ("IMPORTE", "OC", "Recibido?", "Observaciones")


def _hoja(wb, nombre, filas, *, color=None, numero=None, fecha=datetime(2026, 11, 3), referencia="Filtros Case",
          encabezados=ESTANDAR, combinar=(), formatos=None, sub=None):
    """`filas`: listas de valores desde la columna A, a partir de la fila 8."""
    ws = wb.create_sheet(nombre)
    if color is not None:
        ws.sheet_properties.tabColor = color
    ws["A1"], ws["B1"], ws["D1"], ws["E1"] = "Pedido N°:", numero or int(nombre.split()[1]), "Fecha: ", fecha
    ws["A2"], ws["B2"] = "Referencia:", referencia
    ws["A4"], ws["B4"] = "Solicitante(s):", "Juan"
    for c, t in enumerate(("Cantidad", "Producto", "Detalles", "Imputación", None, "PROVEEDOR", *encabezados), 1):
        ws.cell(6, c, t)
    ws["D7"], ws["E7"] = "Cuenta", "Sector"
    for c, t in (sub or {}).items():
        ws.cell(7, c, t)
    for r, fila in enumerate(filas, 8):
        for c, v in enumerate(fila, 1):
            if v is not None:
                ws.cell(r, c, v)
                if c >= 7 and isinstance(v, (int, float)):
                    ws.cell(r, c).number_format = PESOS
    for (r, c), f in (formatos or {}).items():
        ws.cell(r, c).number_format = f
    for rango in combinar:
        ws.merge_cells(rango)
    return ws


def _bytes(wb):
    if "Sheet" in wb.sheetnames:
        del wb["Sheet"]
    salida = io.BytesIO()
    wb.save(salida)
    return salida.getvalue()


def _libro(*hojas):
    """hojas: (nombre, filas, opciones)."""
    wb = openpyxl.Workbook()
    wb.create_sheet("Plantilla pedidos")
    for nombre, filas, opciones in hojas:
        _hoja(wb, nombre, filas, **opciones)
    return _bytes(wb)


def _leer(*hojas):
    return {h.numero: h for h in leer_libro(_libro(*hojas)).hojas}


# ---------------------------------------------------------------------------
# Adaptador (sin base)
# ---------------------------------------------------------------------------

def test_cabecera_y_plantilla_ignorada():
    libro = leer_libro(_libro(("Pedido 1104", [[2, "8605140", "W20F"]], {"color": VERDE_TEMA})))
    assert libro.ignoradas == ["Plantilla pedidos"]
    h = libro.hojas[0]
    assert (h.numero, h.fecha.isoformat(), h.referencia, h.solicitantes) == ("1104", "2026-11-03", "Filtros Case",
                                                                            ["Juan"])
    assert h.filas[0].producto == "8605140"  # un código numérico con cantidad no es un total


@pytest.mark.parametrize("color, estado", [
    (VERDE_TEMA, CERRADO), ("FF00B050", CERRADO), ("FF92D050", CERRADO), ("FF0070C0", CERRADO),
    ("FFFFC000", EN_PROCESO), ("FFFFFF00", EN_PROCESO), (NARANJA_TEMA, EN_PROCESO), ("FFFF0000", ANULADO), ("FFC00000", ANULADO),
    (None, SOLICITADO),
])
def test_estado_por_color_de_pestana(color, estado):
    h = _leer(("Pedido 1", [[1, "Filtro"]], {"color": color}))["1"]
    assert h.estado == estado and not h.revisar


def test_color_desconocido_queda_solicitado_y_a_revisar():
    h = _leer(("Pedido 1", [[1, "Filtro"]], {"color": "FF808080"}))["1"]
    assert h.estado == SOLICITADO
    assert "color de la pestaña" in h.revisar[0]


def test_numero_de_la_hoja_y_sufijo():
    hojas = _leer(("Pedido 770", [[1, "Filtro"]], {"numero": 769}),
                  ("Pedido 762 - NO", [[1, "Bulones"]], {"color": "FFC00000"}))
    assert "dice 769" in hojas["770"].revisar[0]
    assert hojas["762"].notas == ["Nombre de la hoja: «Pedido 762 - NO»"]


def test_celdas_combinadas_se_repiten():
    filas = [[1, "Filtro A", "580 - EQ-027", "CTA-008", "CC-02", "Lange", 10, 100834004],
             [2, "Filtro B", None, None, None, None, 20, None]]
    h = _leer(("Pedido 1", filas, {"combinar": ("C8:C9", "D8:D9", "E8:E9", "F8:F9", "H8:H9")}))["1"]
    b = h.filas[1]
    assert (b.detalles, b.cuenta, b.sector, b.proveedor, b.nro_oc) == ("580 - EQ-027", "CTA-008", "CC-02", "Lange",
                                                                       "100834004")
    assert not b.oc_completada  # vino de la celda combinada, no se dedujo


def test_moneda_por_formato_de_celda():
    filas = [[1, "Con pesos", None, None, None, "A", 10],
             [1, "Con dólares", None, None, None, "A", 10],
             [1, "Sin símbolo", None, None, None, "A", 10],
             [1, "Sin símbolo, otra con pesos", None, None, None, "A", 10, None, None, None, 12]]
    h = _leer(("Pedido 1", filas, {"formatos": {(9, 7): DOLARES, (10, 7): "General", (11, 7): "General"},
                                   "sub": {11: "Otro"}}))["1"]
    monedas = [(c.moneda, c.moneda_inferida) for f in h.filas for c in f.cotizaciones if c.elegida]
    assert monedas == [("ARS", False), ("USD", False), ("USD", True), ("ARS", True)]


def test_importe_unitario_o_total():
    # Con SUM(importe), «IMPORTE» es el total de la línea; si no, el unitario.
    filas = [[2, "Filtro", None, None, None, "A", 100], [None, None, None, None, None, None, "=SUM(G8:G8)"]]
    h = _leer(("Pedido 1", filas, {}), ("Pedido 2", [[2, "Filtro", None, None, None, "A", 100]], {}))
    assert h["1"].filas[0].cotizaciones[0].precio_unitario == 50
    assert h["2"].filas[0].cotizaciones[0].precio_unitario == 100
    # Con «PU», el unitario es «PU».
    h = _leer(("Pedido 3", [[2, "Filtro", None, None, None, "A", 30, 60]],
               {"encabezados": ("PU", "IMPORTE", "OC", "Recibido?", "Observaciones")}))
    assert h["3"].filas[0].cotizaciones[0].precio_unitario == 30


def test_columnas_de_otros_proveedores():
    filas = [[2, "Filtro", None, None, None, "Lange", 100, None, None, None, 120, 100]]
    h = _leer(("Pedido 1", filas, {"sub": {11: "JMG", 12: "Lange S.A."}}))["1"]
    cots = {c.proveedor: (c.precio_unitario, c.elegida) for c in h.filas[0].cotizaciones}
    # La columna «Lange S.A.» repite el precio del elegido: no es otra cotización.
    assert cots == {"Lange": (100, True), "JMG": (120, False)}


def test_una_columna_por_proveedor():
    filas = [[2, "8605140", None, None, None, None, 62.93, 72, None],
             [4, "84557099", None, None, None, "GRUMAQ", 19.96, 34.5, 100834004]]
    h = _leer(("Pedido 1104", filas, {"color": VERDE_TEMA, "encabezados": ("GRUMAQ", "JMG", "OC", "Observaciones"),
                                      "formatos": {(8, 7): "General", (8, 8): "General"}}))["1104"]
    assert h.formato == "proveedores"
    primera = h.filas[0]
    # Hoja cerrada con una sola OC: vale para todas, y con ella el proveedor.
    assert (primera.nro_oc, primera.oc_completada, primera.proveedor) == ("100834004", True, "GRUMAQ")
    assert {c.proveedor: c.elegida for c in primera.cotizaciones} == {"GRUMAQ": True, "JMG": False}
    assert all(c.moneda == "USD" and c.moneda_inferida for c in primera.cotizaciones)


def test_oc_completada_por_proveedor_y_ambigua():
    filas = [[1, "A", None, None, None, "Lange", 10, 100000001],
             [1, "B", None, None, None, "Lange", 10, None],
             [1, "C", None, None, None, "JMG", 10, 100000002],
             [1, "D", None, None, None, None, 10, None]]
    h = _leer(("Pedido 1", filas, {"color": "FF92D050"}))["1"]
    assert [f.nro_oc for f in h.filas] == ["100000001", "100000001", "100000002", None]
    assert "varias OC" in h.filas[3].revisar[0]


def test_en_proceso_no_completa_la_oc():
    filas = [[1, "A", None, None, None, "Lange", 10, 100000001], [1, "B", None, None, None, None, 10, None]]
    h = _leer(("Pedido 1", filas, {"color": "FFFFC000"}))["1"]
    assert h.filas[1].nro_oc is None and not h.filas[1].revisar


def test_filas_sin_cantidad_totales_y_errores():
    filas = [[None, "2 tambor plus 50"], [None, "faltaría 1 cuchilla para pala"], ["40m", "Manguera de aire"],
             [None, "#VALUE!"], [None, "1207727.48"]]
    h = _leer(("Pedido 1", filas, {}))["1"]
    assert [(f.cantidad, f.producto) for f in h.filas] == [(2, "tambor plus 50"), (40, "Manguera de aire")]
    assert all(f.revisar for f in h.filas)
    assert h.notas == ["Fila 9: faltaría 1 cuchilla para pala"]


def test_valores_de_oc():
    assert oc_de_valor(100834004) == ("100834004", None)
    oc, motivo = oc_de_valor("100777817  - 100777819")
    assert oc == "100777817" and "más de un número" in motivo
    assert oc_de_valor("Solicitada")[0] is None and oc_de_valor("Solicitada")[1]
    assert oc_de_valor(52442.742)[0] is None
    assert oc_de_valor(" ") == (None, None)


def test_numero_de_texto():
    assert numero_de_texto("USD 1.429,7520") == 1429.752
    assert numero_de_texto("$ 35.000") == 35000
    assert numero_de_texto("1207727.48") == 1207727.48
    assert numero_de_texto("Filtro 32217") is None


def test_hoja_con_columnas_corridas():
    # Como el 1103: la «OC» está en la columna «PROVEEDOR».
    filas = [[2, "AL150288", "6125D", "CTA-008", "CC-07", 100834008, "Lange", 68399.1, 92681.73]]
    h = _leer(("Pedido 1103", filas, {"color": VERDE_TEMA, "encabezados": ("OC", "OC", "Recibido?")}))["1103"]
    assert h.formato == "corrido" and h.revisar
    f = h.filas[0]
    assert (f.cantidad, f.producto, f.nro_oc, f.cotizaciones) == (2, "AL150288", None, [])
    assert "100834008" in f.observaciones[0]


def test_recibido():
    filas = [[1, "A", None, None, None, None, None, None, "OK 20-05"], [1, "B", None, None, None, None, None, None, "NO"]]
    a, b = _leer(("Pedido 1", filas, {"color": VERDE_TEMA}))["1"].filas
    assert a.recibido_ok and not a.revisar and a.observaciones == ["Recibido?: OK 20-05"]
    assert b.recibido_no and "Recibido?" in b.revisar[0]


def test_porcentajes_y_reparto():
    assert porcentajes("40% CC-02, 30% CC-08, 15% CTA-004, 15% CC-07") == [
        (40, "CC-02"), (30, "CC-08"), (15, "CTA-004"), (15, "CC-07")]
    assert porcentajes("66% CTA-003, 34% CC-06") == [(66, "CTA-003"), (34, "CC-06")]
    assert porcentajes("CC-02") is None
    assert repartir(7, 3) == [3, 2, 2]
    assert repartir(1, 2) == [0.5, 0.5]


# ---------------------------------------------------------------------------
# Importación a la base
# ---------------------------------------------------------------------------

def _guardar(db, *objetos):
    db.session.add_all(objetos)
    db.session.commit()
    return objetos[0] if len(objetos) == 1 else objetos


@pytest.fixture
def maestros(db, sector, cuenta, categorias_activo, estado_sector_activo):
    from app.models.sectores_models import Sector

    tambo = _guardar(db, Sector(nombre_sector="Tambo 1", centro_costo="CC-02",
                                estado_sector_id=estado_sector_activo.estado_sector_id))
    recria = _guardar(db, Sector(nombre_sector="Recría", centro_costo="CC-08",
                                 estado_sector_id=estado_sector_activo.estado_sector_id))
    marca = _guardar(db, Marca(nombre_marca="John Deere"))
    modelo = _guardar(db, Modelo(nombre_modelo="5090D", marca_id=marca.marca_id,
                                 categoria_activo_id=categorias_activo["Tractor"].categoria_activo_id))
    estado = EstadoActivo.query.first().estado_activo_id
    activos = [_guardar(db, Activo(numero_activo=f"EQ-0{n}", descripcion=f"Tractor {n}", modelo_id=modelo.modelo_id,
                                   categoria_activo_id=categorias_activo["Tractor"].categoria_activo_id,
                                   sector_id=sector.sector_id, estado_activo_id=estado)) for n in (17, 26, 20)]
    cat = CategoriaMaterial.query.first().categoria_material_id
    filtro = _guardar(db, Material(codigo="RE504836", descripcion="Filtro de aceite", categoria_material_id=cat))
    lange = _guardar(db, Proveedor(razon_social="Lange"))
    return {"tambo": tambo, "recria": recria, "modelo": modelo, "activos": activos, "filtro": filtro,
            "lange": lange, "sector": sector, "cuenta": cuenta}


def _excel_base():
    return _libro(
        ("Pedido 1104", [
            [3, "RE504836", "5090D - EQ-017 EQ-026 EQ-020", "5101", "Taller", "Lange", 100, 100834004, "ok"],
            [2, "Bolillero 32217", "Sala de balanza", "5101", "50% CC-02, 50% CC-08", None, 50, None, None, None, 60],
        ], {"color": VERDE_TEMA, "sub": {11: "JMG"}}),
        ("Pedido 1105", [[1, "Manijas", "Tractor 17", "5101", "Taller"]], {"color": "FFFF0000"}),
        ("Pedido 1106", [[1, "RE504836", "EQ-017", "5101", "Taller", "Lange", 100]], {"color": "FFFFC000"}),
        ("Pedido 1107", [[1, "Filtro nuevo", None, None, None, None, 80]], {}),
    )


def _importar(contenido=None, **kw):
    return importar_pedidos_historicos(contenido or _excel_base(), nombre="Pedidos.xlsx", **kw)


def _linea(numero, nro=1):
    return PedidoLinea.query.join(Pedido).filter(Pedido.numero == numero, PedidoLinea.nro_linea == nro).one()


def test_importa_pedidos_lineas_y_destinos(maestros):
    r = _importar()
    assert r.ok, r.resumen()
    assert r.conteo["pedidos_creados"] == 4

    p = Pedido.query.filter_by(numero="1104").one()
    assert (p.origen, p.clave_origen, p.solicitante_texto) == ("historico", "excel_pedidos|Pedido 1104", "Juan")

    # Material por código; tres activos con 3 unidades: una para cada uno.
    l1 = _linea("1104", 1)
    assert l1.material_id == maestros["filtro"].material_id
    assert (l1.sin_conformidad, l1.estado_visible, l1.nro_oc) == (True, "Cerrado", "100834004")
    assert sorted((d.activo.numero_activo, d.cantidad) for d in l1.destinos) == [
        ("EQ-017", 1), ("EQ-020", 1), ("EQ-026", 1)]
    assert all(d.sector_imputado_id == maestros["sector"].sector_id and d.cuenta_id == maestros["cuenta"].cuenta_id
               for d in l1.destinos)
    assert "Recibido?: ok" in l1.observaciones

    # Sin código; sector con porcentajes: un destino por centro de costo. La OC se
    # tomó de la otra fila (hoja cerrada con una sola OC).
    l2 = _linea("1104", 2)
    assert l2.material_id is None and l2.nro_oc == "100834004"
    assert sorted((d.sector_imputado.nombre_sector, d.cantidad, d.destino) for d in l2.destinos) == [
        ("Recría", 1, "a_identificar"), ("Tambo 1", 1, "a_identificar")]
    assert l2.destinos[0].detalle_texto == "Sala de balanza"


def test_estados_por_color(maestros):
    _importar()
    anulada = _linea("1105")
    assert anulada.estado_visible == "Anulado" and anulada.motivo.nombre_motivo == MOTIVO_ANULACION_HISTORICO
    # «Tractor 17» es la descripción de un activo.
    assert anulada.destinos[0].activo.numero_activo == "EQ-017"
    en_proceso = _linea("1106")
    assert (en_proceso.estado, en_proceso.estado_visible) == ("en_cotizacion", "Adjudicado")
    solicitada = _linea("1107")
    assert solicitada.estado_visible == "Solicitado"
    # Sin «Detalles»: gasto general (no hay nada que identificar).
    assert solicitada.destinos[0].destino == "gasto_general"


def test_ofertas_y_adjudicaciones(maestros):
    _importar()
    oferta = DocumentoProveedor.query.filter_by(proveedor_texto="Lange", nro_oc="100834004").one()
    assert (oferta.tipo, oferta.origen, oferta.proveedor_id, oferta.moneda, oferta.moneda_inferida) == (
        "oferta", "historico", maestros["lange"].recurso_id, "ARS", False)
    assert oferta.fecha.isoformat() == "2026-11-03"
    # La línea 2 no tiene proveedor, pero sí la OC (tomada de la otra fila), y una
    # OC es de un solo proveedor: también es de Lange.
    assert [(l.cantidad, l.precio_unitario) for l in oferta.lineas] == [(3, 100), (2, 50)]
    assert [l.adjudicaciones[0].cantidad_adjudicada for l in oferta.lineas] == [3, 2]
    # Sin proveedor ni de dónde deducirlo: el precio va a las observaciones.
    assert "Precio sin proveedor: 80 ARS" in _linea("1107").observaciones
    # La cotización de JMG: oferta sin OC, adjudicada en 0 (cotizado, no comprado).
    jmg = DocumentoProveedor.query.filter_by(proveedor_texto="JMG").one()
    assert jmg.nro_oc is None and jmg.proveedor_id is None
    assert jmg.lineas[0].adjudicaciones[0].cantidad_adjudicada == 0
    # Las anuladas no generan ofertas.
    assert not DocumentoProveedor.query.filter(DocumentoProveedor.clave_origen.like("%Pedido 1105%")).count()


def test_reimportar_no_duplica_y_no_pisa_lo_identificado(db, maestros):
    _importar()
    totales = (PedidoLinea.query.count(), PedidoLineaDestino.query.count(), DocumentoLinea.query.count(),
               Adjudicacion.query.count())
    # El gestor identifica el material a mano y revisa la oferta.
    cat = CategoriaMaterial.query.first().categoria_material_id
    l2 = _linea("1104", 2)
    otro = _guardar(db, Material(codigo="ROD-1", descripcion="Rodamiento 32217", categoria_material_id=cat))
    l2.material_id = otro.material_id
    oferta = DocumentoProveedor.query.filter_by(proveedor_texto="JMG").one()
    oferta.revisado, oferta.proveedor_id, oferta.moneda = True, maestros["lange"].recurso_id, "ARS"
    db.session.commit()

    r = _importar()
    assert r.ok, r.resumen()
    assert r.conteo["pedidos_creados"] == r.conteo["lineas_creadas"] == r.conteo["destinos_creados"] == 0
    assert (PedidoLinea.query.count(), PedidoLineaDestino.query.count(), DocumentoLinea.query.count(),
            Adjudicacion.query.count()) == totales
    assert _linea("1104", 2).material_id == otro.material_id
    assert r.conteo["ofertas_revisadas_salteadas"] == 1


def test_no_toca_destinos_cargados_en_la_app(client, maestros):
    _importar()
    l2 = _linea("1104", 2)
    r = client.post("/api/pedido_linea_destinos", json={"pedido_linea_id": l2.pedido_linea_id, "cantidad": 1,
                                                        "destino": "gasto_general"})
    assert r.status_code == 201, r.get_json()
    r = _importar()
    assert r.ok
    assert len(_linea("1104", 2).destinos) == 3
    assert any("destinos cargados en la app" in m for _, _, m in r.informe)


def test_pendientes_y_equivalencias(maestros):
    r = _importar()
    filas = list(csv.DictReader(io.StringIO(r.pendientes_csv().decode("utf-8-sig")), delimiter=";"))
    assert tuple(filas[0]) == COLUMNAS_PENDIENTES
    por_texto = {(f["tipo"], f["texto"]): f for f in filas}
    assert ("material", "Bolillero 32217") in por_texto
    assert ("destino", "Sala de balanza") in por_texto
    # Las anuladas no van a pendientes.
    assert ("material", "Manijas") not in por_texto
    assert "Pedido 1104 (Filtros Case)" in por_texto[("material", "Bolillero 32217")]["contexto"]

    equivalencias = (
        "id;tipo;texto;resultado;codigos;descripcion_propuesta;categoria_propuesta;tipo_material_propuesto;"
        "unidad_propuesta;confianza;motivo\n"
        "M-1;material;Bolillero 32217;material_existente;RE504836;;;;;alta;\n"
        "D-1;destino;Sala de balanza;varios_activos;EQ-017 | EQ-026;;;;;media;\n"
        "D-2;destino;Filtro nuevo;activo;NO-EXISTE;;;;;baja;\n"
    ).encode()
    r = _importar(equivalencias=equivalencias)
    assert r.ok, r.resumen()
    l2 = _linea("1104", 2)
    assert l2.material_id == maestros["filtro"].material_id
    # Varios activos y sector con porcentajes: mandan los porcentajes, con el modelo común.
    assert sorted((d.destino, d.modelo_id, d.cantidad) for d in l2.destinos) == [
        ("modelo", maestros["modelo"].modelo_id, 1), ("modelo", maestros["modelo"].modelo_id, 1)]
    assert r.conteo["equivalencias_usadas"] == 2


def test_simular_no_guarda(maestros):
    r = _importar(simular=True)
    assert r.ok and r.conteo["pedidos_creados"] == 4
    assert Pedido.query.count() == 0


def test_pedido_cargado_en_la_app_no_se_pisa(client, maestros):
    r = client.post("/api/pedidos", json={"numero": "1107", "fecha_pedido": "2026-11-23"})
    assert r.status_code == 201
    r = _importar()
    assert r.ok
    assert Pedido.query.filter_by(numero="1107").one().origen == "app"
    assert any("ya existe el pedido 1107" in m for _, _, m in r.informe)


def test_equivalencias_sin_columnas():
    r = importar_pedidos_historicos(b"", equivalencias=b"id;texto\n1;x\n")
    assert not r.ok and "faltan las columnas" in r.errores[0][3]


def test_comando_importar_pedidos(app, maestros, tmp_path):
    excel = tmp_path / "Pedidos.xlsx"
    excel.write_bytes(_excel_base())
    pendientes, informe = tmp_path / "pendientes.csv", tmp_path / "informe.csv"
    resultado = app.test_cli_runner().invoke(args=[
        "importar-pedidos", str(excel), "--pendientes", str(pendientes), "--informe", str(informe)])
    assert resultado.exit_code == 0, resultado.output
    assert "Pedidos: 4 creados" in resultado.output
    assert pendientes.read_text(encoding="utf-8-sig").startswith("id;tipo;texto;contexto;veces")
    assert informe.exists()


def test_linea_sin_detalles(db, maestros, ubicacion):
    """
    Sin «Detalles»: un repuesto del maestro va al stock del taller de su sector (si
    tiene uno solo); si no, «a identificar» con nota. Lo que no está en el maestro
    (ferretería), a gasto general.
    """
    r = _importar(_libro(("Pedido 735", [
        [2, "RE504836", None, "5101", "Taller"],    # «Taller» tiene una ubicación: Galpón 1
        [1, "RE504836", None, "5101", "Tambo 1"],   # «Tambo 1» no tiene ubicaciones
        [1, "Alicate", None, "5101", "Taller"],
    ], {"color": VERDE_TEMA})))
    assert r.ok, r.resumen()
    stock, sin_taller, alicate = (_linea("735", n).destinos[0] for n in (1, 2, 3))
    assert (stock.destino, stock.ubicacion_id, stock.cantidad) == ("stock", ubicacion.ubicacion_id, 2)
    assert (sin_taller.destino, sin_taller.sector_imputado_id) == ("a_identificar", maestros["tambo"].sector_id)
    assert "falta el taller" in sin_taller.detalle_texto
    assert (alicate.destino, alicate.sector_imputado_id, alicate.cuenta_id) == (
        "gasto_general", maestros["sector"].sector_id, maestros["cuenta"].cuenta_id)
    assert not PedidoLineaDestino.query.filter_by(detalle_texto=None).filter(
        PedidoLineaDestino.destino == "a_identificar").count()


def test_material_identificado_despues_pasa_a_stock(db, maestros, ubicacion):
    excel = _libro(("Pedido 735", [[1, "AL150288", None, "5101", "Taller"]], {"color": VERDE_TEMA}))
    _importar(excel)
    assert _linea("735").destinos[0].destino == "gasto_general"
    cat = CategoriaMaterial.query.first().categoria_material_id
    _guardar(db, Material(codigo="AL150288", descripcion="Filtro", categoria_material_id=cat))
    assert _importar(excel).ok
    d = _linea("735").destinos[0]
    assert (d.destino, d.ubicacion_id) == ("stock", ubicacion.ubicacion_id)
