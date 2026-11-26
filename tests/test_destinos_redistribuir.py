"""
Fase 13, PR 13.4: destinos en la grilla y «Redistribuir».

  * Tipo de destino (decidido 26/11): completar el activo o el modelo lo define;
    la ubicación, solo si estaba «a identificar» (stock). Cambiar el tipo limpia
    el activo o el modelo que ya no corresponde; la ubicación, nunca. Si cambia a
    qué apunta el destino, sector imputado y cuenta se vuelven a sugerir.
  * Subgrilla: los destinos de cada línea se despliegan debajo de ella en la
    pestaña «Líneas» del pedido; lo que se cambia ahí devuelve la fila de la
    línea fuera de banda. En borrador se agregan y se sacan (menos el último).
  * «Redistribuir» (línea enviada): todos los destinos juntos, sin cambiar el
    total, todo o nada. Un destino con recepciones no se saca ni baja de lo
    recibido; si baja de su «comprada (corregida)», se limpia con aviso.
"""
import pytest

from app.crud.meta.registry import MetamodeloError, cargar_overrides, construir_registry
from app.models.activos_models import Activo, EstadoActivo
from app.models.auditoria_models import AuditLog
from app.models.documentos_models import DocumentoProveedor
from app.models.marcas_modelos_models import Marca, Modelo
from app.models.materiales_models import CategoriaMaterial, Material
from app.models.pedidos_models import PedidoLinea, PedidoLineaDestino
from app.models.recursos_models import Proveedor
from app.models.sectores_models import Sector
from app.models.ubicaciones_models import Ubicacion


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
def otro_sector(db, estado_sector_activo):
    return _guardar(db, Sector(nombre_sector="Molienda", centro_costo="CC-200",
                               estado_sector_id=estado_sector_activo.estado_sector_id))


@pytest.fixture
def activos(db, categorias_activo, sector, otro_sector):
    estado = EstadoActivo.query.first().estado_activo_id
    tractor = categorias_activo["Tractor"].categoria_activo_id
    return _guardar(
        db,
        Activo(numero_activo="T-1", descripcion="Tractor 1", categoria_activo_id=tractor,
               sector_id=sector.sector_id, estado_activo_id=estado),
        Activo(numero_activo="T-2", descripcion="Tractor 2", categoria_activo_id=tractor,
               sector_id=otro_sector.sector_id, estado_activo_id=estado),
    )


@pytest.fixture
def modelo(db, categorias_activo):
    marca = _guardar(db, Marca(nombre_marca="John Deere"))
    return _guardar(db, Modelo(nombre_modelo="5090E", marca_id=marca.marca_id,
                               categoria_activo_id=categorias_activo["Tractor"].categoria_activo_id))


@pytest.fixture
def pedido(client, sector):
    r = client.post("/api/pedidos", json={"referencia": "Service", "fecha_pedido": "2026-11-26",
                                          "sector_id": sector.sector_id})
    assert r.status_code == 201, r.get_json()
    return r.get_json()["pedido_id"]


def _linea(client, pedido, material, cantidad=4, **destino):
    destino = destino or {"destino": "a_identificar"}
    r = client.post("/api/pedido_lineas", json={"pedido_id": pedido, "material_id": material.material_id,
                                                "cantidad": cantidad, **destino})
    assert r.status_code == 201, r.get_json()
    return r.get_json()["pedido_linea_id"]


def _destinos(linea_id):
    return PedidoLineaDestino.query.filter_by(pedido_linea_id=linea_id).order_by(
        PedidoLineaDestino.pedido_linea_destino_id).all()


def _celda(client, d, campo, texto, vista="pedido_id"):
    """Lo que manda la celda (con pocas opciones, una FK es un <select>: va el id)."""
    url = f"/pedido_linea_destinos/{d.pedido_linea_destino_id}/celda/{campo}?pedido_linea_id={d.pedido_linea_id}"
    if vista:
        url += f"&vista_padre={vista}"
    return client.post(url, data={campo: texto})


def _subgrilla(client, linea_id, vista="pedido_id"):
    return client.get(f"/pedido_linea_destinos/subgrilla?pedido_linea_id={linea_id}&vista_padre={vista}")


def _url_redistribuir(linea_id, en_subgrilla=True):
    url = f"/pedido_lineas/{linea_id}/accion/redistribuir"
    return url + "?subgrilla=pedido_linea_destinos&vista_padre=pedido_id" if en_subgrilla else url


