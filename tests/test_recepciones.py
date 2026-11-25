"""
Fase 10, PR 10.5: recepciones, reparto entre destinos y estado visible de la línea.
"""
import pytest

from app.models.activos_models import Activo, EstadoActivo
from app.models.documentos_models import DocumentoProveedor
from app.models.materiales_models import CategoriaMaterial, Material
from app.models.motivos_models import MotivoOperacion
from app.models.pedidos_models import PedidoLinea, PedidoLineaDestino
from app.models.recepciones_models import Recepcion
from app.models.recursos_models import Proveedor
from app.models.unidadmedida_models import TipoUnidad, UnidadMedida


def _guardar(db, *objetos):
    db.session.add_all(objetos)
    db.session.commit()
    return objetos[0] if len(objetos) == 1 else objetos


def _errores(r):
    return r.get_json()["errors"]


@pytest.fixture
def m(db):
    tipo = TipoUnidad.query.filter_by(nombre_tipo="Volumen").one().tipo_unidad_id
    litros = _guardar(db, UnidadMedida(nombre_unidad="Litros", abreviatura="L", tipo_unidad_id=tipo))
    cat = CategoriaMaterial.query.first().categoria_material_id
    filtro = _guardar(db, Material(codigo="RE504836", descripcion="Filtro de aceite", categoria_material_id=cat))
    aceite = _guardar(db, Material(codigo="GEN-15W40", descripcion="Aceite 15W-40", es_generico=True,
                                   categoria_material_id=cat, unidad_medida_id=litros.unidad_medida_id))
    bidon = _guardar(db, Material(codigo="AC-20", descripcion="Aceite bidón 20 L", categoria_material_id=cat,
                                  material_generico_id=aceite.material_id, presentacion_cantidad=20,
                                  unidad_medida_id=litros.unidad_medida_id))
    hidra = _guardar(db, Material(codigo="GEN-HI", descripcion="Hidráulico", es_generico=True,
                                  categoria_material_id=cat, unidad_medida_id=litros.unidad_medida_id))
    bidon_h = _guardar(db, Material(codigo="HI-20", descripcion="Hidráulico bidón 20 L", categoria_material_id=cat,
                                    material_generico_id=hidra.material_id, presentacion_cantidad=20,
                                    unidad_medida_id=litros.unidad_medida_id))
    return {"filtro": filtro, "aceite": aceite, "bidon": bidon, "bidon_h": bidon_h}


@pytest.fixture
def activo(db, categorias_activo, sector):
    return _guardar(db, Activo(numero_activo="T-1", descripcion="Tractor 1", sector_id=sector.sector_id,
                               categoria_activo_id=categorias_activo["Tractor"].categoria_activo_id,
                               estado_activo_id=EstadoActivo.query.first().estado_activo_id))


@pytest.fixture
def pedido(client):
    return client.post("/api/pedidos", json={"fecha_pedido": "2026-11-23"}).get_json()


@pytest.fixture
def oferta(client, db):
    p = _guardar(db, Proveedor(razon_social="Lange SA"))
    r = client.post("/api/documentos_proveedor", json={"tipo": "oferta", "proveedor_id": p.recurso_id,
                                                       "numero": "9676", "moneda": "ARS"})
    return db.session.get(DocumentoProveedor, r.get_json()["documento_id"])


def _linea(client, pedido, material, cantidad, **destino):
    destino = destino or {"destino": "a_identificar"}
    r = client.post("/api/pedido_lineas", json={"pedido_id": pedido["pedido_id"], "material_id": material.material_id,
                                                "cantidad": cantidad, **destino})
    assert r.status_code == 201, r.get_json()
    return r.get_json()["pedido_linea_id"]


def _destino(client, linea_id, cantidad, **extra):
    r = client.post("/api/pedido_linea_destinos", json={"pedido_linea_id": linea_id, "cantidad": cantidad,
                                                        "destino": "a_identificar", **extra})
    assert r.status_code == 201, r.get_json()
    return r.get_json()["pedido_linea_destino_id"]


