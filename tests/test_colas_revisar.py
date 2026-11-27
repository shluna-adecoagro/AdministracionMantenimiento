"""
Fase 13, PR 13.6: colas de «a revisar».

  * Framework: `colas` en la spec (ColaSpec). Cada cola es una grilla en
    /<entidad>/cola/<id> con los registros que cumplen su condición (y, salvo
    ?todas=1, su condición por defecto), los filtros del listado y sus propios
    campos editables; las celdas van por las rutas de siempre con ?cola=<id>.
    Una fila resuelta queda marcada hasta recargar. El menú muestra cada cola
    con su cantidad.
  * Colas de pedidos (decidido 27/11): destinos a revisar, líneas sin material,
    líneas y pedidos a revisar (importación) y líneas de documentos sin
    material. Nunca las líneas anuladas; las cerradas, solo si se pide.
  * `pedido_lineas.sin_material_maestro`: saca la línea de la cola de las que no
    tienen material; identificar el material la desmarca.
"""
from datetime import datetime

import pytest

from app.crud.meta.registry import MetamodeloError, cargar_overrides, construir_registry
from app.models.activos_models import Activo, EstadoActivo
from app.models.documentos_models import DocumentoLinea, DocumentoProveedor
from app.models.materiales_models import CategoriaMaterial, Material
from app.models.motivos_models import MotivoOperacion
from app.models.pedidos_models import Pedido, PedidoLinea, PedidoLineaDestino


def _guardar(db, *objetos):
    db.session.add_all(objetos)
    db.session.commit()
    return objetos[0] if len(objetos) == 1 else objetos


def _texto(r):
    return r.get_data(as_text=True)


@pytest.fixture
def material(db):
    cat = CategoriaMaterial.query.first().categoria_material_id
    return _guardar(db, Material(codigo="RE504836", descripcion="Filtro de aceite", categoria_material_id=cat))


@pytest.fixture
def activo(db, categorias_activo, sector):
    estado = EstadoActivo.query.first().estado_activo_id
    return _guardar(db, Activo(numero_activo="T-1", descripcion="Tractor 1", sector_id=sector.sector_id,
                               categoria_activo_id=categorias_activo["Tractor"].categoria_activo_id,
                               estado_activo_id=estado))


@pytest.fixture
def pedido(client, sector):
    r = client.post("/api/pedidos", json={"referencia": "Service", "fecha_pedido": "2026-11-26",
                                          "sector_id": sector.sector_id})
    assert r.status_code == 201, r.get_json()
    return r.get_json()["pedido_id"]


def _linea(client, pedido, material=None, descripcion=None, cantidad=4, **destino):
    datos = {"pedido_id": pedido, "cantidad": cantidad, **(destino or {"destino": "a_identificar"})}
    if material is not None:
        datos["material_id"] = material.material_id
    if descripcion is not None:
        datos["descripcion"] = descripcion
    r = client.post("/api/pedido_lineas", json=datos)
    assert r.status_code == 201, r.get_json()
    return r.get_json()["pedido_linea_id"]


def _destino(linea_id):
    return PedidoLineaDestino.query.filter_by(pedido_linea_id=linea_id).first()


def _anular(db, linea_id):
    """Directo en la base (la acción tiene sus propios tests): anulada con motivo."""
    motivo = _guardar(db, MotivoOperacion(nombre_motivo="Se consiguió por otro canal", tipo_operacion="Anulación"))
    linea = db.session.get(PedidoLinea, linea_id)
    linea.estado, linea.motivo_operacion_id = "anulado", motivo.motivo_operacion_id
    linea.enviada_en = datetime(2026, 11, 26)
    db.session.commit()


def _cerrar(db, linea_id):
    """Cerrada como en el histórico: enviada, con cierre manual."""
    linea = db.session.get(PedidoLinea, linea_id)
    linea.enviada_en, linea.sin_conformidad = datetime(2026, 11, 26), True
    db.session.commit()


def _ids_en_cola(client, url):
    """Los ids de las filas de la grilla de una cola."""
    import re

    r = client.get(url)
    assert r.status_code == 200, _texto(r)
    return {int(x) for x in re.findall(r'id="fila-[a-z_]+-(\d+)"', _texto(r))}


COLA_DESTINOS = "/pedido_linea_destinos/cola/a_revisar"
COLA_SIN_MATERIAL = "/pedido_lineas/cola/sin_material"


# ---------------------------------------------------------------------------
# Destinos a revisar
# ---------------------------------------------------------------------------

