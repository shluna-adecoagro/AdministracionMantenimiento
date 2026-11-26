"""
Fase 10, PR 10.4: documentos de proveedores, adjudicación y lectura con Copilot.

Ejemplo de los tests: el pedido pide 40 L de aceite 15W-40 (el genérico) y un
filtro; la oferta de Lange cotiza bidones de 20 L y el filtro.
"""
import pytest

from app.crud.intercambio.documentos_copilot import COLUMNAS_CABECERA, COLUMNAS_LINEAS, importar_documentos
from app.models.documentos_models import Adjudicacion, DocumentoLinea, DocumentoProveedor
from app.models.materiales_models import CategoriaMaterial, Material
from app.models.motivos_models import MotivoOperacion
from app.models.pedidos_models import PedidoLinea
from app.models.recursos_models import Proveedor
from app.models.unidadmedida_models import TipoUnidad, UnidadMedida


def _guardar(db, *objetos):
    db.session.add_all(objetos)
    db.session.commit()
    return objetos[0] if len(objetos) == 1 else objetos


def _errores(r):
    return r.get_json()["errors"]


@pytest.fixture
def lange(db):
    return _guardar(db, Proveedor(razon_social="Lubricantes Lange S.A.", cuit="30-71234567-8"))


@pytest.fixture
def m(db):
    """Materiales: filtro, aceite 15W-40 (genérico) con su bidón de 20 L, e hidráulico con su bidón."""
    tipo = TipoUnidad.query.filter_by(nombre_tipo="Volumen").one().tipo_unidad_id
    litros = _guardar(db, UnidadMedida(nombre_unidad="Litros", abreviatura="L", tipo_unidad_id=tipo))
    cat = CategoriaMaterial.query.first().categoria_material_id
    filtro = _guardar(db, Material(codigo="RE504836", descripcion="Filtro de aceite", categoria_material_id=cat))
    aceite = _guardar(db, Material(codigo="GEN-15W40", descripcion="Aceite 15W-40", es_generico=True,
                                   categoria_material_id=cat, unidad_medida_id=litros.unidad_medida_id))
    bidon = _guardar(db, Material(codigo="AC-20", descripcion="Aceite 15W-40 bidón 20 L", categoria_material_id=cat,
                                  material_generico_id=aceite.material_id, presentacion_cantidad=20,
                                  unidad_medida_id=litros.unidad_medida_id))
    hidra = _guardar(db, Material(codigo="GEN-HIDRA", descripcion="Aceite hidráulico", es_generico=True,
                                  categoria_material_id=cat, unidad_medida_id=litros.unidad_medida_id))
    bidon_h = _guardar(db, Material(codigo="HI-20", descripcion="Hidráulico bidón 20 L", categoria_material_id=cat,
                                    material_generico_id=hidra.material_id, presentacion_cantidad=20,
                                    unidad_medida_id=litros.unidad_medida_id))
    return {"filtro": filtro, "aceite": aceite, "bidon": bidon, "hidra": hidra, "bidon_h": bidon_h, "litros": litros}


@pytest.fixture
def pedido(client, m):
    p = client.post("/api/pedidos", json={"fecha_pedido": "2026-11-23", "referencia": "Service"}).get_json()
    lineas = {}
    for clave, material, cantidad in (("aceite", m["aceite"], 40), ("filtro", m["filtro"], 3)):
        r = client.post("/api/pedido_lineas", json={"pedido_id": p["pedido_id"], "material_id": material.material_id,
                                                    "cantidad": cantidad, "destino": "a_identificar"})
        assert r.status_code == 201, r.get_json()
        lineas[clave] = db_get(PedidoLinea, r.get_json()["pedido_linea_id"])
    assert client.post(f"/pedidos/{p['pedido_id']}/accion/enviar_a_compras").status_code == 302
    return lineas


def db_get(model, id_):
    from app.core.db import db

    return db.session.get(model, id_)


def _oferta(client, lange, **extra):
    r = client.post("/api/documentos_proveedor", json={
        "tipo": "oferta", "proveedor_id": lange.recurso_id, "numero": "9676", "fecha": "2026-08-26",
        "moneda": "ARS", "total_sin_iva": 1000, **extra})
    assert r.status_code == 201, r.get_json()
    return db_get(DocumentoProveedor, r.get_json()["documento_id"])


