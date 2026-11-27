"""
Fase 13, PR 13.8: subgrilla de adjudicaciones.

Las adjudicaciones de cada línea de oferta se despliegan debajo de ella (como los
destinos bajo la línea de pedido): se editan la ofertada y la adjudicada, se
eliminan y se agregan con la alta rápida («nº de pedido / línea» y cantidad).
"""
from datetime import date

import pytest

from app.crud.meta.registry import MetamodeloError, cargar_overrides, construir_registry
from app.models.documentos_models import Adjudicacion, DocumentoLinea, DocumentoProveedor
from app.models.materiales_models import CategoriaMaterial, Material
from app.models.pedidos_models import Pedido, PedidoLinea
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
    filtro, otro, aceite = _guardar(
        db,
        Material(codigo="RE504836", descripcion="Filtro de aceite", categoria_material_id=cat),
        Material(codigo="P550", descripcion="Filtro equivalente", categoria_material_id=cat),
        Material(codigo="GEN-15W40", descripcion="Aceite 15W-40", es_generico=True, categoria_material_id=cat,
                 unidad_medida_id=litros.unidad_medida_id),
    )
    bidon = _guardar(db, Material(codigo="AC-20", descripcion="Aceite 15W-40 bidón 20 L", categoria_material_id=cat,
                                  material_generico_id=aceite.material_id, presentacion_cantidad=20,
                                  unidad_medida_id=litros.unidad_medida_id))
    return {"filtro": filtro, "otro": otro, "aceite": aceite, "bidon": bidon}


@pytest.fixture
def lange(db):
    return _guardar(db, Proveedor(razon_social="Lubricantes Lange S.A.", cuit="30-71234567-8"))


def _doc(db, lange, tipo="oferta", numero="9676"):
    return _guardar(db, DocumentoProveedor(tipo=tipo, proveedor_id=lange.recurso_id, numero=numero,
                                           fecha=date(2026, 11, 27), moneda="ARS"))


@pytest.fixture
def oferta(db, lange):
    return _doc(db, lange)


def _linea_oferta(db, doc, material, cantidad=10, nro=1):
    return _guardar(db, DocumentoLinea(documento_id=doc.documento_id, nro_linea=nro, tipo_linea="material",
                                       material_id=material.material_id, descripcion_proveedor=material.descripcion,
                                       cantidad=cantidad, precio_unitario=100))


@pytest.fixture
def pedido(client, m, enviar):
    """Pedido enviado con dos líneas: 3 filtros (línea 1) y 40 L de aceite (línea 2)."""
    p = client.post("/api/pedidos", json={"fecha_pedido": "2026-11-27", "referencia": "Service"}).get_json()
    lineas = {}
    for clave, material, cantidad in (("filtro", m["filtro"], 3), ("aceite", m["aceite"], 40)):
        r = client.post("/api/pedido_lineas", json={"pedido_id": p["pedido_id"], "material_id": material.material_id,
                                                    "cantidad": cantidad, "destino": "a_identificar"})
        assert r.status_code == 201, r.get_json()
        lineas[clave] = r.get_json()["pedido_linea_id"]
    enviar(p["pedido_id"])
    return {"id": p["pedido_id"], "numero": p["numero"], **lineas}


def _adjudicar(db, lo, pedido_linea_id, cantidad=0, ofertada=None):
    return _guardar(db, Adjudicacion(documento_linea_id=lo.documento_linea_id, pedido_linea_id=pedido_linea_id,
                                     cantidad_adjudicada=cantidad, cantidad_ofertada=ofertada))


def _q(lo):
    return f"documento_linea_id={lo.documento_linea_id}&vista_padre=documento_id"


def _subgrilla(client, lo):
    return client.get(f"/adjudicaciones/subgrilla?{_q(lo)}")


def _celda(client, lo, a, campo, valor):
    return client.post(f"/adjudicaciones/{a.adjudicacion_id}/celda/{campo}?{_q(lo)}", data={campo: valor})


def _alta(client, lo, linea="", cantidad=""):
    return client.post(f"/adjudicaciones/alta_en_linea?{_q(lo)}",
                       data={"pedido_linea": linea, "cantidad_adjudicada": cantidad})


def _recibir(db, pedido_linea_id, material, cantidad):
    lp = db.session.get(PedidoLinea, pedido_linea_id)
    _guardar(db, Recepcion(pedido_linea_destino_id=lp.destinos[0].pedido_linea_destino_id,
                           material_id=material.material_id, cantidad=cantidad))


# ---------------------------------------------------------------------------
# La subgrilla
# ---------------------------------------------------------------------------

