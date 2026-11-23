"""
Fase 10, PR 10.1: framework para la parte operativa.

  * numeración automática (serie continua y TRA-AAAA-NNNN);
  * campos de solo importación (datos cuyo dueño es el ERP);
  * origen + clave de origen de lo importado (OrigenMixin);
  * archivos con extensiones por campo (PDF);
  * las tablas viejas de pedidos ya no existen.

Ninguna entidad real usa todavía estas piezas (llegan en 10.3 y siguientes), así
que se prueban con una entidad de prueba: su tabla vive en una metadata propia,
fuera de la de la app, y se crea y se borra en cada test.
"""
import io
from datetime import date

import pytest
from sqlalchemy import Column, Integer, MetaData, String
from sqlalchemy.orm import DeclarativeBase
from werkzeug.datastructures import FileStorage

from app.core.db import db as _db
from app.crud.core import numeracion
from app.crud.core.coercion import ErroresValidacion, datos_de_entrada
from app.crud.core.files import ArchivoInvalido, guardar
from app.crud.core.service import ServicioCRUD
from app.crud.entidades import REGISTRY
from app.crud.intercambio.csv_entidades import exportar, importar
from app.crud.meta.registry import construir_spec
from app.crud.model_mixin import ModelMixin
from app.crud.origen_mixin import OrigenMixin
from app.crud.schema import jsonschema


class _Base(DeclarativeBase):
    metadata = MetaData()
    query = _db.session.query_property()  # como db.Model (la importación usa Model.query)


class DocumentoPrueba(_Base, ModelMixin, OrigenMixin):
    __tablename__ = "prueba_documentos"
    __label_field__ = "numero"

    documento_id = Column(Integer, primary_key=True)
    numero = Column(String(30), nullable=False, unique=True, info={"label": "Número"})
    tramite = Column(String(30), nullable=True, unique=True, info={"label": "Trámite"})
    descripcion = Column(String(100), nullable=False, info={"label": "Descripción"})
    nro_erp = Column(String(30), nullable=True, unique=True, info={"label": "Nº ERP"})
    archivo = Column(String(300), nullable=True)


OVERRIDE = {
    "model": DocumentoPrueba,
    "label_singular": "documento",
    "label_plural": "documentos",
    "fields": {
        "numero": {"numeracion": "{n}"},
        "tramite": {"numeracion": "TRA-{año}-{n:04d}"},
        "nro_erp": {"solo_importacion": True},
    },
}


@pytest.fixture
def spec(app):
    spec, errores = construir_spec("prueba_documentos", OVERRIDE)
    assert not errores, errores
    _Base.metadata.create_all(_db.engine)
    yield spec
    _db.session.rollback()
    _Base.metadata.drop_all(_db.engine)


@pytest.fixture
def servicio(spec):
    return ServicioCRUD(spec.model, spec.fields)


def _csv(texto):
    return texto.strip().encode()


# ---------------------------------------------------------------------------
# Numeración automática
# ---------------------------------------------------------------------------

def test_numeracion_serie_continua(servicio):
    for numero in ("1104", "1107", "PED-viejo"):
        servicio.crear({"numero": numero, "descripcion": "x"})
    d = servicio.crear({"descripcion": "Nuevo"})
    assert d.numero == "1108"  # el mayor de la serie + 1; lo que no sigue el formato no cuenta
    assert servicio.crear({"numero": "2000", "descripcion": "A mano"}).numero == "2000"  # se respeta
    assert servicio.crear({"descripcion": "Otro"}).numero == "2001"


def test_numeracion_por_año(servicio):
    año = date.today().year
    a = servicio.crear({"descripcion": "a"})
    b = servicio.crear({"descripcion": "b"})
    assert (a.tramite, b.tramite) == (f"TRA-{año}-0001", f"TRA-{año}-0002")
    # Otro año no cuenta, y el año siguiente arranca de nuevo.
    servicio.crear({"descripcion": "c", "tramite": f"TRA-{año - 1}-0099"})
    assert numeracion.siguiente(DocumentoPrueba, "tramite", "TRA-{año}-{n:04d}") == f"TRA-{año}-0003"
    assert numeracion.siguiente(DocumentoPrueba, "tramite", "TRA-{año}-{n:04d}",
                                hoy=date(año + 1, 1, 1)) == f"TRA-{año + 1}-0001"


def test_numeracion_no_es_obligatoria_al_cargar(spec):
    assert not spec.fields["numero"].required  # la columna es NOT NULL, pero se completa sola
    assert "numero" not in jsonschema.esquema_entrada(spec, "crear").get("required", [])


@pytest.mark.parametrize("formato", ["SIN-NUMERO", "{n}-{n}", "{x}-{n}"])
def test_formato_de_numeracion_invalido(app, formato):
    _, errores = construir_spec("prueba", {**OVERRIDE, "fields": {"numero": {"numeracion": formato}}})
    assert any("numeracion" in e for e in errores), errores


# ---------------------------------------------------------------------------
# Solo importación (dueño: el ERP)
# ---------------------------------------------------------------------------

