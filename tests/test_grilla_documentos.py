"""
Fase 13, PR 13.7: grilla en las líneas de documentos de proveedores.

La pestaña «Líneas» del documento se edita como la de un pedido: celdas, alta
rápida (material o texto, cantidad y precio neto) y reglas según el documento
(revisado) y lo adjudicado o recibido.
"""
import pytest

from app.models.auditoria_models import AuditLog
from app.models.documentos_models import Adjudicacion, DocumentoLinea, DocumentoProveedor
from app.models.materiales_models import CategoriaMaterial, Material
from app.models.recepciones_models import Recepcion
from app.models.recursos_models import Proveedor
from app.models.unidadmedida_models import TipoUnidad, UnidadMedida


def _guardar(db, *objetos):
    db.session.add_all(objetos)
    db.session.commit()
    return objetos[0] if len(objetos) == 1 else objetos


def _texto(r):
    return r.get_data(as_text=True)


@pytest.fixture
def m(db):
    tipo = TipoUnidad.query.filter_by(nombre_tipo="Volumen").one().tipo_unidad_id
    litros = _guardar(db, UnidadMedida(nombre_unidad="Litros", abreviatura="L", tipo_unidad_id=tipo))
    cat = CategoriaMaterial.query.first().categoria_material_id
    filtro, aceite = _guardar(
        db,
        Material(codigo="RE504836", descripcion="Filtro de aceite", categoria_material_id=cat),
        Material(codigo="AC-1", descripcion="Aceite suelto", categoria_material_id=cat,
                 unidad_medida_id=litros.unidad_medida_id),
    )
    return {"filtro": filtro, "aceite": aceite, "litros": litros}


@pytest.fixture
def doc(db):
    lange = _guardar(db, Proveedor(razon_social="Lubricantes Lange S.A.", cuit="30-71234567-8"))
    from datetime import date

    return _guardar(db, DocumentoProveedor(tipo="oferta", proveedor_id=lange.recurso_id, numero="9676",
                                           fecha=date(2026, 11, 27), moneda="ARS"))


def _linea(db, doc, nro=1, **extra):
    datos = {"tipo_linea": "material", "descripcion_proveedor": "Filtro", "cantidad": 4, "precio_unitario": 100}
    return _guardar(db, DocumentoLinea(documento_id=doc.documento_id, nro_linea=nro, **{**datos, **extra}))


def _celda(client, doc, linea, campo, valor):
    return client.post(f"/documento_lineas/{linea.documento_linea_id}/celda/{campo}?documento_id={doc.documento_id}",
                       data={campo: valor})


def _alta(client, doc, material="", cantidad="", precio=""):
    return client.post(f"/documento_lineas/alta_en_linea?documento_id={doc.documento_id}",
                       data={"material": material, "cantidad": cantidad, "precio_unitario": precio})


def _revisar(db, doc):
    doc.revisado = True
    db.session.commit()


@pytest.fixture
def adjudicada(client, db, doc, m, enviar):
    """Una línea de la oferta con 3 adjudicados a una línea de pedido enviada."""
    p = client.post("/api/pedidos", json={"fecha_pedido": "2026-11-27", "referencia": "Service"}).get_json()
    r = client.post("/api/pedido_lineas", json={"pedido_id": p["pedido_id"], "material_id": m["filtro"].material_id,
                                                "cantidad": 3, "destino": "a_identificar"})
    assert r.status_code == 201, r.get_json()
    enviar(p["pedido_id"])
    lo = _linea(db, doc, material_id=m["filtro"].material_id)
    _guardar(db, Adjudicacion(documento_linea_id=lo.documento_linea_id,
                              pedido_linea_id=r.get_json()["pedido_linea_id"], cantidad_adjudicada=3))
    db.session.expire_all()
    return db.session.get(DocumentoLinea, lo.documento_linea_id)


# ---------------------------------------------------------------------------
# La grilla
# ---------------------------------------------------------------------------

def test_la_pestana_lineas_es_una_grilla_con_fila_de_alta(client, doc, db):
    linea = _linea(db, doc)
    html = _texto(client.get(f"/documentos_proveedor/{doc.documento_id}?seccion=documento_lineas"))
    assert 'id="alta-documento_lineas"' in html
    assert f"/documento_lineas/{linea.documento_linea_id}/celda/cantidad" in html
    assert "Precio de lista" in html and "Código del proveedor" in html


