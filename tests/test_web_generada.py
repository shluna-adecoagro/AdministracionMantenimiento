"""Rutas generadas desde el registry (app/crud/web/views.py)."""
from app.crud.entidades import REGISTRY
from app.crud.web.views import ACCIONES, endpoint


def test_cada_entidad_tiene_sus_cinco_pantallas(app):
    reglas = {r.endpoint for r in app.url_map.iter_rules()}
    for nombre in REGISTRY:
        for accion in ACCIONES:
            assert endpoint(nombre, accion) in reglas


def test_las_urls_no_cambian(app):
    with app.test_request_context():
        from flask import url_for

        assert url_for("crud.sectores_listar") == "/sectores"
        assert url_for("crud.ubicaciones_crear", sector_id=3) == "/ubicaciones/crear?sector_id=3"
        assert url_for("crud.cuentas_confirmar_eliminar", id=5) == "/cuentas/5/confirmar_eliminar"


def test_no_quedan_blueprints_viejos(app):
    assert "sectores_web" not in app.blueprints
    assert "cuentas" not in app.blueprints


def test_menu_lateral_sigue_mostrando_las_entidades(client):
    html = client.get("/sectores").get_data(as_text=True)
    assert 'href="/sectores"' in html
    assert 'href="/cuentas"' in html
