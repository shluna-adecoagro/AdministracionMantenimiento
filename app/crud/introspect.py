# app/crud/introspect.py
"""
Introspección de modelos SQLAlchemy -> metamodelo CRUD.

Genera, a partir de un modelo, la descripción de sus campos (etiqueta, widget,
obligatoriedad, FKs...). El registry (app/crud/meta/registry.py) la combina con
los overrides de cada entidad: lo inferido + overrides = EntitySpec.

Solo infiere lo que el modelo realmente sabe. Lo que NO puede saber (labels con
acentos, género, columnas del listado, widgets especiales, subentidades, tabs)
queda para los overrides.

Pensado para SQLAlchemy 2.x (también funciona en 1.4).
"""
from __future__ import annotations

import re
import unicodedata

from sqlalchemy import Column
from sqlalchemy import inspect as sa_inspect
from sqlalchemy import types as T
from sqlalchemy.orm import configure_mappers

# ---------------------------------------------------------------------------
# Convenciones (ajustables)
# ---------------------------------------------------------------------------

# Columnas técnicas que nunca se exponen en formularios.
COLUMNAS_OCULTAS = {"uuid", "creado_en", "actualizado_en"}

# Claves que el introspector entiende dentro de Column(..., info={...}).
CLAVES_INFO = {"label"}

# Convenciones por nombre (se pueden apagar con False):
#  - FK hacia una clase cuyo nombre empieza con "Estado" -> es_estado=True y label "Estado".
#  - Columna String cuyo nombre empieza con "foto"        -> widget "file" en subcarpeta "fotos".
# `info={"label": ...}` en la columna siempre tiene prioridad sobre la convención.
REGLA_ESTADO = True
PREFIJO_ESTADO = "Estado"
REGLA_FOTO = True
PREFIJO_FOTO = "foto"
#  - Columna String cuyo nombre empieza con "color"       -> widget "color" (selector de color).
REGLA_COLOR = True
PREFIJO_COLOR = "color"
SUBCARPETA_FOTOS = "fotos"

# String(n) con n >= TEXTAREA_DESDE se infiere como textarea.
TEXTAREA_DESDE = 300

# Los templates actuales modelan los booleanos como un select No/Sí.
OPCIONES_BOOLEANO = [
    {"value": False, "label": "No"},
    {"value": True, "label": "Sí"},
]


# ---------------------------------------------------------------------------
# Utilidades de texto
# ---------------------------------------------------------------------------

def sin_acentos(texto: str) -> str:
    return "".join(
        c for c in unicodedata.normalize("NFD", str(texto))
        if unicodedata.category(c) != "Mn"
    )


def normalizar_texto(texto) -> str:
    """Minúsculas, sin acentos y con espacios colapsados (para comparar labels)."""
    return re.sub(r"\s+", " ", sin_acentos(texto or "").strip().lower())


def inicial(texto: str) -> str:
    """Mayúscula inicial sin tocar el resto: "BOM de activos" (capitalize daría "Bom de activos")."""
    return texto[:1].upper() + texto[1:]


def humanizar(nombre: str) -> str:
    """'nro_serie_chasis' -> 'Nro serie chasis'; 'NumeroPedido' -> 'Numero pedido'."""
    n = re.sub(r"_id$", "", nombre)
    n = re.sub(r"(?<=[a-z0-9])(?=[A-Z])", " ", n)  # PascalCase -> palabras
    n = n.replace("_", " ").strip().lower()
    return n[:1].upper() + n[1:]


# ---------------------------------------------------------------------------
# Tipos
# ---------------------------------------------------------------------------

def tipo_widget(col) -> tuple[str, dict]:
    """
    Devuelve (tipo, extras) usando el vocabulario que entienden los templates
    actuales: text, number, textarea, date, select (y fk, que se resuelve aparte).
    El orden importa: Enum y Text son subclases de String.
    """
    t = col.type
    if isinstance(t, T.Boolean):
        return "select", {"options": list(OPCIONES_BOOLEANO)}
    if isinstance(t, T.Enum):
        opciones = [{"value": v, "label": humanizar(v)} for v in (t.enums or [])]
        return "select", {"options": opciones}
    if isinstance(t, (T.Date, T.DateTime)):
        # Los templates actuales solo conocen "date" (ver lecturas_medidor.fecha_lectura).
        return "date", {}
    if isinstance(t, (T.Integer, T.Numeric, T.Float)):
        return "number", {}
    if isinstance(t, T.Text):
        return "textarea", {}
    if isinstance(t, T.String):
        return ("textarea" if (t.length or 0) >= TEXTAREA_DESDE else "text"), {}
    return "text", {}