def test_la_cola_de_destinos_muestra_los_a_revisar(client, pedido, material, activo):
    pendiente = _destino(_linea(client, pedido, material))
    resuelto = _destino(_linea(client, pedido, material, destino="activo", activo_id=activo.activo_id))
    assert pendiente.a_revisar == "Sí" and resuelto.a_revisar == "No"
    ids = _ids_en_cola(client, COLA_DESTINOS)
    assert ids == {pendiente.pedido_linea_destino_id}


def test_sin_anuladas_y_las_cerradas_a_pedido(client, db, pedido, material):
    abierta = _linea(client, pedido, material)
    anulada = _linea(client, pedido, material)
    cerrada = _linea(client, pedido, material)
    _anular(db, anulada)
    _cerrar(db, cerrada)
    d = {x: _destino(x).pedido_linea_destino_id for x in (abierta, anulada, cerrada)}
    assert _ids_en_cola(client, COLA_DESTINOS) == {d[abierta]}
    assert _ids_en_cola(client, COLA_DESTINOS + "?todas=1") == {d[abierta], d[cerrada]}


def test_editar_en_la_cola_resuelve_y_la_fila_queda_marcada(client, pedido, material, activo, sector, auditoria):
    d = _destino(_linea(client, pedido, material))
    url = f"/pedido_linea_destinos/{d.pedido_linea_destino_id}/celda/activo_id?cola=a_revisar"
    assert client.get(url).status_code == 200
    r = client.post(url, data={"activo_id": str(activo.activo_id)})
    assert r.status_code == 200, _texto(r)
    html = _texto(r)
    assert "fila-resuelta" in html and "Resuelta" in html
    # La fila se arma con las columnas de la cola (el detalle tal como se pidió).
    assert 'data-campo="detalle_texto"' in html
    d = _destino(d.pedido_linea_id)
    assert d.destino == "activo" and d.sector_imputado_id == sector.sector_id
    assert d.pedido_linea_destino_id not in _ids_en_cola(client, COLA_DESTINOS)
    assert any(log.motivo_operacion == "Edición en línea" for log in auditoria("pedido_linea_destinos"))


def test_una_fila_que_sigue_a_revisar_no_se_marca(client, pedido, material, cuenta):
    d = _destino(_linea(client, pedido, material))
    r = client.post(f"/pedido_linea_destinos/{d.pedido_linea_destino_id}/celda/cuenta_id?cola=a_revisar",
                    data={"cuenta_id": str(cuenta.cuenta_id)})
    assert r.status_code == 200, _texto(r)
    assert "fila-resuelta" not in _texto(r)  # sigue «a identificar»


def test_un_campo_fuera_de_la_cola_no_se_edita(client, pedido, material):
    d = _destino(_linea(client, pedido, material))
    # comprada_corregida no está en edicion_en_linea, ni en la entidad ni en la cola.
    r = client.get(f"/pedido_linea_destinos/{d.pedido_linea_destino_id}/celda/comprada_corregida?cola=a_revisar")
    assert r.status_code == 404


def test_cola_inexistente_404(client):
    assert client.get("/pedido_linea_destinos/cola/no_existe").status_code == 404


def test_la_fila_ofrece_la_linea_y_redistribuir(client, pedido, material, enviar):
    borrador = _linea(client, pedido, material)
    r = client.get(COLA_DESTINOS)
    html = _texto(r)
    assert f"/pedido_lineas/{borrador}?seccion=pedido_linea_destinos" in html
    assert "Destinos de la línea de pedido" in html
    assert "accion/redistribuir" not in html  # en borrador se reparte en la pestaña de la línea
    enviar(pedido)
    html = _texto(client.get(COLA_DESTINOS))
    assert f"/pedido_lineas/{borrador}/accion/redistribuir?volver=" in html


def test_redistribuir_desde_la_cola_vuelve_a_la_cola(client, pedido, material, activo, enviar):
    linea = _linea(client, pedido, material)
    enviar(pedido)
    d = _destino(linea)
    url = f"/pedido_lineas/{linea}/accion/redistribuir?volver={COLA_DESTINOS}"
    assert client.get(url).status_code == 200
    r = client.post(url, data={"id": [str(d.pedido_linea_destino_id), ""], "cantidad": ["2", "2"],
                               "destino": ["T-1", ""]})
    assert r.status_code == 302, _texto(r)
    assert r.headers["Location"].endswith(COLA_DESTINOS)


def test_volver_a_otro_sitio_no_se_acepta(client, pedido, material, enviar):
    linea = _linea(client, pedido, material)
    enviar(pedido)
    d = _destino(linea)
    url = f"/pedido_lineas/{linea}/accion/redistribuir?volver=//otro.sitio/x"
    r = client.get(url)
    assert r.status_code == 200
    assert 'href="//otro.sitio' not in _texto(r)  # «Cancelar» vuelve a la línea
    r = client.post(url, data={"id": [str(d.pedido_linea_destino_id)], "cantidad": ["4"], "destino": [""]})
    assert r.status_code == 302 and "otro.sitio" not in r.headers["Location"]


