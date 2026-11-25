"""
Fase 10, PR 10.2: maestro de materiales.

  * código del ERP en materiales y proveedores (vacío = NULL);
  * genérico y presentaciones (reglas de docs/diseno_tablas_operativas.md);
  * controla stock; cuenta sugerida por categoría de material.
"""
import pytest

from app.crud.entidades import REGISTRY
from app.crud.intercambio.csv_entidades import exportar, importar
from app.models.materiales_models import CategoriaMaterial, Material, StockMaterial
from app.models.recursos_models import Proveedor
from app.models.unidadmedida_models import TipoUnidad, UnidadMedida


def _guardar(db, *objetos):
    db.session.add_all(objetos)
    db.session.commit()
    return objetos[0] if len(objetos) == 1 else objetos


@pytest.fixture
def litros(db):
    tipo = TipoUnidad.query.filter_by(nombre_tipo="Volumen").one().tipo_unidad_id
    return _guardar(db, UnidadMedida(nombre_unidad="Litros", abreviatura="L", tipo_unidad_id=tipo))


@pytest.fixture
def kilos(db):
    tipo = TipoUnidad.query.filter_by(nombre_tipo="Masa").one().tipo_unidad_id
    return _guardar(db, UnidadMedida(nombre_unidad="Kilogramos", abreviatura="kg", tipo_unidad_id=tipo))


@pytest.fixture
def categoria(db):
    return CategoriaMaterial.query.first()


def _api(client, **datos):
    return client.post("/api/materiales", json=datos)


def _generico(client, categoria, litros, codigo="GEN-ACEITE-15W40", **extra):
    return _api(client, codigo=codigo, descripcion="Aceite 15W-40", es_generico=True,
                categoria_material_id=categoria.categoria_material_id,
                unidad_medida_id=litros.unidad_medida_id, **extra)


@pytest.fixture
def aceite(client, categoria, litros):
    r = _generico(client, categoria, litros)
    assert r.status_code == 201, r.get_json()
    return Material.query.filter_by(codigo="GEN-ACEITE-15W40").one()


def _presentacion(client, categoria, generico, codigo="AC-20", contenido=20, **extra):
    datos = {"codigo": codigo, "descripcion": f"Aceite 15W-40 {contenido} L",
             "categoria_material_id": categoria.categoria_material_id,
             "material_generico_id": generico.material_id, "presentacion_cantidad": contenido, **extra}
    return _api(client, **datos)


def _errores(r):
    return r.get_json()["errors"]


# ---------------------------------------------------------------------------
# Códigos del ERP
# ---------------------------------------------------------------------------

def test_codigo_erp_vacio_es_null(app, categoria):
    csv = ("Código (número de parte);Descripción;Categoría;Código ERP\n"
           f"RE504836;Filtro de aceite;{categoria.nombre_categoria};\n"
           f"RE509031;Filtro de combustible;{categoria.nombre_categoria};  \n"
           f"R270857;Correa;{categoria.nombre_categoria};ERP-77\n").encode()
    r = importar(REGISTRY["materiales"], csv)
    assert r.ok, r.resumen()
    assert [m.codigo_erp for m in Material.query.order_by(Material.codigo)] == ["ERP-77", None, None]

    # Un código del ERP cargado sí es único.
    csv = f"Código (número de parte);Descripción;Categoría;Código ERP\nX-1;Otro;{categoria.nombre_categoria};ERP-77\n"
    assert not importar(REGISTRY["materiales"], csv.encode()).ok


def test_codigo_erp_de_proveedores(app, client):
    for nombre in ("Repuestos SA", "Lubricantes SRL"):
        r = client.post("/api/proveedores", json={"razon_social": nombre, "codigo_erp": ""})
        assert r.status_code == 201, r.get_json()
    assert [p.codigo_erp for p in Proveedor.query] == [None, None]
    client.patch(f"/api/proveedores/{Proveedor.query.first().recurso_id}", json={"codigo_erp": "P-100"})
    r = client.post("/api/proveedores", json={"razon_social": "Otro", "codigo_erp": "P-100"})
    assert r.status_code == 409


def test_codigo_es_el_numero_de_parte(app):
    f = REGISTRY["materiales"].fields["codigo"]
    assert f.label == "Código (número de parte)" and f.unique and REGISTRY["materiales"].clave_natural == ("codigo",)


# ---------------------------------------------------------------------------
# Genérico
# ---------------------------------------------------------------------------

