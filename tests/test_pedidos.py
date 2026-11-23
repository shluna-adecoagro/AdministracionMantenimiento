"""
Fase 10, PR 10.3: pedidos, líneas y destinos.
"""
import re

import pytest

from app.crud.entidades import REGISTRY
from app.crud.intercambio.csv_entidades import exportar, importar
from app.models.activos_models import Activo, EstadoActivo
from app.models.materiales_models import CategoriaMaterial, Material
from app.models.motivos_models import MotivoOperacion
from app.models.pedidos_models import Pedido, PedidoLinea, PedidoLineaDestino
from app.models.unidadmedida_models import TipoUnidad, UnidadMedida


def _guardar(db, *objetos):
    db.session.add_all(objetos)
    db.session.commit()
    return objetos[0] if len(objetos) == 1 else objetos


def _errores(r):
    return r.get_json()["errors"]


@pytest.fixture
def cuenta_stock(db, estado_cuenta_activa):
    from app.models.cuentas_models import Cuenta

    return _guardar(db, Cuenta(numero_cuenta="5200", nombre_cuenta="Lubricantes",
                               estado_cuenta_id=estado_cuenta_activa.estado_cuenta_id))


@pytest.fixture
def litros(db):
    tipo = TipoUnidad.query.filter_by(nombre_tipo="Volumen").one().tipo_unidad_id
    return _guardar(db, UnidadMedida(nombre_unidad="Litros", abreviatura="L", tipo_unidad_id=tipo))


@pytest.fixture
def filtro(db, cuenta_stock):
    cat = CategoriaMaterial.query.first()
    cat.cuenta_id = cuenta_stock.cuenta_id
    return _guardar(db, Material(codigo="RE504836", descripcion="Filtro de aceite",
                                 categoria_material_id=cat.categoria_material_id))


@pytest.fixture
def activo(db, categorias_activo, sector):
    return _guardar(db, Activo(numero_activo="T-1", descripcion="Tractor 1",
                               categoria_activo_id=categorias_activo["Tractor"].categoria_activo_id,
                               sector_id=sector.sector_id,
                               estado_activo_id=EstadoActivo.query.first().estado_activo_id))


@pytest.fixture
def pedido(client):
    r = client.post("/api/pedidos", json={"referencia": "Filtros", "fecha_pedido": "2026-11-23"})
    assert r.status_code == 201, r.get_json()
    return Pedido.query.one()


def _linea(client, pedido, **datos):
    return client.post("/api/pedido_lineas", json={"pedido_id": pedido.pedido_id, **datos})


def _motivo(tipo):
    return MotivoOperacion.query.filter_by(tipo_operacion=tipo).first().motivo_operacion_id


# ---------------------------------------------------------------------------
# Pedido
# ---------------------------------------------------------------------------

def test_numero_sigue_la_serie(client, db):
    _guardar(db, Pedido(numero="1104", fecha_pedido=__import__("datetime").date(2026, 1, 5)))
    r = client.post("/api/pedidos", json={"fecha_pedido": "2026-11-23"})
    assert r.status_code == 201 and r.get_json()["numero"] == "1105"
    assert r.get_json()["prioridad"] == "normal"
    assert r.get_json()["origen"] == "app"


def test_canal_sin_historico(app):
    assert {o["value"] for o in REGISTRY["pedidos"].fields["canal"].options} == {"whatsapp", "mail", "site", "app"}


# ---------------------------------------------------------------------------
# Línea: alta con cantidad y destino principal
# ---------------------------------------------------------------------------

def test_alta_de_linea_crea_el_primer_destino(client, pedido, filtro, activo, categorias_activo, cuenta):
    r = _linea(client, pedido, material_id=filtro.material_id, cantidad=10, destino="activo",
               activo_id=activo.activo_id)
    assert r.status_code == 201, r.get_json()
    linea = r.get_json()
    assert (linea["nro_linea"], linea["solicitada"], linea["estado"]) == (1, 10, "solicitado")
    assert "cantidad" not in linea  # es un campo de alta, no un dato de la línea

    d = PedidoLineaDestino.query.one()
    assert (d.destino, d.activo_id, d.cantidad) == ("activo", activo.activo_id, 10)
    # Sugerencias: sector del activo y cuenta del tipo de activo.
    assert (d.sector_imputado_id, d.cuenta_id) == (activo.sector_id, cuenta.cuenta_id)
    assert d.a_revisar == "No"


