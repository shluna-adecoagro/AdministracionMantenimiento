"""
Fase 9: planes preventivos, categoría del modelo y tipo de medidor.

Ejemplo de los tests (el del diseño): las palas tienen un plan parcial cada
300 h y uno completo cada 1200 h que incluye al parcial (ciclo 4).
"""
import re

import pytest

from app.crud.entidades import REGISTRY
from app.crud.intercambio.csv_entidades import importar
from app.models.activos_models import Activo, EstadoActivo
from app.models.marcas_modelos_models import Marca, Modelo
from app.models.materiales_models import CategoriaMaterial, Material
from app.models.preventivos_models import (
    PlanModelo,
    PlanModeloMaterial,
    PlanPreventivo,
    PlanPreventivoTarea,
    TareaPreventivo,
)
from app.models.unidadmedida_models import TipoUnidad, UnidadMedida


# ---------------------------------------------------------------------------
# Datos
# ---------------------------------------------------------------------------

def _guardar(db, *objetos):
    db.session.add_all(objetos)
    db.session.commit()
    return objetos[0] if len(objetos) == 1 else objetos


def _tipo_unidad(nombre):
    return TipoUnidad.query.filter_by(nombre_tipo=nombre).one().tipo_unidad_id


@pytest.fixture
def unidades(db):
    """Horas (horómetro), km (odómetro), meses y litros (sin tipo de medidor)."""
    return {
        "h": _guardar(db, UnidadMedida(nombre_unidad="Horas", abreviatura="h", tipo_medidor="Horómetro",
                                       tipo_unidad_id=_tipo_unidad("Tiempo"))),
        "km": _guardar(db, UnidadMedida(nombre_unidad="Kilómetros", abreviatura="km", tipo_medidor="Odómetro",
                                        tipo_unidad_id=_tipo_unidad("Longitud"))),
        "mes": _guardar(db, UnidadMedida(nombre_unidad="Meses", abreviatura="mes",
                                         tipo_unidad_id=_tipo_unidad("Tiempo"))),
        "l": _guardar(db, UnidadMedida(nombre_unidad="Litros", abreviatura="l",
                                       tipo_unidad_id=_tipo_unidad("Volumen"))),
    }


@pytest.fixture
def palas(categorias_activo):
    return categorias_activo["Pala cargadora"]


@pytest.fixture
def modelo_pala(db, palas):
    marca = _guardar(db, Marca(nombre_marca="CAT"))
    return _guardar(db, Modelo(nombre_modelo="950", marca_id=marca.marca_id,
                               categoria_activo_id=palas.categoria_activo_id))


@pytest.fixture
def modelo_tractor(db, categorias_activo):
    marca = _guardar(db, Marca(nombre_marca="John Deere"))
    return _guardar(db, Modelo(nombre_modelo="6110J", marca_id=marca.marca_id,
                               categoria_activo_id=categorias_activo["Tractor"].categoria_activo_id))


def _plan(client, nombre, categoria, **extra):
    r = client.post("/api/planes_preventivos", json={
        "nombre_plan": nombre, "categoria_activo_id": categoria.categoria_activo_id, **extra})
    return r


@pytest.fixture
def parcial(client, palas, unidades):
    r = _plan(client, "Parcial palas", palas, periodo_uso=300, unidad_uso_id=unidades["h"].unidad_medida_id)
    assert r.status_code == 201, r.get_json()
    return PlanPreventivo.query.filter_by(nombre_plan="Parcial palas").one()


@pytest.fixture
def completo(client, palas, unidades, parcial):
    r = _plan(client, "Completo palas", palas, periodo_uso=1200, unidad_uso_id=unidades["h"].unidad_medida_id,
              plan_inferior_id=parcial.plan_preventivo_id)
    assert r.status_code == 201, r.get_json()
    return PlanPreventivo.query.filter_by(nombre_plan="Completo palas").one()


@pytest.fixture
def tareas(db):
    nombres = ["Cambio de aceite de motor", "Cambio de filtro de aceite", "Cambio de aceite hidráulico"]
    return {n: _guardar(db, TareaPreventivo(nombre_tarea=n, horas_estimadas=1)) for n in nombres}


def _tarea_en_plan(client, plan, tarea, paso=1):
    return client.post("/api/plan_preventivo_tareas", json={
        "plan_preventivo_id": plan.plan_preventivo_id, "tarea_preventivo_id": tarea.tarea_preventivo_id,
        "paso": paso})