def _linea_oferta(client, doc, material=None, cantidad=1, precio=100, **extra):
    datos = {"documento_id": doc.documento_id, "cantidad": cantidad, "precio_unitario": precio, **extra}
    if material is not None:
        datos["material_id"] = material.material_id
    return client.post("/api/documento_lineas", json=datos)


def _adjudicar(client, linea_oferta_id, linea_pedido, cantidad):
    return client.post("/api/adjudicaciones", json={"documento_linea_id": linea_oferta_id,
                                                    "pedido_linea_id": linea_pedido.pedido_linea_id,
                                                    "cantidad_adjudicada": cantidad})


# ---------------------------------------------------------------------------
# Documento
# ---------------------------------------------------------------------------

@pytest.mark.parametrize("datos", [{"proveedor_cuit": "30712345678"},
                                   {"proveedor_texto": "LUBRICANTES LANGE SA"}])
def test_proveedor_identificado(client, lange, datos):
    r = client.post("/api/documentos_proveedor", json={"tipo": "oferta", **datos})
    assert r.status_code == 201 and r.get_json()["proveedor_id"] == lange.recurso_id


def test_proveedor_sin_identificar_y_revisado(client, lange):
    r = client.post("/api/documentos_proveedor", json={"tipo": "oferta", "proveedor_texto": "Otro SRL",
                                                       "fecha": "2026-08-26", "moneda": "ARS"})
    doc = r.get_json()
    assert doc["proveedor_id"] is None and doc["revisado"] is False and doc["origen"] == "app"
    url = f"/api/documentos_proveedor/{doc['documento_id']}"
    r = client.patch(url, json={"revisado": True})
    assert r.status_code == 400 and "el proveedor identificado" in _errores(r)["revisado"]
    assert client.patch(url, json={"revisado": True, "proveedor_id": lange.recurso_id}).status_code == 200


def test_numero_unico_por_proveedor_y_tipo(client, lange):
    _oferta(client, lange)
    r = client.post("/api/documentos_proveedor", json={"tipo": "oferta", "proveedor_id": lange.recurso_id,
                                                       "numero": "9676"})
    assert r.status_code == 409
    r = client.post("/api/documentos_proveedor", json={"tipo": "factura", "proveedor_id": lange.recurso_id,
                                                       "numero": "9676", "nro_oc": " oc 4500 12 "})
    assert r.status_code == 201 and r.get_json()["nro_oc"] == "OC450012"


def test_lineas_y_totales(client, lange, m):
    doc = _oferta(client, lange)
    r = _linea_oferta(client, doc, m["bidon"], cantidad=2, precio=300)
    assert r.status_code == 201, r.get_json()
    linea = r.get_json()
    assert (linea["nro_linea"], linea["unidad_medida_id"], linea["subtotal"]) == (1, m["litros"].unidad_medida_id, 600)
    assert linea["se_cuenta_en"] == "envases (20 L)"
    _linea_oferta(client, doc, m["filtro"], cantidad=3, precio=100)
    d = client.get(f"/api/documentos_proveedor/{doc.documento_id}").get_json()
    assert (d["total_lineas"], d["diferencia"]) == (900, 100)
    assert d["nombre"] == "Oferta 9676 — Lubricantes Lange S.A."


def test_una_oferta_no_tiene_genericos(client, lange, m):
    r = _linea_oferta(client, _oferta(client, lange), m["aceite"])
    assert r.status_code == 400 and "no es una opción válida" in _errores(r)["material_id"]


# ---------------------------------------------------------------------------
# Adjudicación
# ---------------------------------------------------------------------------

def test_generico_y_presentacion_se_convierten(client, lange, m, pedido):
    doc = _oferta(client, lange)
    lo = _linea_oferta(client, doc, m["bidon"], cantidad=5, precio=300).get_json()
    r = _adjudicar(client, lo["documento_linea_id"], pedido["aceite"], 2)
    assert r.status_code == 201, r.get_json()
    assert r.get_json()["adjudicada_en_pedido"] == 40  # 2 bidones × 20 L
    lp = client.get(f"/api/pedido_lineas/{pedido['aceite'].pedido_linea_id}").get_json()
    assert (lp["solicitada"], lp["ofertada"], lp["adjudicada"], lp["pendiente_comprar"]) == (40, 100, 40, 0)
    d = client.get(f"/api/documentos_proveedor/{doc.documento_id}").get_json()
    assert d["total_adjudicado"] == 600


