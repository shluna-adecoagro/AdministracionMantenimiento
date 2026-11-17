# app/crud/core/dependencias.py
"""
Qué pasa con los registros relacionados al borrar uno.

La regla de cada relación se declara en el MODELO, en la relación del hijo:

  * Borrado en cascada (ej: sector → ubicaciones):
        backref=db.backref("ubicaciones", cascade="all, delete")
    Los hijos se borran junto con el padre (y se auditan uno por uno).

  * Bloqueo (lo que queda por defecto si no hay relación ORM, o con
        backref=db.backref("stock", passive_deletes="all")):
    si existe algún registro que apunta al que se quiere borrar, la baja se
    rechaza con un mensaje que dice cuántos y de qué tabla.

Este módulo calcula ambas cosas ANTES de borrar, para poder avisar en la
pantalla de confirmación y para dar un mensaje claro en vez de un error de la base.
"""
from __future__ import annotations

from sqlalchemy import func, inspect as sa_inspect, select

from app.core.db import db


def en_cascada(registro) -> list:
    """
    Registros que se borrarían en cascada junto con `registro` (recursivo),
    en el orden en que conviene auditarlos (primero los más profundos).
    """
    resultado = []
    for rel in sa_inspect(registro).mapper.relationships:
        if rel.direction.name != "ONETOMANY" or not rel.cascade.delete:
            continue
        hijos = getattr(registro, rel.key)
        for hijo in (hijos if isinstance(hijos, (list, tuple, set)) else [hijos]):
            if hijo is not None:
                resultado.extend(en_cascada(hijo))
                resultado.append(hijo)
    return resultado


def _pk(obj):
    return sa_inspect(obj).identity[0]


def bloqueantes(registro) -> list[tuple[str, int]]:
    """
    [(tabla, cantidad)] de registros que apuntan a `registro` (o a los que se
    borrarían en cascada) y que impiden borrarlo.
    """
    a_borrar: dict = {}  # tabla → {pks}
    for obj in [registro, *en_cascada(registro)]:
        a_borrar.setdefault(obj.__table__, set()).add(_pk(obj))

    conteo: dict[str, int] = {}
    for tabla in db.metadata.sorted_tables:
        pk_tabla = list(tabla.primary_key.columns)
        for fk in tabla.foreign_keys:
            destino = fk.column.table
            if destino not in a_borrar:
                continue
            consulta = select(func.count()).select_from(tabla).where(
                fk.parent.in_(a_borrar[destino])
            )
            # Las filas que también se van a borrar no bloquean.
            if tabla in a_borrar and len(pk_tabla) == 1:
                consulta = consulta.where(pk_tabla[0].not_in(a_borrar[tabla]))
            cantidad = db.session.execute(consulta).scalar_one()
            if cantidad:
                conteo[tabla.name] = conteo.get(tabla.name, 0) + cantidad
    return sorted(conteo.items())


def resumen_cascada(registro) -> list[tuple[str, int]]:
    """[(tabla, cantidad)] de lo que se borraría en cascada."""
    conteo: dict[str, int] = {}
    for obj in en_cascada(registro):
        conteo[obj.__tablename__] = conteo.get(obj.__tablename__, 0) + 1
    return sorted(conteo.items())