def test_solo_importacion_se_ignora_en_web_y_api(spec, servicio):
    # Web: el formulario no lo procesa aunque venga.
    datos = datos_de_entrada(spec.model, spec.fields, {"descripcion": "x", "nro_erp": "999"})
    assert "nro_erp" not in datos
    # API: no está entre los campos que se envían y, si se manda, se explica por qué.
    assert "nro_erp" not in jsonschema.esquema_entrada(spec, "crear")["properties"]
    assert jsonschema.esquema_registro(spec)["properties"]["nro_erp"]["readOnly"]
    with pytest.raises(ErroresValidacion) as e:
        jsonschema.validar(spec, {"descripcion": "x", "nro_erp": "999"}, "crear")
    assert e.value.errores["nro_erp"] == "Nº ERP: lo carga la importación; no se modifica por la API."


def test_solo_importacion_entra_por_la_importacion(spec):
    r = importar(spec, _csv("Clave de origen;Descripción;Nº ERP\nX-1;Doc 1;OC-55"))
    assert r.ok, r.resumen()
    d = DocumentoPrueba.query.one()
    assert (d.nro_erp, d.numero) == ("OC-55", "1")  # el número se completó solo


# ---------------------------------------------------------------------------
# Origen y clave de origen
# ---------------------------------------------------------------------------

def test_origen_inferido(spec):
    origen, clave = spec.fields["origen"], spec.fields["clave_origen"]
    assert origen.solo_importacion and clave.solo_importacion
    assert origen.tipo == "select" and {o["value"] for o in origen.options} == {"app", "historico", "reporte", "pdf"}
    assert spec.clave_natural == ("clave_origen",)  # por defecto


def test_lo_cargado_en_la_app_queda_con_origen_app(servicio):
    d = servicio.crear({"descripcion": "En la app"})
    assert (d.origen, d.clave_origen) == ("app", None)


def test_importacion_idempotente_por_clave_de_origen(spec):
    datos = _csv("Origen;Clave de origen;Descripción\nhistorico;pedidos.xlsx|1104;Filtros\nhistorico;pedidos.xlsx|1107;Correas")
    r = importar(spec, datos)
    assert r.ok and r.creados == 2, r.resumen()
    r = importar(spec, datos)
    assert (r.creados, r.sin_cambios) == (0, 2)
    assert {d.origen for d in DocumentoPrueba.query} == {"historico"}

    # Reimportar lo exportado no cambia nada.
    r = importar(spec, exportar(spec))
    assert r.ok and r.sin_cambios == 2 and not r.creados, r.resumen()


def test_fila_sin_clave_de_origen_se_rechaza(spec):
    r = importar(spec, _csv("Clave de origen;Descripción\n;Sin clave"))
    assert not r.ok
    assert r.errores == [(2, "_clave", "falta Clave de origen, que identifica el registro")]
    assert DocumentoPrueba.query.count() == 0


# ---------------------------------------------------------------------------
# Archivos: extensiones por campo
# ---------------------------------------------------------------------------

def test_archivo_se_infiere_como_pdf(spec):
    f = spec.fields["archivo"]
    assert (f.tipo, f.extensiones, f.label) == ("file", (".pdf",), "Archivo")


def test_archivo_solo_acepta_sus_extensiones(tmp_path):
    def subir(nombre):
        return guardar(FileStorage(io.BytesIO(b"x"), filename=nombre), str(tmp_path), "documentos",
                       "documentos", extensiones=(".pdf",))

    assert subir("oferta.PDF").endswith(".pdf")
    with pytest.raises(ArchivoInvalido, match="se aceptan: .pdf"):
        subir("foto.jpg")


def test_extensiones_solo_en_campos_de_archivo(app):
    _, errores = construir_spec("prueba", {**OVERRIDE, "fields": {"descripcion": {"extensiones": [".pdf"]}}})
    assert any("extensiones solo aplica" in e for e in errores)


def test_formulario_de_la_entidad_de_prueba(app, spec):
    from app.crud.web.views import VistasEntidad

    vistas = VistasEntidad(spec, {spec.name: spec})
    with app.test_request_context("/"):
        html, _ = vistas._render_form("INSERT", {}, (None, None), "/volver")
    assert 'accept=".pdf"' in html
    # Solo importación: se ve, deshabilitado y sin name (no se envía).
    assert 'id="nro_erp"' in html and 'name="nro_erp"' not in html
    assert 'id="origen"' in html and 'name="origen"' not in html
    # Numeración: no es obligatorio y se avisa.
    numero = html.split('id="numero"')[1].split(">")[0]
    assert "required" not in numero
    assert "Si se deja vacío, se numera solo." in html


def test_fotos_de_la_app_solo_imagenes(client):
    assert REGISTRY["activos"].fields["foto_path"].extensiones == (".jpg", ".jpeg", ".png", ".gif", ".webp")
    assert 'accept=".jpg,.jpeg,.png,.gif,.webp"' in client.get("/activos/crear").get_data(as_text=True)


def test_el_detalle_muestra_como_imagen_solo_las_imagenes(app):
    es_imagen = app.jinja_env.tests["es_imagen"]
    assert es_imagen("/static/uploads/activos/fotos/a.JPG")
    assert not es_imagen("/static/uploads/documentos/documentos/oferta.pdf")


# ---------------------------------------------------------------------------
# Limpieza
# ---------------------------------------------------------------------------

def test_las_tablas_viejas_de_pedidos_no_existen(app):
    assert "pedido_detalle" not in _db.metadata.tables
    # El nombre «pedidos» lo usa ahora la tabla nueva (PR 10.3).
    assert "PedidoID" not in _db.metadata.tables["pedidos"].columns