def _redistribuir(client, linea_id, filas, en_subgrilla=True):
    """filas: [(id o None, cantidad, destino)]."""
    data = {"id": [], "cantidad": [], "destino": []}
    for id_, cantidad, destino in filas:
        data["id"].append("" if id_ is None else str(id_))
        data["cantidad"].append(str(cantidad))
        data["destino"].append(destino)
    return client.post(_url_redistribuir(linea_id, en_subgrilla), data=data)


# ---------------------------------------------------------------------------
# Tipo de destino según el dato completado (completar_destino)
# ---------------------------------------------------------------------------

def test_completar_el_activo_lo_vuelve_destino_activo(client, pedido, material, activos, sector):
    linea = _linea(client, pedido, material)
    d = _destinos(linea)[0]
    assert d.destino == "a_identificar"
    r = _celda(client, d, "activo_id", str(activos[0].activo_id))
    assert r.status_code == 200, _texto(r)
    d = _destinos(linea)[0]
    assert d.destino == "activo" and d.activo_id == activos[0].activo_id
    assert d.sector_imputado_id == sector.sector_id


def test_completar_el_modelo_limpia_el_activo_y_conserva_la_ubicacion(client, pedido, material, activos,
                                                                      modelo, ubicacion):
    linea = _linea(client, pedido, material, destino="activo", activo_id=activos[0].activo_id,
                   ubicacion_id=ubicacion.ubicacion_id)
    d = _destinos(linea)[0]
    assert _celda(client, d, "modelo_id", str(modelo.modelo_id)).status_code == 200
    d = _destinos(linea)[0]
    assert (d.destino, d.activo_id, d.modelo_id) == ("modelo", None, modelo.modelo_id)
    assert d.ubicacion_id == ubicacion.ubicacion_id  # el taller que recibe


def test_la_ubicacion_vuelve_stock_solo_un_destino_a_identificar(client, pedido, material, activos, ubicacion):
    a_identificar = _destinos(_linea(client, pedido, material))[0]
    assert _celda(client, a_identificar, "ubicacion_id", str(ubicacion.ubicacion_id)).status_code == 200
    assert db_get(a_identificar).destino == "stock"

    del_activo = _destinos(_linea(client, pedido, material, destino="activo",
                                  activo_id=activos[0].activo_id))[0]
    assert _celda(client, del_activo, "ubicacion_id", str(ubicacion.ubicacion_id)).status_code == 200
    d = db_get(del_activo)
    assert d.destino == "activo" and d.activo_id == activos[0].activo_id and d.ubicacion_id == ubicacion.ubicacion_id


def db_get(d):
    from app.core.db import db

    db.session.expire_all()
    return db.session.get(PedidoLineaDestino, d.pedido_linea_destino_id)


def test_cambiar_el_tipo_limpia_lo_que_no_corresponde(client, pedido, material, activos, ubicacion):
    d = _destinos(_linea(client, pedido, material, destino="activo", activo_id=activos[0].activo_id,
                         ubicacion_id=ubicacion.ubicacion_id))[0]
    assert _celda(client, d, "destino", "gasto_general").status_code == 200
    d = db_get(d)
    assert (d.destino, d.activo_id, d.ubicacion_id) == ("gasto_general", None, ubicacion.ubicacion_id)


def test_cambiar_el_activo_vuelve_a_sugerir_el_sector(client, pedido, material, activos, sector, otro_sector):
    d = _destinos(_linea(client, pedido, material, destino="activo", activo_id=activos[0].activo_id))[0]
    assert d.sector_imputado_id == sector.sector_id
    assert _celda(client, d, "activo_id", str(activos[1].activo_id)).status_code == 200
    assert db_get(d).sector_imputado_id == otro_sector.sector_id


def test_cambiar_activo_y_sector_juntos_respeta_el_sector(client, pedido, material, activos, sector, otro_sector):
    d = _destinos(_linea(client, pedido, material, destino="activo", activo_id=activos[0].activo_id))[0]
    d.sector_imputado_id = otro_sector.sector_id
    from app.core.db import db
    db.session.commit()
    # El tractor 2 sugiere «Molienda», pero en la misma operación se eligió «Taller».
    r = client.patch(f"/api/pedido_linea_destinos/{d.pedido_linea_destino_id}",
                     json={"activo_id": activos[1].activo_id, "sector_imputado_id": sector.sector_id})
    assert r.status_code == 200, r.get_json()
    d = db_get(d)
    assert d.activo_id == activos[1].activo_id and d.sector_imputado_id == sector.sector_id