def _material(db, codigo, descripcion, unidad=None):
    cat = CategoriaMaterial.query.first().categoria_material_id
    return _guardar(db, Material(codigo=codigo, descripcion=descripcion, categoria_material_id=cat,
                                 unidad_medida_id=unidad.unidad_medida_id if unidad else None))


def _plan_modelo(client, plan, modelo):
    return client.post("/api/planes_modelo", json={
        "plan_preventivo_id": plan.plan_preventivo_id, "modelo_id": modelo.modelo_id})


def _material_en_plan(client, plan_modelo_id, material, cantidad=1, tarea=None):
    return client.post("/api/plan_modelo_materiales", json={
        "plan_modelo_id": plan_modelo_id, "material_id": material.material_id, "cantidad": cantidad,
        "tarea_preventivo_id": tarea.tarea_preventivo_id if tarea else None})


def _errores(r):
    return r.get_json()["errors"]


# ---------------------------------------------------------------------------
# Tipo de medidor
# ---------------------------------------------------------------------------

def test_tipo_de_medidor_se_calcula_de_la_unidad(db, client, unidades, modelo_tractor, categorias_activo):
    activo = _guardar(db, Activo(numero_activo="T-1", descripcion="Tractor",
                                 categoria_activo_id=categorias_activo["Tractor"].categoria_activo_id,
                                 estado_activo_id=EstadoActivo.query.first().estado_activo_id))
    r = client.post("/api/medidores", json={"nombre_medidor": "Horas motor", "activo_id": activo.activo_id,
                                            "unidad_medida_id": unidades["h"].unidad_medida_id})
    assert r.status_code == 201
    assert r.get_json()["tipo_medidor"] == "Horómetro"
    assert REGISTRY["medidores"].fields["tipo_medidor"].solo_lectura
    assert "Horómetro" in client.get(f"/activos/{activo.activo_id}?seccion=medidores").get_data(as_text=True)

    # Una unidad sin tipo de medidor no se ofrece ni se acepta.
    form = client.get(f"/medidores/crear?activo_id={activo.activo_id}").get_data(as_text=True)
    select = form.split('id="unidad_medida_id"')[1].split("</select>")[0]
    assert "Horas" in select and "Litros" not in select
    r = client.post("/api/medidores", json={"nombre_medidor": "Gasoil", "activo_id": activo.activo_id,
                                            "unidad_medida_id": unidades["l"].unidad_medida_id})
    assert r.status_code == 400
    assert "«Litros» no es una opción válida" in _errores(r)["unidad_medida_id"]


def test_tipo_de_medidor_sugiere_los_habituales_y_los_cargados(db, client, unidades):
    unidades["l"].tipo_medidor = "Caudalímetro de gasoil"
    db.session.commit()
    form = client.get("/unidades_medida/crear").get_data(as_text=True)
    for texto in ("Horómetro", "Odómetro", "Contador de arranques", "Caudalímetro de gasoil"):
        assert f'<option value="{texto}">' in form
    assert '<option value="None">' not in form  # las unidades sin tipo no suman una sugerencia vacía


# ---------------------------------------------------------------------------
# Categoría del modelo
# ---------------------------------------------------------------------------

def test_modelo_pide_categoria(client, db, categorias_activo):
    marca = _guardar(db, Marca(nombre_marca="CAT"))
    r = client.post("/api/modelos", json={"nombre_modelo": "950", "marca_id": marca.marca_id})
    assert r.status_code == 400 and "categoria_activo_id" in _errores(r)
    html = client.get(f"/categorias_activo/{categorias_activo['Tractor'].categoria_activo_id}").get_data(as_text=True)
    assert "Modelos" in html and "Planes preventivos" in html  # pestañas de la categoría


def test_activo_con_modelo_de_otra_categoria(client, modelo_pala, categorias_activo):
    datos = {"numero_activo": "P-1", "descripcion": "Pala", "estado_activo_id": 1, "modelo_id": modelo_pala.modelo_id}
    r = client.post("/api/activos", json={**datos, "categoria_activo_id": categorias_activo["Tractor"].categoria_activo_id})
    assert r.status_code == 400
    assert "«950» no pertenece a «Tractor»" in _errores(r)["modelo_id"]

    r = client.post("/api/activos", json={**datos, "categoria_activo_id": modelo_pala.categoria_activo_id})
    assert r.status_code == 201
    assert r.get_json()["marca_id"] == modelo_pala.marca_id  # se completa, como antes


