"""
Entidades migradas en la Fase 7: activos, medidores, lecturas, insumos, stock,
catálogos de insumo, marcas, modelos, unidades, empleados, proveedores y BOM.
"""
from datetime import datetime

import pytest

from app.crud.entidades import REGISTRY
from app.models.activos_models import Activo, CategoriaActivo, EstadoActivo
from app.models.bom_activo_models import BOMActivo
from app.models.bom_modelo_models import BOMModelo
from app.models.insumos_models import CategoriaInsumo, Insumo, StockInsumo
from app.models.lecturas_medidores_models import LecturaMedidor
from app.models.marcas_modelos_models import Marca, Modelo
from app.models.medidores_models import Medidor
from app.models.recursos_models import ContactoProveedor, Empleado, EstadoRecurso, Proveedor
from app.models.unidadmedida_models import TipoUnidad, UnidadMedida


# ---------------------------------------------------------------------------
# Datos
# ---------------------------------------------------------------------------

def _guardar(db, *objetos):
    db.session.add_all(objetos)
    db.session.commit()
    return objetos[0] if len(objetos) == 1 else objetos


@pytest.fixture
def modelo(db):
    marca = _guardar(db, Marca(nombre_marca="John Deere"))
    return _guardar(db, Modelo(nombre_modelo="6110J", marca_id=marca.marca_id))


@pytest.fixture
def activo(db, modelo, sector):
    categoria = CategoriaActivo.query.filter_by(nombre_categoria="Tractor").one()
    return _guardar(db, Activo(
        numero_activo="AB123CD", descripcion="Tractor 1",
        categoria_activo_id=categoria.categoria_activo_id,
        marca_id=modelo.marca_id, modelo_id=modelo.modelo_id, sector_id=sector.sector_id,
        estado_activo_id=EstadoActivo.query.first().estado_activo_id,
    ))


@pytest.fixture
def unidad(db):
    tipo = TipoUnidad.query.filter_by(nombre_tipo="Tiempo").one()
    return _guardar(db, UnidadMedida(nombre_unidad="Horas", abreviatura="h", tipo_unidad_id=tipo.tipo_unidad_id))


@pytest.fixture
def medidor(db, activo, unidad):
    return _guardar(db, Medidor(nombre_medidor="Horómetro", activo_id=activo.activo_id,
                                unidad_medida_id=unidad.unidad_medida_id, valor_inicial=100))


def _insumo(db, codigo, descripcion):
    cat = CategoriaInsumo.query.filter_by(nombre_categoria="Filtros").one()
    return _guardar(db, Insumo(codigo=codigo, descripcion=descripcion, categoria_insumo_id=cat.categoria_insumo_id))


@pytest.fixture
def insumo(db):
    return _insumo(db, "F-001", "Filtro de aceite")


@pytest.fixture
def empleado(db):
    return _guardar(db, Empleado(nombre="Ana", apellido="Pérez", estado_recurso_id=1))


# ---------------------------------------------------------------------------
# Todas las pantallas responden
# ---------------------------------------------------------------------------

@pytest.mark.parametrize("entidad", sorted(REGISTRY))
def test_listado_y_alta_de_cada_entidad(client, entidad):
    assert client.get(f"/{entidad}").status_code == 200
    assert client.get(f"/{entidad}/crear").status_code == 200


def test_subentidades_abren_sin_el_padre(client, medidor):
    """Antes daban 500 si se abrían sin el ID del padre (error 3 del diagnóstico)."""
    for url in ("/medidores", "/lecturas_medidor", "/stock_insumo", "/modelos",
                "/contactos_proveedor", "/lecturas_medidor/crear", "/modelos/crear"):
        assert client.get(url).status_code == 200, url


def test_detalle_con_todas_sus_pestanas(client, activo, insumo, modelo, medidor):
    pestanas = {
        f"/activos/{activo.activo_id}": ["datos", "historial", "medidores", "bom_activo", "bom_del_modelo", "bom_final"],
        f"/insumos/{insumo.insumo_id}": ["stock_insumo", "bom_modelo", "bom_activo", "compatibilidad_final"],
        f"/modelos/{modelo.modelo_id}": ["bom_modelo"],
        f"/medidores/{medidor.medidor_id}": ["lecturas_medidor"],
    }
    for url, secciones in pestanas.items():
        for seccion in secciones:
            assert client.get(f"{url}?seccion={seccion}").status_code == 200, (url, seccion)