# ---------------------------------------------------------------------------
# Relaciones y FKs
# ---------------------------------------------------------------------------

def _relacion_para(col, mapper):
    """Relationship many-to-one que usa `col` como columna local (None si no hay)."""
    for rel in mapper.relationships:
        if rel.direction.name == "MANYTOONE" and col in rel.local_columns:
            return rel
    return None


def _clase_por_tabla(mapper, tabla):
    """Clase mapeada a `tabla` (para FKs sin relationship declarada)."""
    for m in mapper.registry.mappers:
        if m.local_table is tabla:
            return m.class_
    return None


def columnas_hacia(model, destino) -> list[str]:
    """Columnas de `model` que son FK hacia alguna tabla de `destino`."""
    tablas = set(sa_inspect(destino).tables)
    return [
        attr.key for attr in sa_inspect(model).column_attrs
        if isinstance(attr.columns[0], Column)
        and any(fk.column.table in tablas for fk in attr.columns[0].foreign_keys)
    ]


def fk_apunta_a(hijo, columna: str, padre) -> bool:
    """¿`hijo.columna` es una FK hacia alguna de las tablas de `padre`?"""
    try:
        col = sa_inspect(hijo).column_attrs[columna].columns[0]
    except (KeyError, AttributeError):
        return False
    tablas_padre = set(sa_inspect(padre).tables)
    return any(fk.column.table in tablas_padre for fk in col.foreign_keys)


# ---------------------------------------------------------------------------
# Inferencia
# ---------------------------------------------------------------------------

def info_de(prop) -> dict:
    """
    `info` de un atributo: el de la columna (Column(..., info=...)) o, para un
    valor calculado, el de column_property(..., info=...).
    """
    col = prop.columns[0]
    if isinstance(col, Column):
        return col.info or {}
    return prop.info or {}


def es_calculado(prop) -> bool:
    """column_property con una expresión (ej: una suma), no una columna de la tabla."""
    return not isinstance(prop.columns[0], Column)


def _columna_seleccionada(expresion):
    """
    Si el calculado es `select(Otra.columna)...scalar_subquery()`, devuelve esa
    columna (para saber si trae una FK); si no, None.
    """
    e = getattr(expresion, "element", None)       # Label → ScalarSelect
    e = getattr(e, "element", None)                # ScalarSelect → Select
    columnas = list(getattr(e, "selected_columns", ()) or ())
    if len(columnas) == 1 and isinstance(columnas[0], Column):
        return columnas[0]
    return None


def _inferir_calculado(key: str, prop, mapper) -> dict:
    info = info_de(prop)
    etiqueta = info.get("label") or humanizar(key)

    # Calculado que trae una FK (ej: el tipo de activo, a través de la
    # categoría): se trata como FK de solo lectura. Muestra el nombre del
    # destino y, en el formulario, sirve de filtro para los selects que dependen de él.
    origen = _columna_seleccionada(prop.columns[0])
    fks = list(origen.foreign_keys) if origen is not None else []
    if fks:
        destino = _clase_por_tabla(mapper, fks[0].column.table)
        if destino is not None:
            campo = {"label": etiqueta, "tipo": "fk", "fk_model": destino,
                     "required": False, "solo_lectura": True}
            if getattr(destino, "__label_field__", None):
                campo["fk_label"] = destino.__label_field__
            return campo

    tipo, extras = tipo_widget(prop.columns[0])
    if tipo in ("select", "textarea"):
        tipo, extras = "text", {}
    return {"label": etiqueta, "tipo": tipo, "required": False, "solo_lectura": True}