def test_formulario_del_activo_filtra_modelos_por_categoria_y_marca(client, modelo_pala):
    form = client.get("/activos/crear").get_data(as_text=True)
    opcion = re.search(r'<option value="%d"[^>]*>' % modelo_pala.modelo_id,
                       form.split('id="modelo_id"')[1]).group(0)
    assert f'"categoria_activo_id": {modelo_pala.categoria_activo_id}' in opcion
    assert f'"marca_id": {modelo_pala.marca_id}' in opcion
    assert "950 (Pala cargadora, CAT)" in form


def test_cambiar_categoria_del_modelo_con_activos(client, db, modelo_pala, categorias_activo):
    tractor = categorias_activo["Tractor"].categoria_activo_id
    pala = categorias_activo["Pala cargadora"].categoria_activo_id
    # Sin activos ni planes, se puede.
    assert client.patch(f"/api/modelos/{modelo_pala.modelo_id}", json={"categoria_activo_id": tractor}).status_code == 200
    assert client.patch(f"/api/modelos/{modelo_pala.modelo_id}", json={"categoria_activo_id": pala}).status_code == 200

    _guardar(db, Activo(numero_activo="P-1", descripcion="Pala", categoria_activo_id=pala,
                        modelo_id=modelo_pala.modelo_id, marca_id=modelo_pala.marca_id, estado_activo_id=1))
    r = client.patch(f"/api/modelos/{modelo_pala.modelo_id}", json={"categoria_activo_id": tractor})
    assert r.status_code == 400
    assert "1 activo de este modelo es de otra categoría" in _errores(r)["categoria_activo_id"]


# ---------------------------------------------------------------------------
# Plan preventivo: períodos
# ---------------------------------------------------------------------------

def test_plan_por_uso_por_tiempo_o_los_dos(client, palas, unidades, categorias_activo):
    h, mes = unidades["h"].unidad_medida_id, unidades["mes"].unidad_medida_id
    assert _plan(client, "Solo horas", palas, periodo_uso=300, unidad_uso_id=h).status_code == 201
    assert _plan(client, "Solo meses", palas, periodo_tiempo=6, unidad_tiempo_id=mes).status_code == 201
    r = _plan(client, "Vehículos", categorias_activo["Pickup"], periodo_uso=10000,
              unidad_uso_id=unidades["km"].unidad_medida_id, periodo_tiempo=12, unidad_tiempo_id=mes)
    assert r.status_code == 201
    assert r.get_json()["vigente"] is True  # Sí por defecto


@pytest.mark.parametrize("datos, campo, mensaje", [
    ({}, "periodo_uso", "al menos un período"),
    ({"periodo_uso": 300}, "periodo_uso", "va con su unidad"),
    ({"periodo_uso": 0, "unidad_uso_id": "h"}, "periodo_uso", "mayor que cero"),
    ({"periodo_uso": 300, "unidad_uso_id": "l"}, "unidad_uso_id", "no es una opción válida"),
    ({"periodo_tiempo": 6, "unidad_tiempo_id": "km"}, "unidad_tiempo_id", "no es una opción válida"),
])
def test_periodos_invalidos(client, palas, unidades, datos, campo, mensaje):
    datos = {k: unidades[v].unidad_medida_id if k.startswith("unidad") else v for k, v in datos.items()}
    r = _plan(client, "Plan", palas, **datos)
    assert r.status_code == 400
    assert mensaje in _errores(r)[campo]
    assert PlanPreventivo.query.count() == 0


def test_formulario_ofrece_solo_las_unidades_que_corresponden(client, unidades):
    form = client.get("/planes_preventivos/crear").get_data(as_text=True)
    uso = form.split('id="unidad_uso_id"')[1].split("</select>")[0]
    tiempo = form.split('id="unidad_tiempo_id"')[1].split("</select>")[0]
    assert "Horas" in uso and "Kilómetros" in uso and "Meses" not in uso and "Litros" not in uso
    assert "Meses" in tiempo and "Horas" in tiempo and "Kilómetros" not in tiempo


# ---------------------------------------------------------------------------
# Inclusión (el completo incluye al parcial)
# ---------------------------------------------------------------------------