def test_formulario_que_reenvia_el_sector_sin_cambiarlo_lo_vuelve_a_sugerir(client, pedido, material, activos,
                                                                            otro_sector):
    d = _destinos(_linea(client, pedido, material, destino="activo", activo_id=activos[0].activo_id))[0]
    # La API con todos los campos (como el formulario): el sector viene igual que antes.
    r = client.patch(f"/api/pedido_linea_destinos/{d.pedido_linea_destino_id}",
                     json={"activo_id": activos[1].activo_id, "sector_imputado_id": d.sector_imputado_id,
                           "destino": "activo"})
    assert r.status_code == 200, r.get_json()
    assert db_get(d).sector_imputado_id == otro_sector.sector_id


def test_alta_rapida_de_la_linea_con_un_modelo(client, pedido, material, modelo):
    r = client.post(f"/pedido_lineas/alta_en_linea?pedido_id={pedido}",
                    data={"material": "RE504836", "cantidad": "2", "destino": "5090E"})
    assert r.status_code == 200, _texto(r)
    d = PedidoLineaDestino.query.one()
    assert d.destino == "modelo" and d.modelo_id == modelo.modelo_id


# ---------------------------------------------------------------------------
# Subgrilla
# ---------------------------------------------------------------------------

def test_la_fila_de_la_linea_tiene_el_boton_de_sus_destinos(client, pedido, material):
    linea = _linea(client, pedido, material)
    html = _texto(client.get(f"/pedidos/{pedido}?seccion=pedido_lineas"))
    assert f'data-subgrilla="sub-pedido_linea_destinos-{linea}"' in html
    assert f"/pedido_linea_destinos/subgrilla?vista_padre=pedido_id&amp;pedido_linea_id={linea}" in html
    assert "Destinos (1)" in html
    # También en el listado propio de las líneas.
    assert "vista_padre=listado" in _texto(client.get("/pedido_lineas"))


def test_subgrilla_en_borrador(client, pedido, material):
    linea = _linea(client, pedido, material)
    r = _subgrilla(client, linea)
    assert r.status_code == 200
    html = _texto(r)
    assert f'id="sub-pedido_linea_destinos-{linea}"' in html and 'class="sub-fila"' in html
    d = _destinos(linea)[0]
    assert f'id="fila-pedido_linea_destinos-{d.pedido_linea_destino_id}"' in html
    # Celdas editables, con la vista en la URL (para devolver la fila de la línea).
    assert f"/celda/cantidad?pedido_linea_id={linea}&amp;vista_padre=pedido_id" in html
    # Fila de alta con ids propios de esta subgrilla (puede haber varias abiertas).
    assert f'id="alta-pedido_linea_destinos-{linea}"' in html and "Agregar destino" in html
    assert "Redistribuir" not in html


def test_subgrilla_de_una_linea_enviada(client, pedido, material, enviar):
    linea = _linea(client, pedido, material)
    enviar(pedido)
    html = _texto(_subgrilla(client, linea))
    assert 'id="alta-pedido_linea_destinos' not in html  # no se agregan destinos sueltos
    assert f"/pedido_lineas/{linea}/accion/redistribuir?" in html and "Redistribuir…" in html
    assert "congelada" in html  # la cantidad


def test_subgrilla_sin_vista_o_de_otro_padre_es_404(client, pedido, material):
    linea = _linea(client, pedido, material)
    assert client.get(f"/pedido_linea_destinos/subgrilla?pedido_linea_id={linea}").status_code == 404
    assert client.get("/pedido_linea_destinos/subgrilla?vista_padre=pedido_id").status_code == 404
    assert _subgrilla(client, 999).status_code == 404


def test_editar_un_destino_devuelve_la_linea_fuera_de_banda(client, pedido, material):
    linea = _linea(client, pedido, material, cantidad=4)
    d = _destinos(linea)[0]
    r = _celda(client, d, "cantidad", "6")
    assert r.status_code == 200, _texto(r)
    html = _texto(r)
    assert f'id="fila-pedido_linea_destinos-{d.pedido_linea_destino_id}"' in html
    # La fila de la línea, fuera de banda y sin el foco (es de la fila del destino).
    i = html.index(f'id="fila-pedido_lineas-{linea}"')
    fila_linea = html[i:html.index("</tr>", i)]
    assert 'hx-swap-oob="true"' in html[i - 80:i + 200] and "data-foco" not in fila_linea[:200]
    assert db_linea(linea).solicitada == 6


