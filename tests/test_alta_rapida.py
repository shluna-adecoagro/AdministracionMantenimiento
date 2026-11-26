"""
Fase 13, PR 13.3: alta rápida (última fila de la grilla).

`alta_en_linea` en la spec: la pestaña «Líneas» del pedido termina con una fila
de alta (material o descripción, cantidad y destino). POST
/pedido_lineas/alta_en_linea?pedido_id=N crea la línea con servicio.crear.
"""
import pytest

from app.crud.core.interpretes import FkEntre, FkOTexto
from app.crud.meta.registry import cargar_overrides, construir_spec
from app.models.activos_models import Activo, CategoriaActivo, EstadoActivo
from app.models.auditoria_models import AuditLog
from app.models.materiales_models import CategoriaMaterial, Material
from app.models.pedidos_models import Pedido, PedidoLinea, PedidoLineaDestino
from app.models.ubicaciones_models import Ubicacion


def _guardar(db, *objetos):
    db.session.add_all(objetos)
    db.session.commit()
    return objetos[0] if len(objetos) == 1 else objetos


def _texto(r):
    return r.get_data(as_text=True)


@pytest.fixture
def materiales(db):
    cat = CategoriaMaterial.query.first().categoria_material_id
    filtro, filtro_aire, correa = _guardar(
        db,
        Material(codigo="RE504836", descripcion="Filtro de aceite", categoria_material_id=cat),
        Material(codigo="RE500000", descripcion="Filtro de aire", categoria_material_id=cat),
        Material(codigo="CO-1", descripcion="Correa", categoria_material_id=cat),
    )
    return {"filtro": filtro, "filtro_aire": filtro_aire, "correa": correa}


@pytest.fixture
def activo(db, categorias_activo, sector):
    return _guardar(db, Activo(
        numero_activo="T-12", descripcion="Tractor 2",
        categoria_activo_id=categorias_activo["Tractor"].categoria_activo_id, sector_id=sector.sector_id,
        estado_activo_id=EstadoActivo.query.first().estado_activo_id,
    ))


@pytest.fixture
def pedido(client):
    r = client.post("/api/pedidos", json={"referencia": "Service", "fecha_pedido": "2026-11-26"})
    assert r.status_code == 201, r.get_json()
    return Pedido.query.one()


def _alta(client, pedido, material="", cantidad="", destino=""):
    return client.post(f"/pedido_lineas/alta_en_linea?pedido_id={pedido.pedido_id}",
                       data={"material": material, "cantidad": cantidad, "destino": destino})


def _destino(linea):
    return PedidoLineaDestino.query.filter_by(pedido_linea_id=linea.pedido_linea_id).one()


# ---------------------------------------------------------------------------
# La fila en la pestaña
# ---------------------------------------------------------------------------

def test_la_pestana_lineas_termina_con_la_fila_de_alta(client, pedido, materiales):
    html = _texto(client.get(f"/pedidos/{pedido.pedido_id}?seccion=pedido_lineas"))
    assert 'id="alta-pedido_lineas"' in html and 'id="form-alta-pedido_lineas"' in html
    assert f"/pedido_lineas/alta_en_linea?pedido_id={pedido.pedido_id}" in html
    # Sin líneas, no hace falta el «No hay registros»: está la fila de alta.
    assert "No hay registros" not in html
    # Las sugerencias del material y del destino.
    assert "RE504836 — Filtro de aceite" in html
    # Sin foco al cargar la página (solo después de agregar).
    assert "data-foco-alta" not in html


def test_la_fila_de_alta_no_esta_en_la_pestana_del_material(client, pedido, materiales):
    html = _texto(client.get(f"/materiales/{materiales['filtro'].material_id}?seccion=pedido_lineas"))
    assert 'id="alta-pedido_lineas"' not in html


def test_sin_pedido_en_la_url_es_404(client, pedido):
    assert client.post("/pedido_lineas/alta_en_linea", data={"cantidad": "1"}).status_code == 404
    r = client.post(f"/pedido_lineas/alta_en_linea?material_id=1", data={"cantidad": "1"})
    assert r.status_code == 404
    assert client.post("/pedido_lineas/alta_en_linea?pedido_id=999", data={"cantidad": "1"}).status_code == 404


# ---------------------------------------------------------------------------
# Material o descripción
# ---------------------------------------------------------------------------

