# app/crud/schema/jsonschema.py
"""
JSON Schema de cada entidad, generado desde su EntitySpec.

Se usa para validar lo que llega por la API y para documentarla (OpenAPI).
Hay tres variantes de entrada y una de salida:

    crear       POST   todos los campos obligatorios deben venir
    reemplazar  PUT    igual que crear (los opcionales ausentes quedan vacíos)
    modificar   PATCH  ningún campo es obligatorio; solo se cambia lo enviado
    registro    respuesta: lo que devuelve la API (incluye id, uuid, fechas y etiquetas)

Los campos de tipo "file" no se reciben por la API (las fotos se suben desde la web).
"""
from __future__ import annotations

import re

from jsonschema import Draft202012Validator
from sqlalchemy import inspect as sa_inspect
from sqlalchemy import types as T

from app.crud.core.coercion import ErroresValidacion
from app.crud.meta.spec import EntitySpec

MODOS_ENTRADA = ("crear", "reemplazar", "modificar")

_NOMBRES_TIPO = {
    "string": "un texto",
    "integer": "un número entero",
    "number": "un número",
    "boolean": "true o false",
    "object": "un objeto JSON",
}


# ---------------------------------------------------------------------------
# Esquema de un campo
# ---------------------------------------------------------------------------

def _esquema_columna(columna) -> dict:
    t = columna.type
    if isinstance(t, T.Boolean):
        return {"type": "boolean"}
    if isinstance(t, T.Integer):
        return {"type": "integer"}
    if isinstance(t, (T.Numeric, T.Float)):
        return {"type": "number"}
    if isinstance(t, T.DateTime):
        return {"type": "string", "format": "date-time"}
    if isinstance(t, T.Date):
        return {"type": "string", "format": "date"}
    if isinstance(t, T.Enum):
        return {"type": "string", "enum": list(t.enums)}
    if isinstance(t, T.String):
        esquema = {"type": "string"}
        if t.length:
            esquema["maxLength"] = t.length
        return esquema
    if isinstance(t, T.JSON):
        return {}
    return {"type": "string"}


def esquema_campo(spec: EntitySpec, campo: str) -> dict:
    f = spec.fields[campo]
    columna = sa_inspect(spec.model).columns[campo]
    esquema = {"title": f.label, **_esquema_columna(columna)}

    if f.tipo == "fk":
        esquema["minimum"] = 1
        esquema["description"] = f"ID de {f.fk_model.__name__}"
    elif f.tipo == "select" and f.options and esquema.get("type") != "boolean":
        esquema["enum"] = [o["value"] for o in f.options]
    elif f.tipo == "date" and esquema.get("format") == "date-time":
        # La web solo pide la fecha; la API acepta fecha o fecha y hora.
        esquema["description"] = "Fecha (AAAA-MM-DD) o fecha y hora (AAAA-MM-DDTHH:MM)"
        esquema.pop("format")
    return esquema


def _admite_nulo(esquema: dict) -> dict:
    """Agrega null a los tipos admitidos (JSON Schema 2020-12)."""
    tipo = esquema.get("type")
    if tipo is None:
        return esquema
    resultado = {**esquema, "type": [tipo, "null"]}
    if "enum" in resultado:
        resultado["enum"] = [*resultado["enum"], None]
    return resultado


def campos_api(spec: EntitySpec) -> list[str]:
    """Campos que se pueden enviar por la API."""
    return [c for c, f in spec.fields.items() if f.tipo != "file"]


# ---------------------------------------------------------------------------
# Esquemas de la entidad
# ---------------------------------------------------------------------------

def esquema_entrada(spec: EntitySpec, modo: str) -> dict:
    if modo not in MODOS_ENTRADA:
        raise ValueError(f"modo inválido: {modo}")

    propiedades, requeridos = {}, []
    for campo in campos_api(spec):
        f = spec.fields[campo]
        esquema = esquema_campo(spec, campo)
        if f.required and modo != "modificar":
            requeridos.append(campo)
        if f.required and esquema.get("type") == "string":
            esquema["minLength"] = 1  # obligatorio = no vacío
        if not f.required:
            esquema = _admite_nulo(esquema)
        propiedades[campo] = esquema

    resultado = {
        "$schema": "https://json-schema.org/draft/2020-12/schema",
        "title": f"{spec.label_singular.capitalize()} ({modo})",
        "type": "object",
        "properties": propiedades,
        "additionalProperties": False,
    }
    if requeridos:
        resultado["required"] = requeridos
    if modo == "modificar":
        resultado["minProperties"] = 1
    return resultado