def test_no_se_adjudica_mas_de_lo_ofertado(client, lange, m, pedido):
    lo = _linea_oferta(client, _oferta(client, lange), m["filtro"], cantidad=2).get_json()
    r = _adjudicar(client, lo["documento_linea_id"], pedido["filtro"], 3)
    assert r.status_code == 400 and "más de lo ofertado" in _errores(r)["cantidad_adjudicada"]


def test_presentacion_de_otro_generico(client, lange, m, pedido):
    lo = _linea_oferta(client, _oferta(client, lange), m["bidon_h"], cantidad=2).get_json()
    r = _adjudicar(client, lo["documento_linea_id"], pedido["aceite"], 1)
    assert r.status_code == 400 and "no es una presentación de" in _errores(r)["documento_linea_id"]


def test_material_sin_identificar(client, lange, m, pedido):
    doc = _oferta(client, lange)
    lo = _linea_oferta(client, doc, None, cantidad=3, descripcion_proveedor="FILTRO ACEITE JD").get_json()
    assert lo["a_revisar"] == "Sí"
    # Contra un genérico: no hay de dónde convertir.
    r = _adjudicar(client, lo["documento_linea_id"], pedido["aceite"], 1)
    assert r.status_code == 400 and "no tiene el material identificado" in _errores(r)["documento_linea_id"]
    # Contra un material concreto: tal cual.
    r = _adjudicar(client, lo["documento_linea_id"], pedido["filtro"], 3)
    assert r.status_code == 201 and r.get_json()["adjudicada_en_pedido"] == 3


def test_no_se_adjudica_a_una_linea_anulada(client, lange, m, pedido):
    anulacion = MotivoOperacion.query.filter_by(tipo_operacion="ANULACION").first().motivo_operacion_id
    client.patch(f"/api/pedido_lineas/{pedido['filtro'].pedido_linea_id}",
                 json={"estado": "anulado", "motivo_operacion_id": anulacion})
    lo = _linea_oferta(client, _oferta(client, lange), m["filtro"], cantidad=3).get_json()
    r = _adjudicar(client, lo["documento_linea_id"], pedido["filtro"], 1)
    assert r.status_code == 400 and "anulada" in _errores(r)["pedido_linea_id"]


def test_solo_lineas_de_ofertas(client, lange, m, pedido):
    remito = _oferta(client, lange, tipo="remito", numero="R-1")
    lo = _linea_oferta(client, remito, m["filtro"], cantidad=3).get_json()
    r = _adjudicar(client, lo["documento_linea_id"], pedido["filtro"], 1)
    assert r.status_code == 400 and "no es una opción válida" in _errores(r)["documento_linea_id"]


# ---------------------------------------------------------------------------
# Acciones: vincular y adjudicar
# ---------------------------------------------------------------------------

def test_vincular_y_adjudicar(client, lange, m, pedido):
    doc = _oferta(client, lange)
    _linea_oferta(client, doc, m["bidon"], cantidad=5, precio=300)
    _linea_oferta(client, doc, m["filtro"], cantidad=2, precio=100)
    _linea_oferta(client, doc, None, cantidad=1, descripcion_proveedor="Algo raro")

    r = client.post(f"/documentos_proveedor/{doc.documento_id}/accion/vincular_pedidos", follow_redirects=True)
    html = r.get_data(as_text=True)
    assert "Se vincularon 2 líneas de pedido." in html and "1 línea de la oferta sin el material" in html
    assert Adjudicacion.query.count() == 2 and all(a.cantidad_adjudicada == 0 for a in Adjudicacion.query)
    # Repetir no duplica.
    client.post(f"/documentos_proveedor/{doc.documento_id}/accion/vincular_pedidos")
    assert Adjudicacion.query.count() == 2

    r = client.post(f"/documentos_proveedor/{doc.documento_id}/accion/adjudicar_vinculado", follow_redirects=True)
    assert "Se adjudicaron 2 vínculos" in r.get_data(as_text=True)
    adj = {a.pedido_linea_id: a.cantidad_adjudicada for a in Adjudicacion.query}
    # Aceite: faltan 40 L → 2 bidones. Filtro: faltan 3, pero se ofertaron 2.
    assert adj == {pedido["aceite"].pedido_linea_id: 2, pedido["filtro"].pedido_linea_id: 2}
    lp = client.get(f"/api/pedido_lineas/{pedido['filtro'].pedido_linea_id}").get_json()
    assert lp["pendiente_comprar"] == 1


