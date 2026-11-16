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
# Validación y errores de la base
# ---------------------------------------------------------------------------

def test_crear_sin_nombre_es_rechazado(client, estado_sector_activo, auditoria):
    r = client.post("/sectores/crear", data={
        "nombre_sector": "   ",
        "centro_costo": "CC-1",
        "estado_sector_id": str(estado_sector_activo.estado_sector_id),
    })
    html = r.get_data(as_text=True)
    assert r.status_code == 400
    assert "Nombre del Sector es obligatorio." in html
    assert 'value="CC-1"' in html  # no se pierde lo que se escribió
    assert Sector.query.count() == 0
    assert auditoria("sectores") == []


def test_crear_duplicado_muestra_mensaje(client, sector, auditoria):
    r = client.post("/sectores/crear", data={
        "nombre_sector": "Taller",
        "centro_costo": "CC-999",
        "estado_sector_id": str(sector.estado_sector_id),
    })
    assert r.status_code == 400
    assert "Ya existe un registro con ese valor de «Nombre del Sector»." in r.get_data(as_text=True)
    assert Sector.query.count() == 1
    assert auditoria("sectores") == []  # la auditoría no queda a medias


def test_texto_demasiado_largo(client, estado_sector_activo):
    r = client.post("/sectores/crear", data={
        "nombre_sector": "x" * 151,
        "centro_costo": "CC-1",
        "estado_sector_id": str(estado_sector_activo.estado_sector_id),
    })
    assert r.status_code == 400
    assert "como máximo 150 caracteres" in r.get_data(as_text=True)


def test_editar_conserva_campos_que_no_vienen_en_el_formulario(client, sector):
    r = client.post(f"/sectores/{sector.sector_id}/editar", data={"nombre_sector": "Taller 2"})
    assert r.status_code == 302
    s = Sector.query.get(sector.sector_id)
    assert (s.nombre_sector, s.centro_costo) == ("Taller 2", "CC-100")


# ---------------------------------------------------------------------------
# Borrado: cascada a ubicaciones, bloqueo si algo los usa
# ---------------------------------------------------------------------------

@pytest.fixture
def activo_en(db):
    """Crea un activo asignado a un sector y/o ubicación."""
    from app.models.activos_models import Activo, CategoriaActivo, EstadoActivo

    def _crear(sector_id=None, ubicacion_id=None):
        cat = CategoriaActivo.query.first()
        a = Activo(
            descripcion="Tractor 1",
            tipo_activo_id=cat.tipo_activo_id,
            categoria_activo_id=cat.categoria_activo_id,
            estado_activo_id=EstadoActivo.query.first().estado_activo_id,
            sector_id=sector_id,
            ubicacion_id=ubicacion_id,
        )
        db.session.add(a)
        db.session.commit()
        return a

    return _crear


def test_confirmar_eliminar_avisa_la_cascada(client, sector, ubicacion):
    r = client.get(f"/sectores/{sector.sector_id}/confirmar_eliminar")
    html = r.get_data(as_text=True)
    assert r.status_code == 200
    assert "También se eliminarán: 1 ubicación." in html
    assert "btn-eliminar" in html


def test_eliminar_sector_borra_sus_ubicaciones_y_las_audita(client, sector, ubicacion, auditoria):
    from app.models.ubicaciones_models import Ubicacion

    sector_id, ubicacion_uuid = sector.sector_id, ubicacion.uuid
    r = client.post(f"/sectores/{sector_id}/confirmar_eliminar",
                    data={"motivo_operacion": "Cierre del sector"})
    assert r.status_code == 302
    assert Sector.query.get(sector_id) is None
    assert Ubicacion.query.count() == 0

    [log_sector] = auditoria("sectores")
    assert log_sector.TipoDeCambio == "DELETE"

    [log_ubicacion] = auditoria("ubicaciones")
    assert log_ubicacion.TipoDeCambio == "DELETE"
    assert log_ubicacion.RegistroUUID == ubicacion_uuid
    assert log_ubicacion.EstadoAnterior["nombre_ubicacion"] == "Galpón 1"
    assert log_ubicacion.motivo_operacion == (
        f"Eliminación en cascada de sectores #{sector_id}: Cierre del sector"
    )


def test_no_se_puede_eliminar_sector_con_activos(client, sector, activo_en, auditoria):
    activo_en(sector_id=sector.sector_id)

    # La pantalla de confirmación ya avisa y no ofrece el botón.
    r = client.get(f"/sectores/{sector.sector_id}/confirmar_eliminar")
    html = r.get_data(as_text=True)
    assert "No se puede eliminar porque lo usan 1 activo." in html
    assert "btn-eliminar" not in html

    r = client.post(f"/sectores/{sector.sector_id}/confirmar_eliminar")
    assert r.status_code == 409
    assert Sector.query.get(sector.sector_id) is not None
    assert auditoria("sectores") == []


def test_ubicacion_en_uso_bloquea_la_cascada(client, sector, ubicacion, activo_en, auditoria):
    from app.models.ubicaciones_models import Ubicacion

    activo_en(ubicacion_id=ubicacion.ubicacion_id)
    r = client.post(f"/sectores/{sector.sector_id}/confirmar_eliminar")
    assert r.status_code == 409
    assert "lo usan 1 activo" in r.get_data(as_text=True)
    # No se borró nada: ni el sector ni sus ubicaciones.
    assert Sector.query.get(sector.sector_id) is not None
    assert Ubicacion.query.count() == 1
    assert auditoria("sectores") == [] and auditoria("ubicaciones") == []


def test_eliminar_ubicacion_en_uso_se_bloquea(client, ubicacion, activo_en):
    from app.models.ubicaciones_models import Ubicacion

    activo_en(ubicacion_id=ubicacion.ubicacion_id)
    r = client.post(f"/ubicaciones/{ubicacion.ubicacion_id}/confirmar_eliminar")
    assert r.status_code == 409
    assert Ubicacion.query.get(ubicacion.ubicacion_id) is not None


def test_campo_de_busqueda_no_permitido_se_ignora(client, sector):
    assert client.get("/sectores?campo=uuid&q=abc").status_code == 200
