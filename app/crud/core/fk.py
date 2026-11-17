# app/crud/core/fk.py
"""
Claves foráneas: opciones para los <select> y etiquetas legibles.

Antes este código estaba copiado en cada vista de framework.py. Todo lo que
necesita saber "cómo se muestra el registro al que apunta una FK" está acá.
"""
from __future__ import annotations

from sqlalchemy.orm import selectinload


def es_fk(cfg: dict) -> bool:
    return cfg.get("tipo") == "fk"


def campos_fk(fields: dict) -> dict:
    return {c: cfg for c, cfg in fields.items() if es_fk(cfg)}


def relacion(model, campo: str, cfg: dict) -> str | None:
    """Nombre del relationship que lleva del registro al destino de la FK."""
    if cfg.get("relacion"):
        return cfg["relacion"]
    for rel in model.__mapper__.relationships:
        if any(col.name == campo for col in rel.local_columns):
            return rel.key
    return None


def etiqueta(obj, cfg: dict) -> str:
    """Texto que representa al registro destino (ej: 'Activo', 'Taller')."""
    if cfg.get("fk_label"):
        return getattr(obj, cfg["fk_label"])
    if hasattr(obj, "label"):
        return obj.label
    if hasattr(obj, "pk"):
        return str(obj.pk)
    return str(obj)


def destino(registro, campo: str, cfg: dict):
    rel = relacion(type(registro), campo, cfg)
    return getattr(registro, rel) if rel else None


# ---------------------------------------------------------------------------
# Opciones para formularios y filtros
# ---------------------------------------------------------------------------

def opciones(cfg: dict) -> list[dict]:
    """
    Opciones de un <select> de FK. `extra_field`/`extra_value` permiten filtrar
    selects dependientes en el navegador (ej: modelos según la marca elegida).
    """
    fk_model = cfg["fk_model"]
    pk = fk_model.__mapper__.primary_key[0].name
    padres = [
        c.name for c in fk_model.__table__.columns
        if c.name.endswith("_id") and c.name != pk
    ]
    extra = padres[0] if padres else None

    return [
        {
            "value": getattr(obj, pk),
            "label": etiqueta(obj, cfg),
            "extra_value": getattr(obj, extra) if extra else None,
            "extra_field": extra,
        }
        for obj in fk_model.query.all()
    ]


def opciones_de(fields: dict) -> dict[str, list[dict]]:
    return {c: opciones(cfg) for c, cfg in campos_fk(fields).items()}


def validar_existencia(fields: dict, datos: dict) -> None:
    """
    Verifica que cada FK de `datos` apunte a un registro existente.
    Lanza ErroresValidacion con un mensaje por campo (ej: "Estado: no existe el ID 99.").
    """
    from app.core.db import db
    from app.crud.core.coercion import ErroresValidacion

    errores = {}
    for campo, cfg in campos_fk(fields).items():
        valor = datos.get(campo)
        if valor is not None and db.session.get(cfg["fk_model"], valor) is None:
            errores[campo] = f"{cfg.get('label', campo)}: no existe el ID {valor}."
    if errores:
        raise ErroresValidacion(errores)


# ---------------------------------------------------------------------------
# Etiquetas de un registro
# ---------------------------------------------------------------------------

def etiquetas(registro, fields: dict) -> dict:
    """
    {campo_fk: etiqueta} para un registro. Si el campo es un estado, el valor es
    {"label": ..., "color": ...} para mostrarlo como badge.
    """
    resultado = {}
    for campo, cfg in campos_fk(fields).items():
        obj = destino(registro, campo, cfg)
        if obj is None:
            resultado[campo] = None
        elif cfg.get("es_estado"):
            resultado[campo] = {
                "label": etiqueta(obj, cfg),
                "color": getattr(obj, "color_badge", None),
            }
        else:
            resultado[campo] = etiqueta(obj, cfg)
    return resultado


def agregar_etiquetas(d: dict, registro, fields: dict) -> dict:
    """Agrega `<campo>_label` (y `<campo>_color` para estados) al dict del registro."""
    for campo, cfg in campos_fk(fields).items():
        obj = destino(registro, campo, cfg)
        d[f"{campo}_label"] = etiqueta(obj, cfg) if obj is not None else None
        if obj is not None and cfg.get("es_estado"):
            d[f"{campo}_color"] = getattr(obj, "color_badge", None)
    return d


def para_auditoria(registro, fields: dict) -> dict:
    """
    Dict del registro con las FK expandidas a texto (ej: estado_sector='Activo'),
    para que el historial muestre nombres en lugar de IDs.
    """
    d = registro.to_dict()
    for campo, cfg in campos_fk(fields).items():
        obj = destino(registro, campo, cfg)
        if obj is None:
            continue
        nombre = campo.removesuffix("_id")
        d[nombre] = etiqueta(obj, cfg)
        if cfg.get("es_estado"):
            d[f"{nombre}_color"] = getattr(obj, "color_badge", None)
    return d


# ---------------------------------------------------------------------------
# Carga anticipada (evita una consulta por fila en los listados)
# ---------------------------------------------------------------------------

def carga_anticipada(model, fields: dict) -> list:
    opciones_carga = []
    for campo, cfg in campos_fk(fields).items():
        rel = relacion(model, campo, cfg)
        if rel:
            opciones_carga.append(selectinload(getattr(model, rel)))
    return opciones_carga
