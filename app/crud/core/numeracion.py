# app/crud/core/numeracion.py
"""
Numeración automática de un campo (FieldSpec.numeracion).

El formato lleva {n} (el número, con formato opcional: {n:04d}) y, si la serie
se reinicia cada año, {año}:

    "{n}"                serie continua: 1104, 1105... (sigue la del Excel de pedidos)
    "TRA-{año}-{n:04d}"  TRA-2026-0001, TRA-2026-0002... y TRA-2027-0001

El siguiente número es el mayor de la serie más uno. Los valores que no siguen
el formato (por ejemplo, cargados a mano) no cuentan. Si un valor se carga a
mano, se respeta.
"""
from __future__ import annotations

import re
from datetime import date

from sqlalchemy import select

from app.core.db import db

_MARCA = re.compile(r"\{(año|n)(?::([^}]*))?\}")


class FormatoInvalido(ValueError):
    pass


def validar_formato(formato: str) -> None:
    """Lanza FormatoInvalido si el formato no tiene un único {n} o usa otros marcadores."""
    marcas = [m.group(1) for m in _MARCA.finditer(formato)]
    if marcas.count("n") != 1:
        raise FormatoInvalido("tiene que tener un {n}, una sola vez")
    sin_marcas = _MARCA.sub("", formato)
    if "{" in sin_marcas or "}" in sin_marcas:
        raise FormatoInvalido("solo admite los marcadores {n} y {año}")


def _patron(formato: str, año: int) -> re.Pattern:
    partes, ultimo = [], 0
    for m in _MARCA.finditer(formato):
        partes.append(re.escape(formato[ultimo:m.start()]))
        partes.append(str(año) if m.group(1) == "año" else r"(\d+)")
        ultimo = m.end()
    partes.append(re.escape(formato[ultimo:]))
    return re.compile("^" + "".join(partes) + "$")


def _texto(formato: str, año: int, n: int) -> str:
    def reemplazo(m):
        if m.group(1) == "año":
            return str(año)
        return format(n, m.group(2) or "")
    return _MARCA.sub(reemplazo, formato)


def siguiente(model, campo: str, formato: str, hoy: date | None = None, filtro: dict | None = None):
    """
    Siguiente valor de la serie de `model.campo` según `formato`. Con `filtro`
    ({campo: valor}), la serie se cuenta solo entre esos registros (ej: el número
    de línea dentro de un pedido). Si la columna es numérica, devuelve un entero.
    """
    año = (hoy or date.today()).year
    patron = _patron(formato, año)
    columna = getattr(model, campo)
    consulta = select(columna).where(columna.isnot(None))
    for otro, valor in (filtro or {}).items():
        consulta = consulta.where(getattr(model, otro) == valor)
    maximo = 0
    for (valor,) in db.session.execute(consulta):
        m = patron.match(str(valor))
        if m:
            maximo = max(maximo, int(m.group(1)))
    texto = _texto(formato, año, maximo + 1)
    return int(texto) if _es_entera(columna) else texto


def _es_entera(columna) -> bool:
    try:
        return columna.type.python_type is int
    except NotImplementedError:
        return False