def test_completo_incluye_al_parcial_con_ciclo(client, completo):
    assert completo.ciclo == 4
    html = client.get("/planes_preventivos").get_data(as_text=True)
    assert "Completo palas" in html and "Parcial palas" in html


@pytest.mark.parametrize("datos, mensaje", [
    ({"periodo_uso": 1000}, "tiene que ser un múltiplo"),
    ({"periodo_uso": 300}, "tiene que ser un múltiplo"),  # igual: el factor es 1
    ({"periodo_uso": 1200, "unidad": "km"}, "misma unidad"),
    ({"periodo_tiempo": 12, "unidad_tiempo": "mes"}, "tiene que estar en los dos planes"),
])
def test_inclusion_invalida(client, palas, unidades, parcial, datos, mensaje):
    cuerpo = {"plan_inferior_id": parcial.plan_preventivo_id}
    if "periodo_uso" in datos:
        cuerpo.update(periodo_uso=datos["periodo_uso"], unidad_uso_id=unidades[datos.get("unidad", "h")].unidad_medida_id)
    if "periodo_tiempo" in datos:
        cuerpo.update(periodo_tiempo=datos["periodo_tiempo"],
                      unidad_tiempo_id=unidades[datos["unidad_tiempo"]].unidad_medida_id)
    r = _plan(client, "Completo", palas, **cuerpo)
    assert r.status_code == 400
    assert mensaje in _errores(r)["plan_inferior_id"]


def test_inclusion_con_dos_periodos_misma_proporcion(client, categorias_activo, unidades):
    pickup, km, mes = categorias_activo["Pickup"], unidades["km"].unidad_medida_id, unidades["mes"].unidad_medida_id
    _plan(client, "Service", pickup, periodo_uso=10000, unidad_uso_id=km, periodo_tiempo=12, unidad_tiempo_id=mes)
    inf = PlanPreventivo.query.filter_by(nombre_plan="Service").one().plan_preventivo_id
    r = _plan(client, "Mayor", pickup, periodo_uso=40000, unidad_uso_id=km, periodo_tiempo=24,
              unidad_tiempo_id=mes, plan_inferior_id=inf)
    assert r.status_code == 400 and "misma proporción" in _errores(r)["plan_inferior_id"]
    r = _plan(client, "Mayor", pickup, periodo_uso=40000, unidad_uso_id=km, periodo_tiempo=48,
              unidad_tiempo_id=mes, plan_inferior_id=inf)
    assert r.status_code == 201 and r.get_json()["ciclo"] == 4


def test_inclusion_de_otra_categoria(client, parcial, categorias_activo, unidades):
    r = _plan(client, "Completo tractores", categorias_activo["Tractor"], periodo_uso=1200,
              unidad_uso_id=unidades["h"].unidad_medida_id, plan_inferior_id=parcial.plan_preventivo_id)
    assert r.status_code == 400 and "no pertenece a «Tractor»" in _errores(r)["plan_inferior_id"]


def test_un_plan_es_incluido_por_un_solo_superior(client, palas, unidades, completo, parcial):
    r = _plan(client, "Otro completo", palas, periodo_uso=600, unidad_uso_id=unidades["h"].unidad_medida_id,
              plan_inferior_id=parcial.plan_preventivo_id)
    assert r.status_code == 409


def test_no_se_puede_incluir_en_circulo(client, completo, parcial):
    r = client.patch(f"/api/planes_preventivos/{parcial.plan_preventivo_id}",
                     json={"plan_inferior_id": completo.plan_preventivo_id})
    assert r.status_code == 400 and "ya incluye a este plan" in _errores(r)["plan_inferior_id"]
    r = client.patch(f"/api/planes_preventivos/{completo.plan_preventivo_id}",
                     json={"plan_inferior_id": completo.plan_preventivo_id})
    assert r.status_code == 400 and "ya incluye a este plan" in _errores(r)["plan_inferior_id"]


def test_cambiar_el_inferior_no_puede_romper_al_superior(client, completo, parcial):
    r = client.patch(f"/api/planes_preventivos/{parcial.plan_preventivo_id}", json={"periodo_uso": 500})
    assert r.status_code == 400 and "«Completo palas» incluye a este plan" in _errores(r)["_general"]
    r = client.patch(f"/api/planes_preventivos/{parcial.plan_preventivo_id}", json={"periodo_uso": 400})
    assert r.status_code == 200
    assert client.get(f"/api/planes_preventivos/{completo.plan_preventivo_id}").get_json()["ciclo"] == 3