def test_menu_lateral(client):
    html = client.get("/").get_data(as_text=True)
    for url in ("/activos", "/insumos", "/empleados", "/proveedores", "/marcas",
                "/unidades_medida", "/categorias_insumo"):
        assert f'href="{url}"' in html
    assert 'href="/medidores"' not in html  # subentidad: se llega desde el activo


# ---------------------------------------------------------------------------
# Activos
# ---------------------------------------------------------------------------

def test_crear_activo_con_usuario_asignado_libre(client, sector, empleado):
    form = client.get("/activos/crear").get_data(as_text=True)
    assert '<option value="Ana Pérez">' in form  # sugerencias de empleados

    cat = CategoriaActivo.query.filter_by(nombre_categoria="Pickup").one()
    r = client.post("/activos/crear", data={
        "numero_activo": "AC456", "descripcion": "Hilux",
        "categoria_activo_id": cat.categoria_activo_id, "estado_activo_id": 1,
        "usuario_asignado": "Contratista externo", "año": "2020",
    })
    assert r.status_code == 302
    a = Activo.query.filter_by(descripcion="Hilux").one()
    assert a.usuario_asignado == "Contratista externo"
    assert a.año == 2020


def test_borrar_activo_borra_su_bom(client, activo, insumo):
    BOMActivo.query.session.add(BOMActivo(activo_id=activo.activo_id, insumo_id=insumo.insumo_id))
    BOMActivo.query.session.commit()

    html = client.get(f"/activos/{activo.activo_id}/confirmar_eliminar").get_data(as_text=True)
    assert "También se eliminarán: 1 ítem del BOM de activo" in html

    r = client.post(f"/activos/{activo.activo_id}/confirmar_eliminar")
    assert r.status_code == 302
    assert BOMActivo.query.count() == 0


def test_activo_con_medidores_no_se_borra(client, medidor):
    r = client.post(f"/activos/{medidor.activo_id}/confirmar_eliminar")
    assert r.status_code == 409
    assert "1 medidor" in r.get_data(as_text=True)
    assert Activo.query.count() == 1


# ---------------------------------------------------------------------------
# Medidores y lecturas
# ---------------------------------------------------------------------------

def _lectura(db, medidor, fecha, valor):
    return _guardar(db, LecturaMedidor(medidor_id=medidor.medidor_id, fecha_lectura=fecha, valor=valor))


def test_valor_actual_es_la_ultima_lectura(db, medidor):
    assert medidor.valor_actual == 100  # sin lecturas: el valor inicial

    _lectura(db, medidor, datetime(2026, 3, 1), 250)
    _lectura(db, medidor, datetime(2026, 1, 1), 150)  # cargada después, pero es más vieja
    db.session.expire_all()
    assert db.session.get(Medidor, medidor.medidor_id).valor_actual == 250


def test_valor_actual_no_se_edita(client, medidor):
    form = client.get(f"/medidores/{medidor.medidor_id}/editar").get_data(as_text=True)
    assert 'name="valor_actual"' not in form

    r = client.patch(f"/api/medidores/{medidor.medidor_id}", json={"valor_actual": 5})
    assert r.status_code == 400
    assert "valor_actual" in r.get_json()["errors"]


def test_crear_lectura_desde_el_medidor(client, medidor):
    """Antes daba 500: la fecha llegaba como texto (error 1 del diagnóstico)."""
    r = client.post(f"/lecturas_medidor/crear?medidor_id={medidor.medidor_id}", data={
        "fecha_lectura": "2026-05-10", "valor": "312,5", "origen": "manual",
    })
    assert r.status_code == 302
    assert f"/medidores/{medidor.medidor_id}?seccion=lecturas_medidor" in r.headers["Location"]

    detalle = client.get(f"/medidores/{medidor.medidor_id}").get_data(as_text=True)
    assert "312.5" in detalle


def test_medidor_con_lecturas_no_se_borra(client, db, medidor):
    _lectura(db, medidor, datetime(2026, 1, 1), 150)
    assert client.post(f"/medidores/{medidor.medidor_id}/confirmar_eliminar").status_code == 409


# ---------------------------------------------------------------------------
# Insumos y stock
# ---------------------------------------------------------------------------