def test_alta_con_material_por_codigo(client, pedido, materiales, auditoria):
    r = _alta(client, pedido, "RE504836", "3")
    assert r.status_code == 200, _texto(r)
    linea = PedidoLinea.query.one()
    assert linea.material_id == materiales["filtro"].material_id and linea.descripcion is None
    assert linea.enviada_en is None  # nace en borrador
    assert linea.solicitada == 3
    assert _destino(linea).destino == "a_identificar"
    html = _texto(r)
    # La fila nueva, una fila de alta vacía con el foco en el material.
    assert f'id="fila-pedido_lineas-{linea.pedido_linea_id}"' in html
    assert 'id="alta-pedido_lineas"' in html
    assert 'name="material" value=""' in html and html.index("data-foco-alta") > html.index('name="material"')
    # La auditoría registra el alta con el motivo fijo.
    log = AuditLog.query.filter_by(TablaAfectada="pedido_lineas", TipoDeCambio="INSERT").one()
    assert log.motivo_operacion == "Alta en línea"


def test_alta_con_material_por_etiqueta_y_por_comienzo(client, pedido, materiales):
    assert _alta(client, pedido, "CO-1 — Correa", "1").status_code == 200
    assert _alta(client, pedido, "re5048", "1").status_code == 200
    ids = [l.material_id for l in PedidoLinea.query.order_by(PedidoLinea.pedido_linea_id)]
    assert ids == [materiales["correa"].material_id, materiales["filtro"].material_id]


def test_texto_que_no_es_un_material_queda_como_descripcion(client, pedido, materiales):
    assert _alta(client, pedido, "Cinta aisladora", "2").status_code == 200
    linea = PedidoLinea.query.one()
    assert linea.material_id is None and linea.descripcion == "Cinta aisladora"


def test_texto_que_coincide_con_varios_materiales_es_error(client, pedido, materiales):
    r = _alta(client, pedido, "Filtro", "2")
    assert r.status_code == 422
    html = _texto(r)
    assert "coincide con 2 opciones" in html
    # Lo escrito queda en la fila, con la celda marcada y el foco en ella.
    assert 'value="Filtro"' in html and 'value="2"' in html and "con-error" in html
    assert PedidoLinea.query.count() == 0


def test_sin_material_ni_descripcion_es_error(client, pedido, materiales):
    r = _alta(client, pedido, "", "2")
    assert r.status_code == 422 and "Elegí el material o escribí la descripción" in _texto(r)
    assert PedidoLinea.query.count() == 0


# ---------------------------------------------------------------------------
# Cantidad
# ---------------------------------------------------------------------------

@pytest.mark.parametrize("cantidad, mensaje", [
    ("", "obligatori"),
    ("abc", "Cantidad"),
    ("0", "mayor que cero"),
])
def test_cantidad_invalida(client, pedido, materiales, cantidad, mensaje):
    r = _alta(client, pedido, "CO-1", cantidad)
    assert r.status_code == 422 and mensaje in _texto(r)
    assert PedidoLinea.query.count() == 0 and PedidoLineaDestino.query.count() == 0


def test_cantidad_con_coma_decimal(client, pedido, materiales):
    assert _alta(client, pedido, "CO-1", "2,5").status_code == 200
    assert PedidoLinea.query.one().solicitada == 2.5


# ---------------------------------------------------------------------------
# Destino
# ---------------------------------------------------------------------------

def test_destino_activo_por_numero(client, pedido, materiales, activo):
    assert _alta(client, pedido, "CO-1", "1", "T-12").status_code == 200
    d = _destino(PedidoLinea.query.one())
    assert d.destino == "activo" and d.activo_id == activo.activo_id
    # Con el activo se sugiere el sector imputado (su sector).
    assert d.sector_imputado_id == activo.sector_id


def test_destino_ubicacion_es_stock(client, pedido, materiales, ubicacion):
    assert _alta(client, pedido, "CO-1", "1", "Galpón 1").status_code == 200
    d = _destino(PedidoLinea.query.one())
    assert d.destino == "stock" and d.ubicacion_id == ubicacion.ubicacion_id


def test_destino_por_la_sugerencia_y_por_comienzo(client, pedido, materiales, activo, ubicacion):
    assert _alta(client, pedido, "CO-1", "1", "T-12 — Tractor 2").status_code == 200
    assert _alta(client, pedido, "CO-1", "1", "galp").status_code == 200
    destinos = PedidoLineaDestino.query.order_by(PedidoLineaDestino.pedido_linea_destino_id).all()
    assert [d.destino for d in destinos] == ["activo", "stock"]


