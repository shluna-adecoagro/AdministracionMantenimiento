"""
Fase 13, PR 13.2: borrador y envío a Compras.

La línea de pedido nace en borrador; «Enviar a Compras» (acción del pedido) pone
`enviada_en`. Las reglas (`editable_si`, `eliminable_si`, `creable_si` en la
spec) las aplica el servicio: valen en la grilla, el formulario, la API y la
importación CSV. Ver «Borrador y envío a Compras» en diseno_tablas_operativas.md.
"""
from datetime import datetime

import pytest

from app.crud.entidades import REGISTRY
from app.crud.intercambio.csv_entidades import exportar, importar
from app.crud.meta.registry import cargar_overrides, construir_spec
from app.models.auditoria_models import AuditLog
from app.models.documentos_models import DocumentoProveedor
from app.models.materiales_models import CategoriaMaterial, Material
from app.models.motivos_models import MotivoOperacion
from app.models.pedidos_models import Pedido, PedidoLinea, PedidoLineaDestino
from app.models.recursos_models import Proveedor


def _guardar(db, *objetos):
    db.session.add_all(objetos)
    db.session.commit()
    return objetos[0] if len(objetos) == 1 else objetos


def _errores(r):
    return r.get_json()["errors"]


def _texto(r):
    return r.get_data(as_text=True)


@pytest.fixture
def m(db):
    cat = CategoriaMaterial.query.first().categoria_material_id
    filtro, correa = _guardar(db, Material(codigo="RE504836", descripcion="Filtro de aceite", categoria_material_id=cat),
                              Material(codigo="CO-1", descripcion="Correa", categoria_material_id=cat))
    return {"filtro": filtro, "correa": correa}


@pytest.fixture
def pedido(client):
    r = client.post("/api/pedidos", json={"referencia": "Service", "fecha_pedido": "2026-11-23"})
    assert r.status_code == 201, r.get_json()
    return Pedido.query.one()


def _linea(client, pedido, **datos):
    datos = {"cantidad": 3, "destino": "a_identificar", **datos}
    r = client.post("/api/pedido_lineas", json={"pedido_id": pedido.pedido_id, **datos})
    assert r.status_code == 201, r.get_json()
    return r.get_json()["pedido_linea_id"]


def _api(client, linea_id):
    return client.get(f"/api/pedido_lineas/{linea_id}").get_json()


def _patch(client, linea_id, **datos):
    return client.patch(f"/api/pedido_lineas/{linea_id}", json=datos)


def _motivo(tipo="ANULACION"):
    return MotivoOperacion.query.filter_by(tipo_operacion=tipo).first().motivo_operacion_id


def _destino(linea_id):
    return PedidoLineaDestino.query.filter_by(pedido_linea_id=linea_id).first()


def _accion_enviar(pedido):
    return f"/pedidos/{pedido.pedido_id}/accion/enviar_a_compras"


def _accion_anular(linea_id, **args):
    query = "&".join(f"{k}={v}" for k, v in args.items())
    return f"/pedido_lineas/{linea_id}/accion/anular_o_cancelar" + (f"?{query}" if query else "")


# ---------------------------------------------------------------------------
# Enviar a Compras
# ---------------------------------------------------------------------------

def test_la_linea_nace_en_borrador(client, pedido, m):
    linea = _api(client, _linea(client, pedido, material_id=m["filtro"].material_id))
    assert linea["enviada_en"] is None and linea["estado_visible"] == "Borrador"
    # enviada_en no se recibe por la API: la pone la acción.
    r = client.post("/api/pedido_lineas", json={"pedido_id": pedido.pedido_id, "descripcion": "Correa",
                                                "cantidad": 1, "destino": "a_identificar",
                                                "enviada_en": "2026-11-20T10:00:00"})
    assert r.status_code == 400 or r.get_json()["enviada_en"] is None