def db_linea(linea_id):
    from app.core.db import db

    db.session.expire_all()
    return db.session.get(PedidoLinea, linea_id)


def test_editar_un_destino_desde_su_pestana_no_manda_la_linea(client, pedido, material):
    linea = _linea(client, pedido, material)
    d = _destinos(linea)[0]
    r = _celda(client, d, "cantidad", "6", vista=None)
    assert r.status_code == 200 and f"fila-pedido_lineas-{linea}" not in _texto(r)
    # La pestaña «Destinos» de la línea también es grilla, con su fila de alta.
    html = _texto(client.get(f"/pedido_lineas/{linea}?seccion=pedido_linea_destinos"))
    assert 'id="alta-pedido_linea_destinos"' in html and 'class="celda"' in html


def test_alta_de_un_destino_en_la_subgrilla(client, pedido, material, activos, auditoria):
    linea = _linea(client, pedido, material, cantidad=4)
    r = client.post(f"/pedido_linea_destinos/alta_en_linea?pedido_linea_id={linea}&vista_padre=pedido_id",
                    data={"cantidad": "2", "destino": "T-2"})
    assert r.status_code == 200, _texto(r)
    html = _texto(r)
    nuevo = _destinos(linea)[1]
    assert (nuevo.destino, nuevo.activo_id, nuevo.cantidad) == ("activo", activos[1].activo_id, 2)
    assert f'id="alta-pedido_linea_destinos-{linea}"' in html
    assert f'id="botones-pedido_linea_destinos-{linea}"' in html
    assert f'id="fila-pedido_lineas-{linea}" class="fila" hx-swap-oob="true"' in html
    assert db_linea(linea).solicitada == 6
    assert auditoria("pedido_linea_destinos")[-1].motivo_operacion == "Alta en línea"


def test_alta_de_un_destino_en_una_linea_enviada_se_rechaza(client, pedido, material, enviar):
    linea = _linea(client, pedido, material)
    enviar(pedido)
    r = client.post(f"/pedido_linea_destinos/alta_en_linea?pedido_linea_id={linea}&vista_padre=pedido_id",
                    data={"cantidad": "2", "destino": ""})
    assert r.status_code == 422 and "no se le agregan destinos sueltos" in _texto(r)


def test_eliminar_un_destino_desde_la_subgrilla(client, pedido, material, auditoria):
    linea = _linea(client, pedido, material, cantidad=4)
    client.post(f"/pedido_linea_destinos/alta_en_linea?pedido_linea_id={linea}&vista_padre=pedido_id",
                data={"cantidad": "1", "destino": ""})
    primero, segundo = _destinos(linea)
    r = client.post(f"/pedido_linea_destinos/{segundo.pedido_linea_destino_id}/eliminar_en_linea"
                    f"?pedido_linea_id={linea}&vista_padre=pedido_id")
    assert r.status_code == 200, _texto(r)
    html = _texto(r)
    assert "Se eliminó el destino." in html and f'id="sub-pedido_linea_destinos-{linea}"' in html
    assert f'id="fila-pedido_lineas-{linea}" class="fila" hx-swap-oob="true"' in html
    assert [d.pedido_linea_destino_id for d in _destinos(linea)] == [primero.pedido_linea_destino_id]
    assert auditoria("pedido_linea_destinos")[-1].motivo_operacion == "Eliminado en línea"
    # El último no se saca: para eso se elimina la línea.
    r = client.post(f"/pedido_linea_destinos/{primero.pedido_linea_destino_id}/eliminar_en_linea"
                    f"?pedido_linea_id={linea}&vista_padre=pedido_id")
    assert r.status_code == 422 and "es el único destino de la línea" in _texto(r)
    assert len(_destinos(linea)) == 1


def test_el_ultimo_destino_no_ofrece_eliminar(client, pedido, material):
    linea = _linea(client, pedido, material)
    html = _texto(_subgrilla(client, linea))
    assert "eliminar_en_linea" not in html
    # Tampoco por la API.
    d = _destinos(linea)[0]
    assert client.delete(f"/api/pedido_linea_destinos/{d.pedido_linea_destino_id}").status_code == 409