def _destinos(linea_id):
    return PedidoLineaDestino.query.filter_by(pedido_linea_id=linea_id).order_by(
        PedidoLineaDestino.pedido_linea_destino_id).all()


def _adjudicar(client, oferta, material, cantidad, linea_id, adjudicada, precio=100):
    lo = client.post("/api/documento_lineas", json={"documento_id": oferta.documento_id, "cantidad": cantidad,
                                                    "precio_unitario": precio,
                                                    "material_id": material.material_id}).get_json()
    r = client.post("/api/adjudicaciones", json={"documento_linea_id": lo["documento_linea_id"],
                                                 "pedido_linea_id": linea_id, "cantidad_adjudicada": adjudicada})
    assert r.status_code == 201, r.get_json()


def _recibir(client, destino_id, **datos):
    return client.post("/api/recepciones", json={"pedido_linea_destino_id": destino_id,
                                                 "fecha": "2026-11-25", **datos})


def _linea_api(client, linea_id):
    return client.get(f"/api/pedido_lineas/{linea_id}").get_json()


# ---------------------------------------------------------------------------
# Reparto de lo comprado entre destinos
# ---------------------------------------------------------------------------

def test_reparto_por_unidad_redondea_y_el_resto_va_al_primero(client, pedido, oferta, m):
    linea = _linea(client, pedido, m["filtro"], 3)
    _destino(client, linea, 2)
    _adjudicar(client, oferta, m["filtro"], 3, linea, 3)  # se compraron 3 de 5
    d1, d2 = _destinos(linea)
    assert (d1.comprada, d2.comprada) == (2, 1)  # 1,8 y 1,2 → 1 y 1, y el resto al primero

    # El gestor corrige: el segundo destino se lleva 2; el resto (1) va al primero.
    client.patch(f"/api/pedido_linea_destinos/{d2.pedido_linea_destino_id}", json={"comprada_corregida": 2})
    d1, d2 = _destinos(linea)
    assert (d1.comprada, d2.comprada) == (1, 2)


def test_reparto_en_litros_no_redondea(client, pedido, oferta, m):
    linea = _linea(client, pedido, m["aceite"], 30)
    _destino(client, linea, 10)
    _adjudicar(client, oferta, m["bidon"], 1, linea, 1)  # 20 L de 40
    assert [d.comprada for d in _destinos(linea)] == [15, 5]


# ---------------------------------------------------------------------------
# Recepción: material y cantidad por defecto, conversión
# ---------------------------------------------------------------------------

def test_recepcion_por_defecto_es_lo_adjudicado_y_lo_pendiente(client, pedido, oferta, m):
    linea = _linea(client, pedido, m["aceite"], 30)
    destino = _destinos(linea)[0].pedido_linea_destino_id
    _adjudicar(client, oferta, m["bidon"], 2, linea, 2)  # 2 bidones = 40 L
    r = _recibir(client, destino)
    assert r.status_code == 201, r.get_json()
    rec = r.get_json()
    assert (rec["material_id"], rec["cantidad"], rec["recibida_en_linea"]) == (m["bidon"].material_id, 2, 40)
    assert rec["se_cuenta_en"] == "envases (20 L)"
    l = _linea_api(client, linea)
    assert (l["recibida"], l["pendiente_recibir"], l["estado_visible"]) == (40, 0, "Cerrado")


def test_recepcion_parcial(client, pedido, oferta, m):
    linea = _linea(client, pedido, m["filtro"], 5)
    destino = _destinos(linea)[0].pedido_linea_destino_id
    _adjudicar(client, oferta, m["filtro"], 5, linea, 5)
    assert _recibir(client, destino, cantidad=2).status_code == 201
    l = _linea_api(client, linea)
    assert (l["recibida"], l["pendiente_recibir"], l["estado_visible"]) == (2, 3, "Recibido parcial")
    r = _recibir(client, destino)  # el resto
    assert r.get_json()["cantidad"] == 3
    assert _linea_api(client, linea)["estado_visible"] == "Cerrado"


