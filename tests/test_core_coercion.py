"""Conversión de texto de formulario a tipos Python (app/crud/core/coercion.py)."""
from datetime import date, datetime
from decimal import Decimal

import pytest
from sqlalchemy import Boolean, Column, Date, DateTime, Enum, Float, Integer, Numeric, String

from app.crud.core.coercion import (
    ErroresValidacion,
    convertir,
    datos_de_entrada,
    valor_para_formulario,
)
from app.crud.entidades import REGISTRY


@pytest.mark.parametrize("tipo, crudo, esperado", [
    (String(10), "  hola ", "hola"),
    (String(10), "", None),
    (String(10), None, None),
    (Integer(), "42", 42),
    (Integer(), " 7 ", 7),
    (Numeric(10, 2), "12,5", Decimal("12.5")),
    (Numeric(10, 2), "12.5", Decimal("12.5")),
    (Float(), "3,25", 3.25),
    (Boolean(), "False", False),
    (Boolean(), "True", True),
    (Boolean(), "sí", True),
    (Boolean(), "0", False),
    (Date(), "2026-01-15", date(2026, 1, 15)),
    (Date(), "15/01/2026", date(2026, 1, 15)),
    (DateTime(), "2026-01-15", datetime(2026, 1, 15)),
    (DateTime(), "2026-01-15T08:30", datetime(2026, 1, 15, 8, 30)),
    (Enum("manual", "iot", name="origen"), "iot", "iot"),
])
def test_convertir(tipo, crudo, esperado):
    assert convertir(Column("c", tipo), crudo) == esperado


@pytest.mark.parametrize("tipo, crudo, mensaje", [
    (Integer(), "12a", "entero"),
    (Integer(), "1.5", "entero"),
    (Numeric(10, 2), "abc", "número"),
    (Numeric(10, 2), "NaN", "número"),
    (Boolean(), "quizás", "Sí o No"),
    (Date(), "2026-13-01", "fecha"),
    (String(3), "abcd", "3 caracteres"),
    (Enum("manual", "iot", name="origen"), "otro", "manual, iot"),
])
def test_convertir_invalido(tipo, crudo, mensaje):
    with pytest.raises(ValueError, match=mensaje):
        convertir(Column("c", tipo), crudo)


# ---------------------------------------------------------------------------
# Con modelos y specs reales
# ---------------------------------------------------------------------------

def test_alta_valida_y_convierte(app):
    cfg = REGISTRY["sectores"]
    datos = datos_de_entrada(cfg.model, cfg.fields, {
        "nombre_sector": " Taller ", "centro_costo": "CC", "estado_sector_id": "1",
    })
    assert datos == {"nombre_sector": "Taller", "centro_costo": "CC", "estado_sector_id": 1}


def test_alta_junta_todos_los_errores(app):
    cfg = REGISTRY["sectores"]
    with pytest.raises(ErroresValidacion) as exc:
        datos_de_entrada(cfg.model, cfg.fields, {"estado_sector_id": "x"})
    assert set(exc.value.errores) == {"nombre_sector", "centro_costo", "estado_sector_id"}


def test_edicion_parcial_solo_toca_lo_enviado(app):
    cfg = REGISTRY["sectores"]
    datos = datos_de_entrada(cfg.model, cfg.fields, {"centro_costo": "CC-2"}, parcial=True)
    assert datos == {"centro_costo": "CC-2"}


def test_edicion_parcial_no_permite_vaciar_obligatorios(app):
    cfg = REGISTRY["sectores"]
    with pytest.raises(ErroresValidacion):
        datos_de_entrada(cfg.model, cfg.fields, {"nombre_sector": ""}, parcial=True)


def test_lectura_de_medidor_acepta_fecha_del_formulario(app):
    """Antes daba error 500: SQLite exige datetime, no texto."""
    cfg = REGISTRY["lecturas_medidor"]
    datos = datos_de_entrada(cfg.model, cfg.fields, {
        "medidor_id": "1", "fecha_lectura": "2026-01-15", "valor": "120,5", "origen": "manual",
    })
    assert datos["fecha_lectura"] == datetime(2026, 1, 15)


def test_bom_acepta_booleano_del_formulario(app):
    """Antes daba error 500: llegaba el texto 'False'."""
    cfg = REGISTRY["bom_activo"]
    datos = datos_de_entrada(cfg.model, cfg.fields, {"es_equivalencia": "False"}, parcial=True)
    assert datos == {"es_equivalencia": False}


def test_valor_para_formulario():
    assert valor_para_formulario({"tipo": "date"}, datetime(2026, 1, 15, 10, 0)) == "2026-01-15"
    assert valor_para_formulario({"tipo": "text"}, None) == ""
    assert valor_para_formulario({"tipo": "number"}, 3) == 3


# ---------------------------------------------------------------------------
# Números de un CSV en formato argentino (numero_csv)
# ---------------------------------------------------------------------------

@pytest.mark.parametrize("texto, esperado", [
    ("1.400", "1400"),              # solo miles
    ("12.345.678", "12345678"),
    ("-1.400", "-1400"),
    ("1.234,5", "1234.5"),          # miles y coma decimal
    ("1.234.567,89", "1234567.89"),
    ("1,5", "1,5"),                 # sin cambios: convertir() toma la coma como decimal
    ("1.5", "1.5"),                 # un punto que no agrupa de a tres: decimal
    ("1.25", "1.25"),
    ("300", "300"),
    ("1.4000", "1.4000"),           # grupo de cuatro: no son miles
    ("1,234.5", "1,234.5"),         # formato inglés: queda igual (y convertir() lo rechaza)
    ("12.34,5", "12.34,5"),
])
def test_numero_csv(texto, esperado):
    from app.crud.core.coercion import numero_csv

    assert numero_csv(texto) == esperado