def test_eliminar_la_linea_borra_su_unico_destino(client, pedido, material):
    linea = _linea(client, pedido, material)
    assert client.delete(f"/api/pedido_lineas/{linea}").status_code in (200, 204)
    assert PedidoLineaDestino.query.count() == 0


def test_eliminar_en_linea_de_otra_linea_es_404(client, pedido, material):
    a, b = _linea(client, pedido, material), _linea(client, pedido, material)
    d = _destinos(a)[0]
    r = client.post(f"/pedido_linea_destinos/{d.pedido_linea_destino_id}/eliminar_en_linea"
                    f"?pedido_linea_id={b}&vista_padre=pedido_id")
    assert r.status_code == 404


# ---------------------------------------------------------------------------
# Redistribuir
# ---------------------------------------------------------------------------

@pytest.fixture
def enviada(client, pedido, material, activos, enviar):
    """Una línea enviada de 4: 3 al tractor 1 y 1 a identificar."""
    linea = _linea(client, pedido, material, cantidad=3, destino="activo", activo_id=activos[0].activo_id)
    r = client.post("/api/pedido_linea_destinos", json={"pedido_linea_id": linea, "cantidad": 1,
                                                        "destino": "a_identificar"})
    assert r.status_code == 201, r.get_json()
    enviar(pedido)
    return linea


def test_redistribuir_solo_en_lineas_enviadas(client, pedido, material):
    linea = _linea(client, pedido, material)
    assert client.get(_url_redistribuir(linea)).status_code == 404


def test_formulario_de_redistribuir_en_la_subgrilla(client, enviada):
    r = client.get(_url_redistribuir(enviada), headers={"HX-Request": "true"})
    assert r.status_code == 200
    html = _texto(r)
    assert f'id="sub-pedido_linea_destinos-{enviada}"' in html and 'class="form-filas"' in html
    assert 'value="T-1 — Tractor 1"' in html and 'data-total="4"' in html
    assert 'hx-post="/pedido_lineas/' in html and "+ Fila" in html


def test_redistribuir_cambia_altas_y_bajas_sin_cambiar_el_total(client, enviada, activos, ubicacion, auditoria,
                                                                 otro_sector):
    tractor, a_identificar = _destinos(enviada)
    # Se corrige a mano el sector del tractor 1: tiene que conservarse.
    tractor.sector_imputado_id = otro_sector.sector_id
    from app.core.db import db
    db.session.commit()

    r = _redistribuir(client, enviada, [
        (tractor.pedido_linea_destino_id, "2", "T-1 — Tractor 1"),  # baja a 2
        (a_identificar.pedido_linea_destino_id, "", ""),               # se saca
        (None, "1", "T-2"),                                            # nuevo
        (None, "1", "Galpón 1"),                                       # nuevo: stock
    ])
    assert r.status_code == 200, _texto(r)
    html = _texto(r)
    assert "destinos redistribuidos" in html
    assert f'id="fila-pedido_lineas-{enviada}" class="fila" hx-swap-oob="true"' in html
    destinos = _destinos(enviada)
    assert [(d.destino, d.cantidad) for d in destinos] == [("activo", 2), ("activo", 1), ("stock", 1)]
    assert destinos[0].pedido_linea_destino_id == tractor.pedido_linea_destino_id
    assert destinos[0].sector_imputado_id == otro_sector.sector_id
    assert destinos[2].ubicacion_id == ubicacion.ubicacion_id
    assert db_linea(enviada).solicitada == 4
    logs = auditoria("pedido_linea_destinos")
    assert {log.motivo_operacion for log in logs[-4:]} == {"Redistribución"}


def test_el_total_tiene_que_seguir_igual(client, enviada):
    tractor, a_identificar = _destinos(enviada)
    r = _redistribuir(client, enviada, [(tractor.pedido_linea_destino_id, "3", "T-1"),
                                        (a_identificar.pedido_linea_destino_id, "2", "")])
    assert r.status_code == 422
    html = _texto(r)
    assert "El total tiene que seguir siendo 4 (quedó 5)" in html
    # Lo escrito queda en el formulario; no se cambió nada.
    assert 'value="2"' in html and 'class="form-filas"' in html
    assert [d.cantidad for d in _destinos(enviada)] == [3, 1]


def test_tiene_que_quedar_un_destino(client, enviada):
    r = _redistribuir(client, enviada, [(d.pedido_linea_destino_id, "", "") for d in _destinos(enviada)])
    assert r.status_code == 422 and "Tiene que quedar al menos un destino" in _texto(r)


