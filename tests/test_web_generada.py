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


def _titulo(client, url):
    import re

    return re.search(r"<title>(.*?)</title>", client.get(url).get_data(as_text=True), re.S).group(1).strip()


def test_titulo_de_la_pestana(client, sector):
    assert _titulo(client, "/") == "Mantenimiento Tambos"
    assert _titulo(client, "/sectores") == "Sectores · Mantenimiento Tambos"
    assert _titulo(client, "/sectores/crear") == "Nuevo sector · Mantenimiento Tambos"
    assert _titulo(client, "/ubicaciones/crear") == "Nueva ubicación · Mantenimiento Tambos"
    assert _titulo(client, f"/sectores/{sector.sector_id}") == "Taller · Mantenimiento Tambos"
    assert _titulo(client, f"/sectores/{sector.sector_id}/editar") == "Editar sector · Mantenimiento Tambos"


def test_favicon(client):
    html = client.get("/").get_data(as_text=True)
    for archivo in ("favicon.svg", "favicon-32.png", "apple-touch-icon.png"):
        assert f"/static/img/{archivo}" in html
        assert client.get(f"/static/img/{archivo}").status_code == 200