def test_boton_de_la_subgrilla_solo_en_lineas_de_ofertas(client, db, lange, oferta, m, pedido):
    lo = _linea_oferta(db, oferta, m["filtro"])
    _adjudicar(db, lo, pedido["filtro"])
    html = _texto(client.get(f"/documentos_proveedor/{oferta.documento_id}?seccion=documento_lineas"))
    assert f'data-subgrilla="sub-adjudicaciones-{lo.documento_linea_id}"' in html
    assert "Adjudicaciones (1)" in html

    remito = _doc(db, lange, tipo="remito", numero="R-1")
    lr = _linea_oferta(db, remito, m["filtro"])
    html = _texto(client.get(f"/documentos_proveedor/{remito.documento_id}?seccion=documento_lineas"))
    assert "sub-adjudicaciones" not in html
    # Tampoco por la URL.
    assert _subgrilla(client, lr).status_code == 404


def test_subgrilla_con_celdas_y_alta(client, db, oferta, m, pedido):
    lo = _linea_oferta(db, oferta, m["filtro"])
    a = _adjudicar(db, lo, pedido["filtro"])
    r = _subgrilla(client, lo)
    assert r.status_code == 200
    html = _texto(r)
    assert f"/adjudicaciones/{a.adjudicacion_id}/celda/cantidad_adjudicada" in html
    assert f"/adjudicaciones/{a.adjudicacion_id}/celda/cantidad_ofertada" in html
    assert f"/adjudicaciones/{a.adjudicacion_id}/celda/pedido_linea_id" not in html
    assert "Pendiente de comprar (pedido)" in html
    assert f'id="alta-adjudicaciones-{lo.documento_linea_id}"' in html


def test_la_linea_de_pedido_no_se_cambia(client, db, oferta, m, pedido):
    lo = _linea_oferta(db, oferta, m["filtro"])
    a = _adjudicar(db, lo, pedido["filtro"])
    r = client.patch(f"/api/adjudicaciones/{a.adjudicacion_id}", json={"pedido_linea_id": pedido["aceite"]})
    assert r.status_code == 400
    assert "eliminá la adjudicación" in _texto(r)


def test_editar_la_adjudicada_actualiza_la_fila_de_la_linea(client, db, oferta, m, pedido):
    lo = _linea_oferta(db, oferta, m["filtro"])
    a = _adjudicar(db, lo, pedido["filtro"])
    r = _celda(client, lo, a, "cantidad_adjudicada", "3")
    assert r.status_code == 200, _texto(r)
    html = _texto(r)
    # La fila de la línea de oferta vuelve fuera de banda, con lo adjudicado.
    assert f'id="fila-documento_lineas-{lo.documento_linea_id}"' in html and 'hx-swap-oob="true"' in html
    db.session.expire_all()
    assert db.session.get(DocumentoLinea, lo.documento_linea_id).adjudicada == 3
    assert db.session.get(PedidoLinea, pedido["filtro"]).pendiente_comprar == 0


# ---------------------------------------------------------------------------
# Controles de lo ofertado
# ---------------------------------------------------------------------------

def test_ofertada_no_supera_la_linea_de_oferta(client, db, oferta, m, pedido):
    lo = _linea_oferta(db, oferta, m["filtro"], cantidad=5)
    a = _adjudicar(db, lo, pedido["filtro"])
    r = _celda(client, lo, a, "cantidad_ofertada", "6")
    assert r.status_code == 422
    assert "no puede superar la cantidad de la línea 1" in _texto(r)
    assert _celda(client, lo, a, "cantidad_ofertada", "2").status_code == 200


def test_adjudicada_no_supera_la_ofertada(client, db, oferta, m, pedido):
    lo = _linea_oferta(db, oferta, m["filtro"], cantidad=5)
    a = _adjudicar(db, lo, pedido["filtro"], ofertada=2)
    r = _celda(client, lo, a, "cantidad_adjudicada", "3")
    assert r.status_code == 422
    assert "no puede superar la ofertada" in _texto(r)
    assert _celda(client, lo, a, "cantidad_adjudicada", "2").status_code == 200


def test_adjudicada_no_supera_lo_ofertado_en_la_linea(client, db, oferta, m, pedido):
    lo = _linea_oferta(db, oferta, m["filtro"], cantidad=2)
    a = _adjudicar(db, lo, pedido["filtro"])
    r = _celda(client, lo, a, "cantidad_adjudicada", "3")
    assert r.status_code == 422
    assert "más de lo ofertado" in _texto(r)


# ---------------------------------------------------------------------------
# Recepciones
# ---------------------------------------------------------------------------