def test_numero_de_linea_dentro_de_cada_pedido(client, pedido, filtro):
    for _ in range(2):
        _linea(client, pedido, material_id=filtro.material_id, cantidad=1, destino="a_identificar")
    otro = client.post("/api/pedidos", json={"fecha_pedido": "2026-11-23"}).get_json()
    r = client.post("/api/pedido_lineas", json={"pedido_id": otro["pedido_id"], "descripcion": "Correa",
                                                "cantidad": 1, "destino": "a_identificar"})
    assert [l.nro_linea for l in PedidoLinea.query.order_by(PedidoLinea.pedido_linea_id)] == [1, 2, 1]
    assert r.get_json()["nombre"] == f"{otro['numero']} / 1 — Correa"


def test_linea_necesita_material_o_descripcion(client, pedido):
    r = _linea(client, pedido, cantidad=1, destino="a_identificar")
    assert r.status_code == 400 and "material_id" in _errores(r)
    assert PedidoLinea.query.count() == 0


@pytest.mark.parametrize("destino, campo", [("activo", "activo_id"), ("modelo", "modelo_id"),
                                            ("stock", "ubicacion_id")])
def test_cada_destino_pide_su_dato(client, pedido, filtro, destino, campo):
    r = _linea(client, pedido, material_id=filtro.material_id, cantidad=1, destino=destino)
    assert r.status_code == 400 and campo in _errores(r)
    assert PedidoLinea.query.count() == 0  # no queda la línea sin su destino


def test_destino_stock(client, pedido, filtro, ubicacion, cuenta_stock):
    r = _linea(client, pedido, material_id=filtro.material_id, cantidad=4, destino="stock",
               ubicacion_id=ubicacion.ubicacion_id)
    assert r.status_code == 201, r.get_json()
    d = PedidoLineaDestino.query.one()
    # Sector de la ubicación; cuenta de la categoría del material.
    assert (d.sector_imputado_id, d.cuenta_id) == (ubicacion.sector_id, cuenta_stock.cuenta_id)


def test_sin_de_donde_sugerir_queda_a_revisar(client, pedido):
    r = _linea(client, pedido, descripcion="Bolillero 32217", cantidad=2, destino="a_identificar")
    assert r.status_code == 201
    d = PedidoLineaDestino.query.one()
    assert (d.sector_imputado_id, d.cuenta_id, d.a_revisar) == (None, None, "Sí")


def test_sector_del_pedido_como_ultima_sugerencia(client, db, pedido, sector):
    pedido.sector_id = sector.sector_id
    db.session.commit()
    _linea(client, pedido, descripcion="Bolillero", cantidad=2, destino="gasto_general")
    assert PedidoLineaDestino.query.one().sector_imputado_id == sector.sector_id


def test_varios_destinos_suman_la_solicitada(client, pedido, filtro, activo, ubicacion):
    linea = _linea(client, pedido, material_id=filtro.material_id, cantidad=5, destino="activo",
                   activo_id=activo.activo_id).get_json()
    r = client.post("/api/pedido_linea_destinos", json={
        "pedido_linea_id": linea["pedido_linea_id"], "cantidad": 5, "destino": "stock",
        "ubicacion_id": ubicacion.ubicacion_id})
    assert r.status_code == 201, r.get_json()
    assert client.get(f"/api/pedido_lineas/{linea['pedido_linea_id']}").get_json()["solicitada"] == 10