def test_enviar_a_compras(client, pedido, m, enviar):
    a = _linea(client, pedido, material_id=m["filtro"].material_id)
    html = _texto(client.get(f"/pedidos/{pedido.pedido_id}?seccion=pedido_lineas"))
    assert "Enviar a Compras" in html

    r = client.post(_accion_enviar(pedido), follow_redirects=True)
    assert "Se envió 1 línea a Compras." in _texto(r)
    assert _api(client, a)["estado_visible"] == "Solicitado"
    enviada = db_linea(a).enviada_en
    assert enviada is not None
    log = AuditLog.query.filter_by(TablaAfectada="pedido_lineas", motivo_operacion="Enviar a Compras").one()
    assert log.EstadoActual["enviada_en"]

    # Sin líneas en borrador, el botón no se muestra (y la acción no está disponible).
    html = _texto(client.get(f"/pedidos/{pedido.pedido_id}?seccion=pedido_lineas"))
    assert "Enviar a Compras" not in html
    assert client.post(_accion_enviar(pedido)).status_code == 404

    # Una línea agregada después queda en borrador; el mismo botón la envía, y la
    # ya enviada conserva su fecha.
    b = _linea(client, pedido, descripcion="Correa")
    assert db_linea(b).enviada_en is None
    enviar(pedido.pedido_id)
    assert db_linea(b).enviada_en is not None and db_linea(a).enviada_en == enviada


def db_linea(linea_id):
    from app.core.db import db

    db.session.expire_all()
    return db.session.get(PedidoLinea, linea_id)


def test_enviar_avisa_los_destinos_a_revisar(client, pedido, m):
    _linea(client, pedido, material_id=m["filtro"].material_id)  # destino «a identificar»
    r = client.post(_accion_enviar(pedido), follow_redirects=True)
    assert "1 línea tiene destinos a revisar" in _texto(r)
    assert PedidoLinea.query.one().enviada_en is not None  # se envía igual


def test_no_se_envian_las_anuladas(client, pedido, m, db):
    a = _linea(client, pedido, material_id=m["filtro"].material_id)
    # Una línea anulada en borrador solo puede venir de antes (o del histórico).
    linea = db.session.get(PedidoLinea, a)
    linea.estado, linea.motivo_operacion_id = "anulado", _motivo()
    db.session.commit()
    assert client.post(_accion_enviar(pedido)).status_code == 404


# ---------------------------------------------------------------------------
# Línea enviada: qué queda congelado
# ---------------------------------------------------------------------------

@pytest.fixture
def enviada(client, pedido, m, enviar):
    linea_id = _linea(client, pedido, material_id=m["filtro"].material_id, descripcion="Filtro")
    enviar(pedido.pedido_id)
    return linea_id


def test_material_y_descripcion_congelados(client, enviada, m):
    r = _patch(client, enviada, material_id=m["correa"].material_id)
    assert r.status_code == 400
    assert _errores(r)["material_id"] == ("Material no se puede cambiar: la línea ya se envió a Compras "
                                          "(solo se puede completar si está vacío).")
    r = _patch(client, enviada, descripcion="Otra cosa")
    assert r.status_code == 400 and "ya se envió a Compras" in _errores(r)["descripcion"]
    # Mandar el mismo valor no es un cambio.
    assert _patch(client, enviada, material_id=m["filtro"].material_id, descripcion="Filtro").status_code == 200


def test_material_vacio_se_puede_completar(client, pedido, m, enviar):
    linea = _linea(client, pedido, descripcion="Bolillero 32217")
    enviar(pedido.pedido_id)
    r = _patch(client, linea, material_id=m["filtro"].material_id)
    assert r.status_code == 200, r.get_json()
    # Ya identificado, no se cambia.
    assert _patch(client, linea, material_id=m["correa"].material_id).status_code == 400


def test_cantidades_y_destinos_congelados(client, enviada):
    d = _destino(enviada)
    url = f"/api/pedido_linea_destinos/{d.pedido_linea_destino_id}"
    r = client.patch(url, json={"cantidad": 5})
    assert r.status_code == 400 and "ya se envió a Compras" in _errores(r)["cantidad"]
    r = client.post("/api/pedido_linea_destinos", json={"pedido_linea_id": enviada, "cantidad": 1,
                                                        "destino": "gasto_general"})
    assert r.status_code == 400 and "no se le agregan destinos sueltos" in _errores(r)["_general"]
    r = client.delete(url)
    assert r.status_code == 409 and "no se sacan destinos sueltos" in r.get_json()["message"]


