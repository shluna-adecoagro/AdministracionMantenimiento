# app/crud/core/pegado.py
"""
«Pegar líneas» (fase 13.5): varias altas de una vez desde un texto pegado.

Es el adaptador «pegado»: traduce lo que se copia de un mail, de WhatsApp o de
una planilla a los datos de alta de la entidad (el mismo formato que usa la
alta rápida), y crea todo con el servicio, en una sola transacción.

Cada renglón no vacío es un alta:

    «10 rodamientos uc204»   cantidad 10, texto «rodamientos uc204»
    «4 filtros RE504836.»    cantidad 4, texto «filtros RE504836» (sin el punto final)
    «2<TAB>Correa<TAB>x»     con tabuladores: la primera celda con un número es la
                             cantidad; las demás, unidas, el texto

El texto va al intérprete de la spec (PegadoSpec.texto), que nunca rechaza: lo
que no reconoce queda como texto. Un renglón sin cantidad al principio, con
cantidad cero o sin texto es un error de esa fila, y una fila con error impide
cargar las demás (todo o nada): se corrige el texto y se vuelve a ver.

La vista previa hace lo mismo que la carga (servicio.crear con confirmar=False,
así valen completar, al_guardar, creable_si y la auditoría) y después descarta
todo: lo que muestra es exactamente lo que se cargaría.

Sin Flask: lo usan las vistas web (y podría usarlo la API o la línea de comandos).
"""
from __future__ import annotations

import re
from dataclasses import dataclass, field

from app.core.db import db
from app.crud.core import fk
from app.crud.core.coercion import ErroresValidacion, numero_csv
from app.crud.core.interpretes import Campo
from app.crud.core.service import ErrorIntegridad

# Renglones como máximo por pegado (un pedido largo tiene unas decenas).
MAXIMO_RENGLONES = 300

_NUMERO = r"\d+(?:[.,]\d+)*"
_CANTIDAD_Y_TEXTO = re.compile(rf"^({_NUMERO})\s+(.*)$")
_SOLO_NUMERO = re.compile(rf"^{_NUMERO}$")


@dataclass
class FilaPegada:
    n: int                      # número de renglón (sin contar los vacíos)
    original: str               # el renglón tal cual
    datos: dict = field(default_factory=dict)
    vista: list = field(default_factory=list)       # un texto por columna de la vista previa
    avisos: list[str] = field(default_factory=list)
    error: str | None = None


@dataclass
class ResultadoPegado:
    filas: list[FilaPegada]
    columnas: list[str]         # labels de la vista previa
    creados: list = field(default_factory=list)
    confirmado: bool = False

    @property
    def con_error(self) -> list[FilaPegada]:
        return [f for f in self.filas if f.error]

    @property
    def valido(self) -> bool:
        return bool(self.filas) and not self.con_error


def renglones(texto: str) -> list[str]:
    """Los renglones no vacíos del texto pegado."""
    return [r for r in (texto or "").splitlines() if r.strip()]


def _limpiar(texto: str) -> str:
    """Sin espacios de más ni el punto final («reten  7186.» → «reten 7186»)."""
    return re.sub(r"\s+", " ", texto).strip().rstrip(".").strip()


def separar(renglon: str) -> tuple[str | None, str]:
    """(cantidad tal como está escrita o None, texto) de un renglón."""
    if "\t" in renglon:
        celdas = [c.strip() for c in renglon.split("\t") if c.strip()]
        i = next((i for i, c in enumerate(celdas) if _SOLO_NUMERO.match(c)), None)
        if i is None:
            return None, _limpiar(" ".join(celdas))
        return celdas[i], _limpiar(" ".join(celdas[:i] + celdas[i + 1:]))
    m = _CANTIDAD_Y_TEXTO.match(renglon.strip())
    if m is None:
        texto = renglon.strip()
        return (texto, "") if _SOLO_NUMERO.match(texto) else (None, _limpiar(texto))
    return m.group(1), _limpiar(m.group(2))