def test_error_de_una_fila_va_en_la_fila(client, enviada):
    tractor, a_identificar = _destinos(enviada)
    r = _redistribuir(client, enviada, [(tractor.pedido_linea_destino_id, "3", "Cosechadora"),
                                        (a_identificar.pedido_linea_destino_id, "1", "")])
    assert r.status_code == 422
    html = _texto(r)
    assert "No encontré «Cosechadora»" in html and "fila-accion con-error" in html


def test_cambiar_a_que_apunta_un_destino(client, enviada, activos, otro_sector, ubicacion):
    tractor, a_identificar = _destinos(enviada)
    r = _redistribuir(client, enviada, [(tractor.pedido_linea_destino_id, "3", "T-2"),
                                        (a_identificar.pedido_linea_destino_id, "1", "Galpón 1")])
    assert r.status_code == 200, _texto(r)
    tractor, otro = _destinos(enviada)
    assert tractor.activo_id == activos[1].activo_id and tractor.sector_imputado_id == otro_sector.sector_id
    assert (otro.destino, otro.ubicacion_id) == ("stock", ubicacion.ubicacion_id)


def test_un_gasto_general_que_sigue_igual_conserva_su_tipo(client, pedido, material, ubicacion, enviar):
    linea = _linea(client, pedido, material, cantidad=2, destino="gasto_general",
                   ubicacion_id=ubicacion.ubicacion_id)
    enviar(pedido)
    d = _destinos(linea)[0]
    r = _redistribuir(client, linea, [(d.pedido_linea_destino_id, "1", "Galpón 1"), (None, "1", "")])
    assert r.status_code == 200, _texto(r)
    gasto, nuevo = _destinos(linea)
    assert (gasto.destino, gasto.ubicacion_id, gasto.cantidad) == ("gasto_general", ubicacion.ubicacion_id, 1)
    assert nuevo.destino == "a_identificar"


def test_redistribuir_desde_la_pagina_de_la_accion(client, enviada):
    r = client.get(_url_redistribuir(enviada, en_subgrilla=False))
    assert r.status_code == 200 and 'class="form-filas"' in _texto(r) and "hx-post" not in _texto(r)
    tractor, a_identificar = _destinos(enviada)
    r = _redistribuir(client, enviada, [(tractor.pedido_linea_destino_id, "2", "T-1"),
                                        (a_identificar.pedido_linea_destino_id, "2", "")], en_subgrilla=False)
    assert r.status_code == 302
    assert "seccion=pedido_linea_destinos" in r.headers["Location"]
    assert [d.cantidad for d in _destinos(enviada)] == [2, 2]
    # El botón está en la pestaña «Destinos» de la línea.
    html = _texto(client.get(f"/pedido_lineas/{enviada}?seccion=pedido_linea_destinos"))
    assert f"/pedido_lineas/{enviada}/accion/redistribuir" in html


# --- con compras y recepciones ----------------------------------------------

@pytest.fixture
def comprada(client, db, enviada, material):
    """La línea enviada (3 + 1) con las 4 compradas."""
    p = _guardar(db, Proveedor(razon_social="Lange SA"))
    doc = client.post("/api/documentos_proveedor", json={"tipo": "oferta", "proveedor_id": p.recurso_id,
                                                         "numero": "9676", "moneda": "ARS"}).get_json()
    lo = client.post("/api/documento_lineas", json={"documento_id": doc["documento_id"], "cantidad": 4,
                                                    "precio_unitario": 100,
                                                    "material_id": material.material_id}).get_json()
    r = client.post("/api/adjudicaciones", json={"documento_linea_id": lo["documento_linea_id"],
                                                 "pedido_linea_id": enviada, "cantidad_adjudicada": 4})
    assert r.status_code == 201, r.get_json()
    return enviada


def _recibir(client, destino, cantidad):
    r = client.post("/api/recepciones", json={"pedido_linea_destino_id": destino.pedido_linea_destino_id,
                                              "fecha": "2026-11-25", "cantidad": cantidad})
    assert r.status_code == 201, r.get_json()


