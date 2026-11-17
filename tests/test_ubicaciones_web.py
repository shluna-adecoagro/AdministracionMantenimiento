"""Interfaz web de ubicaciones (subentidad de sectores)."""
import pytest

from app.models.ubicaciones_models import Ubicacion


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
    assert r.headers["Location"].endswith(f"/sectores/{sector.sector_id}?seccion=ubicaciones")

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
    assert r.headers["Location"].endswith(f"/sectores/{sector.sector_id}?seccion=ubicaciones")
    assert Ubicacion.query.get(ubicacion.ubicacion_id).nombre_ubicacion == "Galpón 2"
    assert auditoria("ubicaciones")[-1].TipoDeCambio == "UPDATE"


def test_eliminar(client, ubicacion, sector):
    uid = ubicacion.ubicacion_id
    r = client.post(f"/ubicaciones/{uid}/confirmar_eliminar")
    assert r.status_code == 302
    assert r.headers["Location"].endswith(f"/sectores/{sector.sector_id}?seccion=ubicaciones")
    assert Ubicacion.query.get(uid) is None


# ---------------------------------------------------------------------------
# Ubicaciones por su cuenta (sin venir desde un sector)
# ---------------------------------------------------------------------------

def test_listado_completo_muestra_el_sector(client, ubicacion):
    r = client.get("/ubicaciones")
    html = r.get_data(as_text=True)
    assert r.status_code == 200
    assert "Galpón 1" in html
    assert "Taller" in html  # columna Sector con su nombre, no el ID


def test_formulario_crear_sin_sector(client, sector):
    r = client.get("/ubicaciones/crear")
    html = r.get_data(as_text=True)
    assert r.status_code == 200
    assert 'name="sector_id"' in html
    assert 'href="/ubicaciones"' in html  # Cancelar vuelve al listado


def test_crear_sin_sector_vuelve_al_listado(client, sector):
    r = client.post("/ubicaciones/crear", data={
        "nombre_ubicacion": "Playón", "sector_id": str(sector.sector_id),
    })
    assert r.status_code == 302
    assert r.headers["Location"].endswith("/ubicaciones")
    assert Ubicacion.query.filter_by(nombre_ubicacion="Playón").one().sector_id == sector.sector_id


def test_ubicacion_sin_sector(client):
    r = client.post("/ubicaciones/crear", data={"nombre_ubicacion": "Suelta", "sector_id": ""})
    assert r.status_code == 302
    u = Ubicacion.query.filter_by(nombre_ubicacion="Suelta").one()
    assert u.sector_id is None
    assert client.get(f"/ubicaciones/{u.ubicacion_id}").status_code == 200
    assert "None" not in client.get("/ubicaciones").get_data(as_text=True)


def test_detalle_vuelve_al_sector_y_tiene_historial(client, ubicacion, sector):
    html = client.get(f"/ubicaciones/{ubicacion.ubicacion_id}").get_data(as_text=True)
    assert f'href="/sectores/{sector.sector_id}?seccion=ubicaciones"' in html
    assert "Volver a sector" in html
    assert "Historial" in html