# ---------------------------------------------------------------------------
# Líneas sin material y «sin material del maestro»
# ---------------------------------------------------------------------------

def test_cola_de_lineas_sin_material(client, pedido, material):
    sin = _linea(client, pedido, descripcion="Tornillos 8 mm")
    con = _linea(client, pedido, material)
    ids = _ids_en_cola(client, COLA_SIN_MATERIAL)
    assert sin in ids and con not in ids


def test_identificar_el_material_en_la_cola(client, pedido, material, enviar):
    linea = _linea(client, pedido, descripcion="Filtro RE504836")
    enviar(pedido)  # enviada: el material vacío se puede completar
    # Con pocos materiales la celda es un <select>: va el id.
    r = client.post(f"/pedido_lineas/{linea}/celda/material_id?cola=sin_material",
                    data={"material_id": str(material.material_id)})
    assert r.status_code == 200, _texto(r)
    assert "fila-resuelta" in _texto(r)
    assert PedidoLinea.query.get(linea).material_id == material.material_id
    assert linea not in _ids_en_cola(client, COLA_SIN_MATERIAL)


def test_marcar_sin_material_del_maestro_la_saca_de_la_cola(client, pedido):
    linea = _linea(client, pedido, descripcion="Tornillos 8 mm")
    r = client.post(f"/pedido_lineas/{linea}/celda/sin_material_maestro?cola=sin_material",
                    data={"sin_material_maestro": "True"})
    assert r.status_code == 200, _texto(r)
    assert PedidoLinea.query.get(linea).sin_material_maestro is True
    assert linea not in _ids_en_cola(client, COLA_SIN_MATERIAL)


def test_identificar_el_material_desmarca_sin_material_del_maestro(client, db, pedido, material):
    linea = _linea(client, pedido, descripcion="Filtro")
    r = client.patch(f"/api/pedido_lineas/{linea}", json={"sin_material_maestro": True})
    assert r.status_code == 200, r.get_json()
    r = client.patch(f"/api/pedido_lineas/{linea}", json={"material_id": material.material_id})
    assert r.status_code == 200, r.get_json()
    assert db.session.get(PedidoLinea, linea).sin_material_maestro is False


def test_no_se_marca_sin_material_del_maestro_con_material(client, pedido, material):
    linea = _linea(client, pedido, material)
    r = client.patch(f"/api/pedido_lineas/{linea}", json={"sin_material_maestro": True})
    assert r.status_code in (400, 422), r.get_json()
    assert "ya tiene el material" in str(r.get_json())


def test_subgrilla_de_destinos_en_la_cola_de_lineas(client, pedido):
    """Los destinos de una línea se abren bajo su fila; al cambiarlos vuelve la fila de la cola."""
    linea = _linea(client, pedido, descripcion="Tornillos")
    html = _texto(client.get(COLA_SIN_MATERIAL))
    assert "vista_padre=cola:sin_material" in html or "vista_padre=cola%3Asin_material" in html
    d = _destino(linea)
    r = client.post(f"/pedido_linea_destinos/{d.pedido_linea_destino_id}/celda/cantidad"
                    f"?pedido_linea_id={linea}&vista_padre=cola:sin_material", data={"cantidad": "6"})
    assert r.status_code == 200, _texto(r)
    html = _texto(r)
    # La fila de la línea fuera de banda, con las columnas de la cola.
    assert f'id="fila-pedido_lineas-{linea}"' in html and 'data-campo="sin_material_maestro"' in html


# ---------------------------------------------------------------------------
# Importación: líneas y pedidos con «A revisar (importación)»
# ---------------------------------------------------------------------------

def test_colas_de_importacion(client, db, pedido, material):
    linea = _linea(client, pedido, material)
    otra = _linea(client, pedido, material)
    db.session.get(PedidoLinea, linea).motivo_revision = "Dos OC en una celda"
    db.session.get(PedidoLinea, otra).motivo_revision = ""
    db.session.get(Pedido, pedido).motivo_revision = "Columnas corridas"
    db.session.commit()
    assert _ids_en_cola(client, "/pedido_lineas/cola/importacion") == {linea}
    assert _ids_en_cola(client, "/pedidos/cola/importacion") == {pedido}
    # Borrar el motivo la resuelve.
    r = client.post(f"/pedidos/{pedido}/celda/motivo_revision?cola=importacion", data={"motivo_revision": ""})
    assert r.status_code == 200, _texto(r)
    assert "fila-resuelta" in _texto(r)
    assert _ids_en_cola(client, "/pedidos/cola/importacion") == set()


