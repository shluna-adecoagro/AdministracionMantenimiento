"""
Fase 13, PR 13.5: «Pegar líneas».

`pegado_en_linea` en la spec: la pestaña «Líneas» del pedido ofrece pegar un
texto (de un mail o de WhatsApp) con un renglón por línea, «cantidad código o
descripción». POST /pedido_lineas/pegar?pedido_id=N muestra la vista previa (no
guarda nada) y, con `confirmar`, crea todas las líneas juntas (todo o nada).
El material se reconoce solo por un código exacto; el destino queda «a
identificar».
"""
import pytest

from app.crud.core import pegado
from app.crud.core.interpretes import CodigoEnTexto
from app.crud.meta.registry import cargar_overrides, construir_spec
from app.models.auditoria_models import AuditLog
from app.models.materiales_models import CategoriaMaterial, Material
from app.models.pedidos_models import Pedido, PedidoLinea, PedidoLineaDestino

EJEMPLO = """10 rodamientos uc204
8 cajas fl204
2 filtros 8605140.
4 filtros re504836
4 rodamientos uc210 50,8 diámetro interior.

2 filtros de aire interior
"""


def _guardar(db, *objetos):
    db.session.add_all(objetos)
    db.session.commit()
    return objetos


def _texto(r):
    return r.get_data(as_text=True)


@pytest.fixture
def materiales(db):
    cat = CategoriaMaterial.query.first().categoria_material_id
    filtro, filtro_case = _guardar(
        db,
        Material(codigo="RE504836", descripcion="Filtro de aceite", categoria_material_id=cat),
        Material(codigo="8605140", descripcion="Filtro hidráulico", categoria_material_id=cat),
    )
    return {"filtro": filtro, "filtro_case": filtro_case}


@pytest.fixture
def pedido(client):
    r = client.post("/api/pedidos", json={"referencia": "Rodamientos", "fecha_pedido": "2026-11-27"})
    assert r.status_code == 201, r.get_json()
    return Pedido.query.one()


def _pegar(client, pedido, texto, confirmar=False):
    datos = {"texto": texto}
    if confirmar:
        datos["confirmar"] = "1"
    return client.post(f"/pedido_lineas/pegar?pedido_id={pedido.pedido_id}", data=datos)


def _lineas(pedido):
    return PedidoLinea.query.filter_by(pedido_id=pedido.pedido_id).order_by(PedidoLinea.nro_linea).all()


# ---------------------------------------------------------------------------
# Lectura del texto (sin base)
# ---------------------------------------------------------------------------

@pytest.mark.parametrize("renglon, esperado", [
    ("10 rodamientos uc204", ("10", "rodamientos uc204")),
    ("6 reten 7186.", ("6", "reten 7186")),
    ("4 retenes  4144 ", ("4", "retenes 4144")),
    ("2,5 metros de manguera", ("2,5", "metros de manguera")),
    ("1.000 tornillos", ("1.000", "tornillos")),
    ("Picadora de rollos", (None, "Picadora de rollos")),
    ("5", ("5", "")),
    ("RE504836\t4\tFiltro", ("4", "RE504836 Filtro")),
    ("Filtro\tsin cantidad", (None, "Filtro sin cantidad")),
])
def test_separar_cantidad_y_texto(renglon, esperado):
    assert pegado.separar(renglon) == esperado


def test_renglones_ignora_los_vacios():
    assert pegado.renglones("a\n\n  \nb\r\nc") == ["a", "b", "c"]


# ---------------------------------------------------------------------------
# La pestaña
# ---------------------------------------------------------------------------

def test_la_pestana_ofrece_pegar_lineas(client, pedido):
    html = _texto(client.get(f"/pedidos/{pedido.pedido_id}?seccion=pedido_lineas"))
    assert 'id="pegado-pedido_lineas"' in html
    assert "Pegar líneas" in html
    assert f"/pedido_lineas/pegar?pedido_id={pedido.pedido_id}" in html


def test_no_se_ofrece_en_la_pestana_del_material(client, pedido, materiales):
    html = _texto(client.get(f"/materiales/{materiales['filtro'].material_id}?seccion=pedido_lineas"))
    assert 'id="pegado-pedido_lineas"' not in html