def test_la_imputacion_sigue_editable(client, enviada, sector, ubicacion):
    d = _destino(enviada)
    r = client.patch(f"/api/pedido_linea_destinos/{d.pedido_linea_destino_id}",
                     json={"destino": "stock", "ubicacion_id": ubicacion.ubicacion_id,
                           "sector_imputado_id": sector.sector_id})
    assert r.status_code == 200, r.get_json()


def test_la_enviada_no_se_elimina(client, pedido, enviada):
    r = client.delete(f"/api/pedido_lineas/{enviada}")
    assert r.status_code == 409 and "anulala o cancelá una parte" in r.get_json()["message"]
    # En la web: sin botón, y la confirmación explica por qué.
    assert "btn-eliminar" not in _texto(client.get(f"/pedido_lineas/{enviada}"))
    assert "anulala o cancelá una parte" in _texto(client.get(f"/pedido_lineas/{enviada}/confirmar_eliminar"))
    # El pedido con líneas enviadas tampoco.
    r = client.delete(f"/api/pedidos/{pedido.pedido_id}")
    assert r.status_code == 409 and "tiene 1 línea enviada a Compras" in r.get_json()["message"]


def test_en_borrador_se_elimina(client, pedido, m, auditoria):
    linea = _linea(client, pedido, material_id=m["filtro"].material_id)
    assert "btn-eliminar" in _texto(client.get(f"/pedido_lineas/{linea}"))
    assert client.delete(f"/api/pedido_lineas/{linea}").status_code == 200
    assert PedidoLineaDestino.query.count() == 0
    assert [log.TipoDeCambio for log in auditoria("pedido_lineas")][-1] == "DELETE"
    # Un pedido todo en borrador sí se borra.
    assert client.delete(f"/api/pedidos/{pedido.pedido_id}").status_code == 200


def test_en_borrador_el_seguimiento_no_se_edita(client, pedido, m):
    linea = _linea(client, pedido, material_id=m["filtro"].material_id)
    r = _patch(client, linea, estado="en_cotizacion")
    assert r.status_code == 400 and "en borrador" in _errores(r)["estado"]
    r = _patch(client, linea, nro_oc="4500")
    assert r.status_code == 400 and "en borrador" in _errores(r)["nro_oc"]
    # Tampoco se anula ni se cancela: se elimina o se cambia la cantidad.
    r = _patch(client, linea, cantidad_cancelada=1, motivo_operacion_id=_motivo())
    assert r.status_code == 400 and "en borrador" in _errores(r)["cantidad_cancelada"]


def test_anular_en_borrador_desde_un_alta(client, pedido, m):
    r = client.post("/api/pedido_lineas", json={"pedido_id": pedido.pedido_id, "material_id": m["filtro"].material_id,
                                                "cantidad": 1, "destino": "a_identificar", "estado": "anulado",
                                                "motivo_operacion_id": _motivo()})
    assert r.status_code == 400 and "eliminala" in _errores(r)["estado"]


def test_el_formulario_muestra_los_congelados_deshabilitados(client, enviada, m):
    html = _texto(client.get(f"/pedido_lineas/{enviada}/editar"))
    assert 'value="RE504836 — Filtro de aceite" disabled' in html
    assert "No se puede cambiar: la línea ya se envió a Compras" in html
    assert 'name="material_id"' not in html and 'name="descripcion"' not in html
    # Guardar el formulario (sin los congelados) funciona.
    r = client.post(f"/pedido_lineas/{enviada}/editar", data={"nro_oc": "4500", "estado": "en_cotizacion",
                                                             "sin_conformidad": "False"})
    assert r.status_code == 302, _texto(r)
    assert db_linea(enviada).nro_oc == "4500"


def test_importacion_csv_respeta_lo_congelado(app, client, enviada, m):
    csv = exportar(REGISTRY["pedido_lineas"]).decode("utf-8-sig")
    assert importar(REGISTRY["pedido_lineas"], csv.encode()).sin_cambios == 1
    csv = csv.replace("RE504836 — Filtro de aceite", "CO-1")
    r = importar(REGISTRY["pedido_lineas"], csv.encode())
    assert not r.ok
    assert any("ya se envió a Compras" in str(e) for e in r.errores), r.resumen()


