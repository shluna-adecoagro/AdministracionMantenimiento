# app/crud/core/interpretes.py
"""
Intérpretes de lo escrito en una celda de texto (alta rápida de la grilla, fase 13.3).

Un intérprete convierte el texto de una celda en datos para el servicio, por el
mismo camino que el formulario (coercion + fk.validar_existencia), y dice cómo
se muestra la celda:

    campos                 campos que produce (ubican los errores en la celda)
    control(spec)          "text" | "number" | "lista" | "select"
    opciones(spec)         sugerencias (lista) u opciones {value, label} (select)
    interpretar(texto, spec) -> {campo: valor}; lanza ErroresValidacion

Tres intérpretes genéricos, que se declaran en el override:

    Campo("cantidad")                      un campo, escrito como en la grilla
    FkOTexto("material_id", "descripcion") un registro si se reconoce; si no, texto libre
    FkEntre({"activo_id": {...}, ...})     uno de varios registros relacionados
"""
from __future__ import annotations

from app.crud.core import coercion, fk
from app.crud.core.coercion import ErroresValidacion


def buscar_por_texto(f, campo: str, texto: str) -> int:
    """
    ID del registro de la FK `f` escrito como texto (etiqueta, código o comienzo,
    si corresponde a uno solo). Lanza ErroresValidacion con el mensaje de la grilla.
    """
    texto = texto.strip()
    try:
        return fk.BuscadorFK(f, por_prefijo=True).buscar(texto)
    except fk.Ambiguo as e:
        raise ErroresValidacion({campo: f"«{texto}» coincide con {e.cantidad} opciones. Elegí una de la lista."})
    except ValueError:
        raise ErroresValidacion({campo: f"No encontré «{texto}». Elegí una opción de la lista."})


def _etiquetas(f) -> list[str]:
    """Sugerencias de una FK: las etiquetas, que es lo que reconoce BuscadorFK (como en la grilla)."""
    return [str(o["label"]) for o in fk.opciones(f)]


class Campo:
    """Un campo de la entidad o de alta. Una FK se escribe (etiqueta, código o comienzo)."""

    def __init__(self, campo: str):
        self.campo = campo
        self.campos = (campo,)

    def control(self, spec) -> str:
        f = spec.fields[self.campo]
        if f.tipo == "fk":
            return "lista"
        if f.tipo == "select":
            return "select"
        return "number" if f.tipo == "number" else "text"

    def opciones(self, spec) -> list:
        f = spec.fields[self.campo]
        if f.tipo == "fk":
            return _etiquetas(f)
        if f.tipo == "select":
            return [o for o in f.options if o["value"] not in f.excluir_en_linea]
        return []

    def interpretar(self, texto: str, spec) -> dict:
        f = spec.fields[self.campo]
        entrada = {self.campo: texto}
        if f.tipo == "fk" and texto.strip():
            entrada[self.campo] = str(buscar_por_texto(f, self.campo, texto))
        datos = coercion.datos_de_entrada(spec.model, {self.campo: f}, entrada)
        fk.validar_existencia({self.campo: f}, datos)
        return datos


class FkOTexto:
    """
    Un registro relacionado si el texto lo identifica (exacto, o el comienzo de uno
    solo); si no coincide con ninguno, el texto tal cual en `campo_texto`. Si
    coincide con varios, es un error: no se guarda como texto sin avisar.
    Ej: el material de una línea de pedido o su descripción «tal como se pidió».
    """

    def __init__(self, campo_fk: str, campo_texto: str):
        self.campo_fk = campo_fk
        self.campo_texto = campo_texto
        self.campos = (campo_fk, campo_texto)

    def control(self, spec) -> str:
        return "lista"

    def opciones(self, spec) -> list:
        return _etiquetas(spec.fields[self.campo_fk])

    def interpretar(self, texto: str, spec) -> dict:
        texto = texto.strip()
        if not texto:
            return {}
        try:
            return {self.campo_fk: fk.BuscadorFK(spec.fields[self.campo_fk], por_prefijo=True).buscar(texto)}
        except fk.Ambiguo as e:
            raise ErroresValidacion({self.campo_fk: (
                f"«{texto}» coincide con {e.cantidad} opciones. Elegí una de la lista o, si no es "
                "ninguna, escribí el texto completo.")})
        except fk.NoEncontrado:
            return {self.campo_texto: texto}


class FkEntre:
    """
    Uno de varios registros relacionados, escrito en la misma celda. `opciones`:
    {campo FK: datos que se agregan si el texto es de ese campo}; `vacio`: los
    datos si la celda queda vacía. Ej: el destino de una línea de pedido, un
    activo (destino «activo») o una ubicación (destino «stock»).

    Primero vale el texto exacto de una sugerencia; después, la etiqueta o un
    atributo de búsqueda exactos, y por último el comienzo, siempre que en todos
    los campos juntos haya un solo registro que coincida.
    """

    def __init__(self, opciones: dict[str, dict], vacio: dict | None = None):
        self.por_campo = dict(opciones)
        self.vacio = dict(vacio or {})
        extras = {c for datos in (*self.por_campo.values(), self.vacio) for c in datos}
        self.campos = (*self.por_campo, *sorted(extras - set(self.por_campo)))

    def control(self, spec) -> str:
        return "lista"

    def _sugerencias(self, spec) -> list[dict]:
        """Opciones de todos los campos juntos, con texto único (fk.con_texto)."""
        todas = []
        for campo in self.por_campo:
            for o in fk.opciones(spec.fields[campo]):
                todas.append({**o, "campo": campo})
        return fk.con_texto(todas)

    def opciones(self, spec) -> list:
        return [o["texto"] for o in self._sugerencias(spec)]

    def _resultado(self, campo, id_) -> dict:
        return {campo: id_, **self.por_campo[campo]}

    def interpretar(self, texto: str, spec) -> dict:
        texto = texto.strip()
        if not texto:
            return dict(self.vacio)
        buscado = fk._norm(texto)
        exactas = [o for o in self._sugerencias(spec) if fk._norm(o["texto"]) == buscado]
        if len(exactas) == 1:
            return self._resultado(exactas[0]["campo"], exactas[0]["value"])

        for por_prefijo in (False, True):
            encontrados, cantidad = [], 0
            for campo in self.por_campo:
                try:
                    encontrados.append((campo, fk.BuscadorFK(spec.fields[campo], por_prefijo=por_prefijo)
                                        .buscar(texto)))
                    cantidad += 1
                except fk.Ambiguo as e:
                    cantidad += e.cantidad
                except fk.NoEncontrado:
                    pass
            if cantidad == 1:
                return self._resultado(*encontrados[0])
            if cantidad > 1:
                raise ErroresValidacion({self.campos[0]: (
                    f"«{texto}» coincide con {cantidad} opciones. Elegí una de la lista.")})

        nombres = ", ".join(spec.fields[c].label.lower() for c in self.por_campo)
        raise ErroresValidacion({self.campos[0]: f"No encontré «{texto}» ({nombres}). Elegí una opción de la lista."})
