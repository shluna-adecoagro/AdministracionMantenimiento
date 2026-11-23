# app/crud/intercambio/csv_entidades.py
"""
Importación y exportación de entidades en CSV.

Pensado para traer los datos de SharePoint (exportados a CSV) y para llevar los
de la base a otra fuente. Usa el mismo servicio que la web y la API: misma
validación, mismas reglas de borrado y auditoría de cada cambio.

COLUMNAS. Cada columna se reconoce por el nombre del campo o por su etiqueta, sin
importar mayúsculas ni tildes ("nombre_sector", "Nombre del Sector"). Las
columnas que no corresponden a ningún campo se ignoran (SharePoint agrega
varias: ID, Modificado, Creado por...).

CLAVES FORÁNEAS. Con el nombre exacto del campo (`estado_sector_id`) se espera el
ID; con la etiqueta o el nombre sin "_id" (`Estado`, `estado_sector`) se espera
el TEXTO ("Activo") y se busca el registro por su nombre. Los IDs de otra fuente
no coinciden con los de la base, así que lo normal es usar el texto.

ACTUALIZAR EN VEZ DE DUPLICAR. Cada fila se busca en la base por la clave
natural de la entidad (ej: nombre del sector). Si existe y cambió, se
actualiza; si no cambió, no se toca (no ensucia el historial); si no existe, se
crea.

TODO O NADA. Primero se validan todas las filas y se informan todos los errores
juntos. Si hay alguno, no se guarda nada. Con `simular=True` se hace todo el
proceso y al final se descarta.
"""
from __future__ import annotations

import csv
import io
import os
from dataclasses import dataclass, field
from datetime import date, datetime
from decimal import Decimal

from sqlalchemy import inspect as sa_inspect

from app.core.db import db
from app.crud.core import coercion
from app.crud.core.coercion import ErroresValidacion
from app.crud.core.service import ErrorIntegridad
from app.crud.introspect import normalizar_texto
from app.crud.meta.spec import EntitySpec

SEPARADORES = ",;\t"


@dataclass
class ResultadoImportacion:
    entidad: str
    archivo: str
    simulado: bool = False
    creados: int = 0
    actualizados: int = 0
    sin_cambios: int = 0
    errores: list[tuple[int, str, str]] = field(default_factory=list)  # (fila, campo, mensaje)
    columnas_ignoradas: list[str] = field(default_factory=list)
    solo_en_la_base: int = 0  # registros de la base que no están en el archivo

    @property
    def ok(self) -> bool:
        return not self.errores

    def resumen(self) -> str:
        lineas = [f"Importación de {self.entidad} desde {self.archivo}"
                  + (" (SIMULACIÓN: no se guardó nada)" if self.simulado else "")]
        if self.columnas_ignoradas:
            lineas.append(f"  Columnas ignoradas: {', '.join(self.columnas_ignoradas)}")
        if self.errores:
            lineas.append(f"  ✘ {len(self.errores)} error/es. No se guardó nada:")
            for fila, campo, mensaje in self.errores:
                donde = f"Fila {fila}" if fila else "Archivo"
                lineas.append(f"    {donde} [{campo}]: {mensaje}")
            return "\n".join(lineas)
        lineas.append(f"  ✔ Creados: {self.creados}  Actualizados: {self.actualizados}  "
                      f"Sin cambios: {self.sin_cambios}")
        if self.solo_en_la_base:
            lineas.append(f"  ℹ {self.solo_en_la_base} registro/s de la base no están en el archivo "
                          "(no se modificaron).")
        return "\n".join(lineas)


# ---------------------------------------------------------------------------
# Lectura del archivo
# ---------------------------------------------------------------------------

def _leer_texto(contenido: bytes) -> str:
    # utf-8-sig quita el BOM que agrega Excel; cp1252 es el "ANSI" de Excel en Windows.
    for codificacion in ("utf-8-sig", "cp1252"):
        try:
            return contenido.decode(codificacion)
        except UnicodeDecodeError:
            pass
    return contenido.decode("latin-1")


def _filas_csv(texto: str) -> list[list[str]]:
    primera = texto.split("\n", 1)[0]
    try:
        separador = csv.Sniffer().sniff(primera, delimiters=SEPARADORES).delimiter
    except csv.Error:
        separador = ","
    return list(csv.reader(io.StringIO(texto), delimiter=separador))


def _norm(texto: str) -> str:
    return normalizar_texto(str(texto).replace("_", " "))


# ---------------------------------------------------------------------------
# Columnas → campos
# ---------------------------------------------------------------------------

