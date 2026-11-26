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
    """Registro al que apunta la FK (por la relación del modelo o, si no hay, por su ID)."""
    rel = relacion(type(registro), campo, cfg)
    if rel:
        return getattr(registro, rel)
    valor = getattr(registro, campo, None)
    if valor is None or cfg.get("fk_model") is None:
        return None
    from app.core.db import db

    return db.session.get(cfg["fk_model"], valor)


# ---------------------------------------------------------------------------
# Opciones para formularios y filtros
# ---------------------------------------------------------------------------

# Hasta esta cantidad de opciones se elige con un <select>; con más, con un campo
# con lista (<datalist>) que se acorta al tipear: en formularios y filtros
# (usa_lista) y en la grilla (usa_busqueda). FieldSpec.selector lo fija.
UMBRAL_LISTA = 15


def usa_lista(cfg: dict, opciones_campo: list[dict]) -> bool:
    """True si el campo se elige con un campo con lista en lugar de un <select>."""
    if cfg.get("selector"):
        return cfg["selector"] == "lista"
    return len(opciones_campo) > UMBRAL_LISTA


def con_texto(opciones_campo: list[dict]) -> list[dict]:
    """
    Agrega a cada opción `texto`: lo que se ve y se tipea en un campo con lista.
    Es la etiqueta más el grupo («5090E (John Deere, Tractor)») y no se repite:
    el texto es lo que identifica la opción elegida. Si dos opciones quedan
    iguales, se distinguen por el ID («Equipo (ID 7)»).
    """
    for o in opciones_campo:
        o["texto"] = f"{o['label']} ({o['grupo']})" if o.get("grupo") else str(o["label"])
    vistos: dict[str, int] = {}
    for o in opciones_campo:
        vistos[o["texto"].casefold()] = vistos.get(o["texto"].casefold(), 0) + 1
    for o in opciones_campo:
        if vistos[o["texto"].casefold()] > 1:
            o["texto"] = f"{o['texto']} (ID {o['value']})"
    return opciones_campo


def opciones(cfg: dict) -> list[dict]:
    """
    Opciones de un <select> de FK.

    En un select dependiente (cfg.depende_de, ej: modelo según la marca y la
    categoría), cada opción lleva `deps` = {campo del que depende: valor que le
    corresponde} (ej: {"marca_id": 3, "categoria_activo_id": 5}) y `grupo`, el
    texto de esos valores («John Deere, Tractor»), para distinguir nombres repetidos.
    Con cfg.fk_filtro, solo las opciones que cumplen la condición.
    """
    fk_model = cfg["fk_model"]
    pk = fk_model.__mapper__.primary_key[0].name
    pares = list(zip(cfg.get("depende_de") or (), cfg.get("depende_fk") or ()))
    relaciones = {columna: relacion(fk_model, columna, {}) for _, columna in pares}

    consulta = fk_model.query
    if cfg.get("fk_filtro") is not None:
        consulta = consulta.filter(cfg["fk_filtro"]())

    resultado = []
    for obj in consulta.all():
        opcion = {"value": getattr(obj, pk), "label": etiqueta(obj, cfg), "deps": None, "grupo": None}
        if pares:
            opcion["deps"] = {padre: getattr(obj, columna) for padre, columna in pares}
            nombres = []
            for _, columna in pares:
                padre = getattr(obj, relaciones[columna]) if relaciones[columna] else None
                if padre is not None:
                    nombres.append(str(etiqueta(padre, {})))
            opcion["grupo"] = ", ".join(nombres) or None
        resultado.append(opcion)
    return con_texto(sorted(resultado, key=lambda o: (str(o["grupo"] or ""), str(o["label"] or ""))))


def opciones_de(fields: dict) -> dict[str, list[dict]]:
    return {c: opciones(cfg) for c, cfg in campos_fk(fields).items()}