def test_stock_total_en_el_listado(client, db, insumo, ubicacion, sector):
    from app.models.ubicaciones_models import Ubicacion

    otra = _guardar(db, Ubicacion(nombre_ubicacion="Galpón 2", sector_id=sector.sector_id))
    _guardar(db, StockInsumo(insumo_id=insumo.insumo_id, ubicacion_id=ubicacion.ubicacion_id, cantidad=4),
             StockInsumo(insumo_id=insumo.insumo_id, ubicacion_id=otra.ubicacion_id, cantidad=6))
    db.session.expire_all()
    assert db.session.get(Insumo, insumo.insumo_id).stock_total == 10

    html = client.get("/insumos").get_data(as_text=True)
    assert "Stock total" in html and "10.0" in html


def test_stock_sin_sector_y_unico_por_ubicacion(client, insumo, ubicacion):
    assert "sector_id" not in REGISTRY["stock_insumo"].fields

    datos = {"ubicacion_id": ubicacion.ubicacion_id, "cantidad": "3"}
    url = f"/stock_insumo/crear?insumo_id={insumo.insumo_id}"
    assert client.post(url, data=datos).status_code == 302
    r = client.post(url, data=datos)
    assert r.status_code == 400
    assert "Ya existe" in r.get_data(as_text=True)


def test_insumo_con_stock_no_se_borra(client, db, insumo, ubicacion):
    _guardar(db, StockInsumo(insumo_id=insumo.insumo_id, ubicacion_id=ubicacion.ubicacion_id, cantidad=1))
    assert client.post(f"/insumos/{insumo.insumo_id}/confirmar_eliminar").status_code == 409


def test_marca_en_uso_por_insumos_no_se_borra(client, db, insumo):
    """Antes SQLAlchemy dejaba el insumo sin marca, en silencio."""
    marca = _guardar(db, Marca(nombre_marca="Fram"))
    insumo.marca_id = marca.marca_id
    db.session.commit()
    assert client.post(f"/marcas/{marca.marca_id}/confirmar_eliminar").status_code == 409
    assert db.session.get(Insumo, insumo.insumo_id).marca_id == marca.marca_id


def test_tipos_dependen_de_la_categoria(client):
    """El formulario filtra los tipos según la categoría elegida (data-extra)."""
    form = client.get("/insumos/crear").get_data(as_text=True)
    assert 'data-extra="categoria_insumo_id"' in form


# ---------------------------------------------------------------------------
# Marcas y modelos
# ---------------------------------------------------------------------------

def test_borrar_marca_borra_sus_modelos_y_su_bom(client, db, modelo, insumo):
    _guardar(db, BOMModelo(modelo_id=modelo.modelo_id, insumo_id=insumo.insumo_id))
    r = client.post(f"/marcas/{modelo.marca_id}/confirmar_eliminar")
    assert r.status_code == 302
    assert Modelo.query.count() == 0 and BOMModelo.query.count() == 0


def test_marca_con_modelo_en_uso_no_se_borra(client, activo):
    assert client.post(f"/marcas/{activo.marca_id}/confirmar_eliminar").status_code == 409


def test_modelo_unico_por_marca(client, modelo):
    r = client.post(f"/modelos/crear?marca_id={modelo.marca_id}", data={"nombre_modelo": "6110J"})
    assert r.status_code == 400


# ---------------------------------------------------------------------------
# BOM
# ---------------------------------------------------------------------------

def test_bom_desde_el_insumo_vuelve_al_insumo(client, insumo, modelo):
    """El BOM de modelo cuelga de dos padres: se puede cargar desde el insumo."""
    form = client.get(f"/bom_modelo/crear?insumo_id={insumo.insumo_id}").get_data(as_text=True)
    assert f'<option value="{insumo.insumo_id}"' in form

    r = client.post(f"/bom_modelo/crear?insumo_id={insumo.insumo_id}", data={
        "modelo_id": modelo.modelo_id, "cantidad": "1", "es_equivalencia": "False",
    })
    assert r.status_code == 302
    assert r.headers["Location"].endswith(f"/insumos/{insumo.insumo_id}?seccion=bom_modelo")
    b = BOMModelo.query.one()
    assert (b.insumo_id, b.es_equivalencia) == (insumo.insumo_id, False)


