"""
BOM: el del modelo es la plantilla; el del activo es una copia editable.

  * al crear un activo con modelo (o asignarle o cambiarle el modelo, si su BOM
    está vacío) se copia el BOM del modelo;
  * si el BOM del activo ya tiene ítems, no se toca y se avisa;
  * «Traer ítems del modelo» agrega los materiales que falten, sin tocar los demás;
  * en el detalle del activo hay una sola pestaña: «BOM».
"""
import pytest

from app.models.activos_models import Activo, EstadoActivo
from app.models.auditoria_models import AuditLog
from app.models.bom_activo_models import BOMActivo
from app.models.bom_modelo_models import BOMModelo
from app.models.marcas_modelos_models import Marca, Modelo
from app.models.materiales_models import CategoriaMaterial, Material


@pytest.fixture
def plantilla(db):
    """Modelo 6110J (John Deere) con dos materiales en su BOM, y otro modelo sin BOM."""
    marca = Marca(nombre_marca="John Deere")
    db.session.add(marca)
    db.session.flush()
    modelo = Modelo(nombre_modelo="6110J", marca_id=marca.marca_id)
    otro = Modelo(nombre_modelo="5090E", marca_id=marca.marca_id)
    cat = CategoriaMaterial.query.first().categoria_material_id
    aceite = Material(codigo="F-1", descripcion="Filtro de aceite", categoria_material_id=cat)
    aire = Material(codigo="F-2", descripcion="Filtro de aire", categoria_material_id=cat)
    extra = Material(codigo="F-3", descripcion="Filtro de combustible", categoria_material_id=cat)
    db.session.add_all([modelo, otro, aceite, aire, extra])
    db.session.flush()
    db.session.add_all([
        BOMModelo(modelo_id=modelo.modelo_id, material_id=aceite.material_id, cantidad=1),
        BOMModelo(modelo_id=modelo.modelo_id, material_id=aire.material_id, cantidad=2,
                  es_equivalencia=True, nota_equivalencia="Alternativo"),
    ])
    db.session.commit()
    return {"modelo": modelo, "otro": otro, "aceite": aceite, "aire": aire, "extra": extra}


def _datos(categorias_activo, **extra):
    return {
        "numero_activo": "T-01", "descripcion": "Tractor 1",
        "categoria_activo_id": categorias_activo["Tractor"].categoria_activo_id,
        "estado_activo_id": EstadoActivo.query.first().estado_activo_id,
        **extra,
    }


def _bom(activo_id):
    return {(b.material.codigo, b.cantidad) for b in BOMActivo.query.filter_by(activo_id=activo_id)}


def _activo():
    return Activo.query.filter_by(numero_activo="T-01").one()


# ---------------------------------------------------------------------------
# Copia al crear
# ---------------------------------------------------------------------------

def test_crear_activo_copia_el_bom_del_modelo(client, categorias_activo, plantilla):
    m = plantilla["modelo"]
    r = client.post("/activos/crear", data=_datos(categorias_activo, modelo_id=m.modelo_id),
                    follow_redirects=True)
    assert "Se copió el BOM del modelo 6110J: 2 ítems." in r.get_data(as_text=True)

    a = _activo()
    assert a.marca_id == m.marca_id  # se completa por el modelo
    assert _bom(a.activo_id) == {("F-1", 1), ("F-2", 2)}
    copia = BOMActivo.query.filter_by(activo_id=a.activo_id, material_id=plantilla["aire"].material_id).one()
    assert (copia.es_equivalencia, copia.nota_equivalencia) == (True, "Alternativo")

    # Cada ítem copiado queda en la auditoría, con el motivo.
    logs = AuditLog.query.filter_by(TablaAfectada="bom_activo").all()
    assert len(logs) == 2
    assert logs[0].motivo_operacion == "Copia del BOM del modelo 6110J"


def test_tambien_por_api_e_importacion(client, categorias_activo, plantilla):
    from app.crud.entidades import REGISTRY
    from app.crud.intercambio.csv_entidades import importar

    r = client.post("/api/activos", json=_datos(categorias_activo, modelo_id=plantilla["modelo"].modelo_id))
    assert r.status_code == 201
    assert len(_bom(r.get_json()["activo_id"])) == 2

    csv = ("Número de activo;Descripción;Categoría;Modelo;Estado\n"
           "T-02;Tractor 2;Tractor;6110J;Activo\n").encode()
    assert importar(REGISTRY["activos"], csv).ok
    assert len(_bom(Activo.query.filter_by(numero_activo="T-02").one().activo_id)) == 2


def test_sin_modelo_el_bom_arranca_vacio(client, categorias_activo, plantilla):
    client.post("/activos/crear", data=_datos(categorias_activo))
    assert _bom(_activo().activo_id) == set()


# ---------------------------------------------------------------------------
# Asignar o cambiar el modelo
# ---------------------------------------------------------------------------

def test_asignar_modelo_despues_copia_si_esta_vacio(client, categorias_activo, plantilla):
    client.post("/activos/crear", data=_datos(categorias_activo))
    a = _activo()
    r = client.patch(f"/api/activos/{a.activo_id}", json={"modelo_id": plantilla["modelo"].modelo_id})
    assert r.status_code == 200
    assert len(_bom(a.activo_id)) == 2


def test_cambiar_modelo_con_bom_cargado_no_lo_toca_y_avisa(client, db, categorias_activo, plantilla):
    client.post("/activos/crear", data=_datos(categorias_activo, modelo_id=plantilla["modelo"].modelo_id))
    a = _activo()
    antes = _bom(a.activo_id)

    datos = _datos(categorias_activo, modelo_id=plantilla["otro"].modelo_id,
                   marca_id=plantilla["otro"].marca_id)
    r = client.post(f"/activos/{a.activo_id}/editar", data=datos, follow_redirects=True)
    html = r.get_data(as_text=True)
    assert "su BOM ya tenía ítems y no se modificó" in html
    assert _bom(a.activo_id) == antes