def test_destino_no_encontrado(client, pedido, materiales, activo):
    r = _alta(client, pedido, "CO-1", "1", "Cosechadora")
    assert r.status_code == 422 and "No encontré «Cosechadora»" in _texto(r)
    assert PedidoLinea.query.count() == 0


def test_destino_ambiguo_entre_activo_y_ubicacion(client, db, pedido, materiales, activo, sector):
    _guardar(db, Ubicacion(nombre_ubicacion="Tractores", sector_id=sector.sector_id))
    r = _alta(client, pedido, "CO-1", "1", "T")
    assert r.status_code == 422 and "coincide con 2 opciones" in _texto(r)


def test_el_destino_se_repite_en_la_fila_siguiente(client, pedido, materiales, activo):
    html = _texto(_alta(client, pedido, "CO-1", "1", "T-12"))
    assert 'name="destino" value="T-12"' in html
    assert 'name="cantidad" value=""' in html


# ---------------------------------------------------------------------------
# Pedido enviado y botones de la pestaña
# ---------------------------------------------------------------------------

def test_en_un_pedido_enviado_la_linea_nueva_nace_en_borrador(client, pedido, materiales, enviar):
    _alta(client, pedido, "CO-1", "1")
    enviar(pedido.pedido_id)
    r = _alta(client, pedido, "RE504836", "2")
    assert r.status_code == 200
    lineas = PedidoLinea.query.order_by(PedidoLinea.pedido_linea_id).all()
    assert lineas[0].enviada_en is not None and lineas[1].enviada_en is None


def test_los_botones_de_la_pestana_se_actualizan(client, pedido, materiales):
    html = _texto(_alta(client, pedido, "CO-1", "1"))
    # «Enviar a Compras» aparece con la primera línea en borrador (fuera de banda).
    assert 'id="botones-pedido_lineas" hx-swap-oob="true"' in html
    assert "Enviar a Compras" in html
    pagina = _texto(client.get(f"/pedidos/{pedido.pedido_id}?seccion=pedido_lineas"))
    assert 'id="botones-pedido_lineas"' in pagina


# ---------------------------------------------------------------------------
# Registry
# ---------------------------------------------------------------------------

def _override(**cambios):
    return {**cargar_overrides()["pedido_lineas"], **cambios}


@pytest.mark.parametrize("alta, mensaje", [
    ([{"nombre": "cantidad", "columnas": ["no_existe"]}], "no están en la pestaña"),
    ([{"nombre": "cantidad", "columnas": ["pedido_id"]}], "no están en la pestaña"),
    ([{"nombre": "cantidad", "columnas": ["material_id", "solicitada"]}], "no son consecutivas"),
    ([{"nombre": "cantidad", "columnas": ["solicitada"]},
      {"nombre": "material", "columnas": ["solicitada"], "interprete": FkOTexto("material_id", "descripcion")}],
     "ya es de otra celda"),
    ([{"nombre": "inventado", "columnas": ["solicitada"]}], "no es un campo"),
    ([{"nombre": "x", "columnas": ["solicitada"], "interprete": FkOTexto("solicitada", "descripcion")}],
     "es calculado"),
    ([{"nombre": "x", "columnas": ["solicitada"], "interprete": FkEntre({"pedido_id": {}})}],
     "es el padre"),
    ([{"nombre": "x", "columnas": ["solicitada"], "interprete": object()}], "intérprete no es válido"),
    ([{"nombre": "cantidad", "columnas": ["solicitada"], "otra": 1}], "claves desconocidas"),
])
def test_registry_valida_alta_en_linea(app, alta, mensaje):
    _, errores = construir_spec("pedido_lineas", _override(alta_en_linea=alta))
    assert any(mensaje in e for e in errores), errores


def test_registry_valida_el_padre_del_alta(app):
    _, errores = construir_spec("pedido_lineas", _override(alta_en_linea_padre="sectores"))
    assert any("no es un padre" in e for e in errores), errores
    # En la pestaña del material no se ve la columna del material: la celda no tiene dónde ir.
    _, errores = construir_spec("pedido_lineas", _override(alta_en_linea_padre="materiales"))
    assert any("no están en la pestaña de 'materiales'" in e for e in errores), errores


def test_registry_alta_por_defecto_en_el_padre_principal(app):
    spec, errores = construir_spec("pedido_lineas", _override(alta_en_linea_padre=None))
    assert not errores and spec.alta_en_linea_padre == "pedidos"
    assert [c.nombre for c in spec.alta_en_linea] == ["material", "cantidad", "destino"]
    assert spec.alta_en_linea[1].label == "Cantidad"