def test_bom_final_y_compatibilidad(client, db, activo, modelo):
    original = _insumo(db, "F-001", "Filtro original")
    alternativo = _insumo(db, "F-002", "Filtro alternativo")
    propio = _insumo(db, "F-003", "Filtro extra")
    _guardar(db, BOMModelo(modelo_id=modelo.modelo_id, insumo_id=original.insumo_id, cantidad=1))
    _guardar(db,
             BOMActivo(activo_id=activo.activo_id, insumo_id=alternativo.insumo_id,
                       reemplaza_insumo_modelo_id=original.insumo_id, es_equivalencia=True),
             BOMActivo(activo_id=activo.activo_id, insumo_id=propio.insumo_id))

    html = client.get(f"/activos/{activo.activo_id}?seccion=bom_final").get_data(as_text=True)
    assert "F-002 · Filtro alternativo" in html
    assert "Reemplaza a F-001 · Filtro original" in html
    assert "F-003 · Filtro extra" in html

    # El original ya no aplica a este activo (lo reemplazó); el alternativo sí.
    html = client.get(f"/insumos/{original.insumo_id}?seccion=compatibilidad_final").get_data(as_text=True)
    assert "Tractor 1" not in html
    html = client.get(f"/insumos/{alternativo.insumo_id}?seccion=compatibilidad_final").get_data(as_text=True)
    assert "Tractor 1" in html and "BOM del activo" in html


# ---------------------------------------------------------------------------
# Empleados y proveedores (herencia de Recurso)
# ---------------------------------------------------------------------------

def test_crear_empleado(client, sector):
    r = client.post("/empleados/crear", data={
        "nombre": "Juan", "apellido": "Gómez", "sector_id": sector.sector_id,
        "estado_recurso_id": EstadoRecurso.query.first().estado_recurso_id,
    })
    assert r.status_code == 302
    e = Empleado.query.one()
    assert e.tipo_recurso == "interno"
    assert "Taller" in client.get("/empleados").get_data(as_text=True)


def test_sector_con_empleados_no_se_borra(client, sector):
    from app.core.db import db

    _guardar(db, Empleado(nombre="A", apellido="B", estado_recurso_id=1,
                                               sector_id=sector.sector_id))
    assert client.post(f"/sectores/{sector.sector_id}/confirmar_eliminar").status_code == 409


def test_borrar_proveedor_borra_sus_contactos(client, db):
    p = _guardar(db, Proveedor(razon_social="Repuestos SA", estado_recurso_id=1))
    r = client.post(f"/contactos_proveedor/crear?proveedor_id={p.recurso_id}",
                    data={"nombre_contacto": "Laura"})
    assert r.status_code == 302
    assert client.post(f"/proveedores/{p.recurso_id}/confirmar_eliminar").status_code == 302
    assert ContactoProveedor.query.count() == 0


# ---------------------------------------------------------------------------
# API y CSV
# ---------------------------------------------------------------------------

def test_api_devuelve_los_calculados(client, medidor, insumo):
    assert client.get(f"/api/medidores/{medidor.medidor_id}").get_json()["valor_actual"] == 100
    assert client.get(f"/api/insumos/{insumo.insumo_id}").get_json()["stock_total"] == 0


def test_importar_insumos_por_nombre(app, db):
    from app.crud.intercambio.csv_entidades import exportar, importar

    csv = "Código;Descripción;Categoría\nF-9;Filtro de aire;Filtros\n".encode()
    resultado = importar(REGISTRY["insumos"], csv)
    assert resultado.ok, resultado.resumen()
    assert Insumo.query.filter_by(codigo="F-9").one().categoria_insumo.nombre_categoria == "Filtros"

    # Reimportar lo exportado no cambia nada (el stock total se ignora: es calculado).
    resultado = importar(REGISTRY["insumos"], exportar(REGISTRY["insumos"]))
    assert resultado.ok and resultado.sin_cambios == 1
    assert "Stock total" in resultado.columnas_ignoradas


# ---------------------------------------------------------------------------
# Selects dependientes: modelo ↔ marca, ubicación ↔ sector
# ---------------------------------------------------------------------------

def test_dependencias_inferidas_del_modelo():
    campos = REGISTRY["activos"].fields
    assert (campos["modelo_id"].depende_de, campos["modelo_id"].depende_fk) == ("marca_id", "marca_id")
    assert campos["ubicacion_id"].depende_de == "sector_id"
    assert REGISTRY["insumos"].fields["tipo_insumo_id"].depende_de == "categoria_insumo_id"