# ---------------------------------------------------------------------------
# Estado de seguimiento: solo en líneas enviadas, abiertas y sin compras
# ---------------------------------------------------------------------------

def _adjudicar(client, db, linea_id, material, cantidad):
    prov = _guardar(db, Proveedor(razon_social="Lange SA"))
    doc = client.post("/api/documentos_proveedor", json={"tipo": "oferta", "proveedor_id": prov.recurso_id,
                                                         "numero": "1", "moneda": "ARS"}).get_json()
    lo = client.post("/api/documento_lineas", json={"documento_id": doc["documento_id"], "cantidad": 3,
                                                    "precio_unitario": 10,
                                                    "material_id": material.material_id}).get_json()
    r = client.post("/api/adjudicaciones", json={"documento_linea_id": lo["documento_linea_id"],
                                                 "pedido_linea_id": linea_id, "cantidad_adjudicada": cantidad})
    assert r.status_code == 201, r.get_json()


def test_con_compras_se_cancela_hasta_lo_pendiente(client, enviada, m, db):
    _adjudicar(client, db, enviada, m["filtro"], 1)  # 1 de 3 comprado
    r = client.post(_accion_anular(enviada), data={"motivo_operacion_id": _motivo()})
    assert r.status_code == 400 and "Ya hay 1 comprados" in _texto(r) and "hasta 2" in _texto(r)
    r = client.post(_accion_anular(enviada), data={"motivo_operacion_id": _motivo(), "cantidad": "2.5"})
    assert r.status_code == 400 and "Se puede cancelar hasta 2 en total" in _texto(r)
    r = client.post(_accion_anular(enviada), data={"motivo_operacion_id": _motivo(), "cantidad": "2"})
    assert r.status_code == 302
    assert db_linea(enviada).pendiente_comprar == 0


def test_seguimiento_con_compras_no_se_edita(client, enviada, m, db):
    _adjudicar(client, db, enviada, m["filtro"], 1)
    assert _api(client, enviada)["estado_visible"] == "Adjudicado"
    r = _patch(client, enviada, estado="en_cotizacion")
    assert r.status_code == 400 and "ya hay compras" in _errores(r)["estado"]


# ---------------------------------------------------------------------------
# Anular o cancelar (acción con formulario)
# ---------------------------------------------------------------------------

def test_formulario_de_anular(client, enviada):
    r = client.get(_accion_anular(enviada))
    assert r.status_code == 200
    html = _texto(r)
    assert "Anular o cancelar" in html and 'name="cantidad"' in html
    assert "Se consiguió por otro canal" in html or "motivo_operacion_id" in html


def test_anular_pide_motivo(client, enviada):
    r = client.post(_accion_anular(enviada), data={"motivo_operacion_id": ""})
    assert r.status_code == 400 and "Motivo es obligatorio" in _texto(r)
    r = client.post(_accion_anular(enviada), data={"motivo_operacion_id": _motivo("DELETE")})
    assert r.status_code == 400 and "no es una opción válida" in _texto(r)
    assert db_linea(enviada).estado == "solicitado"


def test_anular_la_linea_entera(client, enviada):
    r = client.post(_accion_anular(enviada), data={"motivo_operacion_id": _motivo()}, follow_redirects=True)
    assert "anulada" in _texto(r)
    linea = db_linea(enviada)
    assert (linea.estado, linea.estado_visible, linea.motivo_operacion_id) == ("anulado", "Anulado", _motivo())
    log = AuditLog.query.filter(AuditLog.TablaAfectada == "pedido_lineas",
                                AuditLog.motivo_operacion.like("Anulación:%")).one()
    assert log.EstadoActual["estado"] == "anulado"
    # Anulada, el botón ya no se ofrece.
    assert client.get(_accion_anular(enviada)).status_code == 404


