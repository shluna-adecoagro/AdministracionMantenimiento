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

import re

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
# Números de un CSV (formato argentino)
# ---------------------------------------------------------------------------

# «1.234,5»: puntos de miles (en grupos de tres) y coma decimal.
_MILES_Y_COMA = re.compile(r"^[-+]?\d{1,3}(\.\d{3})+,\d+$")
# «1.400», «12.345.678»: solo puntos de miles, en grupos de tres.
_SOLO_MILES = re.compile(r"^[-+]?\d{1,3}(\.\d{3})+$")


def numero_csv(texto: str) -> str:
    """
    Normaliza un número escrito en formato argentino, como lo exportan Excel y
    SharePoint, para que convertir() lo lea bien. Solo para la importación CSV:
    los formularios web mandan el punto como decimal («1.5») y no pasan por acá.

        «1.234,5»  → «1234.5»   puntos de miles y coma decimal
        «1.400»    → «1400»     solo puntos en grupos de tres: miles
        «1,5», «1.5», «300»     sin cambios (convertir() ya toma la coma como decimal)

    Lo demás («1,234.5», «12.34,5») queda igual: convertir() lo rechaza con un
    error, en vez de adivinar.
    """
    valor = texto.strip()
    if _MILES_Y_COMA.match(valor):
        return valor.replace(".", "").replace(",", ".")
    if _SOLO_MILES.match(valor):
        return valor.replace(".", "")
    return texto


# ---------------------------------------------------------------------------
# Conversión de un registro completo
# ---------------------------------------------------------------------------

def datos_de_entrada(model, fields: dict, entrada, *, parcial: bool = False,
                     importacion: bool = False) -> dict:
    """
    Convierte y valida los datos recibidos para `model`.

    fields   campos del metamodelo ({nombre: {"label", "tipo", "required", ...}}).
    entrada  dict-like con los valores crudos (request.form, JSON...).
    parcial  False (alta): se procesan todos los campos; los obligatorios
             ausentes o vacíos son error.
             True (edición): solo se procesan los campos presentes en `entrada`;
             los ausentes conservan su valor actual.

    importacion  True: también se procesan los campos de solo importación (datos
             cuyo dueño es el ERP). Desde la web y la API se ignoran.

    Los campos tipo "file", "virtual" y de solo lectura no se procesan acá.
    Devuelve {campo: valor_convertido}; lanza ErroresValidacion con todos los
    errores juntos.
    """
    columnas = sa_inspect(model).columns
    datos: dict = {}
    errores: dict[str, str] = {}

    for campo, cfg in fields.items():
        if cfg.get("virtual") or cfg.get("solo_lectura") or cfg.get("tipo") == "file":
            continue
        if cfg.get("solo_importacion") and not importacion:
            continue
        if parcial and campo not in entrada:
            continue

        crudo = entrada.get(campo)
        columna = columnas.get(campo)
        if cfg.get("solo_alta") and parcial:
            continue  # en una modificación, los campos de alta no existen
        try:
            if columna is not None:
                valor = convertir(columna, crudo)
            elif cfg.get("solo_alta"):
                valor = convertir_sin_columna(cfg, crudo)
            else:
                valor = crudo
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


def convertir_sin_columna(cfg, valor):
    """
    Convierte el valor de un campo que no es una columna (campo de alta) según su
    tipo: número, FK (entero), fecha o texto.
    """
    if valor is None or (isinstance(valor, str) and valor.strip() == ""):
        return None
    tipo = cfg.get("tipo")
    if tipo == "number":
        return convertir(_COLUMNA_NUMERO, valor)
    if tipo == "fk":
        return convertir(_COLUMNA_ENTERO, valor)
    if tipo == "date":
        return convertir(_COLUMNA_FECHA, valor)
    if tipo == "select" and cfg.get("options"):
        texto = str(valor).strip()
        validos = {str(o["value"]): o["value"] for o in cfg["options"]}
        if texto not in validos:
            raise ValueError("no es una opción válida")
        return validos[texto]
    return str(valor).strip()


class _Columna:
    def __init__(self, tipo):
        self.type = tipo


_COLUMNA_NUMERO = _Columna(T.Float())
_COLUMNA_ENTERO = _Columna(T.Integer())
_COLUMNA_FECHA = _Columna(T.Date())


def valor_para_formulario(cfg: dict, valor):
    """Valor de la base → texto para un <input> HTML."""
    if valor is None:
        return ""
    if cfg.get("tipo") == "date" and isinstance(valor, (date, datetime)):
        return (valor.date() if isinstance(valor, datetime) else valor).isoformat()
    if cfg.get("tipo") == "datetime" and isinstance(valor, datetime):
        return valor.strftime("%Y-%m-%dT%H:%M")
    return valor