def test_editar_una_celda(client, db, doc, auditoria):
    linea = _linea(db, doc)
    r = _celda(client, doc, linea, "cantidad", "6")
    assert r.status_code == 200, _texto(r)
    db.session.expire_all()
    assert db.session.get(DocumentoLinea, linea.documento_linea_id).cantidad == 6
    assert AuditLog.query.filter_by(TablaAfectada="documento_lineas", TipoDeCambio="UPDATE").count() == 1


def test_el_material_completa_la_unidad(client, db, doc, m):
    linea = _linea(db, doc)
    r = _celda(client, doc, linea, "material_id", str(m["aceite"].material_id))
    assert r.status_code == 200, _texto(r)
    db.session.expire_all()
    assert db.session.get(DocumentoLinea, linea.documento_linea_id).unidad_medida_id == m["litros"].unidad_medida_id


# ---------------------------------------------------------------------------
# Precio neto
# ---------------------------------------------------------------------------

def test_neto_vacio_se_calcula_de_lista_y_descuento(client, doc):
    r = client.post("/api/documento_lineas", json={"documento_id": doc.documento_id, "cantidad": 2,
                                                   "precio_lista": 200, "descuento_pct": 26.2})
    assert r.status_code == 201, r.get_json()
    assert r.get_json()["precio_unitario"] == pytest.approx(147.6)


def test_neto_escrito_manda(client, doc):
    r = client.post("/api/documento_lineas", json={"documento_id": doc.documento_id, "cantidad": 2,
                                                   "precio_lista": 200, "descuento_pct": 10, "precio_unitario": 150})
    assert r.status_code == 201, r.get_json()
    assert r.get_json()["precio_unitario"] == 150


def test_sin_neto_ni_lista_es_error(client, doc):
    r = client.post("/api/documento_lineas", json={"documento_id": doc.documento_id, "cantidad": 2})
    assert r.status_code in (400, 422)
    assert "precio_unitario" in r.get_json()["errors"]


def test_cambiar_el_descuento_recalcula_el_neto(client, db, doc):
    linea = _linea(db, doc, precio_lista=100, descuento_pct=0, precio_unitario=100)
    assert _celda(client, doc, linea, "descuento_pct", "20").status_code == 200
    db.session.expire_all()
    assert db.session.get(DocumentoLinea, linea.documento_linea_id).precio_unitario == pytest.approx(80)


def test_cambiar_solo_el_neto_no_toca_la_lista(client, db, doc):
    linea = _linea(db, doc, precio_lista=100, descuento_pct=0, precio_unitario=100)
    assert _celda(client, doc, linea, "precio_unitario", "90").status_code == 200
    db.session.expire_all()
    l2 = db.session.get(DocumentoLinea, linea.documento_linea_id)
    assert (l2.precio_unitario, l2.precio_lista, l2.descuento_pct) == (90, 100, 0)


# ---------------------------------------------------------------------------
# Alta rápida
# ---------------------------------------------------------------------------

def test_alta_rapida_con_material_del_maestro(client, doc, m):
    r = _alta(client, doc, "RE504836", "4", "1500")
    assert r.status_code == 200, _texto(r)
    linea = DocumentoLinea.query.filter_by(documento_id=doc.documento_id).one()
    assert (linea.material_id, linea.cantidad, linea.precio_unitario, linea.nro_linea) == (
        m["filtro"].material_id, 4, 1500, 1)
    assert linea.tipo_linea == "material"


def test_alta_rapida_con_texto_va_a_la_descripcion(client, doc, m):
    r = _alta(client, doc, "Mano de obra de colocación", "1", "50000")
    assert r.status_code == 200, _texto(r)
    linea = DocumentoLinea.query.filter_by(documento_id=doc.documento_id).one()
    assert linea.material_id is None and linea.descripcion_proveedor == "Mano de obra de colocación"


def test_alta_rapida_sin_precio_marca_la_celda(client, doc, m):
    r = _alta(client, doc, "RE504836", "4", "")
    assert r.status_code == 422
    assert "Falta el precio neto" in _texto(r)
    assert DocumentoLinea.query.count() == 0


# ---------------------------------------------------------------------------
# Documento revisado
# ---------------------------------------------------------------------------