def test_adjudicar_redondea_a_envases_enteros(client, lange, m, enviar):
    p = client.post("/api/pedidos", json={"fecha_pedido": "2026-11-23"}).get_json()
    client.post("/api/pedido_lineas", json={"pedido_id": p["pedido_id"], "material_id": m["aceite"].material_id,
                                            "cantidad": 30, "destino": "a_identificar"})
    enviar(p["pedido_id"])  # «Vincular con pedidos» toma solo las líneas enviadas
    doc = _oferta(client, lange)
    _linea_oferta(client, doc, m["bidon"], cantidad=5, precio=300)
    client.post(f"/documentos_proveedor/{doc.documento_id}/accion/vincular_pedidos")
    client.post(f"/documentos_proveedor/{doc.documento_id}/accion/adjudicar_vinculado")
    assert Adjudicacion.query.one().cantidad_adjudicada == 2  # 30 L → 2 bidones de 20 L


def test_acciones_solo_en_ofertas(client, lange):
    remito = _oferta(client, lange, tipo="remito", numero="R-9")
    html = client.get(f"/documentos_proveedor/{remito.documento_id}?seccion=documento_lineas").get_data(as_text=True)
    assert "Vincular con pedidos" not in html
    oferta = _oferta(client, lange, numero="X-1")
    html = client.get(f"/documentos_proveedor/{oferta.documento_id}?seccion=documento_lineas").get_data(as_text=True)
    assert "Vincular con pedidos" in html and "Adjudicar lo vinculado" in html


def test_borrado(client, lange, m, pedido):
    doc = _oferta(client, lange)
    lo = _linea_oferta(client, doc, m["filtro"], cantidad=3).get_json()
    _adjudicar(client, lo["documento_linea_id"], pedido["filtro"], 1)
    # Una línea de pedido con adjudicaciones no se borra; el documento sí, con lo suyo.
    assert client.delete(f"/api/pedido_lineas/{pedido['filtro'].pedido_linea_id}").status_code == 409
    assert client.delete(f"/api/proveedores/{lange.recurso_id}").status_code == 409
    assert client.delete(f"/api/documentos_proveedor/{doc.documento_id}").status_code in (200, 204)
    assert (DocumentoLinea.query.count(), Adjudicacion.query.count()) == (0, 0)


# ---------------------------------------------------------------------------
# Lectura con Copilot
# ---------------------------------------------------------------------------

def _csv(columnas, filas):
    lineas = [";".join(columnas)]
    for fila in filas:
        lineas.append(";".join(f'"{fila.get(c, "")}"' for c in columnas))
    return "\n".join(lineas).encode()


CABECERA = {"clave_documento": "LANGE-oferta-9676", "tipo": "oferta", "numero": "9676",
            "proveedor_nombre": "Lubricantes Lange SA", "fecha": "2026-08-26", "moneda": "ARS",
            "total_sin_iva": "4422863.15", "descuento_global_pct": "26.20", "total": "5351664.41",
            "total_usd_informado": "3486.43", "archivo": "Lange 9676.pdf"}
LINEAS = [
    {"clave_documento": "LANGE-oferta-9676", "nro_linea": "1", "tipo_linea": "material",
     "codigo_proveedor": "RE504836", "descripcion_proveedor": "RE504836 JD FILTRO ACEITE MOTOR",
     "cantidad": "10", "precio_lista": "53936.52", "descuento_pct": "26.20", "precio_unitario": "39805.1518",
     "material_sugerido": "RE504836"},
    {"clave_documento": "LANGE-oferta-9676", "nro_linea": "2", "tipo_linea": "material",
     "codigo_proveedor": "XX-99", "descripcion_proveedor": "CORREA", "cantidad": "1",
     "precio_unitario": "100", "material_sugerido": "XX-99"},
]


