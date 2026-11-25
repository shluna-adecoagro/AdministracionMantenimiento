# app/crud/core/repository.py
"""
Consultas de lectura: búsqueda, filtros y carga de registros.
"""
from __future__ import annotations

from sqlalchemy import Column, String, cast, or_, select
from sqlalchemy import inspect as sa_inspect

from app.core.db import db
from app.crud.core import fk


def obtener_o_404(model, id_):
    return db.get_or_404(model, id_)


def valores(registro, *, calculados: bool = True) -> dict:
    """
    {atributo: valor} de todas las columnas del registro (también las heredadas,
    en modelos con herencia). Con calculados=False se omiten los column_property
    calculados (ej: stock total), que no son datos propios del registro.

    Reemplaza a los to_dict() de cada modelo, que no siempre son serializables.
    """
    resultado = {
        attr.key: getattr(registro, attr.key)
        for attr in sa_inspect(type(registro)).column_attrs
        if calculados or isinstance(attr.columns[0], Column)
    }
    if calculados:
        # Calculados en Python (propiedades declaradas en __calculados__).
        for nombre in getattr(type(registro), "__calculados__", None) or {}:
            resultado[nombre] = getattr(registro, nombre)
    return resultado


def _columna(model, campo):
    col = model.__table__.columns.get(campo)
    if col is None:
        return None
    # CAST permite buscar texto también en columnas numéricas (portable a MariaDB).
    return col if isinstance(col.type, String) else cast(col, String)


def campos_de_filtro(fields: dict, filtros: list[str]) -> list[str]:
    """
    Campos de `filtros` que se filtran eligiendo un valor (no escribiendo): FK,
    opciones fijas y Sí/No. Son los selects combinables del listado y los que
    aceptan ?campo=valor en la URL.
    """
    return [c for c in filtros if c in fields and fields[c].get("tipo") in ("fk", "select")]


def _condicion_texto(model, fields: dict, campo: str, patron: str):
    """
    Condición «contiene» para un campo de la búsqueda de texto. En una FK se
    busca en el texto del registro vinculado (el nombre del modelo, del sector),
    no en su ID; si ese texto no es una columna (una propiedad de Python), la
    FK no participa de la búsqueda.
    """
    cfg = fields.get(campo) or {}
    if fk.es_fk(cfg):
        destino, etiqueta = cfg.get("fk_model"), cfg.get("fk_label")
        if destino is None or not etiqueta or etiqueta not in sa_inspect(destino).column_attrs:
            return None
        pk_destino = destino.__mapper__.primary_key[0]
        coincidencias = select(pk_destino).where(getattr(destino, etiqueta).ilike(patron))
        return getattr(model, campo).in_(coincidencias)
    col = _columna(model, campo)
    return None if col is None else col.ilike(patron)


def consulta_listado(
    model,
    fields: dict,
    filtros: list[str],
    *,
    q: str = "",
    campo: str = "todos",
    valores: dict | None = None,
    valor_fk=None,
    filtro_padre: tuple[str, object] | None = None,
):
    """
    Devuelve la query del listado.

    q             texto a buscar (contiene, sin distinguir mayúsculas). En las FK
                  busca en el texto del registro vinculado («5090» encuentra el
                  modelo 5090E).
    campo         "todos" busca en todos los `filtros`; si no, solo en ese campo
    valores       {campo: valor} filtros exactos, combinados con Y (ej:
                  categoría = 2 y sector = 3). Los valores ya convertidos.
    valor_fk      (compatibilidad) con `campo` = un campo FK, filtra por igualdad
    filtro_padre  (fk, valor) para subentidades (ej: ("sector_id", 3))

    Campos que no están en `filtros` se ignoran: el parámetro viene de la URL y
    no debe permitir consultar cualquier columna.
    """
    query = model.query.options(*fk.carga_anticipada(model, fields))

    if q:
        campos_busqueda = filtros if campo == "todos" else [campo] if campo in filtros else []
        patron = f"%{q}%"
        condiciones = [c for c in (_condicion_texto(model, fields, cb, patron) for cb in campos_busqueda)
                       if c is not None]
        if condiciones:
            query = query.filter(or_(*condiciones))

    exactos = dict(valores or {})
    if valor_fk not in (None, "") and campo in fk.campos_fk(fields):
        exactos.setdefault(campo, valor_fk)
    for c, valor in exactos.items():
        if c in filtros and c in fields:
            columna = getattr(model, c)
            query = query.filter(columna.is_(None) if valor is None else columna == valor)

    if filtro_padre and filtro_padre[1] not in (None, ""):
        fk_padre, valor = filtro_padre
        query = query.filter(getattr(model, fk_padre) == valor)

    return query
