"""
Fase 13, PR 13.1: edición en línea (grilla) generada desde la spec.

Rutas GET/POST /<entidad>/<id>/celda/<campo> y GET /<entidad>/<id>/fila, activadas
por `edicion_en_linea`. Se prueban sobre las líneas de pedido (pestaña «Líneas»).
"""
import pytest

from app.crud.core import fk
from app.crud.meta.registry import cargar_overrides, construir_spec
from app.models.auditoria_models import AuditLog
from app.models.materiales_models import CategoriaMaterial, Material
from app.models.pedidos_models import Pedido, PedidoLinea
from app.models.unidadmedida_models import TipoUnidad, UnidadMedida


def _guardar(db, *objetos):
    db.session.add_all(objetos)
    db.session.commit()
    return objetos[0] if len(objetos) == 1 else objetos


@pytest.fixture
def unidades(db):
    tipo = TipoUnidad.query.filter_by(nombre_tipo="Volumen").one().tipo_unidad_id
    return _guardar(db, UnidadMedida(nombre_unidad="Litros", abreviatura="L", tipo_unidad_id=tipo),
                    UnidadMedida(nombre_unidad="Mililitros", abreviatura="mL", tipo_unidad_id=tipo))


@pytest.fixture
def materiales(db, unidades):
    """Un filtro, un aceite y, para pasar el umbral de la búsqueda, 20 materiales más."""
    litros, mililitros = unidades
    cat = CategoriaMaterial.query.first().categoria_material_id
    filtro = Material(codigo="RE504836", descripcion="Filtro de aceite", categoria_material_id=cat,
                      unidad_medida_id=litros.unidad_medida_id)
    aditivo = Material(codigo="AD-10", descripcion="Aditivo", categoria_material_id=cat,
                       unidad_medida_id=mililitros.unidad_medida_id)
    otros = [Material(codigo=f"X{i:03d}", descripcion=f"Repuesto {i}", categoria_material_id=cat)
             for i in range(20)]
    _guardar(db, filtro, aditivo, *otros)
    return {"filtro": filtro, "aditivo": aditivo}


@pytest.fixture
def pedido(client):
    r = client.post("/api/pedidos", json={"referencia": "Filtros", "fecha_pedido": "2026-11-23"})
    assert r.status_code == 201, r.get_json()
    return Pedido.query.one()


@pytest.fixture
def linea(client, pedido, materiales):
    r = client.post("/api/pedido_lineas", json={
        "pedido_id": pedido.pedido_id, "material_id": materiales["filtro"].material_id,
        "cantidad": 2, "destino": "a_identificar",
    })
    assert r.status_code == 201, r.get_json()
    return PedidoLinea.query.one()


def _url(linea, campo=None):
    base = f"/pedido_lineas/{linea.pedido_linea_id}"
    return (f"{base}/celda/{campo}" if campo else f"{base}/fila") + f"?pedido_id={linea.pedido_id}"


def _texto(r):
    return r.get_data(as_text=True)


# ---------------------------------------------------------------------------
# Registry
# ---------------------------------------------------------------------------

def _override(entidad, **cambios):
    return {**cargar_overrides()[entidad], **cambios}


@pytest.mark.parametrize("campo, motivo", [
    ("solicitada", "es calculado"),
    ("se_cuenta_en", "es calculado"),
    ("origen", "de solo importación"),
    ("cantidad", "campo de alta"),
    ("pedido_id", "padre principal"),
    ("observaciones", "no está en el listado"),
    ("no_existe", "no es un campo"),
])
def test_registry_rechaza_campos_no_editables(app, campo, motivo):
    _, errores = construir_spec("pedido_lineas", _override("pedido_lineas", edicion_en_linea=[campo]))
    assert any("edicion_en_linea" in e and motivo in e for e in errores), errores


def test_registry_rechaza_archivos(app):
    _, errores = construir_spec("materiales", _override("materiales", edicion_en_linea=["foto"]))
    assert any("'foto' es un archivo" in e for e in errores), errores


def test_registry_acepta_un_padre_secundario(app):
    # La línea también cuelga del material: su material sí se edita (en la pestaña
    # del material, esa columna no se muestra).
    spec, errores = construir_spec("pedido_lineas", _override("pedido_lineas"))
    assert not errores
    assert "material_id" in spec.edicion_en_linea


