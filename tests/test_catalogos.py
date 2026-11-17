"""Menú en dos grupos (datos maestros / catálogos) y pantallas de los catálogos."""
from app.crud.entidades import REGISTRY


def test_menu_separa_datos_maestros_y_catalogos(client):
    html = client.get("/").get_data(as_text=True)
    maestros, catalogos = html.split("Datos maestros")[1].split('<details class="sidebar-grupo"', 1)
    for url in ("/activos", "/materiales", "/empleados", "/sectores", "/marcas"):
        assert f'href="{url}"' in maestros
    for url in ("/estados_activo", "/tipos_activo", "/categorias_material",
                "/unidades_medida", "/motivos_operacion"):
        assert f'href="{url}"' in catalogos
    assert "Catálogos" in catalogos
    assert "open" not in catalogos.split(">")[0]  # plegado si no estoy en un catálogo


def test_catalogos_se_abre_si_estoy_en_uno(client):
    html = client.get("/tipos_activo").get_data(as_text=True)
    assert '<details class="sidebar-grupo" open>' in html


def test_color_del_estado(client):
    assert REGISTRY["estados_sector"].fields["color_badge"].tipo == "color"
    assert 'type="color"' in client.get("/estados_sector/crear").get_data(as_text=True)
    assert 'class="muestra-color"' in client.get("/estados_sector").get_data(as_text=True)


def test_tipo_de_activo_muestra_sus_categorias(client, categorias_activo):
    from app.models.activos_models import TipoActivo

    tipo = TipoActivo.query.filter_by(nombre_tipo="Maquinaria").one()
    html = client.get(f"/tipos_activo/{tipo.tipo_activo_id}?seccion=categorias_activo").get_data(as_text=True)
    assert "Tractor" in html and "Pala cargadora" in html


def test_motivo_muestra_la_operacion_en_castellano(client):
    html = client.get("/motivos_operacion").get_data(as_text=True)
    assert "Modificación" in html and ">UPDATE<" not in html


def test_estado_en_uso_no_se_borra(client, cuenta, estado_cuenta_activa):
    """Antes SQLAlchemy intentaba dejar las cuentas sin estado."""
    r = client.post(f"/estados_cuenta/{estado_cuenta_activa.estado_cuenta_id}/confirmar_eliminar")
    assert r.status_code == 409
    assert "1 cuenta" in r.get_data(as_text=True)


def test_booleanos_se_ven_como_si_no(client, db):
    """El listado muestra el texto de las opciones (Sí/No), no True/False."""
    from app.models.bom_modelo_models import BOMModelo
    from app.models.marcas_modelos_models import Marca, Modelo
    from app.models.materiales_models import CategoriaMaterial, Material

    m = Marca(nombre_marca="M"); db.session.add(m); db.session.flush()
    mo = Modelo(nombre_modelo="X", marca_id=m.marca_id)
    mat = Material(codigo="C", descripcion="D", categoria_material_id=CategoriaMaterial.query.first().categoria_material_id)
    db.session.add_all([mo, mat]); db.session.flush()
    db.session.add(BOMModelo(modelo_id=mo.modelo_id, material_id=mat.material_id, es_equivalencia=True))
    db.session.commit()
    html = client.get("/bom_modelo").get_data(as_text=True)
    assert "Sí" in html and "True" not in html
