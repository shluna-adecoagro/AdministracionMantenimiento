"""Interfaz web de cuentas."""
from app.models.cuentas_models import Cuenta


def test_listado(client, cuenta):
    r = client.get("/cuentas")
    html = r.get_data(as_text=True)
    assert r.status_code == 200
    assert "Repuestos" in html
    assert "Activa" in html


def test_formulario_crear(client):
    assert client.get("/cuentas/crear").status_code == 200


def test_detalle(client, cuenta):
    r = client.get(f"/cuentas/{cuenta.cuenta_id}")
    assert r.status_code == 200
    assert "5101" in r.get_data(as_text=True)


def test_crear(client, estado_cuenta_activa, auditoria):
    r = client.post("/cuentas/crear", data={
        "numero_cuenta": "5102",
        "nombre_cuenta": "Lubricantes",
        "estado_cuenta_id": str(estado_cuenta_activa.estado_cuenta_id),
    })
    assert r.status_code == 302
    c = Cuenta.query.filter_by(numero_cuenta="5102").one()
    assert c.nombre_cuenta == "Lubricantes"
    assert auditoria("cuentas")[-1].TipoDeCambio == "INSERT"


def test_editar(client, cuenta, auditoria):
    r = client.post(f"/cuentas/{cuenta.cuenta_id}/editar", data={
        "numero_cuenta": "5101",
        "nombre_cuenta": "Repuestos y accesorios",
        "estado_cuenta_id": str(cuenta.estado_cuenta_id),
    })
    assert r.status_code == 302
    assert Cuenta.query.get(cuenta.cuenta_id).nombre_cuenta == "Repuestos y accesorios"
    assert auditoria("cuentas")[-1].TipoDeCambio == "UPDATE"


def test_eliminar(client, cuenta, auditoria):
    cid = cuenta.cuenta_id
    assert client.post(f"/cuentas/{cid}/confirmar_eliminar").status_code == 302
    assert Cuenta.query.get(cid) is None
    assert auditoria("cuentas")[-1].TipoDeCambio == "DELETE"


def test_numero_de_cuenta_repetido_se_rechaza(client, cuenta):
    r = client.post("/cuentas/crear", data={
        "numero_cuenta": "5101",
        "nombre_cuenta": "Otra",
        "estado_cuenta_id": str(cuenta.estado_cuenta_id),
    })
    assert r.status_code == 400
    assert "Ya existe un registro con ese valor de «Número de cuenta»." in r.get_data(as_text=True)