def test_sin_pedido_en_la_url_es_404(client, pedido, materiales):
    assert client.post("/pedido_lineas/pegar", data={"texto": "1 x"}).status_code == 404
    r = client.post(f"/pedido_lineas/pegar?material_id={materiales['filtro'].material_id}", data={"texto": "1 x"})
    assert r.status_code == 404
    assert client.post("/pedido_lineas/pegar?pedido_id=999", data={"texto": "1 x"}).status_code == 404


# ---------------------------------------------------------------------------
# Vista previa
# ---------------------------------------------------------------------------

def test_vista_previa_no_guarda_nada(client, pedido, materiales):
    antes = AuditLog.query.count()
    r = _pegar(client, pedido, EJEMPLO)
    assert r.status_code == 200
    html = _texto(r)
    assert "Agregar 6 líneas de pedido" in html
    # El material se reconoce por el código exacto; el texto queda tal cual.
    assert "RE504836 — Filtro de aceite" in html and "8605140 — Filtro hidráulico" in html
    assert "rodamientos uc210 50,8 diámetro interior" in html
    assert _lineas(pedido) == []
    assert PedidoLineaDestino.query.count() == 0
    assert AuditLog.query.count() == antes


def test_renglon_sin_cantidad_bloquea_todo(client, pedido, materiales):
    r = _pegar(client, pedido, "10 rodamientos uc204\nPicadora de rollos\n0 cajas\n3")
    html = _texto(r)
    assert r.status_code == 200
    assert "No empieza con la cantidad" in html
    assert "mayor que cero" in html
    assert "Falta el código o la descripción" in html
    assert "3 renglones con error" in html
    assert "Agregar" not in html.split("Vista previa</button>")[1]
    # Confirmar igual (sin pasar por la vista previa): no se carga nada.
    r = _pegar(client, pedido, "10 rodamientos uc204\nPicadora de rollos", confirmar=True)
    assert r.status_code == 422
    assert _lineas(pedido) == []


def test_texto_vacio(client, pedido):
    html = _texto(_pegar(client, pedido, "\n  \n"))
    assert "No hay renglones para cargar" in html


def test_demasiados_renglones(client, pedido):
    texto = "\n".join(f"1 item {i}" for i in range(pegado.MAXIMO_RENGLONES + 1))
    assert "se pueden pegar hasta" in _texto(_pegar(client, pedido, texto))


# ---------------------------------------------------------------------------
# Confirmación
# ---------------------------------------------------------------------------

def test_confirmar_crea_todas_las_lineas(client, pedido, materiales, auditoria):
    r = _pegar(client, pedido, EJEMPLO, confirmar=True)
    assert r.status_code == 204
    assert r.headers["HX-Redirect"].endswith(f"/pedidos/{pedido.pedido_id}?seccion=pedido_lineas")

    lineas = _lineas(pedido)
    assert [l.nro_linea for l in lineas] == [1, 2, 3, 4, 5, 6]
    assert [l.descripcion for l in lineas] == [
        "rodamientos uc204", "cajas fl204", "filtros 8605140", "filtros re504836",
        "rodamientos uc210 50,8 diámetro interior", "filtros de aire interior"]
    assert [l.material_id for l in lineas] == [
        None, None, materiales["filtro_case"].material_id, materiales["filtro"].material_id, None, None]
    assert [float(l.solicitada) for l in lineas] == [10, 8, 2, 4, 4, 2]
    # En borrador y con un destino «a identificar» por toda la cantidad.
    assert all(l.enviada_en is None and l.origen == "app" for l in lineas)
    for l in lineas:
        d = PedidoLineaDestino.query.filter_by(pedido_linea_id=l.pedido_linea_id).one()
        assert d.destino == "a_identificar" and float(d.cantidad) == float(l.solicitada)
        assert d.detalle_texto is None
    # Auditoría con el motivo fijo.
    logs = auditoria("pedido_lineas")
    assert len(logs) == 6 and {l.motivo_operacion for l in logs} == {"Líneas pegadas"}

    # La pestaña muestra el mensaje.
    html = _texto(client.get(r.headers["HX-Redirect"]))
    assert "Se agregaron 6 líneas de pedido." in html