def test_por_defecto_no_es_generico_ni_controla_stock(client, categoria):
    r = _api(client, codigo="F-1", descripcion="Filtro", categoria_material_id=categoria.categoria_material_id)
    assert r.status_code == 201
    assert (r.get_json()["es_generico"], r.get_json()["controla_stock"]) == (False, False)


@pytest.mark.parametrize("extra, campo, mensaje", [
    ({"codigo": "ACEITE"}, "codigo", "empieza con GEN-"),
    ({"presentacion_cantidad": 20}, "presentacion_cantidad", "no tiene envase"),
    ({"unidad_medida_id": None}, "unidad_medida_id", "necesita la unidad"),
])
def test_reglas_del_generico(client, categoria, litros, extra, campo, mensaje):
    datos = {"codigo": "GEN-X", "descripcion": "Aceite", "es_generico": True,
             "categoria_material_id": categoria.categoria_material_id,
             "unidad_medida_id": litros.unidad_medida_id, **extra}
    r = _api(client, **datos)
    assert r.status_code == 400 and mensaje in _errores(r)[campo]
    assert Material.query.count() == 0


def test_un_generico_no_tiene_generico(client, categoria, litros, aceite):
    r = _generico(client, categoria, litros, codigo="GEN-OTRO", material_generico_id=aceite.material_id)
    assert r.status_code == 400
    assert "material_generico_id" in _errores(r)


# ---------------------------------------------------------------------------
# Presentaciones
# ---------------------------------------------------------------------------

def test_presentacion_toma_la_unidad_del_generico(client, categoria, aceite, litros):
    r = _presentacion(client, categoria, aceite)
    assert r.status_code == 201, r.get_json()
    d = r.get_json()
    assert (d["unidad_medida_id"], d["material_generico_id_label"]) == (
        litros.unidad_medida_id, "GEN-ACEITE-15W40 — Aceite 15W-40")


def test_presentacion_con_otra_unidad(client, categoria, aceite, kilos):
    r = _presentacion(client, categoria, aceite, unidad_medida_id=kilos.unidad_medida_id)
    assert r.status_code == 400
    assert "no pertenece a «Kilogramos»" in _errores(r)["material_generico_id"]


def test_presentacion_necesita_contenido(client, categoria, aceite):
    r = _presentacion(client, categoria, aceite, contenido=None)
    assert r.status_code == 400 and "contenido por envase" in _errores(r)["presentacion_cantidad"]


def test_solo_se_elige_un_generico(client, db, categoria, aceite):
    filtro = _guardar(db, Material(codigo="F-1", descripcion="Filtro de aire",
                                   categoria_material_id=categoria.categoria_material_id))
    form = client.get("/materiales/crear").get_data(as_text=True)
    opciones = form.split('id="material_generico_id"')[1].split("</select>")[0]
    assert "Aceite 15W-40" in opciones and "Filtro de aire" not in opciones
    r = _presentacion(client, categoria, filtro)
    assert r.status_code == 400 and "no es una opción válida" in _errores(r)["material_generico_id"]


def test_generico_con_presentaciones(client, categoria, aceite, kilos):
    _presentacion(client, categoria, aceite)
    r = client.patch(f"/api/materiales/{aceite.material_id}", json={"es_generico": False})
    assert r.status_code == 400 and "no puede dejar de ser genérico" in _errores(r)["es_generico"]
    r = client.patch(f"/api/materiales/{aceite.material_id}", json={"unidad_medida_id": kilos.unidad_medida_id})
    assert r.status_code == 400 and "Sus presentaciones están en Litros" in _errores(r)["unidad_medida_id"]
    # Un genérico con presentaciones no se borra.
    assert client.delete(f"/api/materiales/{aceite.material_id}").status_code == 409


def test_pestana_presentaciones_solo_en_genericos(client, categoria, aceite):
    _presentacion(client, categoria, aceite)
    presentacion = Material.query.filter_by(codigo="AC-20").one()
    html = client.get(f"/materiales/{aceite.material_id}?seccion=materiales").get_data(as_text=True)
    assert "Presentaciones" in html and "AC-20" in html
    assert "Presentaciones" not in client.get(f"/materiales/{presentacion.material_id}").get_data(as_text=True)
    # «Nueva presentación» llega con el genérico elegido.
    import re

    form = client.get(f"/materiales/crear?material_generico_id={aceite.material_id}").get_data(as_text=True)
    select = form.split('id="material_generico_id"')[1].split("</select>")[0]
    assert re.search(rf'<option value="{aceite.material_id}"[^>]*\bselected\b', select)


# ---------------------------------------------------------------------------
# Stock: de las presentaciones, nunca del genérico
# ---------------------------------------------------------------------------

