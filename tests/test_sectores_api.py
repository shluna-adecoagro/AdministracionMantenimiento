"""API REST de sectores (/api/sectores). Es el contrato que usa src/sync."""
import pytest

from app.models.sectores_models import Sector


def test_listar(client, sector):
    r = client.get("/api/sectores/")
    assert r.status_code == 200
    datos = r.get_json()
    assert [s["nombre_sector"] for s in datos] == ["Taller"]


def test_json_invalido_da_400(client):
    r = client.post("/api/sectores/", json={"nombre_sector": "X"})
    assert r.status_code == 400
    assert r.get_json()["status"] == "error"


def test_campo_extra_da_400(client, estado_sector_activo):
    r = client.post("/api/sectores/", json={
        "nombre_sector": "X", "centro_costo": "CC",
        "estado_sector_id": estado_sector_activo.estado_sector_id,
        "otro": 1,
    })
    assert r.status_code == 400


def test_estado_inexistente_da_400(client):
    r = client.post("/api/sectores/", json={
        "nombre_sector": "X", "centro_costo": "CC", "estado_sector_id": 999,
    })
    assert r.status_code == 400


def test_eliminar_inexistente_da_404(client):
    assert client.delete("/api/sectores/999").status_code == 404


# --- Bugs conocidos --------------------------------------------------------

@pytest.mark.xfail(reason="Fase 4: el decorador de auditoría de la API no completa RegistroUUID (NOT NULL)")
def test_crear(client, estado_sector_activo):
    r = client.post("/api/sectores/", json={
        "nombre_sector": "Mantenimiento", "centro_costo": "CC-300",
        "estado_sector_id": estado_sector_activo.estado_sector_id,
    })
    assert r.status_code == 201
    assert Sector.query.filter_by(nombre_sector="Mantenimiento").count() == 1


@pytest.mark.xfail(reason="Fase 4: el decorador de auditoría de la API no completa RegistroUUID (NOT NULL)")
def test_actualizar(client, sector):
    r = client.put(f"/api/sectores/{sector.sector_id}", json={
        "nombre_sector": "Taller central", "centro_costo": "CC-100",
        "estado_sector_id": sector.estado_sector_id,
    })
    assert r.status_code == 200