def test_plan_incluido_no_se_borra(client, completo, parcial):
    assert client.delete(f"/api/planes_preventivos/{parcial.plan_preventivo_id}").status_code == 409
    assert client.delete(f"/api/planes_preventivos/{completo.plan_preventivo_id}").status_code in (200, 204)
    assert client.delete(f"/api/planes_preventivos/{parcial.plan_preventivo_id}").status_code in (200, 204)


# ---------------------------------------------------------------------------
# Tareas: el superior hereda las del inferior
# ---------------------------------------------------------------------------

def test_tareas_heredadas(client, completo, parcial, tareas):
    assert _tarea_en_plan(client, parcial, tareas["Cambio de aceite de motor"], 1).status_code == 201
    assert _tarea_en_plan(client, parcial, tareas["Cambio de filtro de aceite"], 2).status_code == 201
    assert _tarea_en_plan(client, completo, tareas["Cambio de aceite hidráulico"], 1).status_code == 201

    html = client.get(f"/planes_preventivos/{completo.plan_preventivo_id}?seccion=todas_las_tareas").get_data(as_text=True)
    posiciones = [html.index(t) for t in ("Cambio de aceite de motor", "Cambio de filtro de aceite",
                                          "Cambio de aceite hidráulico")]
    assert posiciones == sorted(posiciones)  # primero las heredadas, en su orden
    propias = client.get(f"/planes_preventivos/{completo.plan_preventivo_id}?seccion=plan_preventivo_tareas")
    assert "Cambio de aceite de motor" not in propias.get_data(as_text=True)


def test_tarea_repetida_en_la_cadena(client, completo, parcial, tareas):
    aceite = tareas["Cambio de aceite de motor"]
    _tarea_en_plan(client, parcial, aceite)
    r = _tarea_en_plan(client, completo, aceite)
    assert r.status_code == 400
    assert "«Cambio de aceite de motor» está en «Parcial palas» y en «Completo palas»" in _errores(r)["tarea_preventivo_id"]
    assert PlanPreventivoTarea.query.count() == 1


def test_incluir_un_plan_con_tareas_repetidas(client, palas, unidades, parcial, tareas):
    aceite = tareas["Cambio de aceite de motor"]
    _tarea_en_plan(client, parcial, aceite)
    _plan(client, "Completo", palas, periodo_uso=1200, unidad_uso_id=unidades["h"].unidad_medida_id)
    completo = PlanPreventivo.query.filter_by(nombre_plan="Completo").one()
    _tarea_en_plan(client, completo, aceite)
    r = client.patch(f"/api/planes_preventivos/{completo.plan_preventivo_id}",
                     json={"plan_inferior_id": parcial.plan_preventivo_id})
    assert r.status_code == 400 and "está en «Parcial palas» y en «Completo»" in _errores(r)["plan_inferior_id"]


def test_tarea_en_uso_no_se_borra(client, parcial, tareas):
    aceite = tareas["Cambio de aceite de motor"]
    _tarea_en_plan(client, parcial, aceite)
    assert client.post(f"/tareas_preventivo/{aceite.tarea_preventivo_id}/confirmar_eliminar").status_code == 409


# ---------------------------------------------------------------------------
# Plan del modelo y sus materiales
# ---------------------------------------------------------------------------

def test_plan_del_modelo_de_la_misma_categoria(client, parcial, modelo_pala, modelo_tractor):
    r = _plan_modelo(client, parcial, modelo_tractor)
    assert r.status_code == 400
    assert "«6110J» es de la categoría «Tractor» y el plan, de «Pala cargadora»" in _errores(r)["modelo_id"]

    r = _plan_modelo(client, parcial, modelo_pala)
    assert r.status_code == 201
    d = r.get_json()
    assert d["nombre"] == "Parcial palas — 950"
    assert (d["categoria_activo_id"], d["marca_id"]) == (parcial.categoria_activo_id, modelo_pala.marca_id)
    assert d["vigente"] is True
    assert _plan_modelo(client, parcial, modelo_pala).status_code == 409  # una vez por modelo

    # Se ve desde el plan y desde el modelo.
    assert "950" in client.get(f"/planes_preventivos/{parcial.plan_preventivo_id}?seccion=planes_modelo").get_data(as_text=True)
    assert "Parcial palas" in client.get(f"/modelos/{modelo_pala.modelo_id}?seccion=planes_modelo").get_data(as_text=True)


