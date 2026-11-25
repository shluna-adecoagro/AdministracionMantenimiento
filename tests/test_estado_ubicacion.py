"""Estado de las ubicaciones: catálogo estados_ubicacion, «Operativa» por defecto."""
import re

from app.crud.entidades import REGISTRY
from app.crud.intercambio.csv_entidades import importar
from app.models.ubicaciones_models import EstadoUbicacion, Ubicacion


def estado(nombre):
    return EstadoUbicacion.query.filter_by(nombre_estado_ubicacion=nombre).one()


def test_seed_carga_los_tres_estados(app):
    nombres = {e.nombre_estado_ubicacion for e in EstadoUbicacion.query.all()}
    assert nombres == {"Operativa", "En mantenimiento", "Inactiva"}


def test_sin_estado_queda_operativa(ubicacion):
    assert ubicacion.estado.nombre_estado_ubicacion == "Operativa"


def test_sin_operativa_toma_el_primer_estado(db, sector):
    """Si «Operativa» se renombró, el valor por defecto es el primer estado cargado."""
    estado("Operativa").nombre_estado_ubicacion = "Disponible"
    u = Ubicacion(nombre_ubicacion="Pañol", sector_id=sector.sector_id)
    db.session.add(u)
    db.session.commit()
    assert u.estado.nombre_estado_ubicacion == "Disponible"


# ---------------------------------------------------------------------------
# Web
# ---------------------------------------------------------------------------

def test_alta_web_preselecciona_operativa(client, sector):
    html = client.get(f"/ubicaciones/crear?sector_id={sector.sector_id}").get_data(as_text=True)
    assert 'name="estado_ubicacion_id"' in html
    seleccionada = re.search(r'<option value="(\d+)"[^>]*\bselected\b', html)
    assert seleccionada and int(seleccionada.group(1)) == estado("Operativa").estado_ubicacion_id


def test_alta_web_con_estado(client, sector):
    r = client.post(f"/ubicaciones/crear?sector_id={sector.sector_id}", data={
        "nombre_ubicacion": "Pañol",
        "sector_id": str(sector.sector_id),
        "estado_ubicacion_id": str(estado("En mantenimiento").estado_ubicacion_id),
        "motivo_operacion": "Alta",
    })
    assert r.status_code == 302
    u = Ubicacion.query.filter_by(nombre_ubicacion="Pañol").one()
    assert u.estado.nombre_estado_ubicacion == "En mantenimiento"


def test_cambio_de_estado_queda_en_la_auditoria(client, ubicacion, sector, auditoria):
    r = client.post(f"/ubicaciones/{ubicacion.ubicacion_id}/editar", data={
        "nombre_ubicacion": "Galpón 1",
        "sector_id": str(sector.sector_id),
        "estado_ubicacion_id": str(estado("En mantenimiento").estado_ubicacion_id),
        "motivo_operacion": "Cambio de estado",
    })
    assert r.status_code == 302
    assert Ubicacion.query.get(ubicacion.ubicacion_id).estado.nombre_estado_ubicacion == "En mantenimiento"
    log = auditoria("ubicaciones")[-1]
    assert log.TipoDeCambio == "UPDATE"
    nuevo = estado("En mantenimiento").estado_ubicacion_id
    assert log.EstadoActual["estado_ubicacion_id"] == nuevo


def test_detalle_muestra_el_estado(client, ubicacion):
    assert "Operativa" in client.get(f"/ubicaciones/{ubicacion.ubicacion_id}").get_data(as_text=True)


def test_estado_en_uso_no_se_borra(client, ubicacion):
    r = client.post(f"/estados_ubicacion/{estado('Operativa').estado_ubicacion_id}/confirmar_eliminar")
    assert r.status_code == 409
    assert "1 ubicación" in r.get_data(as_text=True)


# ---------------------------------------------------------------------------
# API e importación
# ---------------------------------------------------------------------------

def test_api_alta_sin_estado_queda_operativa(client, sector):
    r = client.post("/api/ubicaciones", json={"nombre_ubicacion": "Pañol", "sector_id": sector.sector_id})
    assert r.status_code == 201, r.get_json()
    assert Ubicacion.query.get(r.get_json()["ubicacion_id"]).estado.nombre_estado_ubicacion == "Operativa"


def test_api_put_sin_estado_lo_mantiene(client, ubicacion, db):
    ubicacion.estado_ubicacion_id = estado("Inactiva").estado_ubicacion_id
    db.session.commit()
    r = client.put(f"/api/ubicaciones/{ubicacion.ubicacion_id}", json={"nombre_ubicacion": "Galpón 2"})
    assert r.status_code == 200
    assert Ubicacion.query.get(ubicacion.ubicacion_id).estado.nombre_estado_ubicacion == "Inactiva"


def test_api_no_permite_vaciar_el_estado(client, ubicacion):
    r = client.patch(f"/api/ubicaciones/{ubicacion.ubicacion_id}", json={"estado_ubicacion_id": None})
    assert r.status_code == 200
    assert Ubicacion.query.get(ubicacion.ubicacion_id).estado.nombre_estado_ubicacion == "Operativa"


def test_importar_con_y_sin_estado(app, sector):
    datos = (
        "Nombre de la ubicación;Sector;Estado\n"
        "Pañol;Taller;En mantenimiento\n"
        "Galpón 3;Taller;\n"
    ).encode("utf-8")
    r = importar(REGISTRY["ubicaciones"], datos)
    assert r.ok, r.resumen()
    estados = {u.nombre_ubicacion: u.estado.nombre_estado_ubicacion for u in Ubicacion.query.all()}
    assert estados == {"Pañol": "En mantenimiento", "Galpón 3": "Operativa"}