# ---------------------------------------------------------------------------
# Rutas y grilla
# ---------------------------------------------------------------------------

def test_sin_edicion_en_linea_no_hay_rutas(client, sector):
    assert client.get(f"/sectores/{sector.sector_id}/fila").status_code == 404
    assert client.get(f"/sectores/{sector.sector_id}/celda/nombre_sector").status_code == 404
    assert 'class="grilla"' not in _texto(client.get("/sectores"))


def test_pestana_lineas_es_una_grilla(client, linea):
    html = _texto(client.get(f"/pedidos/{linea.pedido_id}?seccion=pedido_lineas"))
    assert "tabla-listado grilla" in html
    assert f'hx-get="{_url(linea, "descripcion")}"' in html
    assert 'class="calc" tabindex="-1" data-campo="solicitada"' in html
    # La columna del padre no se muestra en su propia pestaña.
    assert 'data-campo="pedido_id"' not in html


def test_htmx_sin_cdn(client, linea):
    html = _texto(client.get(f"/pedidos/{linea.pedido_id}?seccion=pedido_lineas"))
    assert "/static/vendor/htmx/htmx.min.js" in html and "unpkg.com" not in html
    assert client.get("/static/vendor/htmx/htmx.min.js").status_code == 200
    assert client.get("/static/js/grilla.js").status_code == 200


def test_campo_no_editable_da_404(client, linea):
    assert client.get(_url(linea, "solicitada")).status_code == 404
    assert client.post(_url(linea, "observaciones"), data={"observaciones": "x"}).status_code == 404
    assert client.get("/pedido_lineas/999/celda/descripcion").status_code == 404


def test_fila_en_lectura(client, linea):
    r = client.get(_url(linea))
    assert r.status_code == 200
    html = _texto(r)
    assert html.strip().startswith(f'<tr id="fila-pedido_lineas-{linea.pedido_linea_id}"')
    assert "editando" not in html


# ---------------------------------------------------------------------------
# Celda en edición
# ---------------------------------------------------------------------------

def test_material_con_busqueda_por_texto(client, linea):
    html = _texto(client.get(_url(linea, "material_id")))
    assert html.strip().startswith('<td class="celda editando"')
    assert 'value="RE504836 — Filtro de aceite" list="lista-pedido_lineas-material_id"' in html
    assert '<option value="AD-10 — Aditivo">' in html


def test_pocas_opciones_es_un_select(app, db, unidades):
    from app.crud.entidades import REGISTRY
    from app.crud.web.views import control_celda

    f = REGISTRY["pedido_lineas"].fields["unidad_medida_id"]
    control, opciones = control_celda(f)
    assert control == "select" and {o["label"] for o in opciones} >= {"Litros", "Mililitros"}
    assert control_celda(REGISTRY["pedido_lineas"].fields["estado"])[0] == "select"


# ---------------------------------------------------------------------------
# Guardar
# ---------------------------------------------------------------------------

def test_guardar_devuelve_la_fila_entera(client, linea):
    r = client.post(_url(linea, "descripcion"), data={"descripcion": "Filtro de aceite motor"})
    assert r.status_code == 200
    html = _texto(r)
    assert f'<tr id="fila-pedido_lineas-{linea.pedido_linea_id}" class="fila" data-foco="descripcion">' in html
    assert "Filtro de aceite motor" in html
    assert PedidoLinea.query.one().descripcion == "Filtro de aceite motor"


def test_aplica_completar(client, linea):
    client.post(_url(linea, "nro_oc"), data={"nro_oc": " oc 4500 12 "})
    assert PedidoLinea.query.one().nro_oc == "OC450012"


def test_auditoria_con_motivo_fijo(client, linea):
    client.post(_url(linea, "nro_oc"), data={"nro_oc": "4500"})
    log = AuditLog.query.filter_by(TablaAfectada="pedido_lineas", TipoDeCambio="UPDATE").one()
    assert log.motivo_operacion == "Edición en línea"
    assert log.EstadoActual["nro_oc"] == "4500"