def test_recibir_de_mas_avisa(client, pedido, oferta, m):
    linea = _linea(client, pedido, m["filtro"], 2)
    destino = _destinos(linea)[0].pedido_linea_destino_id
    _adjudicar(client, oferta, m["filtro"], 2, linea, 2)
    r = client.post(f"/recepciones/crear?pedido_linea_destino_id={destino}", data={
        "pedido_linea_destino_id": destino, "fecha": "2026-11-25", "cantidad": "3"}, follow_redirects=True)
    assert "Se recibió más de lo comprado en este destino (3 de 2" in r.get_data(as_text=True)
    assert Recepcion.query.count() == 1


def test_material_a_indicar(client, pedido, m):
    linea = _linea(client, pedido, m["aceite"], 40)  # pide el genérico, sin adjudicaciones
    destino = _destinos(linea)[0].pedido_linea_destino_id
    r = _recibir(client, destino, cantidad=2)
    assert r.status_code == 400 and "Indicá qué material llegó" in _errores(r)["material_id"]
    r = _recibir(client, destino, cantidad=2, material_id=m["bidon_h"].material_id)
    assert r.status_code == 400 and "no es una presentación de" in _errores(r)["material_id"]
    r = _recibir(client, destino, cantidad=2, material_id=m["aceite"].material_id)
    assert r.status_code == 400 and "no es una opción válida" in _errores(r)["material_id"]  # nunca un genérico
    r = _recibir(client, destino, cantidad=2, material_id=m["bidon"].material_id)
    assert r.status_code == 201 and r.get_json()["recibida_en_linea"] == 40


def test_solo_lineas_de_remitos(client, db, pedido, oferta, m):
    linea = _linea(client, pedido, m["filtro"], 1)
    destino = _destinos(linea)[0].pedido_linea_destino_id
    lo = client.post("/api/documento_lineas", json={"documento_id": oferta.documento_id, "cantidad": 1,
                                                    "precio_unitario": 1, "material_id": m["filtro"].material_id})
    r = _recibir(client, destino, cantidad=1, documento_linea_id=lo.get_json()["documento_linea_id"])
    assert r.status_code == 400 and "no es una opción válida" in _errores(r)["documento_linea_id"]
    remito = client.post("/api/documentos_proveedor", json={"tipo": "remito", "proveedor_id": oferta.proveedor_id,
                                                            "numero": "R-1"}).get_json()
    lr = client.post("/api/documento_lineas", json={"documento_id": remito["documento_id"], "cantidad": 1,
                                                    "precio_unitario": 0, "material_id": m["filtro"].material_id})
    r = _recibir(client, destino, cantidad=1, documento_linea_id=lr.get_json()["documento_linea_id"])
    assert r.status_code == 201


# ---------------------------------------------------------------------------
# Estado visible
# ---------------------------------------------------------------------------

def test_estado_visible_de_punta_a_punta(client, pedido, oferta, m):
    linea = _linea(client, pedido, m["filtro"], 4)
    destino = _destinos(linea)[0].pedido_linea_destino_id
    url = f"/api/pedido_lineas/{linea}"
    assert _linea_api(client, linea)["estado_visible"] == "Solicitado"
    client.patch(url, json={"estado": "en_cotizacion"})
    assert _linea_api(client, linea)["estado_visible"] == "En cotización"
    _adjudicar(client, oferta, m["filtro"], 4, linea, 3)
    assert _linea_api(client, linea)["estado_visible"] == "Adjudicado"
    client.patch(f"/api/documentos_proveedor/{oferta.documento_id}", json={"nro_oc": "OC-1"})
    assert _linea_api(client, linea)["estado_visible"] == "OC emitida"
    _recibir(client, destino, cantidad=3)
    # Se recibió todo lo comprado, pero falta comprar 1: «Recibido», no cerrado.
    l = _linea_api(client, linea)
    assert (l["estado_visible"], l["pendiente_comprar"], l["estado_salteado"]) == ("Recibido", 1, "No")
    client.patch(url, json={"cantidad_cancelada": 1, "motivo_operacion_id": MotivoOperacion.query.filter_by(
        tipo_operacion="ANULACION").first().motivo_operacion_id})
    assert _linea_api(client, linea)["estado_visible"] == "Cerrado"