def test_cola_de_lineas_de_documentos_sin_material(client, db, material):
    doc = _guardar(db, DocumentoProveedor(tipo="oferta", fecha=datetime(2026, 11, 26).date(), moneda="ARS"))
    sin = _guardar(db, DocumentoLinea(documento_id=doc.documento_id, nro_linea=1, tipo_linea="material",
                                      descripcion_proveedor="Filtro aceite", cantidad=2, precio_unitario=10))
    _guardar(db, DocumentoLinea(documento_id=doc.documento_id, nro_linea=2, tipo_linea="mano_de_obra",
                                descripcion_proveedor="Mano de obra", cantidad=1, precio_unitario=50))
    url = "/documento_lineas/cola/sin_material"
    assert _ids_en_cola(client, url) == {sin.documento_linea_id}
    r = client.post(f"/documento_lineas/{sin.documento_linea_id}/celda/material_id?cola=sin_material",
                    data={"material_id": str(material.material_id)})
    assert r.status_code == 200, _texto(r)
    assert _ids_en_cola(client, url) == set()


# ---------------------------------------------------------------------------
# Menú y pantalla
# ---------------------------------------------------------------------------

def test_el_menu_muestra_las_colas_con_su_cantidad(client, pedido, material):
    _linea(client, pedido, material)
    _linea(client, pedido, material)
    html = _texto(client.get("/pedidos"))
    assert "A revisar" in html and "Destinos a revisar" in html
    i = html.index("Destinos a revisar")
    assert '<span class="contador">2</span>' in html[i:i + 200]
    assert "Líneas de documentos sin material" in html


def test_la_celda_no_cuenta_las_colas(client, app, pedido, material):
    """Los parciales de la grilla no llevan el menú: no se cuentan las colas en cada celda."""
    d = _destino(_linea(client, pedido, material))
    llamadas = []
    import app.crud.web.views as views

    original = views.menu_colas
    views.menu_colas = lambda registry: llamadas.append(1) or original(registry)
    try:
        client.get(f"/pedido_linea_destinos/{d.pedido_linea_destino_id}/celda/cantidad?cola=a_revisar")
        assert llamadas == []
        client.get(COLA_DESTINOS)
        assert llamadas == [1]
    finally:
        views.menu_colas = original


def test_pantalla_de_la_cola(client, pedido, material):
    _linea(client, pedido, material)
    html = _texto(client.get(COLA_DESTINOS))
    assert "<h2>Destinos a revisar</h2>" in html
    assert "Incluir los de líneas cerradas" in html
    assert "Crear destino" not in html
    assert 'class="grilla"' in html


def test_filtros_del_listado_en_la_cola(client, pedido, material, sector):
    linea = _linea(client, pedido, material)
    d = _destino(linea)
    assert d.pedido_linea_destino_id in _ids_en_cola(client, COLA_DESTINOS + "?q=RE504836")
    assert _ids_en_cola(client, COLA_DESTINOS + "?q=no-existe") == set()


# ---------------------------------------------------------------------------
# Registry
# ---------------------------------------------------------------------------

def _con_cola(cola):
    ov = cargar_overrides()
    ov["pedido_linea_destinos"] = {**ov["pedido_linea_destinos"], "colas": [cola]}
    return ov


def test_registry_rechaza_una_cola_con_un_campo_calculado():
    cola = {"id": "x", "label": "X", "condicion": lambda: True, "columnas": ["cantidad", "comprada"],
            "edicion_en_linea": ["comprada"]}
    with pytest.raises(MetamodeloError, match="colas.x: edicion_en_linea: 'comprada' es calculado"):
        construir_registry(_con_cola(cola))


def test_registry_rechaza_una_columna_que_no_existe():
    cola = {"id": "x", "label": "X", "condicion": lambda: True, "columnas": ["cantidad", "no_existe"]}
    with pytest.raises(MetamodeloError, match="columna 'no_existe'"):
        construir_registry(_con_cola(cola))


def test_registry_pide_label_todas_con_por_defecto():
    cola = {"id": "x", "label": "X", "condicion": lambda: True, "por_defecto": lambda: True,
            "columnas": ["cantidad"]}
    with pytest.raises(MetamodeloError, match="label_todas"):
        construir_registry(_con_cola(cola))


def test_por_defecto_la_cola_edita_lo_de_la_entidad_que_muestra():
    from app.crud.entidades import REGISTRY

    cola = REGISTRY["pedido_linea_destinos"].cola("a_revisar")
    assert "cantidad" in cola.edicion_en_linea and "cuenta_id" in cola.edicion_en_linea
