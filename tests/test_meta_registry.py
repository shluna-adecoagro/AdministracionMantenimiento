"""Registry de metamodelos: inferencia + overrides + validación."""
import pytest

from app.crud.meta.registry import MetamodeloError, construir_registry
from app.crud.metamodelos import ENTIDADES, REGISTRY
from app.models.cuentas_models import Cuenta, EstadoCuenta
from app.models.sectores_models import EstadoSector, Sector
from app.models.ubicaciones_models import Ubicacion

BASE = {
    "sectores": {"model": Sector, "label_singular": "sector", "label_plural": "sectores"},
    "ubicaciones": {
        "model": Ubicacion,
        "padre": {"entidad": "sectores", "fk": "sector_id"},
    },
}


def con(nombre, **cambios):
    """Copia de BASE con cambios en el override de una entidad."""
    ov = {k: dict(v) for k, v in BASE.items()}
    ov[nombre].update(cambios)
    return ov


def errores_de(overrides):
    with pytest.raises(MetamodeloError) as exc:
        construir_registry(overrides)
    return exc.value.errores


# ---------------------------------------------------------------------------
# Registry real de la app
# ---------------------------------------------------------------------------

def test_entidades_migradas():
    assert set(REGISTRY) == {"sectores", "ubicaciones", "cuentas"}


def test_sectores_inferido_del_modelo():
    s = REGISTRY["sectores"]
    assert s.model is Sector
    assert s.pk == "sector_id"
    assert s.tabla == "sectores"
    assert s.auditoria is True  # usa AuditMixin
    assert list(s.fields) == ["nombre_sector", "centro_costo", "estado_sector_id"]

    nombre = s.fields["nombre_sector"]
    assert nombre.label == "Nombre del Sector"  # info={"label": ...} del modelo
    assert nombre.tipo == "text"
    assert nombre.required is True
    assert nombre.max_length == 150
    assert nombre.unique is True

    estado = s.fields["estado_sector_id"]
    assert estado.tipo == "fk"
    assert estado.fk_model is EstadoSector
    assert estado.relacion == "estado"
    assert estado.fk_label == "nombre_estado_sector"
    assert estado.es_estado is True


def test_columnas_tecnicas_no_se_exponen():
    for spec in REGISTRY.values():
        assert not {"uuid", "creado_en", "actualizado_en"} & set(spec.fields)


def test_subentidad_y_padre():
    u = REGISTRY["ubicaciones"]
    assert u.es_subentidad
    assert (u.padre.entidad, u.padre.fk) == ("sectores", "sector_id")
    assert REGISTRY["sectores"].hijos == ("ubicaciones",)
    assert REGISTRY["cuentas"].hijos == ()


def test_cuentas_labels_desde_el_modelo():
    c = REGISTRY["cuentas"]
    assert c.fields["numero_cuenta"].label == "Número de cuenta"
    assert c.fields["estado_cuenta_id"].fk_model is EstadoCuenta


def test_listado_y_filtros_por_defecto():
    s = REGISTRY["sectores"]
    assert s.listado == ("nombre_sector", "centro_costo", "estado_sector_id")
    assert s.filtros == ("nombre_sector", "centro_costo", "estado_sector_id")


def test_formato_legacy_para_framework():
    d = ENTIDADES["sectores"]
    assert d["bp_name"] == "crud"
    assert d["listado"] == {"columns": ["nombre_sector", "centro_costo", "estado_sector_id"]}
    assert d["subentidades"][0]["entidad"] == "ubicaciones"
    assert d["subentidades"][0]["fk"] == "sector_id"
    assert d["subentidades"][0]["label"] == "Ubicaciones"

    u = ENTIDADES["ubicaciones"]
    assert u["es_subentidad"] is True
    assert (u["entidad_padre"], u["fk_padre"]) == ("sectores", "sector_id")


# ---------------------------------------------------------------------------
# Overrides
# ---------------------------------------------------------------------------

def test_override_de_campo_gana_sobre_el_modelo():
    reg = construir_registry(con("sectores", fields={"centro_costo": {"label": "CeCo"}}))
    assert reg["sectores"].fields["centro_costo"].label == "CeCo"


def test_excluir_campo():
    reg = construir_registry(con("sectores", excluir=["centro_costo"]))
    assert "centro_costo" not in reg["sectores"].fields
    assert "centro_costo" not in reg["sectores"].listado


def test_listado_explicito():
    reg = construir_registry(con("sectores", listado=["nombre_sector"]))
    assert reg["sectores"].listado == ("nombre_sector",)


def test_valores_por_defecto():
    reg = construir_registry({"sectores": {"model": Sector}})
    s = reg["sectores"]
    assert (s.label_plural, s.label_singular, s.genero) == ("sectores", "sectores", "m")
    assert s.sidebar is False


# ---------------------------------------------------------------------------
# Validación: errores claros al arrancar
# ---------------------------------------------------------------------------

def test_clave_de_entidad_desconocida_sugiere_la_correcta():
    [error] = errores_de(con("sectores", lable_plural="x"))
    assert "lable_plural" in error and "label_plural" in error


def test_campo_inexistente():
    [error] = errores_de(con("sectores", fields={"nombre_sectr": {"label": "x"}}))
    assert "nombre_sectr" in error and "nombre_sector" in error


def test_clave_de_campo_desconocida():
    [error] = errores_de(con("sectores", fields={"nombre_sector": {"requerido": True}}))
    assert "requerido" in error and "required" in error


def test_tipo_invalido():
    [error] = errores_de(con("sectores", fields={"centro_costo": {"tipo": "texto"}}))
    assert "texto" in error


def test_select_sin_opciones():
    [error] = errores_de(con("sectores", fields={"centro_costo": {"tipo": "select"}}))
    assert "options" in error


def test_listado_con_campo_inexistente():
    [error] = errores_de(con("sectores", listado=["nombre_sector", "codigo"]))
    assert "listado" in error and "codigo" in error


def test_genero_invalido():
    [error] = errores_de(con("sectores", genero="x"))
    assert "genero" in error


def test_padre_inexistente():
    [error] = errores_de(con("ubicaciones", padre={"entidad": "sector", "fk": "sector_id"}))
    assert "'sector'" in error and "sectores" in error


def test_padre_fk_que_no_apunta_al_padre():
    [error] = errores_de(con("ubicaciones", padre={"entidad": "sectores", "fk": "nombre_ubicacion"}))
    assert "no es una FK hacia Sector" in error


def test_falta_model():
    [error] = errores_de({"sectores": {"label_plural": "sectores"}})
    assert "falta 'model'" in error


def test_model_que_no_es_sqlalchemy():
    [error] = errores_de({"sectores": {"model": dict}})
    assert "no es un modelo SQLAlchemy" in error


def test_junta_todos_los_errores_de_una_vez():
    errores = errores_de({
        "sectores": {"model": Sector, "genero": "x", "listado": ["nada"]},
        "cuentas": {"model": Cuenta, "fields": {"no_existe": {}}},
    })
    assert len(errores) == 3