def test_editar_otro_campo_no_vuelve_a_copiar(client, db, categorias_activo, plantilla):
    """Si el usuario vació el BOM a propósito, editar el activo no lo vuelve a llenar."""
    client.post("/activos/crear", data=_datos(categorias_activo, modelo_id=plantilla["modelo"].modelo_id))
    a = _activo()
    BOMActivo.query.filter_by(activo_id=a.activo_id).delete()
    db.session.commit()

    r = client.patch(f"/api/activos/{a.activo_id}", json={"descripcion": "Tractor del tambo 3"})
    assert r.status_code == 200
    assert _bom(a.activo_id) == set()


# ---------------------------------------------------------------------------
# El BOM del activo se edita sin tocar la plantilla
# ---------------------------------------------------------------------------

def test_editar_el_bom_del_activo_no_cambia_el_del_modelo(client, categorias_activo, plantilla):
    client.post("/activos/crear", data=_datos(categorias_activo, modelo_id=plantilla["modelo"].modelo_id))
    a = _activo()
    item = BOMActivo.query.filter_by(activo_id=a.activo_id, material_id=plantilla["aceite"].material_id).one()
    r = client.patch(f"/api/bom_activo/{item.bom_activo_id}", json={"cantidad": 3})
    assert r.status_code == 200
    assert BOMModelo.query.filter_by(material_id=plantilla["aceite"].material_id).one().cantidad == 1


def test_un_material_una_sola_vez_por_activo(client, categorias_activo, plantilla):
    client.post("/activos/crear", data=_datos(categorias_activo, modelo_id=plantilla["modelo"].modelo_id))
    a = _activo()
    r = client.post("/api/bom_activo", json={"activo_id": a.activo_id, "material_id": plantilla["aceite"].material_id,
                                             "es_equivalencia": False})
    assert r.status_code == 409


# ---------------------------------------------------------------------------
# «Traer ítems del modelo»
# ---------------------------------------------------------------------------

def test_traer_items_del_modelo_agrega_solo_los_que_faltan(client, db, categorias_activo, plantilla):
    client.post("/activos/crear", data=_datos(categorias_activo, modelo_id=plantilla["modelo"].modelo_id))
    a = _activo()
    # El usuario cambió una cantidad, quitó un ítem y agregó uno propio...
    aceite = BOMActivo.query.filter_by(activo_id=a.activo_id, material_id=plantilla["aceite"].material_id).one()
    aceite.cantidad = 5
    BOMActivo.query.filter_by(activo_id=a.activo_id, material_id=plantilla["aire"].material_id).delete()
    db.session.add(BOMActivo(activo_id=a.activo_id, material_id=plantilla["extra"].material_id))
    db.session.commit()

    # ...y después trae los ítems del modelo: vuelve el filtro de aire, lo demás queda igual.
    url = f"/activos/{a.activo_id}/accion/traer_bom_modelo"
    r = client.post(url, follow_redirects=True)
    assert "Se agregaron 1 ítem del modelo 6110J." in r.get_data(as_text=True)
    assert _bom(a.activo_id) == {("F-1", 5), ("F-2", 2), ("F-3", None)}

    r = client.post(url, follow_redirects=True)
    assert "El BOM ya tiene todos los materiales del modelo 6110J." in r.get_data(as_text=True)


def test_boton_solo_en_la_pestana_bom_y_con_modelo(client, categorias_activo, plantilla):
    client.post("/activos/crear", data=_datos(categorias_activo, modelo_id=plantilla["modelo"].modelo_id))
    a = _activo()
    assert "Traer ítems del modelo" in client.get(f"/activos/{a.activo_id}?seccion=bom_activo").get_data(as_text=True)
    assert "Traer ítems del modelo" not in client.get(f"/activos/{a.activo_id}").get_data(as_text=True)

    client.patch(f"/api/activos/{a.activo_id}", json={"modelo_id": None})
    assert "Traer ítems del modelo" not in client.get(f"/activos/{a.activo_id}?seccion=bom_activo").get_data(as_text=True)
    assert client.post(f"/activos/{a.activo_id}/accion/traer_bom_modelo").status_code == 404


# ---------------------------------------------------------------------------
# Pestañas
# ---------------------------------------------------------------------------

def _pestanas(client, url):
    import re

    html = client.get(url).get_data(as_text=True)
    return [t.strip() for t in re.findall(r'class="detalle-tab[^"]*">\s*([^<]+?)\s*</a>', html)]


def test_pestanas_segun_el_padre(client, categorias_activo, plantilla):
    client.post("/activos/crear", data=_datos(categorias_activo, modelo_id=plantilla["modelo"].modelo_id))
    assert _pestanas(client, f"/activos/{_activo().activo_id}") == ["Datos", "Historial", "Medidores", "BOM"]
    assert _pestanas(client, f"/materiales/{plantilla['aceite'].material_id}") == [
        "Datos", "Historial", "Usado en modelos", "Usado en activos", "Stock por ubicación"]
    assert _pestanas(client, f"/modelos/{plantilla['modelo'].modelo_id}") == ["Datos", "Historial", "BOM"]

    modelo = client.get(f"/modelos/{plantilla['modelo'].modelo_id}?seccion=bom_modelo").get_data(as_text=True)
    assert "Filtro de aceite" in modelo