@pytest.mark.parametrize("texto", ["RE504836 — Filtro de aceite", "ad-10", "Aditivo", "AD-1"])
def test_material_por_etiqueta_codigo_descripcion_o_comienzo(client, linea, materiales, texto):
    r = client.post(_url(linea, "material_id"), data={"material_id": texto})
    assert r.status_code == 200, _texto(r)
    esperado = materiales["filtro"] if texto.startswith("RE") else materiales["aditivo"]
    assert PedidoLinea.query.one().material_id == esperado.material_id


def test_cambiar_el_material_recalcula_la_unidad(client, linea, materiales, unidades):
    # La unidad depende del material: no da «no pertenece», toma la del material
    # nuevo, y la fila devuelta muestra la columna calculada actualizada.
    assert PedidoLinea.query.one().unidad_medida_id == unidades[0].unidad_medida_id
    r = client.post(_url(linea, "material_id"), data={"material_id": "AD-10"})
    assert r.status_code == 200, _texto(r)
    assert PedidoLinea.query.one().unidad_medida_id == unidades[1].unidad_medida_id
    assert "Mililitros" in _texto(r)


def test_material_inexistente_deja_la_celda_abierta(client, linea, materiales):
    r = client.post(_url(linea, "material_id"), data={"material_id": "zzz"})
    assert r.status_code == 422
    html = _texto(r)
    assert html.strip().startswith(f'<tr id="fila-pedido_lineas-{linea.pedido_linea_id}"')
    assert 'class="celda editando con-error"' in html
    assert 'value="zzz"' in html  # lo escrito no se pierde
    assert "No encontré «zzz». Elegí una opción de la lista." in html
    assert PedidoLinea.query.one().material_id == materiales["filtro"].material_id


def test_comienzo_ambiguo(client, linea):
    r = client.post(_url(linea, "material_id"), data={"material_id": "X00"})
    assert r.status_code == 422 and "coincide con 10 opciones" in _texto(r)


def test_error_de_otro_campo_se_muestra_en_la_celda(client, pedido):
    # Una línea solo con descripción: si se borra la descripción, la regla marca el
    # error en el material; se ve en la celda editada, con la etiqueta del material.
    client.post("/api/pedido_lineas", json={"pedido_id": pedido.pedido_id, "descripcion": "Correa",
                                            "cantidad": 1, "destino": "a_identificar"})
    linea = PedidoLinea.query.one()
    r = client.post(_url(linea, "descripcion"), data={"descripcion": ""})
    assert r.status_code == 422
    html = _texto(r)
    assert 'data-campo="descripcion"' in html and "con-error" in html
    assert "Material: Elegí el material o escribí la descripción" in html
    assert PedidoLinea.query.one().descripcion == "Correa"
    assert AuditLog.query.filter_by(TablaAfectada="pedido_lineas", TipoDeCambio="UPDATE").count() == 0


def test_listado_propio_tambien_es_grilla(client, linea):
    html = _texto(client.get("/pedido_lineas"))
    assert 'class="grilla"' in html
    assert f'hx-get="/pedido_lineas/{linea.pedido_linea_id}/celda/descripcion"' in html


# ---------------------------------------------------------------------------
# Buscador de FK por texto (núcleo; también lo usa la importación CSV)
# ---------------------------------------------------------------------------

def test_buscador_por_prefijo(app, materiales):
    from app.crud.entidades import REGISTRY

    f = REGISTRY["pedido_lineas"].fields["material_id"]
    exacto = fk.BuscadorFK(f)
    with pytest.raises(fk.NoEncontrado):
        exacto.buscar("RE5048")  # la importación sigue pidiendo el texto exacto
    assert fk.BuscadorFK(f, por_prefijo=True).buscar("re5048") == materiales["filtro"].material_id
    with pytest.raises(fk.Ambiguo):
        fk.BuscadorFK(f, por_prefijo=True).buscar("Repuesto")


def test_umbral_de_busqueda(app, db, unidades):
    from app.crud.entidades import REGISTRY

    f = REGISTRY["pedido_lineas"].fields["material_id"]
    cat = CategoriaMaterial.query.first().categoria_material_id
    _guardar(db, *[Material(codigo=f"M{i}", descripcion=f"M {i}", categoria_material_id=cat)
                   for i in range(fk.UMBRAL_LISTA)])
    assert not fk.usa_busqueda(f)
    _guardar(db, Material(codigo="M-otro", descripcion="Uno más", categoria_material_id=cat))
    assert fk.usa_busqueda(f)
