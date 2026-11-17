"""API REST generada (/api/<entidad>)."""
import pytest

from app.models.cuentas_models import Cuenta
from app.models.sectores_models import Sector
from app.models.ubicaciones_models import Ubicacion


def nuevo_sector(estado, **cambios):
    datos = {"nombre_sector": "Mantenimiento", "centro_costo": "CC-300", "estado_sector_id": estado}
    datos.update(cambios)
    return datos


# ---------------------------------------------------------------------------
# Listado
# ---------------------------------------------------------------------------

def test_listado_vacio(client):
    r = client.get("/api/sectores")
    assert r.status_code == 200
    assert r.get_json() == []
    assert r.headers["X-Total-Count"] == "0"


def test_listado_devuelve_registros_con_etiquetas(client, sector):
    [s] = client.get("/api/sectores").get_json()
    assert s["sector_id"] == sector.sector_id
    assert s["nombre_sector"] == "Taller"
    assert s["estado_sector_id_label"] == "Activo"
    assert s["uuid"] == sector.uuid
    assert "T" in s["creado_en"]  # fecha en formato ISO


def test_barra_final_compatible_con_src_sync(client, sector):
    assert client.get("/api/sectores/").status_code == 200


def test_filtro_exacto_por_campo(client, sector, ubicacion, db):
    db.session.add(Ubicacion(nombre_ubicacion="Suelta"))
    db.session.commit()

    datos = client.get(f"/api/ubicaciones?sector_id={sector.sector_id}").get_json()
    assert [u["nombre_ubicacion"] for u in datos] == ["Galpón 1"]
    assert datos[0]["sector_id_label"] == "Taller"


def test_filtro_con_valor_invalido(client):
    r = client.get("/api/ubicaciones?sector_id=abc")
    assert r.status_code == 400
    assert "sector_id" in r.get_json()["errors"]


def test_busqueda_y_paginacion(client, sector, db):
    for i in range(5):
        db.session.add(Ubicacion(nombre_ubicacion=f"Estante {i}", sector_id=sector.sector_id))
    db.session.add(Ubicacion(nombre_ubicacion="Galpón"))
    db.session.commit()

    r = client.get("/api/ubicaciones?q=estante&limit=2&offset=2")
    assert r.headers["X-Total-Count"] == "5"
    assert [u["nombre_ubicacion"] for u in r.get_json()] == ["Estante 2", "Estante 3"]


def test_paginacion_invalida(client):
    assert client.get("/api/sectores?limit=-1").status_code == 400


# ---------------------------------------------------------------------------
# Alta
# ---------------------------------------------------------------------------

def test_crear(client, estado_sector_activo, auditoria):
    r = client.post("/api/sectores", json=nuevo_sector(estado_sector_activo.estado_sector_id),
                    headers={"X-Usuario": "sync-excel"})
    assert r.status_code == 201
    datos = r.get_json()
    assert datos["sector_id"] > 0  # los clientes usan el ID devuelto
    assert datos["nombre_sector"] == "Mantenimiento"

    [log] = auditoria("sectores")
    assert log.TipoDeCambio == "INSERT"
    assert log.Usuario == "sync-excel"
    assert log.EstadoActual["estado_sector"] == "Activo"


def test_crear_con_barra_final(client, estado_sector_activo):
    r = client.post("/api/sectores/", json=nuevo_sector(estado_sector_activo.estado_sector_id))
    assert r.status_code == 201


def test_usuario_por_defecto(client, estado_sector_activo, auditoria):
    client.post("/api/sectores", json=nuevo_sector(estado_sector_activo.estado_sector_id))
    assert auditoria("sectores")[0].Usuario == "api"


def test_faltan_obligatorios(client):
    r = client.post("/api/sectores", json={"nombre_sector": "X"})
    assert r.status_code == 400
    cuerpo = r.get_json()
    assert cuerpo["status"] == "error"
    assert cuerpo["errors"] == {
        "centro_costo": "Centro de Costo es obligatorio.",
        "estado_sector_id": "Estado es obligatorio.",
    }


