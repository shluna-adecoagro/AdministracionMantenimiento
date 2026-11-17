# app/crud/core/repository.py
"""
Consultas de lectura: búsqueda, filtros y carga de registros.
"""
from __future__ import annotations

from sqlalchemy import Column, String, cast, or_
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
    return {
        attr.key: getattr(registro, attr.key)
        for attr in sa_inspect(type(registro)).column_attrs
        if calculados or isinstance(attr.columns[0], Column)
    }


def _columna(model, campo):
    col = model.__table__.columns.get(campo)
    if col is None:
        return None
    # CAST permite buscar texto también en columnas numéricas (portable a MariaDB).
    return col if isinstance(col.type, String) else cast(col, String)


def consulta_listado(
    model,
    fields: dict,
    filtros: list[str],
    *,
    q: str = "",
    campo: str = "todos",
    valor_fk=None,
    filtro_padre: tuple[str, object] | None = None,
):
    """
    Devuelve la query del listado.

    q             texto a buscar (contiene, sin distinguir mayúsculas)
    campo         "todos" busca en todos los `filtros`; si no, solo en ese campo
    valor_fk      con `campo` = un campo FK, filtra por igualdad (ej: estado = 1)
    filtro_padre  (fk, valor) para subentidades (ej: ("sector_id", 3))

    Campos que no están en `filtros` se ignoran: el parámetro viene de la URL y
    no debe permitir consultar cualquier columna.
    """
    query = model.query.options(*fk.carga_anticipada(model, fields))

    if q:
        campos_busqueda = filtros if campo == "todos" else [campo] if campo in filtros else []
        condiciones = [
            col.ilike(f"%{q}%")
            for col in (_columna(model, c) for c in campos_busqueda)
            if col is not None
        ]
        if condiciones:
            query = query.filter(or_(*condiciones))

    if valor_fk not in (None, "") and campo in fk.campos_fk(fields) and campo in filtros:
        query = query.filter(getattr(model, campo) == valor_fk)

    if filtro_padre and filtro_padre[1] not in (None, ""):
        fk_padre, valor = filtro_padre
        query = query.filter(getattr(model, fk_padre) == valor)

    return query
