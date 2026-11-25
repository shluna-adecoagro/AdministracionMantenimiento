"""
Listados: filtros combinables (un select por FK, opción fija o Sí/No, combinados
con Y) y búsqueda de texto que también mira el nombre de lo vinculado.

Ejemplo: «los tractores 5090E del Feedlot».
"""
import re

import pytest

from app.models.activos_models import Activo, EstadoActivo
from app.models.marcas_modelos_models import Marca, Modelo
from app.models.sectores_models import Sector


def _guardar(db, *objetos):
    db.session.add_all(objetos)
    db.session.commit()
    return objetos[0] if len(objetos) == 1 else objetos


@pytest.fixture
def flota(db, categorias_activo, estado_sector_activo):
    """Tres tractores (dos 5090E y un 6110J) y una pala, en dos sectores."""
    tractor = categorias_activo["Tractor"]
    pala = categorias_activo["Pala cargadora"]
    jd, mi = _guardar(db, Marca(nombre_marca="John Deere"), Marca(nombre_marca="Michigan"))
    m5090, m6110, mm165 = _guardar(
        db,
        Modelo(nombre_modelo="5090E", marca_id=jd.marca_id, categoria_activo_id=tractor.categoria_activo_id),
        Modelo(nombre_modelo="6110J", marca_id=jd.marca_id, categoria_activo_id=tractor.categoria_activo_id),
        Modelo(nombre_modelo="MM165", marca_id=mi.marca_id, categoria_activo_id=pala.categoria_activo_id),
    )
    feedlot, tambo = _guardar(
        db,
        Sector(nombre_sector="Feedlot", centro_costo="CC-1", estado_sector_id=estado_sector_activo.estado_sector_id),
        Sector(nombre_sector="Tambo", centro_costo="CC-2", estado_sector_id=estado_sector_activo.estado_sector_id),
    )
    estado = EstadoActivo.query.first().estado_activo_id

    def activo(numero, categoria, modelo, sector):
        return Activo(numero_activo=numero, descripcion=f"Activo {numero}",
                      categoria_activo_id=categoria.categoria_activo_id, marca_id=modelo.marca_id,
                      modelo_id=modelo.modelo_id, sector_id=sector.sector_id, estado_activo_id=estado)

    _guardar(db,
             activo("T-01", tractor, m5090, feedlot),
             activo("T-02", tractor, m5090, tambo),
             activo("T-03", tractor, m6110, feedlot),
             activo("P-01", pala, mm165, feedlot))
    return {"tractor": tractor, "m5090": m5090, "feedlot": feedlot, "tambo": tambo}


def tabla(html):
    """Solo las filas del listado (sin el panel de filtros)."""
    return html[html.index("<tbody>"):html.index("</tbody>")]


def filas_visibles(html):
    """Campos con su fila de filtro a la vista (no ocultas)."""
    return {campo for campo, oculta in
            re.findall(r'<div class="filtro-fila" data-campo="(\w+)"\s*(hidden)?', html) if not oculta}


def numeros(html):
    return set(re.findall(r"\b[TP]-0\d\b", tabla(html)))


def test_filtros_combinados(client, flota):
    url = (f"/activos?categoria_activo_id={flota['tractor'].categoria_activo_id}"
           f"&modelo_id={flota['m5090'].modelo_id}&sector_id={flota['feedlot'].sector_id}")
    html = client.get(url).get_data(as_text=True)
    assert numeros(html) == {"T-01"}
    assert "1 resultado" in html
    # Filtros a demanda: se ven las filas de los aplicados, y los demás quedan
    # para «+ Agregar filtro».
    assert filas_visibles(html) == {"categoria_activo_id", "modelo_id", "sector_id"}
    assert re.search(r'<option value="sector_id"\s+hidden disabled>', html)
    assert re.search(r'<option value="marca_id"\s*>', html)