def test_cancelar_una_parte(client, enviada):
    r = client.post(_accion_anular(enviada), data={"motivo_operacion_id": _motivo(), "cantidad": "1"})
    assert r.status_code == 302
    r = client.post(_accion_anular(enviada), data={"motivo_operacion_id": _motivo(), "cantidad": "1,5"})
    assert r.status_code == 302
    linea = db_linea(enviada)
    assert (linea.cantidad_cancelada, linea.pendiente_comprar, linea.estado) == (2.5, 0.5, "solicitado")
    r = client.post(_accion_anular(enviada), data={"motivo_operacion_id": _motivo(), "cantidad": "1"})
    assert r.status_code == 400 and "No se puede cancelar más de lo solicitado (3)." in _texto(r)
    r = client.post(_accion_anular(enviada), data={"motivo_operacion_id": _motivo(), "cantidad": "0"})
    assert r.status_code == 400 and "mayor que cero" in _texto(r)


def test_con_compras_no_se_anula_entera(client, enviada, m):
    # Compra directa: con nº de OC, lo solicitado se considera comprado.
    assert _patch(client, enviada, nro_oc="4500").status_code == 200
    r = client.post(_accion_anular(enviada), data={"motivo_operacion_id": _motivo()})
    assert r.status_code == 400 and "no se anula entera" in _texto(r)
    assert db_linea(enviada).estado == "solicitado"


def test_anular_desde_la_fila_vuelve_al_pedido(client, pedido, enviada):
    html = _texto(client.get(f"/pedidos/{pedido.pedido_id}?seccion=pedido_lineas"))
    url = _accion_anular(enviada, desde="fila", pedido_id=pedido.pedido_id)
    assert url.replace("&", "&amp;") in html
    r = client.post(url, data={"motivo_operacion_id": _motivo()})
    assert r.status_code == 302 and r.headers["Location"].endswith(
        f"/pedidos/{pedido.pedido_id}?seccion=pedido_lineas")


# ---------------------------------------------------------------------------
# Grilla
# ---------------------------------------------------------------------------

def _celda(linea_id, campo, pedido_id):
    return f"/pedido_lineas/{linea_id}/celda/{campo}?pedido_id={pedido_id}"


def test_grilla_celdas_congeladas(client, pedido, enviada):
    html = _texto(client.get(f"/pedidos/{pedido.pedido_id}?seccion=pedido_lineas"))
    assert 'class="calc congelada"' in html and 'data-campo="material_id"' in html
    assert "No se puede cambiar: la línea ya se envió a Compras" in html
    assert client.get(_celda(enviada, "material_id", pedido.pedido_id)).status_code == 404
    assert client.post(_celda(enviada, "descripcion", pedido.pedido_id), data={"descripcion": "x"}).status_code == 404
    # El nº de OC sí, y la fila no ofrece «Eliminar» pero sí «Anular o cancelar».
    assert client.get(_celda(enviada, "nro_oc", pedido.pedido_id)).status_code == 200
    assert "Anular o cancelar" in html


def test_grilla_en_borrador(client, pedido, m):
    linea = _linea(client, pedido, material_id=m["filtro"].material_id)
    html = _texto(client.get(f"/pedidos/{pedido.pedido_id}?seccion=pedido_lineas"))
    assert "Eliminar" in html and "Anular o cancelar" not in html
    assert client.get(_celda(linea, "material_id", pedido.pedido_id)).status_code == 200
    assert client.get(_celda(linea, "estado", pedido.pedido_id)).status_code == 404


def test_grilla_estado_sobre_la_columna_visible(client, pedido, enviada):
    r = client.get(_celda(enviada, "estado", pedido.pedido_id))
    html = _texto(r)
    assert r.status_code == 200 and 'data-campo="estado_visible"' in html and 'name="estado"' in html
    assert "En cotización" in html and "Anulado" not in html  # se anula con su acción
    r = client.post(_celda(enviada, "estado", pedido.pedido_id), data={"estado": "en_cotizacion"})
    assert r.status_code == 200 and 'data-foco="estado_visible"' in _texto(r)
    assert ">En cotización<" in _texto(r).replace("\n", "").replace("  ", "")
    assert db_linea(enviada).estado == "en_cotizacion"
    r = client.post(_celda(enviada, "estado", pedido.pedido_id), data={"estado": "anulado"})
    assert r.status_code == 422 and "no se elige en la grilla" in _texto(r)


