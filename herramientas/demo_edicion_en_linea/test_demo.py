"""Pruebas de las rutas de la demo (cliente de pruebas de Flask, sin navegador)."""
import pytest

import demo

H = {"HX-Request": "true"}


@pytest.fixture
def c():
    demo.reiniciar_datos()
    demo.app.config["TESTING"] = True
    return demo.app.test_client()


def test_pagina(c):
    r = c.get("/")
    assert r.status_code == 200
    html = r.get_data(as_text=True)
    assert 'id="linea-1"' in html and 'id="fila-nueva"' in html
    assert "RE504836 — Filtro de aceite" in html


def test_abrir_celda_en_edicion(c):
    r = c.get("/lineas/1/celda/nro_oc", headers=H)
    assert r.status_code == 200
    html = r.get_data(as_text=True)
    assert 'class="celda editando' in html and 'hx-post="/lineas/1/celda/nro_oc"' in html


def test_columna_calculada_no_se_edita(c):
    assert c.get("/lineas/1/celda/solicitada", headers=H).status_code == 404


def test_guardar_oc_normaliza_y_devuelve_fila(c):
    r = c.post("/lineas/1/celda/nro_oc", data={"valor": " oc 4500 12 "}, headers=H)
    assert r.status_code == 200
    html = r.get_data(as_text=True)
    assert html.lstrip().startswith("<tr") and 'data-foco="nro_oc"' in html
    assert "OC450012" in html
    assert demo.LINEAS[1].nro_oc == "OC450012"


def test_material_cambia_la_unidad(c):
    r = c.post("/lineas/3/celda/material_id", data={"valor": "TY26402 — Aceite Hy-Gard (tambor 208 l)"}, headers=H)
    assert r.status_code == 200
    assert demo.LINEAS[3].unidad == "envases"
    # El destino sin cuenta toma la del material.
    assert demo.LINEAS[3].destinos[0].cuenta_id == 11


def test_error_deja_la_celda_en_edicion(c):
    # Sin material ni descripción no se puede.
    r = c.post("/lineas/3/celda/descripcion", data={"valor": ""}, headers=H)
    assert r.status_code == 422
    html = r.get_data(as_text=True)
    assert "con-error" in html and "Elegí el material" in html
    assert demo.LINEAS[3].descripcion  # no cambió


def test_material_inexistente(c):
    r = c.post("/lineas/3/celda/material_id", data={"valor": "XXX"}, headers=H)
    assert r.status_code == 422 and "No encontré" in r.get_data(as_text=True)


def test_destino_actualiza_la_linea_fuera_de_banda(c):
    d = demo.LINEAS[3].destinos[0]
    r = c.post(f"/destinos/{d.id}/celda/cantidad", data={"valor": "10"}, headers=H)
    assert r.status_code == 200
    html = r.get_data(as_text=True)
    assert f'id="destino-{d.id}"' in html
    assert 'id="linea-3"' in html and 'hx-swap-oob="true"' in html
    assert demo.LINEAS[3].solicitada == 10


def test_completar_activo_define_el_tipo_y_sugiere(c):
    d = demo.LINEAS[3].destinos[0]  # a identificar
    assert d.a_revisar
    r = c.post(f"/destinos/{d.id}/celda/activo_id", data={"valor": "Mixer 1"}, headers=H)
    assert r.status_code == 200
    assert d.destino == "activo" and d.activo_id == 3
    assert d.cuenta_id == 10 and not d.a_revisar


def test_destino_activo_sin_activo(c):
    d = demo.LINEAS[3].destinos[0]
    r = c.post(f"/destinos/{d.id}/celda/destino", data={"valor": "activo"}, headers=H)
    assert r.status_code == 422 and "necesita el activo" in r.get_data(as_text=True)
    assert d.destino == "a_identificar"


def test_alta_de_linea(c):
    r = c.post("/lineas", data={"material": "AR26003", "cantidad": "3"}, headers=H)
    assert r.status_code == 200
    html = r.get_data(as_text=True)
    assert 'id="linea-4"' in html and 'id="fila-nueva"' in html and "autofocus" in html
    assert demo.LINEAS[4].material_id == 2 and demo.LINEAS[4].solicitada == 3