def _alias(spec: EntitySpec) -> dict[str, tuple[str, str]]:
    """
    {alias normalizado: (campo, modo)}; modo "valor", "id" (FK por ID) o "texto"
    (FK por nombre). Un alias que apunta a dos campos se descarta por ambiguo.
    """
    candidatos: dict[str, set] = {}
    for campo, f in spec.fields.items():
        if f.tipo == "file" or f.solo_lectura or f.solo_alta:
            continue
        if f.tipo == "fk":
            pares = [(campo, "id"), (f.label, "texto"), (campo.removesuffix("_id"), "texto")]
            pares += [(a, "texto") for a in f.alias]
        else:
            pares = [(campo, "valor"), (f.label, "valor")] + [(a, "valor") for a in f.alias]
        for alias, modo in pares:
            candidatos.setdefault(_norm(alias), set()).add((campo, modo))
    return {a: next(iter(c)) for a, c in candidatos.items() if len(c) == 1}


class _BuscadorFK:
    """
    Busca el ID de un registro relacionado por su texto (ej: "Activo" → 1). Además
    de la etiqueta, reconoce los atributos de `__buscar_por__` del modelo (ej: el
    código o la descripción de un material). Si un texto coincide con varios
    registros, es ambiguo y hay que usar el ID.
    """

    def __init__(self, f):
        self.f = f
        atributo = f.fk_label or getattr(f.fk_model, "__label_field__", None)
        self.indice: dict[str, set] = {}
        if atributo:
            pk = f.fk_model.__mapper__.primary_key[0].name
            otros = getattr(f.fk_model, "__buscar_por__", ()) or ()
            for obj in f.fk_model.query.all():
                for a in (atributo, *otros):
                    texto = getattr(obj, a, None)
                    if texto not in (None, ""):
                        self.indice.setdefault(_norm(texto), set()).add(getattr(obj, pk))
        self.atributo = atributo

    def buscar(self, texto: str):
        if not self.atributo:
            raise ValueError("no se puede buscar por nombre; usá la columna con el ID")
        ids = self.indice.get(_norm(texto), [])
        if not ids:
            raise ValueError(f"no existe «{texto}»")
        if len(ids) > 1:
            raise ValueError(f"hay {len(ids)} registros llamados «{texto}»; usá el ID")
        return next(iter(ids))


# ---------------------------------------------------------------------------
# Importación
# ---------------------------------------------------------------------------

