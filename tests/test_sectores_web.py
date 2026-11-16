"""Interfaz web de sectores (entidad principal con auditoría y subentidad ubicaciones)."""
import pytest

from app.models.sectores_models import Sector


# ---------------------------------------------------------------------------
# Lectura
# ---------------------------------------------------------------------------

def test_listado_vacio(client):
    r = client.get("/sectores")
    assert r.status_code == 200


def test_listado_muestra_sector_y_estado(client, sector):
    r = client.get("/sectores")
    html = r.get_data(as_text=True)
    assert r.status_code == 200
    assert "Taller" in html
    assert "CC-100" in html
    assert "Activo" in html  # label del estado, no su ID


def test_busqueda_por_texto(client, sector, db, estado_sector_activo):
    db.session.add(
        Sector(nombre_sector="Depósito", centro_costo="CC-200",
               estado_sector_id=estado_sector_activo.estado_sector_id)
    )
    db.session.commit()

    html = client.get("/sectores?campo=nombre_sector&q=tall").get_data(as_text=True)
    assert "Taller" in html
    assert "Depósito" not in html


def test_formulario_crear(client):
    r = client.get("/sectores/crear")
    html = r.get_data(as_text=True)
    assert r.status_code == 200
    assert 'name="nombre_sector"' in html
    assert 'name="estado_sector_id"' in html


def test_detalle(client, sector):
    r = client.get(f"/sectores/{sector.sector_id}")
    html = r.get_data(as_text=True)
    assert r.status_code == 200
    assert "Taller" in html
    assert "Ubicaciones" in html  # pestaña de la subentidad


def test_detalle_pestana_ubicaciones(client, sector, ubicacion):
    r = client.get(f"/sectores/{sector.sector_id}?seccion=ubicaciones")
    assert r.status_code == 200
    assert "Galpón 1" in r.get_data(as_text=True)


def test_detalle_inexistente_da_404(client):
    assert client.get("/sectores/999").status_code == 404


def test_formulario_editar(client, sector):
    r = client.get(f"/sectores/{sector.sector_id}/editar")
    assert r.status_code == 200
    assert "Taller" in r.get_data(as_text=True)


def test_confirmar_eliminar(client, sector):
    assert client.get(f"/sectores/{sector.sector_id}/confirmar_eliminar").status_code == 200


# ---------------------------------------------------------------------------
# Escritura + auditoría
# ---------------------------------------------------------------------------

def test_crear(client, estado_sector_activo, auditoria):
    r = client.post("/sectores/crear", data={
        "nombre_sector": "Mantenimiento",
        "centro_costo": "CC-300",
        "estado_sector_id": str(estado_sector_activo.estado_sector_id),
        "motivo_operacion": "Alta inicial",
    })
    assert r.status_code == 302
    assert r.headers["Location"].endswith("/sectores")

    s = Sector.query.filter_by(nombre_sector="Mantenimiento").one()
    assert s.centro_costo == "CC-300"
    assert s.uuid

    logs = auditoria("sectores")
    assert len(logs) == 1
    log = logs[0]
    assert log.TipoDeCambio == "INSERT"
    assert log.Version == 1
    assert log.RegistroUUID == s.uuid
    assert log.motivo_operacion == "Alta inicial"
    assert log.EstadoAnterior is None
    assert log.EstadoActual["nombre_sector"] == "Mantenimiento"
    assert log.EstadoActual["estado_sector"] == "Activo"  # FK expandida a texto
    assert "uuid" not in log.EstadoActual


def test_editar(client, sector, auditoria):
    r = client.post(f"/sectores/{sector.sector_id}/editar", data={
        "nombre_sector": "Taller central",
        "centro_costo": "CC-100",
        "estado_sector_id": str(sector.estado_sector_id),
        "motivo_operacion": "Corrección",
    })
    assert r.status_code == 302

    assert Sector.query.get(sector.sector_id).nombre_sector == "Taller central"

    log = auditoria("sectores")[-1]
    assert log.TipoDeCambio == "UPDATE"
    assert log.EstadoAnterior["nombre_sector"] == "Taller"
    assert log.EstadoActual["nombre_sector"] == "Taller central"


def test_eliminar(client, sector, auditoria):
    sector_id = sector.sector_id
    r = client.post(f"/sectores/{sector_id}/confirmar_eliminar",
                    data={"motivo_operacion": "Baja"})
    assert r.status_code == 302
    assert Sector.query.get(sector_id) is None

    log = auditoria("sectores")[-1]
    assert log.TipoDeCambio == "DELETE"
    assert log.EstadoActual is None
    assert log.EstadoAnterior["nombre_sector"] == "Taller"


def test_versiones_de_auditoria_se_incrementan(client, sector, auditoria):
    for nombre in ("A", "B"):
        client.post(f"/sectores/{sector.sector_id}/editar", data={
            "nombre_sector": nombre,
            "centro_costo": "CC-100",
            "estado_sector_id": str(sector.estado_sector_id),
        })
    assert [log.Version for log in auditoria("sectores")] == [1, 2]


def test_historial_en_detalle(client, sector):
    client.post(f"/sectores/{sector.sector_id}/editar", data={
        "nombre_sector": "Taller central",
        "centro_costo": "CC-100",
        "estado_sector_id": str(sector.estado_sector_id),
        "motivo_operacion": "Corrección de nombre",
    })
    html = client.get(f"/sectores/{sector.sector_id}?seccion=historial").get_data(as_text=True)
    assert "Corrección de nombre" in html


# ---------------------------------------------------------------------------
# Bugs conocidos (ver docs/plan_refactor_crud.md). Están marcados como xfail
# estricto: cuando se corrijan, el test empezará a pasar y pytest avisará para
# quitar la marca.
# ---------------------------------------------------------------------------

@pytest.mark.xfail(reason="Fase 2: no hay validación de 'required' en el servidor")
def test_crear_sin_nombre_es_rechazado(client, estado_sector_activo):
    client.post("/sectores/crear", data={
        "nombre_sector": "",
        "centro_costo": "CC-1",
        "estado_sector_id": str(estado_sector_activo.estado_sector_id),
    })
    assert Sector.query.count() == 0


@pytest.mark.xfail(reason="Fase 2: IntegrityError (nombre duplicado) termina en error 500")
def test_crear_duplicado_no_da_500(client, sector):
    r = client.post("/sectores/crear", data={
        "nombre_sector": "Taller",
        "centro_costo": "CC-999",
        "estado_sector_id": str(sector.estado_sector_id),
    })
    assert r.status_code < 500