def test_alta_sin_cantidad(c):
    r = c.post("/lineas", data={"material": "AR26003", "cantidad": ""}, headers=H)
    assert r.status_code == 422 and len(demo.LINEAS) == 3


def test_alta_con_texto_libre_queda_como_descripcion(c):
    c.post("/lineas", data={"material": "Cinta aisladora", "cantidad": "2"}, headers=H)
    l = demo.LINEAS[4]
    assert l.material_id is None and l.descripcion == "Cinta aisladora"


def test_pegado_vista_previa_y_confirmacion(c):
    texto = "RE504836\t2\tTractor 2\nCinta aisladora\t5\t\nAR26003\t\tMixer 1\nBUL-M12\t20\tGalpón 4\n"
    r = c.post("/pegar", data={"texto": texto}, headers=H)
    html = r.get_data(as_text=True)
    assert "Agregar 3 líneas" in html and "invalida" in html
    assert "material sin identificar" in html and "Galpón 4" in html
    assert len(demo.LINEAS) == 3  # nada guardado todavía

    r = c.post("/pegar/confirmar", data={"texto": texto}, headers=H)
    assert r.status_code == 200 and "Se agregaron 3 líneas" in r.get_data(as_text=True)
    assert len(demo.LINEAS) == 6
    assert demo.LINEAS[4].destinos[0].activo_id == 2
    assert demo.LINEAS[6].destinos[0].destino == "a_identificar"


def test_destinos_y_alta_de_destino(c):
    r = c.get("/lineas/3/destinos", headers=H)
    assert r.status_code == 200 and "Agregar destino" in r.get_data(as_text=True)
    r = c.post("/lineas/3/destinos", data={"cantidad": "1"}, headers=H)
    assert r.status_code == 200 and len(demo.LINEAS[3].destinos) == 2
    assert 'hx-swap-oob="true"' in r.get_data(as_text=True)


# --- Borrador y envío a Compras ------------------------------------------

def test_linea_enviada_tiene_material_y_cantidades_congeladas(c):
    assert c.get("/lineas/1/celda/material_id", headers=H).status_code == 404
    assert c.post("/lineas/1/celda/material_id", data={"valor": "AR26003"}, headers=H).status_code == 404
    d = demo.LINEAS[1].destinos[0]
    assert c.get(f"/destinos/{d.id}/celda/cantidad", headers=H).status_code == 404
    assert c.post("/lineas/1/destinos", data={"cantidad": "1"}, headers=H).status_code == 404
    html = c.get("/lineas/1/destinos", headers=H).get_data(as_text=True)
    assert "Redistribuir" in html and "Agregar destino" not in html


def test_linea_enviada_sigue_con_la_imputacion_editable(c):
    d = demo.LINEAS[1].destinos[0]
    r = c.post(f"/destinos/{d.id}/celda/activo_id", data={"valor": "Tractor 2"}, headers=H)
    assert r.status_code == 200 and d.activo_id == 2


def test_borrador_edita_todo(c):
    assert c.get("/lineas/3/celda/material_id", headers=H).status_code == 200
    # El estado de seguimiento es de Compras: en borrador no se edita.
    assert c.get("/lineas/3/celda/estado", headers=H).status_code == 404


def test_eliminar_linea_en_borrador(c):
    r = c.delete("/lineas/3", headers=H)
    assert r.status_code == 200 and 3 not in demo.LINEAS
    html = r.get_data(as_text=True)
    assert 'id="sub-3" hx-swap-oob="delete"' in html and 'id="estado-pedido"' in html


def test_linea_enviada_no_se_elimina(c):
    r = c.delete("/lineas/1", headers=H)
    assert r.status_code == 422 and r.headers["HX-Reswap"] == "none"
    assert 1 in demo.LINEAS and "anulala" in r.get_data(as_text=True)


def test_eliminar_destino(c):
    l = demo.LINEAS[3]
    c.post("/lineas/3/destinos", data={"cantidad": "2"}, headers=H)
    d = l.destinos[0]
    assert c.delete(f"/destinos/{d.id}", headers=H).status_code == 200 and len(l.destinos) == 1
    r = c.delete(f"/destinos/{l.destinos[0].id}", headers=H)
    assert r.status_code == 422 and "único destino" in r.get_data(as_text=True)