def test_unidad_de_la_linea(client, db, pedido, litros):
    cat = CategoriaMaterial.query.first().categoria_material_id
    generico = _guardar(db, Material(codigo="GEN-ACEITE", descripcion="Aceite 15W-40", es_generico=True,
                                     categoria_material_id=cat, unidad_medida_id=litros.unidad_medida_id))
    bidon = _guardar(db, Material(codigo="AC-20", descripcion="Aceite 15W-40 bidón 20 L", categoria_material_id=cat,
                                  material_generico_id=generico.material_id, presentacion_cantidad=20,
                                  unidad_medida_id=litros.unidad_medida_id))
    a = _linea(client, pedido, material_id=generico.material_id, cantidad=40, destino="a_identificar").get_json()
    b = _linea(client, pedido, material_id=bidon.material_id, cantidad=2, destino="a_identificar").get_json()
    assert (a["unidad_medida_id"], a["se_cuenta_en"]) == (litros.unidad_medida_id, "Litros")
    assert (b["unidad_medida_id"], b["se_cuenta_en"]) == (litros.unidad_medida_id, "envases (20 L)")


def test_nro_oc_normalizado(client, pedido, filtro):
    linea = _linea(client, pedido, material_id=filtro.material_id, cantidad=1, destino="a_identificar").get_json()
    r = client.patch(f"/api/pedido_lineas/{linea['pedido_linea_id']}", json={"nro_oc": " oc 4500 12 "})
    assert r.get_json()["nro_oc"] == "OC450012"


def test_cantidad_solo_en_el_alta(client, pedido, filtro):
    linea = _linea(client, pedido, material_id=filtro.material_id, cantidad=1, destino="a_identificar").get_json()
    r = client.patch(f"/api/pedido_lineas/{linea['pedido_linea_id']}", json={"cantidad": 3})
    assert r.status_code == 400 and "solo se usa al crear" in _errores(r)["cantidad"]


# ---------------------------------------------------------------------------
# Anulación y cancelación
# ---------------------------------------------------------------------------

def test_anular_pide_motivo_de_anulacion(client, pedido, filtro):
    linea = _linea(client, pedido, material_id=filtro.material_id, cantidad=3, destino="a_identificar").get_json()
    url = f"/api/pedido_lineas/{linea['pedido_linea_id']}"
    r = client.patch(url, json={"estado": "anulado"})
    assert r.status_code == 400 and "motivo" in _errores(r)["motivo_operacion_id"]
    r = client.patch(url, json={"estado": "anulado", "motivo_operacion_id": _motivo("DELETE")})
    assert r.status_code == 400 and "no es una opción válida" in _errores(r)["motivo_operacion_id"]
    r = client.patch(url, json={"estado": "anulado", "motivo_operacion_id": _motivo("ANULACION")})
    assert r.status_code == 200


def test_cancelar_mas_de_lo_solicitado(client, pedido, filtro):
    linea = _linea(client, pedido, material_id=filtro.material_id, cantidad=3, destino="a_identificar").get_json()
    url = f"/api/pedido_lineas/{linea['pedido_linea_id']}"
    r = client.patch(url, json={"cantidad_cancelada": 5, "motivo_operacion_id": _motivo("ANULACION")})
    assert r.status_code == 400 and "más de lo solicitado (3)" in _errores(r)["cantidad_cancelada"]
    r = client.patch(url, json={"cantidad_cancelada": 1})
    assert r.status_code == 400 and "motivo_operacion_id" in _errores(r)


# ---------------------------------------------------------------------------
# Resumen, pantallas y borrado
# ---------------------------------------------------------------------------

def test_resumen_del_pedido(client, pedido, filtro):
    assert client.get(f"/api/pedidos/{pedido.pedido_id}").get_json()["resumen"] == "Sin líneas"
    ids = [_linea(client, pedido, material_id=filtro.material_id, cantidad=1, destino="a_identificar")
           .get_json()["pedido_linea_id"] for _ in range(3)]
    client.patch(f"/api/pedido_lineas/{ids[0]}", json={"estado": "en_cotizacion"})
    assert client.get(f"/api/pedidos/{pedido.pedido_id}").get_json()["resumen"] == (
        "3 líneas: 2 solicitadas, 1 en cotización")
    assert "2 solicitadas, 1 en cotización" in client.get("/pedidos").get_data(as_text=True)