def test_sin_filtros_el_panel_esta_plegado(client, flota):
    html = client.get("/activos").get_data(as_text=True)
    assert numeros(html) == {"T-01", "T-02", "T-03", "P-01"}
    assert "4 resultados" in html
    assert filas_visibles(html) == set()
    # Todos los campos con opciones se pueden agregar como filtro.
    for campo in ("tipo_activo_id", "categoria_activo_id", "marca_id", "modelo_id",
                  "sector_id", "ubicacion_id", "estado_activo_id"):
        assert f'name="{campo}"' in html
        assert re.search(rf'<option value="{campo}"\s*>', html)


def test_texto_busca_en_el_nombre_de_lo_vinculado(client, flota):
    """«5090» encuentra los activos del modelo 5090E (antes buscaba en el ID)."""
    html = client.get("/activos?q=5090").get_data(as_text=True)
    assert numeros(html) == {"T-01", "T-02"}


def test_texto_y_filtro_se_combinan(client, flota):
    html = client.get(f"/activos?q=5090&sector_id={flota['tambo'].sector_id}").get_data(as_text=True)
    assert numeros(html) == {"T-02"}


def test_enlace_viejo_con_campo_y_valor_fk(client, flota):
    html = client.get(f"/activos?campo=sector_id&valor_fk={flota['tambo'].sector_id}").get_data(as_text=True)
    assert numeros(html) == {"T-02"}


def test_valor_invalido_se_ignora(client, flota):
    html = client.get("/activos?sector_id=abc").get_data(as_text=True)
    assert numeros(html) == {"T-01", "T-02", "T-03", "P-01"}


def test_opciones_dependientes_llevan_sus_datos(client, flota):
    """El select de modelos sabe de qué categoría y marca es cada uno (para filtrarse)."""
    html = client.get("/activos").get_data(as_text=True)
    select = html[html.index('name="modelo_id"'):]
    select = select[:select.index("</select>")]
    opcion = re.search(rf'<option value="{flota["m5090"].modelo_id}"\s+data-deps=\'([^\']+)\'', select)
    assert opcion and '"categoria_activo_id": ' in opcion.group(1) and '"marca_id": ' in opcion.group(1)


def test_filtro_si_no(client, db, categorias_activo):
    from app.models.bom_modelo_models import BOMModelo
    from app.models.materiales_models import CategoriaMaterial, Material

    marca = _guardar(db, Marca(nombre_marca="M"))
    mo = _guardar(db, Modelo(nombre_modelo="X", marca_id=marca.marca_id,
                             categoria_activo_id=categorias_activo["Tractor"].categoria_activo_id))
    cat = CategoriaMaterial.query.first().categoria_material_id
    a, b = _guardar(db, Material(codigo="ORIG-1", descripcion="Original", categoria_material_id=cat),
                    Material(codigo="EQUI-1", descripcion="Equivalente", categoria_material_id=cat))
    _guardar(db, BOMModelo(modelo_id=mo.modelo_id, material_id=a.material_id, es_equivalencia=False),
             BOMModelo(modelo_id=mo.modelo_id, material_id=b.material_id, es_equivalencia=True))

    html = client.get("/bom_modelo?es_equivalencia=Sí").get_data(as_text=True)
    assert "EQUI-1" in tabla(html) and "ORIG-1" not in tabla(html)
    assert re.search(r'<option value="Sí"\s+selected', html)


def test_api_busca_en_el_nombre_de_lo_vinculado(client, flota):
    r = client.get("/api/activos?q=5090")
    assert r.status_code == 200
    assert {a["numero_activo"] for a in r.get_json()} == {"T-01", "T-02"}


def test_hoja_de_estilos_con_version(client):
    """La URL de estilos.css cambia con el archivo: el navegador no usa la copia vieja."""
    html = client.get("/activos").get_data(as_text=True)
    assert re.search(r'css/estilos\.css\?v=\d{9,}', html)
