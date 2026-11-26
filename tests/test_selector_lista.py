"""
Selectores con lista (datalist) y activo como «número — descripción».

Una FK o un filtro con muchas opciones se elige tipeando (campo con lista); con
pocas, sigue siendo un <select>. FieldSpec.selector fija uno u otro.
"""
import re

import pytest

from app.crud.core import fk
from app.crud.entidades import REGISTRY
from app.crud.meta.registry import construir_registry
from app.models.activos_models import Activo, CategoriaActivo, EstadoActivo, TipoActivo


def _guardar(db, *objetos):
    db.session.add_all(objetos)
    db.session.commit()
    return objetos[0] if len(objetos) == 1 else objetos


@pytest.fixture
def activos(db, categorias_activo):
    """Una cantidad de activos que supera el umbral (se eligen con lista)."""
    tractor = categorias_activo["Tractor"]
    estado = EstadoActivo.query.first().estado_activo_id
    return _guardar(db, *[
        Activo(numero_activo=f"EQ-{n:02d}", descripcion=f"Tractor {n % 3}",
               categoria_activo_id=tractor.categoria_activo_id, estado_activo_id=estado)
        for n in range(fk.UMBRAL_LISTA + 1)
    ])


def _muchas_categorias(db, cuenta):
    tipo = _guardar(db, TipoActivo(nombre_tipo="Maquinaria", cuenta_id=cuenta.cuenta_id))
    _guardar(db, *[CategoriaActivo(nombre_categoria=f"Categoría {n:02d}", tipo_activo_id=tipo.tipo_activo_id)
                   for n in range(fk.UMBRAL_LISTA + 1)])


def lista(html, id_):
    """Textos de las opciones del <datalist> de un campo."""
    bloque = html[html.index(f'<datalist id="{id_}__lista">'):]
    bloque = bloque[:bloque.index("</datalist>")]
    return re.findall(r'<option value="([^"]*)"', bloque)


# ---------------------------------------------------------------------------
# Activo como «número — descripción»
# ---------------------------------------------------------------------------

def test_activo_se_muestra_con_numero_y_descripcion(app, activos):
    assert activos[0].etiqueta == "EQ-00 — Tractor 0"
    opciones = fk.opciones(REGISTRY["medidores"].fields["activo_id"])
    assert opciones[0]["label"] == "EQ-00 — Tractor 0"


def test_activo_al_importar_por_numero_o_descripcion(app, activos):
    buscador = fk.BuscadorFK(REGISTRY["medidores"].fields["activo_id"])
    assert buscador.buscar("eq-01") == activos[1].activo_id
    assert buscador.buscar("EQ-01 — Tractor 1") == activos[1].activo_id
    with pytest.raises(ValueError, match="usá el ID"):
        buscador.buscar("Tractor 1")  # la descripción se repite


def test_busqueda_de_texto_encuentra_el_activo_por_numero(client, activos):
    from app.models.medidores_models import Medidor
    from app.models.unidadmedida_models import TipoUnidad, UnidadMedida
    from app.core.db import db

    tipo = TipoUnidad.query.filter_by(nombre_tipo="Tiempo").one()
    h = _guardar(db, UnidadMedida(nombre_unidad="Horas", abreviatura="h", tipo_medidor="Horómetro",
                                  tipo_unidad_id=tipo.tipo_unidad_id))
    _guardar(db, Medidor(nombre_medidor="Horómetro A", activo_id=activos[4].activo_id,
                         unidad_medida_id=h.unidad_medida_id),
             Medidor(nombre_medidor="Horómetro B", activo_id=activos[5].activo_id,
                     unidad_medida_id=h.unidad_medida_id))
    html = client.get("/medidores?q=EQ-04").get_data(as_text=True)
    assert "EQ-04 — Tractor 1" in html  # la columna muestra número y descripción
    assert "Horómetro A" in html and "Horómetro B" not in html


# ---------------------------------------------------------------------------
# Cuándo se usa lista y texto de cada opción
# ---------------------------------------------------------------------------

def test_usa_lista_segun_el_largo_o_el_override():
    corta = [{}] * fk.UMBRAL_LISTA
    larga = [{}] * (fk.UMBRAL_LISTA + 1)
    assert not fk.usa_lista({}, corta)
    assert fk.usa_lista({}, larga)
    assert fk.usa_lista({"selector": "lista"}, corta)
    assert not fk.usa_lista({"selector": "select"}, larga)


def test_la_grilla_respeta_el_selector(app, activos):
    """La grilla (fase 13) usa el mismo umbral y el mismo override que formularios y filtros."""
    f = REGISTRY["medidores"].fields["activo_id"]
    assert fk.usa_busqueda(f)  # más de UMBRAL_LISTA activos
    assert not fk.usa_busqueda({**{k: f.get(k) for k in ("fk_model", "fk_filtro")}, "selector": "select"})
    assert fk.usa_busqueda({"fk_model": f.fk_model, "selector": "lista"})