def test_no_baja_de_lo_recibido(client, db, oferta, m, pedido):
    lo = _linea_oferta(db, oferta, m["filtro"])
    a = _adjudicar(db, lo, pedido["filtro"], cantidad=3)
    _recibir(db, pedido["filtro"], m["filtro"], 2)
    r = _celda(client, lo, a, "cantidad_adjudicada", "1")
    assert r.status_code == 422
    assert "ya recibió 2" in _texto(r)
    assert _celda(client, lo, a, "cantidad_adjudicada", "2").status_code == 200
    # Subir siempre se puede.
    assert _celda(client, lo, a, "cantidad_adjudicada", "3").status_code == 200


def test_subir_se_puede_aunque_se_haya_recibido_de_mas(client, db, oferta, m, pedido):
    lo = _linea_oferta(db, oferta, m["filtro"])
    a = _adjudicar(db, lo, pedido["filtro"], cantidad=1)
    _recibir(db, pedido["filtro"], m["filtro"], 3)
    assert _celda(client, lo, a, "cantidad_adjudicada", "2").status_code == 200


def test_eliminar(client, db, oferta, m, pedido):
    lo = _linea_oferta(db, oferta, m["filtro"])
    a = _adjudicar(db, lo, pedido["filtro"], cantidad=3)
    r = client.post(f"/adjudicaciones/{a.adjudicacion_id}/eliminar_en_linea?{_q(lo)}")
    assert r.status_code == 200, _texto(r)
    assert Adjudicacion.query.count() == 0


def test_no_se_elimina_si_queda_por_debajo_de_lo_recibido(client, db, oferta, m, pedido, lange):
    lo = _linea_oferta(db, oferta, m["filtro"])
    a = _adjudicar(db, lo, pedido["filtro"], cantidad=2)
    _recibir(db, pedido["filtro"], m["filtro"], 1)
    html = _texto(_subgrilla(client, lo))
    assert f"/adjudicaciones/{a.adjudicacion_id}/eliminar_en_linea" not in html
    r = client.delete(f"/api/adjudicaciones/{a.adjudicacion_id}")
    assert r.status_code in (400, 409) and "recibido" in _texto(r)

    # Con otra adjudicación que cubre lo recibido, sí.
    otra = _doc(db, lange, numero="9677")
    lo2 = _linea_oferta(db, otra, m["filtro"])
    _adjudicar(db, lo2, pedido["filtro"], cantidad=1)
    assert client.delete(f"/api/adjudicaciones/{a.adjudicacion_id}").status_code in (200, 204)


# ---------------------------------------------------------------------------
# Alta rápida
# ---------------------------------------------------------------------------

@pytest.mark.parametrize("escrito", ["{n}/1", "{n} / 1", "{n}-1"])
def test_alta_por_numero_de_pedido_y_linea(client, db, oferta, m, pedido, escrito):
    lo = _linea_oferta(db, oferta, m["filtro"])
    r = _alta(client, lo, escrito.format(n=pedido["numero"]), "3")
    assert r.status_code == 200, _texto(r)
    a = Adjudicacion.query.one()
    assert a.pedido_linea_id == pedido["filtro"] and a.cantidad_adjudicada == 3
    # Sin aviso: es el mismo material.
    assert "aviso-fila" not in _texto(r)


def test_alta_sin_cantidad_queda_cotizada(client, db, oferta, m, pedido):
    lo = _linea_oferta(db, oferta, m["filtro"])
    assert _alta(client, lo, f"{pedido['numero']}/1").status_code == 200
    assert Adjudicacion.query.one().cantidad_adjudicada == 0


def test_alta_eligiendo_de_la_lista(client, db, oferta, m, pedido):
    lo = _linea_oferta(db, oferta, m["filtro"])
    etiqueta = db.session.get(PedidoLinea, pedido["filtro"]).nombre
    html = _texto(_subgrilla(client, lo))
    assert etiqueta in html  # sugerencia de la lista
    assert _alta(client, lo, etiqueta, "1").status_code == 200
    assert Adjudicacion.query.one().pedido_linea_id == pedido["filtro"]


def test_alta_linea_inexistente(client, db, oferta, m, pedido):
    lo = _linea_oferta(db, oferta, m["filtro"])
    r = _alta(client, lo, f"{pedido['numero']}/9", "1")
    assert r.status_code == 422
    assert f"No encontré la línea 9 del pedido {pedido['numero']}" in _texto(r)