def test_salteo_y_anulado(client, pedido, oferta, m):
    linea = _linea(client, pedido, m["filtro"], 2)
    _adjudicar(client, oferta, m["filtro"], 2, linea, 2)
    assert _linea_api(client, linea)["estado_salteado"] == "Sí"  # nunca pasó por «en cotización»
    client.patch(f"/api/pedido_lineas/{linea}", json={"estado": "anulado", "motivo_operacion_id":
                 MotivoOperacion.query.filter_by(tipo_operacion="ANULACION").first().motivo_operacion_id})
    assert _linea_api(client, linea)["estado_visible"] == "Anulado"


def test_sin_conformidad_cierra(client, pedido, m):
    linea = _linea(client, pedido, m["filtro"], 2)
    client.patch(f"/api/pedido_lineas/{linea}", json={"sin_conformidad": True})
    assert _linea_api(client, linea)["estado_visible"] == "Cerrado"


def test_compra_directa_sin_oferta(client, pedido, m):
    linea = _linea(client, pedido, m["filtro"], 3)
    destino = _destinos(linea)[0].pedido_linea_destino_id
    # Sin OC ni recepciones no se compró nada: no hay pendiente de recibir.
    l = _linea_api(client, linea)
    assert (l["comprado"], l["pendiente_comprar"]) == (0, 3)
    r = _recibir(client, destino)
    assert r.status_code == 400 and "No queda nada pendiente" in _errores(r)["cantidad"]
    # Con nº de OC (histórico o compra directa) se da por comprado.
    client.patch(f"/api/pedido_lineas/{linea}", json={"nro_oc": "OC-9"})
    l = _linea_api(client, linea)
    assert (l["comprado"], l["estado_visible"]) == (3, "OC emitida")
    assert _recibir(client, destino).get_json()["cantidad"] == 3
    assert _linea_api(client, linea)["estado_visible"] == "Cerrado"


def test_resumen_y_pantallas(client, pedido, oferta, m):
    a = _linea(client, pedido, m["filtro"], 2)
    b = _linea(client, pedido, m["filtro"], 1)
    _adjudicar(client, oferta, m["filtro"], 3, a, 2)
    _adjudicar(client, oferta, m["filtro"], 1, b, 1)
    _recibir(client, _destinos(a)[0].pedido_linea_destino_id)
    resumen = client.get(f"/api/pedidos/{pedido['pedido_id']}").get_json()["resumen"]
    assert resumen == "2 líneas: 1 adjudicada, 1 cerrada"
    html = client.get(f"/pedido_lineas/{a}?seccion=recepciones_linea").get_data(as_text=True)
    assert "2026-11-25" in html and "RE504836 — Filtro de aceite" in html
    listado = client.get("/pedido_lineas").get_data(as_text=True)
    assert "Cerrado" in listado and "Adjudicado" in listado
    # Un destino con recepciones no se borra.
    destino = _destinos(a)[0].pedido_linea_destino_id
    assert client.delete(f"/api/pedido_linea_destinos/{destino}").status_code == 409


def test_importar_exportar_lineas_con_estado_visible(app, client, pedido, m):
    from app.crud.entidades import REGISTRY
    from app.crud.intercambio.csv_entidades import exportar, importar

    _linea(client, pedido, m["filtro"], 2)
    csv = exportar(REGISTRY["pedido_lineas"]).decode("utf-8-sig")
    assert "Estado de seguimiento" in csv.splitlines()[0] and ";Estado;" in csv.splitlines()[0]
    r = importar(REGISTRY["pedido_lineas"], csv.encode())
    assert r.ok and r.sin_cambios == 1, r.resumen()
    assert PedidoLinea.query.count() == 1