def test_formularios(client, pedido, filtro):
    alta = client.get(f"/pedido_lineas/crear?pedido_id={pedido.pedido_id}").get_data(as_text=True)
    orden = [alta.index(f'id="{c}"') for c in ("material_id", "cantidad", "destino", "activo_id", "estado")]
    assert orden == sorted(orden)  # la cantidad y el destino junto al material
    assert "RE504836 — Filtro de aceite" in alta
    linea = _linea(client, pedido, material_id=filtro.material_id, cantidad=1, destino="a_identificar").get_json()
    edicion = client.get(f"/pedido_lineas/{linea['pedido_linea_id']}/editar").get_data(as_text=True)
    assert 'id="cantidad"' not in edicion and 'id="destino"' not in edicion


def test_alta_desde_la_web(client, pedido, filtro, activo):
    r = client.post(f"/pedido_lineas/crear?pedido_id={pedido.pedido_id}", data={
        "pedido_id": pedido.pedido_id, "material_id": filtro.material_id, "cantidad": "2,5",
        "destino": "activo", "activo_id": activo.activo_id, "estado": "solicitado",
        "sin_conformidad": "False", "cantidad_cancelada": "",
    })
    assert r.status_code == 302, r.get_data(as_text=True)
    assert PedidoLinea.query.one().solicitada == 2.5
    html = client.get(f"/pedidos/{pedido.pedido_id}?seccion=pedido_lineas").get_data(as_text=True)
    assert "RE504836 — Filtro de aceite" in html
    linea = PedidoLinea.query.one()
    html = client.get(f"/pedido_lineas/{linea.pedido_linea_id}?seccion=pedido_linea_destinos").get_data(as_text=True)
    assert "Tractor 1" in html
    assert "Tractor 1" in client.get(f"/activos/{activo.activo_id}?seccion=pedido_linea_destinos").get_data(as_text=True)


def test_borrado(client, pedido, filtro, activo):
    _linea(client, pedido, material_id=filtro.material_id, cantidad=1, destino="activo", activo_id=activo.activo_id)
    # Un material pedido o un activo con destinos no se borran.
    assert client.delete(f"/api/materiales/{filtro.material_id}").status_code == 409
    assert client.delete(f"/api/activos/{activo.activo_id}").status_code == 409
    # Borrar el pedido borra sus líneas y destinos.
    assert client.delete(f"/api/pedidos/{pedido.pedido_id}").status_code in (200, 204)
    assert (PedidoLinea.query.count(), PedidoLineaDestino.query.count()) == (0, 0)


# ---------------------------------------------------------------------------
# Importación
# ---------------------------------------------------------------------------

def test_importar_pedidos_y_lineas(app, db, filtro):
    csv = "Número;Fecha del pedido;Referencia\n1104;2026-01-05;Filtros\n1107;2026-01-09;Correas\n".encode()
    r = importar(REGISTRY["pedidos"], csv)
    assert r.ok and r.creados == 2, r.resumen()
    assert importar(REGISTRY["pedidos"], csv).sin_cambios == 2  # por número

    csv = ("Pedido;Línea;Material;Descripción (como se pidió)\n"
           "1104;1;RE504836;\n"
           "1104;2;;Bolillero 32217\n").encode()
    r = importar(REGISTRY["pedido_lineas"], csv)
    assert r.ok and r.creados == 2, r.resumen()
    r = importar(REGISTRY["pedido_lineas"], exportar(REGISTRY["pedido_lineas"]))
    assert r.ok and r.sin_cambios == 2, r.resumen()


def test_motivos_de_anulacion_precargados(app):
    assert MotivoOperacion.query.filter_by(tipo_operacion="ANULACION").count() == 3
    assert any(o["value"] == "ANULACION" for o in REGISTRY["motivos_operacion"].fields["tipo_operacion"].options)


def test_listado_de_lineas_muestra_el_pedido(client, pedido, filtro):
    _linea(client, pedido, material_id=filtro.material_id, cantidad=1, destino="a_identificar")
    html = client.get("/pedido_lineas").get_data(as_text=True)
    assert re.search(rf">\s*{pedido.numero}\s*<", html)