def test_formulario_del_plan_del_modelo_filtra_por_categoria(client, parcial, modelo_pala):
    form = client.get("/planes_modelo/crear").get_data(as_text=True)
    assert 'id="categoria_activo_id"' in form and 'name="categoria_activo_id"' not in form  # filtro
    assert 'id="marca_id"' in form and 'name="marca_id"' not in form
    plan = form.split('id="plan_preventivo_id"')[1].split("</select>")[0]
    assert f'"categoria_activo_id": {parcial.categoria_activo_id}' in plan
    orden = [form.index(f'id="{c}"') for c in ("categoria_activo_id", "plan_preventivo_id", "marca_id", "modelo_id")]
    assert orden == sorted(orden)


def test_materiales_heredados_y_tarea_del_plan(client, db, completo, parcial, modelo_pala, tareas, unidades):
    _tarea_en_plan(client, parcial, tareas["Cambio de aceite de motor"])
    _tarea_en_plan(client, completo, tareas["Cambio de aceite hidráulico"])
    pm_parcial = _plan_modelo(client, parcial, modelo_pala).get_json()["plan_modelo_id"]
    pm_completo = _plan_modelo(client, completo, modelo_pala).get_json()["plan_modelo_id"]
    aceite = _material(db, "A-15W40", "Aceite 15W40", unidades["l"])
    hidraulico = _material(db, "A-HID", "Aceite hidráulico", unidades["l"])

    r = _material_en_plan(client, pm_parcial, aceite, 20, tareas["Cambio de aceite de motor"])
    assert r.status_code == 201
    assert r.get_json()["unidad_medida_id_label"] == "Litros"  # la del material

    # La tarea tiene que estar en el plan: la del completo no está en el parcial...
    r = _material_en_plan(client, pm_parcial, hidraulico, 40, tareas["Cambio de aceite hidráulico"])
    assert r.status_code == 400 and "no está en el plan «Parcial palas»" in _errores(r)["tarea_preventivo_id"]
    # ...pero la del parcial sí está (heredada) en el completo.
    assert _material_en_plan(client, pm_completo, hidraulico, 40, tareas["Cambio de aceite de motor"]).status_code == 201

    # Un material heredado no se repite en el superior.
    r = _material_en_plan(client, pm_completo, aceite, 20)
    assert r.status_code == 400 and "«Aceite 15W40» está en «Parcial palas»" in _errores(r)["material_id"]

    html = client.get(f"/planes_modelo/{pm_completo}?seccion=todos_los_materiales").get_data(as_text=True)
    assert html.index("Aceite 15W40") < html.index("Aceite hidráulico")
    assert "20 l" in html and "40 l" in html

    # El material en uso no se borra; desde el material se ve dónde se usa.
    assert client.post(f"/materiales/{aceite.material_id}/confirmar_eliminar").status_code == 409
    assert "Parcial palas — 950" in client.get(
        f"/materiales/{aceite.material_id}?seccion=plan_modelo_materiales").get_data(as_text=True)


def test_borrar_plan_borra_tareas_modelos_y_materiales(client, db, parcial, modelo_pala, tareas):
    _tarea_en_plan(client, parcial, tareas["Cambio de aceite de motor"])
    pm = _plan_modelo(client, parcial, modelo_pala).get_json()["plan_modelo_id"]
    _material_en_plan(client, pm, _material(db, "F-1", "Filtro"), 1)

    html = client.get(f"/planes_preventivos/{parcial.plan_preventivo_id}/confirmar_eliminar").get_data(as_text=True)
    assert "tareas" in html.lower()
    assert client.delete(f"/api/planes_preventivos/{parcial.plan_preventivo_id}").status_code in (200, 204)
    assert (PlanPreventivoTarea.query.count(), PlanModelo.query.count(), PlanModeloMaterial.query.count()) == (0, 0, 0)


def test_borrar_modelo_borra_sus_planes_del_modelo(client, parcial, modelo_pala):
    _plan_modelo(client, parcial, modelo_pala)
    assert client.delete(f"/api/modelos/{modelo_pala.modelo_id}").status_code in (200, 204)
    assert PlanModelo.query.count() == 0 and PlanPreventivo.query.count() == 1