def test_importar_lectura_de_copilot(app, lange, m):
    r = importar_documentos(_csv(COLUMNAS_CABECERA, [CABECERA]), _csv(COLUMNAS_LINEAS, LINEAS))
    assert r.ok, r.resumen()
    assert (r.documentos_creados, r.lineas_creadas) == (1, 2)
    doc = DocumentoProveedor.query.one()
    assert (doc.proveedor_id, doc.origen, doc.clave_origen, doc.revisado) == (
        lange.recurso_id, "pdf", "LANGE-oferta-9676", False)
    assert doc.descuento_global_pct == 26.2 and "[Lange 9676.pdf]" in doc.observaciones
    l1, l2 = doc.lineas
    assert (l1.material_id, l1.precio_unitario, l1.clave_origen) == (m["filtro"].material_id, 39805.1518,
                                                                     "LANGE-oferta-9676|1")
    assert l2.material_id is None and "XX-99" in l2.motivo_revision and l2.a_revisar == "Sí"

    # Repetir no cambia nada.
    r = importar_documentos(_csv(COLUMNAS_CABECERA, [CABECERA]), _csv(COLUMNAS_LINEAS, LINEAS))
    assert r.ok and (r.documentos_sin_cambios, r.lineas_creadas, r.lineas_actualizadas) == (1, 0, 0)

    # Si una línea ya no viene, se borra.
    r = importar_documentos(_csv(COLUMNAS_CABECERA, [CABECERA]), _csv(COLUMNAS_LINEAS, LINEAS[:1]))
    assert r.ok and r.lineas_borradas == 1 and DocumentoLinea.query.count() == 1


def test_un_documento_revisado_no_se_pisa(app, db, lange, m):
    importar_documentos(_csv(COLUMNAS_CABECERA, [CABECERA]), _csv(COLUMNAS_LINEAS, LINEAS))
    doc = DocumentoProveedor.query.one()
    doc.revisado, doc.observaciones = True, "Corregido a mano"
    db.session.commit()
    r = importar_documentos(_csv(COLUMNAS_CABECERA, [{**CABECERA, "total": "1"}]), _csv(COLUMNAS_LINEAS, LINEAS))
    assert r.ok and r.revisados_salteados == ["LANGE-oferta-9676"]
    assert "ya revisados" in r.resumen().lower()
    doc = db.session.get(DocumentoProveedor, doc.documento_id)
    assert (doc.total, doc.observaciones) == (5351664.41, "Corregido a mano")


def test_importar_todo_o_nada(app, lange, m):
    malas = [LINEAS[0], {**LINEAS[1], "cantidad": "1.234,5"}, {**LINEAS[0], "clave_documento": "OTRA"}]
    r = importar_documentos(_csv(COLUMNAS_CABECERA, [CABECERA]), _csv(COLUMNAS_LINEAS, malas))
    assert not r.ok
    mensajes = " ".join(e[3] for e in r.errores)
    assert "no es un número" in mensajes and "«OTRA» no está en documentos.csv" in mensajes
    assert DocumentoProveedor.query.count() == 0


def test_material_sugerido_generico_no_se_usa(app, lange, m):
    lineas = [{**LINEAS[0], "material_sugerido": "GEN-15W40"}]
    r = importar_documentos(_csv(COLUMNAS_CABECERA, [CABECERA]), _csv(COLUMNAS_LINEAS, lineas))
    assert r.ok and DocumentoLinea.query.one().material_id is None


def test_comando_importar_documentos(app, lange, m, tmp_path):
    a, b = tmp_path / "documentos.csv", tmp_path / "documento_lineas.csv"
    a.write_bytes(_csv(COLUMNAS_CABECERA, [CABECERA]))
    b.write_bytes(_csv(COLUMNAS_LINEAS, LINEAS))
    r = app.test_cli_runner().invoke(args=["importar-documentos", str(a), str(b), "--simular"])
    assert r.exit_code == 0, r.output
    assert "SIMULACIÓN" in r.output and DocumentoProveedor.query.count() == 0
    r = app.test_cli_runner().invoke(args=["importar-documentos", str(a), str(b)])
    assert r.exit_code == 0 and "1 creados" in r.output