# ---------------------------------------------------------------------------
# Registry
# ---------------------------------------------------------------------------

def _override(entidad, **cambios):
    return {**cargar_overrides()[entidad], **cambios}


@pytest.mark.parametrize("cambios, texto", [
    ({"editable_si": {"inexistente": lambda r: True}}, "editable_si: 'inexistente' no es un campo"),
    ({"editable_si": {"nro_oc": "no"}}, "editable_si.nro_oc debe ser una función"),
    ({"eliminable_si": "no"}, "eliminable_si debe ser una función"),
    ({"edicion_en_linea": [("estado", "inexistente")]}, "la columna 'inexistente' de 'estado' no está en el listado"),
    ({"edicion_en_linea": [("estado", "nro_oc"), "nro_oc"]}, "ya edita otro campo"),
])
def test_registry_valida_las_reglas(app, cambios, texto):
    _, errores = construir_spec("pedido_lineas", _override("pedido_lineas", **cambios))
    assert any(texto in e for e in errores), errores


def test_registry_valida_excluir_en_linea(app):
    ov = _override("pedido_lineas")
    ov["fields"] = {**ov["fields"], "nro_oc": {"excluir_en_linea": ("x",)}}
    _, errores = construir_spec("pedido_lineas", ov)
    assert any("excluir_en_linea" in e for e in errores), errores


# ---------------------------------------------------------------------------
# Otros: vincular ofertas solo con líneas enviadas; migración
# ---------------------------------------------------------------------------

def test_vincular_ofertas_solo_con_lineas_enviadas(client, pedido, m, db):
    _linea(client, pedido, material_id=m["filtro"].material_id)
    prov = _guardar(db, Proveedor(razon_social="Lange SA"))
    doc = client.post("/api/documentos_proveedor", json={"tipo": "oferta", "proveedor_id": prov.recurso_id,
                                                         "numero": "1", "moneda": "ARS"}).get_json()
    client.post("/api/documento_lineas", json={"documento_id": doc["documento_id"], "cantidad": 3,
                                               "precio_unitario": 10, "material_id": m["filtro"].material_id})
    url = f"/documentos_proveedor/{doc['documento_id']}/accion/vincular_pedidos"
    assert "No se encontraron líneas de pedido abiertas" in _texto(client.post(url, follow_redirects=True))
    client.post(_accion_enviar(pedido))
    assert "Se vinculó 1 línea de pedido." in _texto(client.post(url, follow_redirects=True))
    assert db.session.get(DocumentoProveedor, doc["documento_id"]) is not None


def test_migracion_envia_las_lineas_existentes(tmp_path):
    """Las líneas que existían antes de la 13.2 quedan enviadas, con la fecha de su pedido."""
    from flask_migrate import upgrade
    from sqlalchemy import text

    from app import create_app
    from app.core.db import db

    app = create_app("testing", {"SQLALCHEMY_DATABASE_URI": f"sqlite:///{tmp_path / 'prueba.db'}"})
    with app.app_context():
        upgrade(revision="1d89261de669")
        db.session.execute(text(
            "INSERT INTO pedidos (pedido_id, uuid, numero, fecha_pedido, prioridad, origen) "
            "VALUES (1, 'u1', '1104', '2026-01-05', 'normal', 'app')"))
        db.session.execute(text(
            "INSERT INTO pedido_lineas (pedido_linea_id, uuid, pedido_id, nro_linea, descripcion, estado, "
            "sin_conformidad, cantidad_cancelada, origen) VALUES (1, 'u2', 1, 1, 'Correa', 'solicitado', 0, 0, 'app')"))
        db.session.commit()
        upgrade()
        enviada = db.session.execute(text("SELECT enviada_en FROM pedido_lineas")).scalar()
        assert str(enviada).startswith("2026-01-05 00:00:00")
        assert datetime.fromisoformat(str(enviada)) == datetime(2026, 1, 5)