def _inferir_campo(key: str, col, mapper) -> dict:
    info = getattr(col, "info", None) or {}
    etiqueta = info.get("label") or humanizar(key)
    requerido = not getattr(col, "nullable", True)

    fks = list(getattr(col, "foreign_keys", ()) or ())
    if fks:
        fk = fks[0]
        rel = _relacion_para(col, mapper)
        destino = (
            rel.mapper.class_ if rel is not None
            else _clase_por_tabla(mapper, fk.column.table)
        )
        campo = {
            "label": etiqueta,
            "tipo": "fk",
            "fk_model": destino,
            "required": requerido,
        }
        if rel is not None:
            campo["relacion"] = rel.key
        if REGLA_ESTADO and destino is not None and destino.__name__.startswith(PREFIJO_ESTADO):
            campo["es_estado"] = True
            if not info.get("label"):
                campo["label"] = "Estado"
        etiqueta_fk = getattr(destino, "__label_field__", None) if destino else None
        if etiqueta_fk:
            campo["fk_label"] = etiqueta_fk
        return campo

    tipo, extras = tipo_widget(col)
    if REGLA_FOTO and key.startswith(PREFIJO_FOTO) and isinstance(col.type, T.String):
        tipo, extras = "file", {"subcarpeta": SUBCARPETA_FOTOS}
        if not info.get("label"):
            etiqueta = "Foto"
    if REGLA_COLOR and key.startswith(PREFIJO_COLOR) and isinstance(col.type, T.String):
        tipo, extras = "color", {}
        if not info.get("label"):
            etiqueta = "Color"
    campo = {"label": etiqueta, "tipo": tipo, "required": requerido}
    campo.update(extras)
    return campo


def inferir_entidad(model) -> dict:
    """
    Devuelve:
      {
        "meta":      dict con el esquema del metamodelo (model, pk, fields, auditoria),
        "excluidos": [(atributo, motivo), ...]  # columnas que no se exponen
        "avisos":    [(atributo, mensaje), ...]  # problemas en la metadata del modelo (info mal escrita)
      }
    """
    configure_mappers()
    mapper = sa_inspect(model)

    es_hijo = mapper.inherits is not None
    discriminador = mapper.polymorphic_on

    campos: dict[str, dict] = {}
    excluidos: list[tuple[str, str]] = []
    avisos: list[tuple[str, str]] = []

    for prop in mapper.column_attrs:
        key = prop.key
        col = prop.columns[0]

        # Validar `info` antes de cualquier `continue`: un typo no debe pasar en silencio.
        info = info_de(prop)
        desconocidas = sorted(set(info) - CLAVES_INFO)
        if desconocidas:
            avisos.append((key, f"info con claves desconocidas {desconocidas} (¿typo? válidas: {sorted(CLAVES_INFO)})"))
        if "label" in info and not (isinstance(info["label"], str) and info["label"].strip()):
            avisos.append((key, "info['label'] debe ser un texto no vacío"))

        if es_calculado(prop):
            campos[key] = _inferir_calculado(key, prop, mapper)
            continue
        if getattr(col, "primary_key", False):
            continue
        if key in COLUMNAS_OCULTAS:
            excluidos.append((key, "columna técnica (convención)"))
            continue
        if es_hijo and discriminador is not None and col is discriminador:
            excluidos.append((key, "discriminador polimórfico"))
            continue
        if isinstance(col.type, T.JSON):
            excluidos.append((key, "JSON (se gestiona aparte)"))
            continue

        campos[key] = _inferir_campo(key, col, mapper)

    # Orden: primero las columnas propias, después las heredadas (ej: el estado
    # de un empleado, que está en "recursos") y al final los valores calculados.
    def _orden(key):
        if campos[key].get("solo_lectura") and es_calculado(mapper.attrs[key]):
            return 2
        return 0 if mapper.attrs[key].columns[0].table is mapper.local_table else 1

    campos = {k: campos[k] for k in sorted(campos, key=_orden)}

    meta = {
        "model": model,
        "pk": mapper.primary_key[0].name,
        "fields": campos,
        # AuditMixin aporta obtener_historial(); es la señal más barata de auditabilidad.
        "auditoria": {"enabled": hasattr(model, "obtener_historial")},
    }
    return {"meta": meta, "excluidos": excluidos, "avisos": avisos}