def sugerencias_de(fields: dict) -> dict[str, list[str]]:
    """
    Sugerencias de los campos "datalist" (texto libre con lista de ayuda): las
    opciones fijas más, si tiene fk_model, los valores de ese modelo (ej: los
    empleados, o los tipos de medidor ya cargados en otras unidades).
    """
    resultado = {}
    for c, cfg in fields.items():
        if cfg.get("tipo") != "datalist":
            continue
        textos = {str(o["label"]) for o in cfg.get("options") or ()}
        if cfg.get("fk_model") is not None:
            textos |= {str(e) for e in (etiqueta(o, cfg) for o in cfg["fk_model"].query.all())
                       if e is not None}
        resultado[c] = sorted(t for t in textos if t)
    return resultado


# ---------------------------------------------------------------------------
# Búsqueda por texto (importación CSV y edición en línea)
# ---------------------------------------------------------------------------

class NoEncontrado(ValueError):
    """Ningún registro coincide con el texto."""


class Ambiguo(ValueError):
    """Varios registros coinciden con el texto. `cantidad`: cuántos."""

    def __init__(self, mensaje: str, cantidad: int):
        super().__init__(mensaje)
        self.cantidad = cantidad


def _norm(texto) -> str:
    from app.crud.introspect import normalizar_texto

    return normalizar_texto(str(texto).replace("_", " "))


class BuscadorFK:
    """
    Busca el ID de un registro relacionado por su texto (ej: "Activo" → 1). Además
    de la etiqueta, reconoce los atributos de `__buscar_por__` del modelo (ej: el
    código o la descripción de un material). Sin importar mayúsculas ni tildes.

    por_prefijo  True: si ningún texto coincide exacto, vale el comienzo siempre que
                 corresponda a un solo registro («RE5048» → el filtro RE504836).

    Lanza NoEncontrado o Ambiguo (los dos son ValueError).
    """

    def __init__(self, f, *, por_prefijo: bool = False):
        self.f = f
        self.por_prefijo = por_prefijo
        fk_model = f.get("fk_model")
        atributo = f.get("fk_label") or getattr(fk_model, "__label_field__", None)
        self.indice: dict[str, set] = {}
        if atributo:
            pk = fk_model.__mapper__.primary_key[0].name
            otros = getattr(fk_model, "__buscar_por__", ()) or ()
            for obj in fk_model.query.all():
                for a in (atributo, *otros):
                    texto = getattr(obj, a, None)
                    if texto not in (None, ""):
                        self.indice.setdefault(_norm(texto), set()).add(getattr(obj, pk))
        self.atributo = atributo

    def buscar(self, texto: str):
        if not self.atributo:
            raise ValueError("no se puede buscar por nombre; usá la columna con el ID")
        buscado = _norm(texto)
        ids = self.indice.get(buscado, set())
        if not ids and self.por_prefijo and buscado:
            ids = {i for clave, grupo in self.indice.items() if clave.startswith(buscado) for i in grupo}
        if not ids:
            raise NoEncontrado(f"no existe «{texto}»")
        if len(ids) > 1:
            raise Ambiguo(f"hay {len(ids)} registros llamados «{texto}»; usá el ID", len(ids))
        return next(iter(ids))


def usa_busqueda(cfg: dict) -> bool:
    """
    True si la FK se edita en la grilla escribiendo (<input list>): con más de
    UMBRAL_LISTA registros, o si FieldSpec.selector lo fija (mismo criterio que
    usa_lista en formularios y filtros). Se cuenta al abrir la celda.
    """
    if cfg.get("selector"):
        return cfg["selector"] == "lista"
    consulta = cfg["fk_model"].query
    if cfg.get("fk_filtro") is not None:
        consulta = consulta.filter(cfg["fk_filtro"]())
    return consulta.limit(UMBRAL_LISTA + 1).count() > UMBRAL_LISTA


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
    from app.crud.core.repository import valores

    d = valores(registro, calculados=False)
    for campo, cfg in campos_fk(fields).items():
        if cfg.get("solo_lectura"):
            continue  # calculado (ej: tipo de activo): no es un dato propio del registro
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