def _mensaje(spec, errores: dict) -> str:
    """Los errores del servicio en una línea, con la etiqueta de cada campo."""
    partes = []
    for campo, texto in errores.items():
        label = spec.fields[campo].label if campo in spec.fields else None
        partes.append(texto if not label or texto.startswith(label) else f"{label}: {texto}")
    return " ".join(partes)


def _texto_de(spec, campo, valor) -> str:
    if valor is None:
        return ""
    f = spec.fields[campo]
    if f.tipo == "fk":
        obj = db.session.get(f.get("fk_model"), valor)
        return fk.etiqueta(obj, f) if obj is not None else str(valor)
    return str(valor)


def _formato_cantidad(valor) -> str:
    """10.0 → «10»; 2.5 → «2,5»."""
    return f"{float(valor):g}".replace(".", ",")


def leer(spec, texto: str) -> ResultadoPegado:
    """Interpreta el texto pegado, sin tocar la base: una FilaPegada por renglón."""
    p = spec.pegado_en_linea
    campo_cantidad = Campo(p.cantidad)
    columnas = [spec.fields[p.cantidad].label] + [spec.fields[c].label for c in p.texto.campos]
    lineas = renglones(texto)
    if len(lineas) > MAXIMO_RENGLONES:
        fila = FilaPegada(n=0, original="", error=(
            f"Son {len(lineas)} renglones; se pueden pegar hasta {MAXIMO_RENGLONES} por vez."))
        return ResultadoPegado(filas=[fila], columnas=columnas)

    indice = p.texto.indice(spec) if hasattr(p.texto, "indice") else None
    filas = []
    for n, renglon in enumerate(lineas, start=1):
        fila = FilaPegada(n=n, original=renglon.strip())
        filas.append(fila)
        cantidad, resto = separar(renglon)
        if cantidad is None:
            fila.error = "No empieza con la cantidad (ej: «4 filtros RE504836»)."
            continue
        try:
            datos = campo_cantidad.interpretar(numero_csv(cantidad), spec)
        except ErroresValidacion as e:
            fila.error = _mensaje(spec, e.errores)
            continue
        if datos.get(p.cantidad) is None or datos[p.cantidad] <= 0:
            fila.error = "La cantidad tiene que ser mayor que cero."
            continue
        if not resto:
            fila.error = "Falta el código o la descripción (el renglón tiene solo la cantidad)."
            continue
        extra, avisos = (p.texto.leer(resto, spec, indice) if indice is not None
                         else p.texto.leer(resto, spec))
        fila.datos = {**p.datos, **datos, **extra}
        fila.avisos.extend(avisos)
        fila.vista = [_formato_cantidad(datos[p.cantidad])] + [
            _texto_de(spec, c, fila.datos.get(c)) for c in p.texto.campos]
    return ResultadoPegado(filas=filas, columnas=columnas)


def procesar(spec, servicio, texto: str, padre_fk: str, padre_id, *, motivo: str,
             confirmar: bool) -> ResultadoPegado:
    """
    Lee el texto y crea un registro por fila con `servicio` (con confirmar=False).
    confirmar=False (vista previa) o alguna fila con error: se descarta todo
    (rollback). confirmar=True y sin errores: se confirma todo junto.
    """
    p = spec.pegado_en_linea
    resultado = leer(spec, texto)
    if resultado.con_error:
        return resultado

    for fila in resultado.filas:
        datos = {padre_fk: padre_id, **fila.datos}
        if p.aviso is not None:
            aviso = p.aviso(datos, padre_id)
            if aviso:
                fila.avisos.append(aviso)
        try:
            registro = servicio.crear(datos, motivo)
        except ErroresValidacion as e:
            fila.error = _mensaje(spec, e.errores)
        except ErrorIntegridad as e:
            fila.error = _mensaje(spec, {e.campo or "_general": e.mensaje})
        else:
            resultado.creados.append(registro)

    if confirmar and resultado.valido:
        db.session.commit()
        resultado.confirmado = True
    else:
        db.session.rollback()
        resultado.creados = []
    return resultado