def test_borrar_categoria_borra_sus_planes(client, db, categorias_activo, unidades):
    galpon = categorias_activo["Galpón"]
    _plan(client, "Inspección anual", galpon, periodo_tiempo=12, unidad_tiempo_id=unidades["mes"].unidad_medida_id)
    assert client.post(f"/categorias_activo/{galpon.categoria_activo_id}/confirmar_eliminar").status_code == 302
    assert PlanPreventivo.query.count() == 0


# ---------------------------------------------------------------------------
# Importación
# ---------------------------------------------------------------------------

def test_importar_planes_tareas_y_materiales(app, db, palas, unidades, modelo_pala, tareas):
    csv = ("Nombre;Categoría de activo;Período por uso;Unidad (uso);Incluye al plan\n"
           "Parcial palas;Pala cargadora;300;Horas;\n").encode()
    r = importar(REGISTRY["planes_preventivos"], csv)
    assert r.ok, r.resumen()
    csv = ("Nombre;Categoría de activo;Período por uso;Unidad (uso);Incluye al plan\n"
           "Completo palas;Pala cargadora;1200;Horas;Parcial palas\n").encode()
    r = importar(REGISTRY["planes_preventivos"], csv)
    assert r.ok, r.resumen()
    assert PlanPreventivo.query.filter_by(nombre_plan="Completo palas").one().ciclo == 4

    csv = ("Plan;Tarea;Paso\n"
           "Parcial palas;Cambio de aceite de motor;1\n"
           "Completo palas;Cambio de aceite hidráulico;1\n").encode()
    r = importar(REGISTRY["plan_preventivo_tareas"], csv)
    assert r.ok, r.resumen()

    csv = "Plan;Modelo\nParcial palas;950\n".encode()
    assert importar(REGISTRY["planes_modelo"], csv).ok

    _material(db, "A-15W40", "Aceite 15W40", unidades["l"])
    csv = ("Plan del modelo;Material;Cantidad;Tarea\n"
           "Parcial palas — 950;Aceite 15W40;20;Cambio de aceite de motor\n").encode()
    r = importar(REGISTRY["plan_modelo_materiales"], csv)
    assert r.ok, r.resumen()
    assert PlanModeloMaterial.query.one().cantidad == 20

    # Reimportar lo exportado no cambia nada.
    from app.crud.intercambio.csv_entidades import exportar
    for entidad in ("planes_preventivos", "plan_preventivo_tareas", "planes_modelo", "plan_modelo_materiales"):
        r = importar(REGISTRY[entidad], exportar(REGISTRY[entidad]))
        assert r.ok and r.sin_cambios and not (r.creados or r.actualizados), (entidad, r.resumen())


def test_importar_respeta_las_reglas(app, db, palas, unidades, tareas):
    csv = ("Nombre;Categoría de activo;Período por uso;Unidad (uso)\n"
           "Parcial;Pala cargadora;300;Litros\n").encode()
    r = importar(REGISTRY["planes_preventivos"], csv)
    assert not r.ok and r.errores[0][1] == "unidad_uso_id"
    assert PlanPreventivo.query.count() == 0


# ---------------------------------------------------------------------------
# Pantallas
# ---------------------------------------------------------------------------

def test_menu_y_pantallas(client, completo, modelo_pala):
    html = client.get("/").get_data(as_text=True)
    assert 'href="/planes_preventivos"' in html and 'href="/tareas_preventivo"' in html
    for seccion in ("datos", "historial", "plan_preventivo_tareas", "planes_modelo", "todas_las_tareas"):
        r = client.get(f"/planes_preventivos/{completo.plan_preventivo_id}?seccion={seccion}")
        assert re.search(rf'seccion={seccion}"\s+class="detalle-tab active', r.get_data(as_text=True)), seccion
    pm = _plan_modelo(client, completo, modelo_pala).get_json()["plan_modelo_id"]
    for seccion in ("plan_modelo_materiales", "todos_los_materiales"):
        r = client.get(f"/planes_modelo/{pm}?seccion={seccion}")
        assert r.status_code == 200


def test_vigente_arranca_en_si(client):
    """El alta muestra el valor por defecto de la columna («Vigente» = Sí)."""
    form = client.get("/planes_preventivos/crear").get_data(as_text=True)
    vigente = form.split('id="vigente"')[1].split("</select>")[0]
    assert re.search(r'value="True"\s+selected', vigente)
