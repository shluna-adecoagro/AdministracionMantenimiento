"""Interfaz web de ubicaciones (subentidad de sectores)."""
import pytest

from app.models.ubicaciones_models import Ubicacion


@pytest.mark.xfail(reason="Fase 3: el listado propio de una subentidad falla ('sub' is undefined en la plantilla)")
def test_listado_filtrado_por_sector(client, ubicacion, sector, db):
    from app.models.sectores_models import Sector

    otro = Sector(nombre_sector="Depósito", centro_costo="CC-200",
                  estado_sector_id=sector.estado_sector_id)
    db.session.add(otro)
    db.session.flush()
    db.session.add(Ubicacion(nombre_ubicacion="Estantería 9", sector_id=otro.sector_id))
    db.session.commit()

    r = client.get(f"/ubicaciones?sector_id={sector.sector_id}")
    html = r.get_data(as_text=True)
    assert r.status_code == 200
    assert "Galpón 1" in html
    assert "Estantería 9" not in html


def test_formulario_crear_desde_sector(client, sector):
    r = client.get(f"/ubicaciones/crear?sector_id={sector.sector_id}")
    assert r.status_code == 200
    assert 'name="nombre_ubicacion"' in r.get_data(as_text=True)


def test_crear_desde_sector_vuelve_al_detalle_del_sector(client, sector, auditoria):
    r = client.post(f"/ubicaciones/crear?sector_id={sector.sector_id}", data={
        "nombre_ubicacion": "Pañol",
        "sector_id": str(sector.sector_id),
        "motivo_operacion": "Alta",
    })
    assert r.status_code == 302
    assert r.headers["Location"].endswith(f"/sectores/{sector.sector_id}")

    u = Ubicacion.query.filter_by(nombre_ubicacion="Pañol").one()
    assert u.sector_id == sector.sector_id

    log = auditoria("ubicaciones")[-1]
    assert log.TipoDeCambio == "INSERT"
    assert log.RegistroUUID == u.uuid


def test_detalle(client, ubicacion):
    r = client.get(f"/ubicaciones/{ubicacion.ubicacion_id}")
    assert r.status_code == 200
    assert "Galpón 1" in r.get_data(as_text=True)


def test_editar(client, ubicacion, sector, auditoria):
    r = client.post(f"/ubicaciones/{ubicacion.ubicacion_id}/editar", data={
        "nombre_ubicacion": "Galpón 2",
        "sector_id": str(sector.sector_id),
    })
    assert r.status_code == 302
    assert r.headers["Location"].endswith(f"/sectores/{sector.sector_id}")
    assert Ubicacion.query.get(ubicacion.ubicacion_id).nombre_ubicacion == "Galpón 2"
    assert auditoria("ubicaciones")[-1].TipoDeCambio == "UPDATE"


def test_eliminar(client, ubicacion, sector):
    uid = ubicacion.ubicacion_id
    r = client.post(f"/ubicaciones/{uid}/confirmar_eliminar")
    assert r.status_code == 302
    assert r.headers["Location"].endswith(f"/sectores/{sector.sector_id}")
    assert Ubicacion.query.get(uid) is None


# --- Bugs conocidos --------------------------------------------------------

@pytest.mark.xfail(reason="Fase 3: abrir el listado sin ?sector_id da error 500 (BuildError)")
def test_listado_sin_sector_no_da_500(client):
    assert client.get("/ubicaciones").status_code < 500


@pytest.mark.xfail(reason="Fase 3: abrir el formulario sin ?sector_id da error 500 (BuildError)")
def test_crear_sin_sector_no_da_500(client):
    assert client.get("/ubicaciones/crear").status_code < 500