def test_un_destino_con_recepciones_no_baja_de_lo_recibido(client, comprada):
    tractor, a_identificar = _destinos(comprada)
    _recibir(client, tractor, 2)
    r = _redistribuir(client, comprada, [(tractor.pedido_linea_destino_id, "1", "T-1"),
                                         (a_identificar.pedido_linea_destino_id, "3", "")])
    assert r.status_code == 422 and "Ya se recibieron 2: la cantidad no puede bajar de eso" in _texto(r)
    # Puede bajar hasta lo recibido.
    r = _redistribuir(client, comprada, [(tractor.pedido_linea_destino_id, "2", "T-1"),
                                         (a_identificar.pedido_linea_destino_id, "2", "")])
    assert r.status_code == 200, _texto(r)


def test_un_destino_con_recepciones_no_se_saca(client, comprada):
    tractor, a_identificar = _destinos(comprada)
    _recibir(client, a_identificar, 1)
    r = _redistribuir(client, comprada, [(tractor.pedido_linea_destino_id, "4", "T-1"),
                                         (a_identificar.pedido_linea_destino_id, "", "")])
    assert r.status_code == 422 and "este destino no se saca" in _texto(r)
    # Tampoco si se quita la fila del formulario.
    r = _redistribuir(client, comprada, [(tractor.pedido_linea_destino_id, "4", "T-1")])
    assert r.status_code == 422 and "no se saca" in _texto(r)
    assert len(_destinos(comprada)) == 2


def test_bajar_de_la_comprada_corregida_la_limpia_con_aviso(client, db, comprada):
    tractor, a_identificar = _destinos(comprada)
    tractor.comprada_corregida = 3
    db.session.commit()
    r = _redistribuir(client, comprada, [(tractor.pedido_linea_destino_id, "2", "T-1"),
                                         (a_identificar.pedido_linea_destino_id, "2", "")])
    assert r.status_code == 200, _texto(r)
    assert "Se limpió 1 «comprada (corregida)»" in _texto(r)
    tractor = _destinos(comprada)[0]
    assert tractor.comprada_corregida is None and tractor.comprada == 2  # reparto proporcional


def test_sacar_un_destino_con_comprada_corregida_avisa(client, db, comprada):
    tractor, a_identificar = _destinos(comprada)
    a_identificar.comprada_corregida = 1
    db.session.commit()
    r = _redistribuir(client, comprada, [(tractor.pedido_linea_destino_id, "4", "T-1"),
                                         (a_identificar.pedido_linea_destino_id, "", "")])
    assert r.status_code == 200, _texto(r)
    assert "Se limpió 1 «comprada (corregida)»" in _texto(r)


def test_sin_redistribuir_en_lineas_anuladas(client, db, enviada):
    linea = db_linea(enviada)
    linea.estado = "anulado"
    db.session.commit()
    assert client.get(_url_redistribuir(enviada)).status_code == 404


# ---------------------------------------------------------------------------
# Validación del registry
# ---------------------------------------------------------------------------

def _con(overrides, entidad, **cambios):
    resultado = dict(overrides)
    resultado[entidad] = {**overrides[entidad], **cambios}
    return resultado


def test_subgrilla_de_algo_que_no_es_un_hijo():
    ov = _con(cargar_overrides(), "pedido_lineas", subgrillas=["sectores"])
    with pytest.raises(MetamodeloError, match="'sectores' no es una subentidad de 'pedido_lineas'"):
        construir_registry(ov)


def test_subgrilla_de_un_hijo_sin_grilla():
    ov = cargar_overrides()
    ov = _con(ov, "pedido_linea_destinos", edicion_en_linea=[], alta_en_linea=[])
    with pytest.raises(MetamodeloError, match="'pedido_linea_destinos' no tiene edicion_en_linea"):
        construir_registry(ov)


def test_acciones_de_filas_validadas():
    ov = cargar_overrides()
    accion = next(a for a in ov["pedido_lineas"]["acciones"] if a["id"] == "redistribuir")
    mala = {**accion, "filas": {**accion["filas"], "entidad": "sectores"}}
    otras = [a for a in ov["pedido_lineas"]["acciones"] if a["id"] != "redistribuir"]
    with pytest.raises(MetamodeloError, match="'sectores' no es una subentidad"):
        construir_registry(_con(ov, "pedido_lineas", acciones=[*otras, mala]))
    sin_celdas = {**accion, "filas": {**accion["filas"], "celdas": []}}
    with pytest.raises(MetamodeloError, match="al menos una celda"):
        construir_registry(_con(ov, "pedido_lineas", acciones=[*otras, sin_celdas]))