def test_stock_de_un_generico_se_rechaza(client, db, aceite, ubicacion):
    r = client.post("/api/stock_material", json={"material_id": aceite.material_id,
                                                 "ubicacion_id": ubicacion.ubicacion_id, "cantidad": 3})
    assert r.status_code == 400 and "no es una opción válida" in _errores(r)["material_id"]


def test_material_con_stock_no_pasa_a_generico(client, db, categoria, litros, ubicacion):
    m = _guardar(db, Material(codigo="GEN-Y", descripcion="Grasa", categoria_material_id=categoria.categoria_material_id,
                              unidad_medida_id=litros.unidad_medida_id))
    _guardar(db, StockMaterial(material_id=m.material_id, ubicacion_id=ubicacion.ubicacion_id, cantidad=2))
    r = client.patch(f"/api/materiales/{m.material_id}", json={"es_generico": True})
    assert r.status_code == 400 and "Tiene stock" in _errores(r)["es_generico"]


def test_el_bom_acepta_el_generico(client, db, aceite, categorias_activo):
    from app.models.marcas_modelos_models import Marca, Modelo

    marca = _guardar(db, Marca(nombre_marca="CAT"))
    modelo = _guardar(db, Modelo(nombre_modelo="950", marca_id=marca.marca_id,
                                 categoria_activo_id=categorias_activo["Pala cargadora"].categoria_activo_id))
    r = client.post("/api/bom_modelo", json={"modelo_id": modelo.modelo_id, "material_id": aceite.material_id,
                                             "cantidad": 20, "es_equivalencia": False})
    assert r.status_code == 201


# ---------------------------------------------------------------------------
# Cuenta por categoría de material; exportación
# ---------------------------------------------------------------------------

def test_cuenta_de_la_categoria(client, db, categoria, cuenta):
    r = client.patch(f"/api/categorias_material/{categoria.categoria_material_id}", json={"cuenta_id": cuenta.cuenta_id})
    assert r.status_code == 200
    assert client.post(f"/cuentas/{cuenta.cuenta_id}/confirmar_eliminar").status_code == 409  # en uso


def test_exportar_e_importar_presentaciones(app, client, categoria, aceite):
    _presentacion(client, categoria, aceite)
    csv = exportar(REGISTRY["materiales"]).decode("utf-8-sig")
    encabezado = csv.splitlines()[0].split(";")
    for columna in ("Código (número de parte)", "Código ERP", "Es genérico", "Genérico",
                    "Contenido por envase", "Controla stock"):
        assert columna in encabezado
    assert "AC-20;Aceite 15W-40 20 L;;No;GEN-ACEITE-15W40 — Aceite 15W-40;" in csv
    r = importar(REGISTRY["materiales"], csv.encode("utf-8"))
    assert r.ok and r.sin_cambios == 2, r.resumen()


# ---------------------------------------------------------------------------
# Cómo se muestra y se busca un material
# ---------------------------------------------------------------------------

def test_material_se_muestra_con_codigo_y_descripcion(client, db, categoria, categorias_activo):
    from app.models.marcas_modelos_models import Marca, Modelo

    for codigo in ("RE504836", "RE509031"):
        _guardar(db, Material(codigo=codigo, descripcion="Filtro de aceite",
                              categoria_material_id=categoria.categoria_material_id))
    form = client.get("/bom_modelo/crear").get_data(as_text=True)
    assert "RE504836 — Filtro de aceite" in form and "RE509031 — Filtro de aceite" in form

    marca = _guardar(db, Marca(nombre_marca="JD"))
    _guardar(db, Modelo(nombre_modelo="6110J", marca_id=marca.marca_id,
                        categoria_activo_id=categorias_activo["Tractor"].categoria_activo_id))
    # Al importar se reconoce por el código, por la etiqueta o por la descripción si no se repite.
    csv = ("Material;Modelo;Es equivalencia\n"
           "RE504836;6110J;No\n"
           "RE509031 — Filtro de aceite;6110J;No\n").encode()
    r = importar(REGISTRY["bom_modelo"], csv)
    assert r.ok and r.creados == 2, r.resumen()
    r = importar(REGISTRY["bom_modelo"], "Material;Modelo;Es equivalencia\nFiltro de aceite;6110J;No\n".encode())
    assert not r.ok and "hay 2 registros llamados «Filtro de aceite»" in r.errores[0][2]
    # Reimportar lo exportado no cambia nada.
    r = importar(REGISTRY["bom_modelo"], exportar(REGISTRY["bom_modelo"]))
    assert r.ok and r.sin_cambios == 2, r.resumen()