def test_texto_vacio_es_obligatorio(client, estado_sector_activo):
    r = client.post("/api/sectores", json=nuevo_sector("uno", centro_costo=""))
    assert r.get_json()["errors"] == {
        "centro_costo": "Centro de Costo es obligatorio.",
        "estado_sector_id": "Estado debe ser un número entero.",
    }


def test_respuestas_con_tildes_legibles(client):
    r = client.post("/api/sectores", json={})
    assert "Centro de Costo es obligatorio" in r.get_data(as_text=True)
    assert "\\u00" not in r.get_data(as_text=True)


def test_campo_desconocido(client, estado_sector_activo):
    r = client.post("/api/sectores", json=nuevo_sector(estado_sector_activo.estado_sector_id, color="rojo"))
    assert r.status_code == 400
    assert r.get_json()["errors"] == {"color": "Campo desconocido: «color»."}


def test_tipo_incorrecto(client):
    r = client.post("/api/sectores", json=nuevo_sector("uno"))
    assert r.status_code == 400
    assert r.get_json()["errors"]["estado_sector_id"] == "Estado debe ser un número entero."


def test_texto_demasiado_largo(client, estado_sector_activo):
    r = client.post("/api/sectores", json=nuevo_sector(estado_sector_activo.estado_sector_id,
                                                       nombre_sector="x" * 151))
    assert r.status_code == 400
    assert "150 caracteres" in r.get_json()["errors"]["nombre_sector"]


def test_fk_inexistente(client):
    r = client.post("/api/sectores", json=nuevo_sector(999))
    assert r.status_code == 400
    assert r.get_json()["errors"] == {"estado_sector_id": "Estado: no existe el ID 999."}


def test_duplicado_da_409(client, sector):
    r = client.post("/api/sectores", json=nuevo_sector(sector.estado_sector_id, nombre_sector="Taller"))
    assert r.status_code == 409
    assert "Ya existe" in r.get_json()["message"]


def test_cuerpo_que_no_es_json(client):
    r = client.post("/api/sectores", data="hola", content_type="text/plain")
    assert r.status_code == 400
    assert "JSON" in r.get_json()["errors"]["_general"]


def test_cuerpo_que_no_es_objeto(client):
    r = client.post("/api/sectores", json=[1, 2])
    assert r.status_code == 400


def test_opcional_puede_ser_null(client):
    r = client.post("/api/ubicaciones", json={"nombre_ubicacion": "Suelta", "sector_id": None})
    assert r.status_code == 201
    assert r.get_json()["sector_id"] is None


# ---------------------------------------------------------------------------
# Consulta, modificación y baja
# ---------------------------------------------------------------------------

def test_obtener(client, sector):
    r = client.get(f"/api/sectores/{sector.sector_id}")
    assert r.status_code == 200
    assert r.get_json()["nombre_sector"] == "Taller"


def test_inexistente_da_404_json(client):
    r = client.get("/api/sectores/999")
    assert r.status_code == 404
    assert r.get_json()["status"] == "error"


def test_metodo_no_permitido_da_405_json(client, sector):
    r = client.post(f"/api/sectores/{sector.sector_id}", json={})
    assert r.status_code == 405
    assert r.get_json()["status"] == "error"


def test_reemplazar(client, sector, auditoria):
    r = client.put(f"/api/sectores/{sector.sector_id}",
                   json=nuevo_sector(sector.estado_sector_id, nombre_sector="Taller central"))
    assert r.status_code == 200
    assert r.get_json()["nombre_sector"] == "Taller central"
    assert auditoria("sectores")[-1].TipoDeCambio == "UPDATE"


def test_reemplazar_exige_todos_los_obligatorios(client, sector):
    r = client.put(f"/api/sectores/{sector.sector_id}", json={"nombre_sector": "X"})
    assert r.status_code == 400


def test_reemplazar_vacia_los_opcionales_ausentes(client, ubicacion):
    r = client.put(f"/api/ubicaciones/{ubicacion.ubicacion_id}", json={"nombre_ubicacion": "Galpón 2"})
    assert r.status_code == 200
    assert r.get_json()["sector_id"] is None