def test_alta_linea_en_borrador(client, db, oferta, m):
    p = client.post("/api/pedidos", json={"fecha_pedido": "2026-11-27"}).get_json()
    client.post("/api/pedido_lineas", json={"pedido_id": p["pedido_id"], "material_id": m["filtro"].material_id,
                                            "cantidad": 3, "destino": "a_identificar"})
    lo = _linea_oferta(db, oferta, m["filtro"])
    r = _alta(client, lo, f"{p['numero']}/1", "1")
    assert r.status_code == 422 and "borrador" in _texto(r)
    # Tampoco por la API.
    lp = PedidoLinea.query.filter_by(pedido_id=p["pedido_id"]).one()
    r = client.post("/api/adjudicaciones", json={"documento_linea_id": lo.documento_linea_id,
                                                 "pedido_linea_id": lp.pedido_linea_id})
    assert r.status_code == 400 and "borrador" in _texto(r)


def test_alta_material_distinto_con_aviso(client, db, oferta, m, pedido):
    lo = _linea_oferta(db, oferta, m["otro"])
    r = _alta(client, lo, f"{pedido['numero']}/1", "3")
    assert r.status_code == 200, _texto(r)
    html = _texto(r)
    assert "aviso-fila" in html and "Se acepta como equivalente" in html
    assert Adjudicacion.query.one().cantidad_adjudicada == 3
    # El aviso no queda para la página siguiente.
    assert "Se acepta como equivalente" not in _texto(client.get(f"/documentos_proveedor/{oferta.documento_id}"))


def test_presentacion_del_generico_sin_aviso(client, db, oferta, m, pedido):
    lo = _linea_oferta(db, oferta, m["bidon"], cantidad=2)
    r = _alta(client, lo, f"{pedido['numero']}/2", "2")
    assert r.status_code == 200, _texto(r)
    assert "aviso-fila" not in _texto(r)
    db.session.expire_all()
    assert db.session.get(PedidoLinea, pedido["aceite"]).adjudicada == 40


def test_el_aviso_no_se_repite_al_editar_la_cantidad(client, db, oferta, m, pedido):
    lo = _linea_oferta(db, oferta, m["otro"])
    a = _adjudicar(db, lo, pedido["filtro"])
    r = _celda(client, lo, a, "cantidad_adjudicada", "2")
    assert r.status_code == 200 and "aviso-fila" not in _texto(r)


# ---------------------------------------------------------------------------
# Desde la línea de pedido
# ---------------------------------------------------------------------------

def test_pestana_de_la_linea_de_pedido_editable_sin_alta(client, db, oferta, m, pedido):
    lo = _linea_oferta(db, oferta, m["filtro"])
    a = _adjudicar(db, lo, pedido["filtro"])
    html = _texto(client.get(f"/pedido_lineas/{pedido['filtro']}?seccion=adjudicaciones"))
    assert f"/adjudicaciones/{a.adjudicacion_id}/celda/cantidad_adjudicada" in html
    assert 'id="alta-adjudicaciones' not in html
    r = client.post(f"/adjudicaciones/{a.adjudicacion_id}/celda/cantidad_adjudicada?pedido_linea_id={pedido['filtro']}",
                    data={"cantidad_adjudicada": "1"})
    assert r.status_code == 200, _texto(r)


def test_numero_de_pedido_con_guion(client, db, oferta, m, enviar):
    """Un número con guion («1104-A») se separa por el último guion o barra."""
    p = client.post("/api/pedidos", json={"fecha_pedido": "2026-11-27", "numero": "1104-A"}).get_json()
    client.post("/api/pedido_lineas", json={"pedido_id": p["pedido_id"], "material_id": m["filtro"].material_id,
                                            "cantidad": 3, "destino": "a_identificar"})
    enviar(p["pedido_id"])
    lo = _linea_oferta(db, oferta, m["filtro"])
    assert _alta(client, lo, "1104-A/1", "1").status_code == 200
    assert Pedido.query.filter_by(numero="1104-A").one().lineas[0].adjudicada == 1


# ---------------------------------------------------------------------------
# Validación del registry
# ---------------------------------------------------------------------------

def _con(overrides, entidad, **cambios):
    resultado = dict(overrides)
    resultado[entidad] = {**overrides[entidad], **cambios}
    return resultado


def test_subgrillas_si_de_algo_que_no_es_una_subgrilla():
    ov = _con(cargar_overrides(), "documento_lineas", subgrillas_si={"recepciones": lambda r: True})
    with pytest.raises(MetamodeloError, match="subgrillas_si: 'recepciones' no está en subgrillas"):
        construir_registry(ov)


def test_subgrillas_si_sin_funcion():
    ov = _con(cargar_overrides(), "documento_lineas", subgrillas_si={"adjudicaciones": True})
    with pytest.raises(MetamodeloError, match="la regla de 'adjudicaciones' no es una función"):
        construir_registry(ov)
