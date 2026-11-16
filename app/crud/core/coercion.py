# app/crud/core/coercion.py
"""
Conversión y validación de datos de entrada.

Un formulario HTML siempre envía texto ("2026-01-15", "False", "12,5", "").
Antes de guardar hay que convertir cada valor al tipo de su columna y validar
obligatoriedad y largo. La conversión se decide por el TIPO DE LA COLUMNA del
modelo (no por el widget), así funciona igual para la web y para la API.

No depende de Flask: recibe cualquier dict-like (request.form, un JSON, un dict).
"""
from __future__ import annotations

from datetime import date, datetime
from decimal import Decimal, InvalidOperation

from sqlalchemy import inspect as sa_inspect
from sqlalchemy import types as T

VERDADEROS = {"true", "1", "si", "sí", "on", "yes"}
FALSOS = {"false", "0", "no", "off"}

_FORMATOS_FECHA = ("%Y-%m-%d", "%d/%m/%Y")
_FORMATOS_FECHA_HORA = ("%Y-%m-%dT%H:%M", "%Y-%m-%dT%H:%M:%S", "%Y-%m-%d %H:%M:%S",
                        "%Y-%m-%d %H:%M", "%d/%m/%Y %H:%M")


class ErroresValidacion(Exception):
    """Uno o más campos no son válidos. `errores` = {campo: mensaje}."""

    def __init__(self, errores: dict[str, str]):
        self.errores = errores
        super().__init__("; ".join(f"{c}: {m}" for c, m in errores.items()))


# ---------------------------------------------------------------------------
# Conversión de un valor
# ---------------------------------------------------------------------------

def _parsear(valor: str, formatos):
    for fmt in formatos:
        try:
            return datetime.strptime(valor, fmt)
        except ValueError:
            pass
    return None


def convertir(columna, valor):
    """
    Convierte `valor` al tipo Python de `columna`.
    "" y None → None. Lanza ValueError con un mensaje legible si no se puede.
    """
    if valor is None:
        return None
    if isinstance(valor, str):
        valor = valor.strip()
        if valor == "":
            return None

    t = columna.type

    # El orden importa: Boolean e Integer, Enum y String, DateTime y Date.
    if isinstance(t, T.Boolean):
        if isinstance(valor, bool):
            return valor
        texto = str(valor).strip().lower()
        if texto in VERDADEROS:
            return True
        if texto in FALSOS:
            return False
        raise ValueError("debe ser Sí o No")

    if isinstance(t, T.Integer):
        if isinstance(valor, bool):
            raise ValueError("debe ser un número entero")
        if isinstance(valor, int):
            return valor
        try:
            return int(str(valor))
        except ValueError:
            raise ValueError("debe ser un número entero") from None

    if isinstance(t, (T.Numeric, T.Float)):
        try:
            numero = Decimal(str(valor).replace(",", "."))
        except InvalidOperation:
            raise ValueError("debe ser un número") from None
        if not numero.is_finite():
            raise ValueError("debe ser un número")
        return float(numero) if isinstance(t, T.Float) or not t.asdecimal else numero

    if isinstance(t, T.DateTime):
        if isinstance(valor, datetime):
            return valor
        if isinstance(valor, date):
            return datetime(valor.year, valor.month, valor.day)
        resultado = _parsear(valor, _FORMATOS_FECHA_HORA) or _parsear(valor, _FORMATOS_FECHA)
        if resultado is None:
            raise ValueError("debe ser una fecha válida (AAAA-MM-DD)")
        return resultado

    if isinstance(t, T.Date):
        if isinstance(valor, datetime):
            return valor.date()
        if isinstance(valor, date):
            return valor
        resultado = _parsear(valor, _FORMATOS_FECHA)
        if resultado is None:
            raise ValueError("debe ser una fecha válida (AAAA-MM-DD)")
        return resultado.date()

    if isinstance(t, T.Enum):
        if t.enums and valor not in t.enums:
            raise ValueError(f"debe ser uno de: {', '.join(t.enums)}")
        return valor

    if isinstance(t, T.String):
        valor = str(valor)
        if t.length and len(valor) > t.length:
            raise ValueError(f"admite como máximo {t.length} caracteres")
        return valor

    return valor


# ---------------------------------------------------------------------------
# Conversión de un registro completo
# ---------------------------------------------------------------------------

def datos_de_entrada(model, fields: dict, entrada, *, parcial: bool = False) -> dict:
    """
    Convierte y valida los datos recibidos para `model`.

    fields   campos del metamodelo ({nombre: {"label", "tipo", "required", ...}}).
    entrada  dict-like con los valores crudos (request.form, JSON...).
    parcial  False (alta): se procesan todos los campos; los obligatorios
             ausentes o vacíos son error.
             True (edición): solo se procesan los campos presentes en `entrada`;
             los ausentes conservan su valor actual.

    Los campos tipo "file" y "virtual" no se procesan acá.
    Devuelve {campo: valor_convertido}; lanza ErroresValidacion con todos los
    errores juntos.
    """
    columnas = sa_inspect(model).columns
    datos: dict = {}
    errores: dict[str, str] = {}

    for campo, cfg in fields.items():
        if cfg.get("virtual") or cfg.get("tipo") == "file":
            continue
        if parcial and campo not in entrada:
            continue

        crudo = entrada.get(campo)
        columna = columnas.get(campo)
        try:
            valor = convertir(columna, crudo) if columna is not None else crudo
        except ValueError as e:
            errores[campo] = f"{cfg.get('label', campo)} {e}."
            continue

        if valor is None and cfg.get("required"):
            errores[campo] = f"{cfg.get('label', campo)} es obligatorio."
            continue

        datos[campo] = valor

    if errores:
        raise ErroresValidacion(errores)
    return datos


def valor_para_formulario(cfg: dict, valor):
    """Valor de la base → texto para un <input> HTML."""
    if valor is None:
        return ""
    if cfg.get("tipo") == "date" and isinstance(valor, (date, datetime)):
        return (valor.date() if isinstance(valor, datetime) else valor).isoformat()
    if cfg.get("tipo") == "datetime" and isinstance(valor, datetime):
        return valor.strftime("%Y-%m-%dT%H:%M")
    return valor