def test_modificar_solo_lo_enviado(client, sector):
    r = client.patch(f"/api/sectores/{sector.sector_id}", json={"centro_costo": "CC-999"})
    assert r.status_code == 200
    s = Sector.query.get(sector.sector_id)
    assert (s.nombre_sector, s.centro_costo) == ("Taller", "CC-999")


def test_modificar_sin_campos(client, sector):
    r = client.patch(f"/api/sectores/{sector.sector_id}", json={})
    assert r.status_code == 400


def test_modificar_no_permite_vaciar_obligatorio(client, sector):
    r = client.patch(f"/api/sectores/{sector.sector_id}", json={"nombre_sector": None})
    assert r.status_code == 400


def test_eliminar_en_cascada_con_motivo(client, sector, ubicacion, auditoria):
    r = client.delete(f"/api/sectores/{sector.sector_id}?motivo=Cierre",
                      headers={"X-Usuario": "ana"})
    assert r.status_code == 200
    assert r.get_json() == {"status": "ok"}
    assert Ubicacion.query.count() == 0
    log = auditoria("sectores")[-1]
    assert (log.TipoDeCambio, log.motivo_operacion, log.Usuario) == ("DELETE", "Cierre", "ana")
    assert auditoria("ubicaciones")[-1].TipoDeCambio == "DELETE"


def test_eliminar_en_uso_da_409(client, ubicacion, db, categorias_activo):
    from app.models.activos_models import Activo, CategoriaActivo, EstadoActivo

    cat = CategoriaActivo.query.first()
    db.session.add(Activo(
        numero_activo="A-1", descripcion="Tractor",
        categoria_activo_id=cat.categoria_activo_id,
        estado_activo_id=EstadoActivo.query.first().estado_activo_id,
        ubicacion_id=ubicacion.ubicacion_id,
    ))
    db.session.commit()
    r = client.delete(f"/api/ubicaciones/{ubicacion.ubicacion_id}")
    assert r.status_code == 409
    assert "lo usan 1 activo" in r.get_json()["message"]


def test_cuentas(client, estado_cuenta_activa):
    r = client.post("/api/cuentas", json={
        "numero_cuenta": "5101", "nombre_cuenta": "Repuestos",
        "estado_cuenta_id": estado_cuenta_activa.estado_cuenta_id,
    })
    assert r.status_code == 201
    assert Cuenta.query.count() == 1
    assert client.get("/api/cuentas").get_json()[0]["estado_cuenta_id_label"] == "Activa"


# ---------------------------------------------------------------------------
# Documentación
# ---------------------------------------------------------------------------

def test_openapi_3_valido(client):
    from openapi_spec_validator import validate

    doc = client.get("/api/openapi.json").get_json()
    validate(doc)
    assert doc["openapi"] == "3.0.3"
    assert doc["servers"] == [{"url": "http://localhost/api"}]
    assert {"/sectores", "/sectores/{id}", "/ubicaciones", "/cuentas"} <= set(doc["paths"])
    crear = doc["components"]["schemas"]["SectorCrear"]
    assert crear["required"] == ["nombre_sector", "centro_costo", "estado_sector_id"]
    assert crear["properties"]["nombre_sector"]["maxLength"] == 150


def test_swagger_2_valido_para_power_apps(client):
    from openapi_spec_validator import validate

    doc = client.get("/api/swagger.json").get_json()
    validate(doc)
    assert doc["swagger"] == "2.0"
    assert doc["host"] == "localhost"
    assert doc["basePath"] == "/api"
    assert "SectorCrear" in doc["definitions"]


def test_pagina_de_documentacion(client):
    r = client.get("/api/docs")
    assert r.status_code == 200
    assert "/api/openapi.json" in r.get_data(as_text=True)


@pytest.mark.parametrize("modo", ["crear", "reemplazar", "modificar"])
def test_esquemas_de_entrada_son_json_schema_validos(modo):
    from jsonschema import Draft202012Validator

    from app.crud.entidades import REGISTRY
    from app.crud.schema.jsonschema import esquema_entrada

    for spec in REGISTRY.values():
        Draft202012Validator.check_schema(esquema_entrada(spec, modo))