def esquema_registro(spec: EntitySpec) -> dict:
    """Forma de un registro en las respuestas de la API."""
    columnas = sa_inspect(spec.model).columns
    propiedades = {spec.pk: {"type": "integer", "title": "ID", "readOnly": True}}
    if "uuid" in columnas:
        propiedades["uuid"] = {"type": "string", "format": "uuid", "readOnly": True}

    for campo, f in spec.fields.items():
        esquema = esquema_campo(spec, campo)
        if f.tipo == "file":
            esquema = {"title": f.label, "type": "string", "description": "Ruta pública del archivo"}
        propiedades[campo] = _admite_nulo(esquema) if not f.required else esquema
        if f.tipo == "fk":
            propiedades[f"{campo}_label"] = {
                "type": ["string", "null"], "readOnly": True,
                "title": f"{f.label} (texto)",
            }

    for tecnica in ("creado_en", "actualizado_en"):
        if tecnica in columnas:
            propiedades[tecnica] = {"type": ["string", "null"], "format": "date-time", "readOnly": True}

    return {
        "title": spec.label_singular.capitalize(),
        "type": "object",
        "properties": propiedades,
    }


# ---------------------------------------------------------------------------
# Validación
# ---------------------------------------------------------------------------

def _mensaje(spec: EntitySpec, error) -> tuple[str, str]:
    """(campo, mensaje en castellano) para un error de jsonschema."""
    def label(c):
        f = spec.fields.get(c)
        return f.label if f else c

    if error.validator == "required":
        # Un error por cada campo faltante: "'centro_costo' is a required property"
        m = re.match(r"'(.+)' is a required property", error.message)
        faltante = m.group(1) if m else "_general"
        return faltante, f"{label(faltante)} es obligatorio."
    if error.validator == "minProperties":
        return "_general", "Hay que enviar al menos un campo para modificar."

    campo = error.path[0] if error.path else "_general"
    if campo == "_general" and error.validator == "type":
        return campo, "El cuerpo de la petición debe ser un objeto JSON."

    nombre = label(campo)
    v = error.validator_value
    if error.validator == "type":
        tipos = [v] if isinstance(v, str) else v
        nombres = [_NOMBRES_TIPO.get(t, t) for t in tipos if t != "null"]
        sufijo = " o vacío (null)" if "null" in tipos else ""
        return campo, f"{nombre} debe ser {' o '.join(nombres)}{sufijo}."
    if error.validator == "minLength":
        return campo, f"{nombre} es obligatorio."
    if error.validator == "maxLength":
        return campo, f"{nombre} admite como máximo {v} caracteres."
    if error.validator == "minimum":
        return campo, f"{nombre} debe ser mayor o igual a {v}."
    if error.validator == "enum":
        opciones = ", ".join("null" if o is None else str(o) for o in v)
        return campo, f"{nombre} debe ser uno de: {opciones}."
    return campo, f"{nombre}: {error.message}"


def validar(spec: EntitySpec, datos, modo: str) -> None:
    """Lanza ErroresValidacion con todos los problemas encontrados en `datos`."""
    esquema = esquema_entrada(spec, modo)
    errores: dict[str, str] = {}

    if isinstance(datos, dict):
        for campo in sorted(set(datos) - set(esquema["properties"])):
            errores[campo] = f"Campo desconocido: «{campo}»."

    validador = Draft202012Validator({**esquema, "additionalProperties": True})
    for error in sorted(validador.iter_errors(datos), key=lambda e: list(e.path)):
        campo, mensaje = _mensaje(spec, error)
        errores.setdefault(campo, mensaje)

    if errores:
        raise ErroresValidacion(errores)