def test_enviar_a_compras(c):
    assert demo.estado_pedido()["sin_enviar"] == 1
    r = c.post("/enviar", headers=H)
    assert "Se enviaron 1 línea a Compras" in r.get_data(as_text=True)
    assert not demo.LINEAS[3].borrador and demo.estado_pedido()["texto"] == "Enviado a Compras"
    # Lo que se agrega después queda en borrador hasta el próximo envío.
    c.post("/lineas", data={"material": "AR26003", "cantidad": "1"}, headers=H)
    assert demo.LINEAS[4].borrador and "1 línea sin enviar" in demo.estado_pedido()["texto"]


def test_anular_linea_sin_compras(c):
    r = c.post("/lineas/2/anular", data={"motivo_id": "", "cantidad": ""}, headers=H)
    assert r.status_code == 422 and "motivo" in r.get_data(as_text=True)
    r = c.post("/lineas/2/anular", data={"motivo_id": "3", "cantidad": ""}, headers=H)
    assert r.status_code == 200 and demo.LINEAS[2].anulada
    assert "Línea 2 anulada" in r.get_data(as_text=True)


def test_linea_con_compras_no_se_anula_entera(c):
    r = c.post("/lineas/1/anular", data={"motivo_id": "2", "cantidad": ""}, headers=H)
    assert r.status_code == 422 and "no se puede anular entera" in r.get_data(as_text=True)
    r = c.post("/lineas/1/anular", data={"motivo_id": "2", "cantidad": "3"}, headers=H)
    assert r.status_code == 422 and "hasta 2" in r.get_data(as_text=True)
    r = c.post("/lineas/1/anular", data={"motivo_id": "2", "cantidad": "2"}, headers=H)
    assert r.status_code == 200 and demo.LINEAS[1].cantidad_cancelada == 2
    assert demo.LINEAS[1].pendiente_comprar == 0


def test_borrador_no_se_anula(c):
    r = c.post("/lineas/3/anular", data={"motivo_id": "1", "cantidad": ""}, headers=H)
    assert r.status_code == 422 and "eliminala" in r.get_data(as_text=True)


def _redistribuir(c, filas):
    data = {"id": [], "cantidad": [], "activo": [], "ubicacion": []}
    for f in filas:
        for k in data:
            data[k].append(f.get(k, ""))
    return c.post("/lineas/1/redistribuir", data=data, headers=H)


def test_redistribuir_entre_activos_y_talleres(c):
    d1, d2 = demo.LINEAS[1].destinos
    r = _redistribuir(c, [
        {"id": str(d1.id), "cantidad": "3", "activo": "Tractor 1"},
        {"id": str(d2.id), "cantidad": "2", "activo": "Mixer 1"},
        {"cantidad": "1", "ubicacion": "Pañol feedlot"},
    ])
    assert r.status_code == 200, r.get_data(as_text=True)
    l = demo.LINEAS[1]
    assert [d.cantidad for d in l.destinos] == [3, 2, 1] and l.solicitada == 6
    assert l.destinos[2].destino == "stock" and l.destinos[2].sector_id == 2
    assert "Destinos redistribuidos" in r.get_data(as_text=True)


def test_redistribuir_no_cambia_el_total(c):
    d1, d2 = demo.LINEAS[1].destinos
    r = _redistribuir(c, [{"id": str(d1.id), "cantidad": "5", "activo": "Tractor 1"},
                          {"id": str(d2.id), "cantidad": "2", "activo": "Mixer 1"}])
    assert r.status_code == 422 and "seguir siendo 6" in r.get_data(as_text=True)
    assert [d.cantidad for d in demo.LINEAS[1].destinos] == [4, 2]  # no cambió nada


def test_redistribuir_sacando_un_destino(c):
    d1, _ = demo.LINEAS[1].destinos
    r = _redistribuir(c, [{"id": str(d1.id), "cantidad": "6", "activo": "Tractor 1"}])
    assert r.status_code == 200 and len(demo.LINEAS[1].destinos) == 1


def test_redistribuir_solo_en_lineas_enviadas(c):
    assert c.get("/lineas/3/redistribuir", headers=H).status_code == 404
    assert c.get("/lineas/1/redistribuir", headers=H).status_code == 200