def test_texto_de_cada_opcion_no_se_repite():
    opciones = fk.con_texto([
        {"value": 1, "label": "5090E", "grupo": "John Deere"},
        {"value": 2, "label": "5090E", "grupo": "Deutz"},
        {"value": 3, "label": "Equipo", "grupo": None},
        {"value": 4, "label": "equipo", "grupo": None},
    ])
    assert [o["texto"] for o in opciones] == [
        "5090E (John Deere)", "5090E (Deutz)", "Equipo (ID 3)", "equipo (ID 4)"]


def test_selector_invalido_es_error_del_metamodelo():
    from app.crud.meta.registry import MetamodeloError
    from app.models.sectores_models import Sector

    with pytest.raises(MetamodeloError) as exc:
        construir_registry({"sectores": {
            "model": Sector, "fields": {"estado_sector_id": {"selector": "combo"},
                                        "nombre_sector": {"selector": "lista"}}}})
    errores = "\n".join(exc.value.errores)
    assert "selector 'combo' inválido" in errores
    assert "selector solo aplica a un campo 'fk' o 'select'" in errores


# ---------------------------------------------------------------------------
# Pantallas
# ---------------------------------------------------------------------------

def test_formulario_con_muchos_activos_usa_lista(client, activos):
    html = client.get("/medidores/crear").get_data(as_text=True)
    assert 'class="campo-lista' in html and 'id="activo_id"' in html
    assert '<input type="hidden" id="activo_id__valor" name="activo_id"' in html
    assert "EQ-00 — Tractor 0" in lista(html, "activo_id")
    # La unidad tiene pocas opciones: sigue siendo un select.
    assert re.search(r'<select name="unidad_medida_id" id="unidad_medida_id"', html)


def test_formulario_de_edicion_muestra_el_texto_elegido(client, db, activos):
    from app.models.medidores_models import Medidor
    from app.models.unidadmedida_models import TipoUnidad, UnidadMedida

    tipo = TipoUnidad.query.filter_by(nombre_tipo="Tiempo").one()
    h = _guardar(db, UnidadMedida(nombre_unidad="Horas", abreviatura="h", tipo_medidor="Horómetro",
                                  tipo_unidad_id=tipo.tipo_unidad_id))
    m = _guardar(db, Medidor(nombre_medidor="Horómetro", activo_id=activos[2].activo_id,
                             unidad_medida_id=h.unidad_medida_id))
    html = client.get(f"/medidores/{m.medidor_id}/editar").get_data(as_text=True)
    assert re.search(r'id="activo_id"[^>]*value="EQ-02 — Tractor 2"', html)
    assert re.search(rf'id="activo_id__valor" name="activo_id"\s+value="{activos[2].activo_id}"', html)


def test_filtro_con_muchas_opciones_usa_lista(client, db, cuenta):
    _muchas_categorias(db, cuenta)
    elegida = CategoriaActivo.query.filter_by(nombre_categoria="Categoría 03").one()
    html = client.get(f"/activos?categoria_activo_id={elegida.categoria_activo_id}").get_data(as_text=True)
    assert re.search(r'id="filtro-categoria_activo_id"[^>]*value="Categoría 03 \(Maquinaria\)"', html)
    assert re.search(rf'id="filtro-categoria_activo_id__valor" name="categoria_activo_id"\s+'
                     rf'value="{elegida.categoria_activo_id}"', html)
    assert len(lista(html, "filtro-categoria_activo_id")) == fk.UMBRAL_LISTA + 1
    # Pocas opciones (estados): select, como antes.
    assert 'select class="filtro-select filtro-combinable" name="estado_activo_id"' in html


def test_alta_por_formulario_con_lista(client, activos):
    """El oculto lleva el ID: el alta funciona igual que con el select."""
    from app.models.medidores_models import Medidor
    from app.models.unidadmedida_models import TipoUnidad, UnidadMedida
    from app.core.db import db

    tipo = TipoUnidad.query.filter_by(nombre_tipo="Tiempo").one()
    h = _guardar(db, UnidadMedida(nombre_unidad="Horas", abreviatura="h", tipo_medidor="Horómetro",
                                  tipo_unidad_id=tipo.tipo_unidad_id))
    r = client.post("/medidores/crear", data={
        "nombre_medidor": "Horómetro", "activo_id": activos[3].activo_id,
        "unidad_medida_id": h.unidad_medida_id, "valor_inicial": 0, "motivo_operacion": "Alta",
    })
    assert r.status_code == 302
    assert Medidor.query.one().activo_id == activos[3].activo_id