def test_en_un_pedido_enviado_las_lineas_nacen_en_borrador(client, pedido, materiales, enviar):
    _pegar(client, pedido, "1 correa", confirmar=True)
    enviar(pedido.pedido_id)
    _pegar(client, pedido, "2 correas más", confirmar=True)
    primera, segunda = _lineas(pedido)
    assert primera.enviada_en is not None and segunda.enviada_en is None


def test_aviso_de_linea_repetida(client, pedido, materiales):
    _pegar(client, pedido, "4 filtros re504836\n10 rodamientos uc204", confirmar=True)
    html = _texto(_pegar(client, pedido,
                         "4 filtro RE504836\n10 Rodamientos  UC204\n5 rodamientos uc204\n3 cajas\n3 cajas"))
    assert html.count("Igual a la línea") == 3
    assert "Igual a la línea 1 del pedido" in html      # mismo material
    assert "Igual a la línea 2 del pedido" in html      # misma descripción (sin mayúsculas ni espacios)
    assert "Igual a la línea 6 del pedido" in html      # repetida dentro del mismo pegado
    # El aviso no bloquea.
    assert "Agregar 5 líneas de pedido" in html


# ---------------------------------------------------------------------------
# Intérprete: el código dentro del texto
# ---------------------------------------------------------------------------

def test_codigo_en_texto(app, materiales, db):
    from app.crud.entidades import REGISTRY

    spec = REGISTRY["pedido_lineas"]
    i = CodigoEnTexto("material_id", "descripcion", "codigo")
    filtro = materiales["filtro"].material_id
    assert i.leer("4 filtros (re504836)", spec) == ({"descripcion": "4 filtros (re504836)", "material_id": filtro}, [])
    # Sin comienzos ni partes de un código.
    assert i.leer("filtros RE5048", spec) == ({"descripcion": "filtros RE5048"}, [])
    assert i.leer("filtros RE504836X", spec) == ({"descripcion": "filtros RE504836X"}, [])
    # Dos códigos de materiales distintos: ninguno, con aviso.
    datos, avisos = i.leer("RE504836 o 8605140", spec)
    assert "material_id" not in datos and "queda sin identificar" in avisos[0]


# ---------------------------------------------------------------------------
# Registry
# ---------------------------------------------------------------------------

def _override(**cambios):
    return {**cargar_overrides()["pedido_lineas"], **cambios}


@pytest.mark.parametrize("cfg, mensaje", [
    ({"texto": CodigoEnTexto("material_id", "descripcion", "codigo")}, "es {'cantidad', 'texto'}"),
    ({"cantidad": "descripcion", "texto": CodigoEnTexto("material_id", "descripcion", "codigo")},
     "campo numérico"),
    ({"cantidad": "cantidad", "texto": object()}, "no es válido"),
    ({"cantidad": "cantidad", "texto": CodigoEnTexto("material_id", "no_existe", "codigo")},
     "'no_existe' no es un campo"),
    ({"cantidad": "cantidad", "texto": CodigoEnTexto("material_id", "descripcion", "codigo"),
      "datos": {"pedido_id": 1}}, "es el padre"),
    ({"cantidad": "cantidad", "texto": CodigoEnTexto("material_id", "descripcion", "codigo"),
      "datos": {"solicitada": 1}}, "es calculado"),
    ({"cantidad": "cantidad", "texto": CodigoEnTexto("material_id", "descripcion", "codigo"),
      "aviso": "no"}, "'aviso' debe ser una función"),
])
def test_registry_valida_pegado(app, cfg, mensaje):
    _, errores = construir_spec("pedido_lineas", _override(pegado_en_linea=cfg))
    assert any(mensaje in e for e in errores), errores


def test_registry_pegado_requiere_alta_en_linea(app):
    _, errores = construir_spec("pedido_lineas", _override(alta_en_linea=None))
    assert any("requiere alta_en_linea" in e for e in errores), errores


def test_registry_pegado_de_pedido_lineas(app):
    spec, errores = construir_spec("pedido_lineas", _override())
    assert not errores
    p = spec.pegado_en_linea
    assert p.label == "Pegar líneas" and p.cantidad == "cantidad" and p.datos == {"destino": "a_identificar"}