def test_revisado_congela_lo_leido(client, db, doc):
    linea = _linea(db, doc)
    _revisar(db, doc)
    # En la grilla, la celda queda congelada (con el porqué).
    html = _texto(client.get(f"/documentos_proveedor/{doc.documento_id}?seccion=documento_lineas"))
    assert "No se puede cambiar: el documento está revisado" in html
    assert _celda(client, doc, linea, "cantidad", "9").status_code == 404
    r = client.patch(f"/api/documento_lineas/{linea.documento_linea_id}", json={"cantidad": 9})
    assert r.status_code == 400
    assert "el documento está revisado" in r.get_json()["errors"]["cantidad"]
    db.session.expire_all()
    assert db.session.get(DocumentoLinea, linea.documento_linea_id).cantidad == 4


def test_revisado_deja_identificar_el_material(client, db, doc, m):
    linea = _linea(db, doc)
    _revisar(db, doc)
    assert _celda(client, doc, linea, "material_id", str(m["filtro"].material_id)).status_code == 200


def test_revisado_sin_alta_ni_eliminar(client, db, doc):
    linea = _linea(db, doc)
    _revisar(db, doc)
    html = _texto(client.get(f"/documentos_proveedor/{doc.documento_id}?seccion=documento_lineas"))
    assert 'id="alta-documento_lineas"' not in html
    r = client.post("/api/documento_lineas", json={"documento_id": doc.documento_id, "cantidad": 1,
                                                   "precio_unitario": 1})
    assert r.status_code in (400, 422)
    r = client.delete(f"/api/documento_lineas/{linea.documento_linea_id}")
    assert r.status_code in (400, 409, 422)
    assert DocumentoLinea.query.count() == 1


# ---------------------------------------------------------------------------
# Adjudicadas y recibidas
# ---------------------------------------------------------------------------

def test_con_adjudicado_el_material_no_cambia(client, doc, adjudicada, m):
    assert _celda(client, doc, adjudicada, "material_id", str(m["aceite"].material_id)).status_code == 404
    r = client.patch(f"/api/documento_lineas/{adjudicada.documento_linea_id}",
                     json={"material_id": m["aceite"].material_id})
    assert r.status_code == 400
    assert "adjudicadas" in r.get_json()["errors"]["material_id"]


def test_la_cantidad_no_baja_de_lo_adjudicado(client, db, doc, adjudicada):
    r = _celda(client, doc, adjudicada, "cantidad", "2")
    assert r.status_code == 422
    assert "menor que lo adjudicado" in _texto(r)
    assert _celda(client, doc, adjudicada, "cantidad", "3").status_code == 200


def test_con_adjudicado_no_se_elimina(client, doc, adjudicada):
    r = client.delete(f"/api/documento_lineas/{adjudicada.documento_linea_id}")
    assert r.status_code in (400, 409, 422)


def test_cotizada_en_0_se_elimina_con_su_vinculo(client, db, doc, adjudicada):
    adj = Adjudicacion.query.one()
    adj.cantidad_adjudicada = 0
    db.session.commit()
    r = client.delete(f"/api/documento_lineas/{adjudicada.documento_linea_id}")
    assert r.status_code in (200, 204), _texto(r)
    assert Adjudicacion.query.count() == 0


def test_linea_de_remito_recibida_no_se_elimina(client, db, doc, m, enviar):
    from app.models.pedidos_models import PedidoLineaDestino

    doc.tipo = "remito"
    db.session.commit()
    linea = _linea(db, doc, material_id=m["filtro"].material_id)
    p = client.post("/api/pedidos", json={"fecha_pedido": "2026-11-27", "referencia": "Service"}).get_json()
    r = client.post("/api/pedido_lineas", json={"pedido_id": p["pedido_id"], "material_id": m["filtro"].material_id,
                                                "cantidad": 4, "destino": "a_identificar"})
    enviar(p["pedido_id"])
    destino = PedidoLineaDestino.query.filter_by(pedido_linea_id=r.get_json()["pedido_linea_id"]).one()
    _guardar(db, Recepcion(pedido_linea_destino_id=destino.pedido_linea_destino_id, material_id=m["filtro"].material_id,
                           cantidad=4, documento_linea_id=linea.documento_linea_id))
    r = client.delete(f"/api/documento_lineas/{linea.documento_linea_id}")
    assert r.status_code in (400, 409, 422)
    assert "recepciones" in _texto(r)
