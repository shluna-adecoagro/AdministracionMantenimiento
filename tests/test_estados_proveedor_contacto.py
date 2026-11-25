"""Estados de proveedor (Activo, Retenido, Inactivo) y de contacto (Disponible,
No disponible): catálogos informativos con valor por defecto."""
import re

from app.crud.entidades import REGISTRY
from app.crud.intercambio.csv_entidades import importar
from app.models.recursos_models import (ContactoProveedor, Empleado, EstadoContacto,
                                        EstadoProveedor, Proveedor)


def estado_proveedor(nombre):
    return EstadoProveedor.query.filter_by(nombre_estado_proveedor=nombre).one()


def estado_contacto(nombre):
    return EstadoContacto.query.filter_by(nombre_estado_contacto=nombre).one()


def _guardar(db, obj):
    db.session.add(obj)
    db.session.commit()
    return obj


def seleccionada(html):
    m = re.search(r'<option value="(\d+)"[^>]*\bselected\b', html)
    return int(m.group(1)) if m else None


def test_seed_carga_los_estados(app):
    assert {e.nombre_estado_proveedor for e in EstadoProveedor.query.all()} == {
        "Activo", "Retenido", "Inactivo"}
    assert {e.nombre_estado_contacto for e in EstadoContacto.query.all()} == {
        "Disponible", "No disponible"}


def test_valores_por_defecto(db):
    p = _guardar(db, Proveedor(razon_social="Lange SA"))
    c = _guardar(db, ContactoProveedor(nombre_contacto="Laura", proveedor_id=p.recurso_id))
    assert p.estado.nombre_estado_proveedor == "Activo"
    assert c.estado.nombre_estado_contacto == "Disponible"


def test_empleado_sigue_con_estado_de_recurso(db):
    e = _guardar(db, Empleado(nombre="Ana", apellido="Pérez", estado_recurso_id=1))
    assert e.estado.nombre_estado_recurso == "Activo"


# ---------------------------------------------------------------------------
# Web
# ---------------------------------------------------------------------------

def test_alta_web_preselecciona_los_valores_por_defecto(client, db):
    html = client.get("/proveedores/crear").get_data(as_text=True)
    assert seleccionada(html) == estado_proveedor("Activo").estado_proveedor_id

    p = _guardar(db, Proveedor(razon_social="Lange SA"))
    html = client.get(f"/contactos_proveedor/crear?proveedor_id={p.recurso_id}").get_data(as_text=True)
    assert 'name="division"' in html
    estado = html[html.index('name="estado_contacto_id"'):]
    assert seleccionada(estado) == estado_contacto("Disponible").estado_contacto_id


def test_retener_un_proveedor_queda_en_la_auditoria(client, db, auditoria):
    p = _guardar(db, Proveedor(razon_social="Lange SA"))
    retenido = estado_proveedor("Retenido").estado_proveedor_id
    r = client.post(f"/proveedores/{p.recurso_id}/editar", data={
        "razon_social": "Lange SA", "estado_proveedor_id": str(retenido),
        "motivo_operacion": "Cambio de estado",
    })
    assert r.status_code == 302
    assert Proveedor.query.get(p.recurso_id).estado.nombre_estado_proveedor == "Retenido"
    assert auditoria("proveedores")[-1].EstadoActual["estado_proveedor_id"] == retenido
    assert "Retenido" in client.get(f"/proveedores/{p.recurso_id}").get_data(as_text=True)


def test_contacto_no_disponible(client, db):
    p = _guardar(db, Proveedor(razon_social="Lange SA"))
    r = client.post(f"/contactos_proveedor/crear?proveedor_id={p.recurso_id}", data={
        "nombre_contacto": "Laura", "proveedor_id": str(p.recurso_id), "division": "Repuestos",
        "estado_contacto_id": str(estado_contacto("No disponible").estado_contacto_id),
    })
    assert r.status_code == 302
    c = ContactoProveedor.query.one()
    assert (c.division, c.estado.nombre_estado_contacto) == ("Repuestos", "No disponible")


def test_estado_en_uso_no_se_borra(client, db):
    _guardar(db, Proveedor(razon_social="Lange SA"))
    r = client.post(f"/estados_proveedor/{estado_proveedor('Activo').estado_proveedor_id}/confirmar_eliminar")
    assert r.status_code == 409


# ---------------------------------------------------------------------------
# API e importación
# ---------------------------------------------------------------------------

def test_api_alta_sin_estado_y_put_que_lo_mantiene(client):
    r = client.post("/api/proveedores", json={"razon_social": "Lange SA"})
    assert r.status_code == 201, r.get_json()
    pid = r.get_json()["recurso_id"]
    assert Proveedor.query.get(pid).estado.nombre_estado_proveedor == "Activo"

    retenido = estado_proveedor("Retenido").estado_proveedor_id
    assert client.patch(f"/api/proveedores/{pid}", json={"estado_proveedor_id": retenido}).status_code == 200
    assert client.put(f"/api/proveedores/{pid}", json={"razon_social": "Lange S.A."}).status_code == 200
    assert Proveedor.query.get(pid).estado.nombre_estado_proveedor == "Retenido"


def test_api_contacto_sin_estado(client, db):
    p = _guardar(db, Proveedor(razon_social="Lange SA"))
    r = client.post("/api/contactos_proveedor", json={"nombre_contacto": "Laura", "proveedor_id": p.recurso_id})
    assert r.status_code == 201, r.get_json()
    assert ContactoProveedor.query.one().estado.nombre_estado_contacto == "Disponible"


def test_importar_proveedores_con_y_sin_estado(app):
    datos = "Razón social;Estado\nLange SA;Retenido\nOtro SA;\n".encode("utf-8")
    r = importar(REGISTRY["proveedores"], datos)
    assert r.ok, r.resumen()
    estados = {p.razon_social: p.estado.nombre_estado_proveedor for p in Proveedor.query.all()}
    assert estados == {"Lange SA": "Retenido", "Otro SA": "Activo"}