def importar(spec: EntitySpec, contenido: bytes, nombre_archivo: str = "archivo.csv", *,
             simular: bool = False, usuario: str = "importación", motivo: str | None = None,
             etiqueta_tabla=None) -> ResultadoImportacion:
    resultado = ResultadoImportacion(spec.name, nombre_archivo, simulado=simular)

    if not spec.clave_natural:
        resultado.errores.append((0, "_entidad", f"«{spec.name}» no tiene clave_natural definida en su override"))
        return resultado

    filas = [f for f in _filas_csv(_leer_texto(contenido)) if any(c.strip() for c in f)]
    if not filas:
        resultado.errores.append((0, "_archivo", "el archivo está vacío"))
        return resultado

    # --- encabezados -----------------------------------------------------
    alias = _alias(spec)
    # Encabezados que son la etiqueta de un calculado (ej: «Estado», el visible):
    # se ignoran aunque coincidan con el nombre de otro campo.
    calculados = {_norm(f.label) for f in spec.fields.values() if f.solo_lectura}
    etiquetas = {_norm(f.label) for f in spec.fields.values() if not f.solo_lectura}
    columnas: list[tuple[int, str, str]] = []  # (índice, campo, modo)
    vistos: set[str] = set()
    for i, encabezado in enumerate(filas[0]):
        clave = _norm(encabezado)
        destino = None if clave in calculados and clave not in etiquetas else alias.get(clave)
        if destino is None:
            if encabezado.strip():
                resultado.columnas_ignoradas.append(encabezado.strip())
            continue
        if destino[0] in vistos:
            resultado.errores.append((1, destino[0], f"el campo aparece en más de una columna («{encabezado}»)"))
            continue
        vistos.add(destino[0])
        columnas.append((i, *destino))

    for campo, f in spec.fields.items():
        if campo not in vistos and (f.required or campo in spec.clave_natural) and f.tipo != "file" \
                and not f.solo_alta:
            resultado.errores.append((1, campo, f"falta la columna «{f.label}» (o «{campo}»)"))
    if resultado.errores:
        return resultado

    # --- validación de todas las filas -----------------------------------
    buscadores = {c: _BuscadorFK(spec.fields[c]) for _, c, modo in columnas if modo == "texto"}
    campos_archivo = {c: spec.fields[c] for _, c, _ in columnas}
    validas: list[tuple[int, dict]] = []
    claves_vistas: dict[tuple, int] = {}

    for numero, fila in enumerate(filas[1:], start=2):
        crudo, errores_fila = {}, {}
        for i, campo, modo in columnas:
            valor = fila[i].strip() if i < len(fila) else ""
            if modo == "texto" and valor:
                try:
                    valor = buscadores[campo].buscar(valor)
                except ValueError as e:
                    errores_fila[campo] = f"{spec.fields[campo].label}: {e}."
                    continue
            crudo[campo] = valor
        try:
            datos = coercion.datos_de_entrada(spec.model, campos_archivo, crudo, parcial=True,
                                              importacion=True)
            faltan = [c for c, f in campos_archivo.items() if f.required and datos.get(c) is None]
            if faltan:
                raise ErroresValidacion({c: f"{spec.fields[c].label} es obligatorio." for c in faltan})
        except ErroresValidacion as e:
            for c, m in e.errores.items():
                errores_fila.setdefault(c, m)  # el error de búsqueda es más preciso
            datos = None

        if errores_fila:
            resultado.errores.extend((numero, c, m) for c, m in errores_fila.items())
            continue

        clave = tuple(datos.get(c) for c in spec.clave_natural)
        if all(v is None for v in clave):
            # Sin clave no se puede saber si el registro ya existe: se crearía uno
            # nuevo en cada importación (ej: una fila sin clave de origen).
            etiquetas = " + ".join(spec.fields[c].label for c in spec.clave_natural)
            resultado.errores.append((numero, "_clave", f"falta {etiquetas}, que identifica el registro"))
            continue
        if clave in claves_vistas:
            resultado.errores.append((numero, "_clave", f"repite el registro de la fila {claves_vistas[clave]}"))
            continue
        claves_vistas[clave] = numero
        validas.append((numero, datos))

    if resultado.errores:
        return resultado

    # --- escritura (una sola transacción) ---------------------------------
    from app.crud.entidades import servicio as servicio_de

    servicio = servicio_de(spec, confirmar=False)
    motivo = motivo or f"Importación de {os.path.basename(nombre_archivo)}"
    pk = spec.pk
    tocados: set = set()

    try:
        for numero, datos in validas:
            filtro = [
                getattr(spec.model, c).is_(None) if datos.get(c) is None else getattr(spec.model, c) == datos[c]
                for c in spec.clave_natural
            ]
            existentes = spec.model.query.filter(*filtro).all()
            if len(existentes) > 1:
                resultado.errores.append((numero, "_clave", f"hay {len(existentes)} registros con esa clave en la base"))
                continue
            if existentes:
                registro = existentes[0]
                cambios = {c: v for c, v in datos.items() if getattr(registro, c) != v}
                if cambios:
                    servicio.actualizar(registro, cambios, motivo, usuario)
                    resultado.actualizados += 1
                else:
                    resultado.sin_cambios += 1
            else:
                registro = servicio.crear(datos, motivo, usuario)
                resultado.creados += 1
            tocados.add(getattr(registro, pk))
    except ErrorIntegridad as e:
        resultado.errores.append((numero, e.campo or "_base", e.mensaje))
    except ErroresValidacion as e:
        resultado.errores.extend((numero, c, m) for c, m in e.errores.items())

    if resultado.errores or simular:
        db.session.rollback()
        if resultado.errores:
            resultado.creados = resultado.actualizados = resultado.sin_cambios = 0
        return resultado

    db.session.commit()
    total = db.session.query(getattr(spec.model, pk)).count()
    resultado.solo_en_la_base = total - len(tocados)
    return resultado


# ---------------------------------------------------------------------------
# Exportación
# ---------------------------------------------------------------------------

def _texto(valor) -> str:
    if valor is None:
        return ""
    if isinstance(valor, bool):
        return "Sí" if valor else "No"
    if isinstance(valor, datetime):
        return valor.isoformat(sep=" ", timespec="minutes")
    if isinstance(valor, date):
        return valor.isoformat()
    if isinstance(valor, Decimal):
        return format(valor, "f")
    return str(valor)


def exportar(spec: EntitySpec, separador: str = ";") -> bytes:
    """
    CSV con una columna por campo, encabezados con las etiquetas y las FK como
    texto. Se puede volver a importar tal cual. Codificado en UTF-8 con BOM para
    que Excel muestre bien las tildes; `;` como separador (Excel en castellano).
    """
    from app.crud.core import fk

    campos = [c for c, f in spec.fields.items() if f.tipo != "file" and not f.solo_alta]
    salida = io.StringIO()
    escritor = csv.writer(salida, delimiter=separador, lineterminator="\n")
    escritor.writerow([spec.fields[c].label for c in campos])

    orden = getattr(spec.model, spec.pk)
    for registro in spec.model.query.order_by(orden).all():
        etiquetas = fk.etiquetas(registro, spec.fields)
        fila = []
        for c in campos:
            if spec.fields[c].tipo == "fk":
                e = etiquetas.get(c)
                fila.append(_texto(e["label"] if isinstance(e, dict) else e))
            else:
                fila.append(_texto(getattr(registro, c)))
        escritor.writerow(fila)
    return ("﻿" + salida.getvalue()).encode("utf-8")