def test_ubicaciones_repetidas_se_distinguen_por_sector(client, db, ubicacion, estado_sector_activo):
    from app.models.sectores_models import Sector
    from app.models.ubicaciones_models import Ubicacion

    otro = _guardar(db, Sector(nombre_sector="Depósito", centro_costo="CC-2",
                               estado_sector_id=estado_sector_activo.estado_sector_id))
    _guardar(db, Ubicacion(nombre_ubicacion="Galpón 1", sector_id=otro.sector_id))
    form = client.get("/activos/crear").get_data(as_text=True)
    assert "Galpón 1 (Taller)" in form and "Galpón 1 (Depósito)" in form
    assert f'data-extra="sector_id"' in form


def _datos_activo(**extra):
    cat = CategoriaActivo.query.first()
    return {"numero_activo": "N-1", "descripcion": "Equipo", "categoria_activo_id": cat.categoria_activo_id,
            "estado_activo_id": 1, **extra}


def test_marca_y_sector_se_completan_solos(client, modelo, ubicacion):
    r = client.post("/activos/crear", data=_datos_activo(
        modelo_id=modelo.modelo_id, ubicacion_id=ubicacion.ubicacion_id))
    assert r.status_code == 302
    a = Activo.query.filter_by(numero_activo="N-1").one()
    assert (a.marca_id, a.sector_id) == (modelo.marca_id, ubicacion.sector_id)


def test_modelo_de_otra_marca_se_rechaza(client, db, modelo):
    otra = _guardar(db, Marca(nombre_marca="Massey"))
    r = client.post("/activos/crear", data=_datos_activo(marca_id=otra.marca_id, modelo_id=modelo.modelo_id))
    assert r.status_code == 400
    assert "«6110J» no pertenece a «Massey» (marca)" in r.get_data(as_text=True)


def test_api_cambiar_solo_el_sector_choca_con_la_ubicacion(client, db, activo, ubicacion, estado_sector_activo):
    from app.models.sectores_models import Sector

    activo.ubicacion_id = ubicacion.ubicacion_id
    db.session.commit()
    otro = _guardar(db, Sector(nombre_sector="Depósito", centro_costo="CC-2",
                               estado_sector_id=estado_sector_activo.estado_sector_id))
    r = client.patch(f"/api/activos/{activo.activo_id}", json={"sector_id": otro.sector_id})
    assert r.status_code == 400
    assert "ubicacion_id" in r.get_json()["errors"]

    # Cambiando los dos juntos (o sacando la ubicación) sí se puede.
    r = client.patch(f"/api/activos/{activo.activo_id}", json={"sector_id": otro.sector_id, "ubicacion_id": None})
    assert r.status_code == 200


def test_numeros_de_serie_y_motor_unicos(client, activo):
    activo.numero_serie = "S-1"
    from app.core.db import db
    db.session.commit()
    r = client.post("/activos/crear", data=_datos_activo(numero_serie="S-1"))
    assert r.status_code == 400
    assert "Número de serie" in r.get_data(as_text=True)
    # Vacío no cuenta como repetido.
    assert client.post("/activos/crear", data=_datos_activo(numero_serie="", numero_motor="")).status_code == 302


def test_importar_activos_por_numero(app, db, modelo):
    from app.crud.intercambio.csv_entidades import importar

    csv = ("Número de activo;Descripción;Categoría;Modelo;Estado\n"
           "T-01;Tractor;Tractor;6110J;Activo\n").encode()
    resultado = importar(REGISTRY["activos"], csv)
    assert resultado.ok, resultado.resumen()
    assert Activo.query.filter_by(numero_activo="T-01").one().marca_id == modelo.marca_id

    otra = _guardar(db, Marca(nombre_marca="Massey"))
    csv = ("Número de activo;Descripción;Categoría;Marca;Modelo;Estado\n"
           "T-02;Tractor;Tractor;Massey;6110J;Activo\n").encode()
    resultado = importar(REGISTRY["activos"], csv)
    assert not resultado.ok and resultado.errores[0][1] == "modelo_id"
    assert Activo.query.filter_by(numero_activo="T-02").count() == 0
    assert otra
