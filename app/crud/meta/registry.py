# app/crud/meta/registry.py
"""
Registry de entidades: lo inferido del modelo + overrides = EntitySpec.

    inferir_entidad(model)  ──┐
                              ├──►  EntitySpec (validada)
    OVERRIDES[nombre]  ───────┘

Precedencia de cada dato (de mayor a menor):
    1. override de la entidad (app/crud/meta/overrides/*.py)
    2. info={...} de la columna en el modelo (ej: info={"label": "Centro de costo"})
    3. lo que se infiere del tipo de columna, nullable, FKs y relaciones

La validación corre al construir el registry, es decir al arrancar la app: un
typo en un override o un campo que ya no existe en el modelo frena el arranque
con un mensaje que dice qué corregir, en vez de fallar más tarde en una pantalla.
"""
from __future__ import annotations

import difflib
import importlib
import pkgutil
from dataclasses import replace

from sqlalchemy import inspect as sa_inspect
from sqlalchemy.exc import NoInspectionAvailable

from app.crud.introspect import fk_apunta_a, inferir_entidad
from app.crud.meta.spec import (
    AUDITORIA_IGNORAR_DEFAULT,
    GENEROS,
    TIPOS_CAMPO,
    EntitySpec,
    FieldSpec,
    ParentSpec,
)

PAQUETE_OVERRIDES = "app.crud.meta.overrides"

# Claves válidas en el override de una entidad.
CLAVES_ENTIDAD = frozenset({
    "model",              # obligatoria: clase SQLAlchemy
    "label_singular",     # "sector"
    "label_plural",       # "sectores"
    "genero",             # "m" | "f" (para "Nuevo sector" / "Nueva ubicación")
    "fields",             # {campo: {clave: valor}} sobrescribe lo inferido
    "excluir",            # [campo, ...] campos inferidos que no se exponen
    "listado",            # [campo, ...] columnas del listado
    "filtros",            # [campo, ...] campos de búsqueda
    "padre",              # {"entidad": "sectores", "fk": "sector_id"} → subentidad
    "sidebar",            # True para mostrarla en el menú lateral
    "orden",              # posición en el menú lateral
    "auditoria",          # True/False (por defecto: si el modelo usa AuditMixin)
    "auditoria_ignorar",  # columnas que no se registran en el historial
    "tabs_extra",         # pestañas adicionales en el detalle
})

# Tipos de widget que por defecto aparecen en listado y filtros.
_TIPOS_LISTADO = {"text", "number", "date", "fk", "select", "datalist"}
_TIPOS_FILTRO = {"text", "textarea", "fk", "select", "datalist"}


class MetamodeloError(Exception):
    """Uno o más overrides son inconsistentes con los modelos."""

    def __init__(self, errores: list[str]):
        self.errores = errores
        detalle = "\n".join(f"  - {e}" for e in errores)
        super().__init__(f"Metamodelo inválido ({len(errores)} error/es):\n{detalle}")


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _sugerir(valor: str, opciones) -> str:
    parecidos = difflib.get_close_matches(valor, list(opciones), n=1)
    return f" ¿Quisiste decir '{parecidos[0]}'?" if parecidos else ""


def _columna(model, nombre):
    try:
        return sa_inspect(model).columns[nombre]
    except KeyError:
        return None


def _field_spec(nombre: str, inferido: dict, override: dict, model) -> FieldSpec:
    datos = dict(inferido)
    datos.update(override)
    if "options" in datos:
        datos["options"] = tuple(dict(o) for o in datos["options"])

    col = _columna(model, nombre)
    if col is not None:
        datos.setdefault("max_length", getattr(col.type, "length", None))
        datos.setdefault("unique", bool(col.unique))

    return FieldSpec(name=nombre, **datos)


# ---------------------------------------------------------------------------
# Construcción de una entidad
# ---------------------------------------------------------------------------

def construir_spec(nombre: str, ov: dict) -> tuple[EntitySpec | None, list[str]]:
    """Devuelve (spec, errores). Si hay errores, spec puede ser None."""
    errores: list[str] = []
    pref = f"[{nombre}]"

    desconocidas = sorted(set(ov) - CLAVES_ENTIDAD)
    for k in desconocidas:
        errores.append(f"{pref} clave desconocida '{k}'.{_sugerir(k, CLAVES_ENTIDAD)}")

    model = ov.get("model")
    if model is None:
        return None, errores + [f"{pref} falta 'model'"]
    try:
        sa_inspect(model)
    except NoInspectionAvailable:
        return None, errores + [f"{pref} 'model' no es un modelo SQLAlchemy: {model!r}"]

    resultado = inferir_entidad(model)
    meta = resultado["meta"]
    for campo, msg in resultado["avisos"]:
        errores.append(f"{pref} modelo {model.__name__}.{campo}: {msg}")

    inferidos: dict[str, dict] = meta["fields"]

    # --- excluir ---------------------------------------------------------
    excluir = list(ov.get("excluir", []))
    for c in excluir:
        if c not in inferidos:
            errores.append(f"{pref} excluir: '{c}' no es un campo de {model.__name__}.{_sugerir(c, inferidos)}")

    # --- campos ----------------------------------------------------------
    overrides_campos: dict = ov.get("fields", {})
    for c, cfg in overrides_campos.items():
        if c not in inferidos:
            errores.append(
                f"{pref} fields: '{c}' no es un campo editable de {model.__name__}.{_sugerir(c, inferidos)}"
            )
            continue
        for k in sorted(set(cfg) - FieldSpec.claves_override()):
            errores.append(
                f"{pref} fields.{c}: clave desconocida '{k}'.{_sugerir(k, FieldSpec.claves_override())}"
            )

    campos: dict[str, FieldSpec] = {}
    for c, inferido in inferidos.items():
        if c in excluir:
            continue
        cfg = {
            k: v for k, v in overrides_campos.get(c, {}).items()
            if k in FieldSpec.claves_override()
        }
        f = _field_spec(c, inferido, cfg, model)
        if f.tipo not in TIPOS_CAMPO:
            errores.append(f"{pref} fields.{c}: tipo '{f.tipo}' inválido (válidos: {sorted(TIPOS_CAMPO)})")
        if f.tipo == "fk" and f.fk_model is None:
            errores.append(f"{pref} fields.{c}: tipo 'fk' sin 'fk_model'")
        if f.tipo == "select" and not f.options:
            errores.append(f"{pref} fields.{c}: tipo 'select' sin 'options'")
        campos[c] = f

    # --- listado y filtros ----------------------------------------------
    listado = tuple(ov.get("listado") or [
        c for c, f in campos.items() if f.tipo in _TIPOS_LISTADO and not f.oculto
    ])
    filtros = tuple(ov.get("filtros") or [
        c for c, f in campos.items() if f.tipo in _TIPOS_FILTRO and not f.oculto
    ])
    for clave, lista in (("listado", listado), ("filtros", filtros)):
        for c in lista:
            if c not in campos:
                errores.append(f"{pref} {clave}: '{c}' no es un campo de la entidad.{_sugerir(c, campos)}")

    # --- padre (se valida contra el resto del registry más adelante) -----
    padre = None
    if "padre" in ov:
        p = ov["padre"]
        if not isinstance(p, dict) or set(p) != {"entidad", "fk"}:
            errores.append(f"{pref} padre debe ser {{'entidad': ..., 'fk': ...}}")
        else:
            padre = ParentSpec(entidad=p["entidad"], fk=p["fk"])
            if padre.fk not in campos:
                errores.append(f"{pref} padre.fk: '{padre.fk}' no es un campo de la entidad.{_sugerir(padre.fk, campos)}")

    # --- textos ----------------------------------------------------------
    label_plural = ov.get("label_plural", nombre.replace("_", " "))
    genero = ov.get("genero", "m")
    if genero not in GENEROS:
        errores.append(f"{pref} genero '{genero}' inválido (válidos: {sorted(GENEROS)})")

    spec = EntitySpec(
        name=nombre,
        model=model,
        pk=meta["pk"],
        label_singular=ov.get("label_singular", label_plural),
        label_plural=label_plural,
        genero=genero,
        fields=campos,
        listado=listado,
        filtros=filtros,
        auditoria=ov.get("auditoria", meta["auditoria"]["enabled"]),
        auditoria_ignorar=tuple(ov.get("auditoria_ignorar", AUDITORIA_IGNORAR_DEFAULT)),
        padre=padre,
        sidebar=bool(ov.get("sidebar", False)),
        orden=ov.get("orden", 999),
        tabs_extra=tuple(ov.get("tabs_extra", ())),
    )
    return spec, errores


# ---------------------------------------------------------------------------
# Construcción del registry completo
# ---------------------------------------------------------------------------

def construir_registry(overrides: dict[str, dict]) -> dict[str, EntitySpec]:
    """Construye y valida todas las entidades. Lanza MetamodeloError si algo falla."""
    errores: list[str] = []
    specs: dict[str, EntitySpec] = {}

    for nombre, ov in overrides.items():
        spec, errs = construir_spec(nombre, ov)
        errores.extend(errs)
        if spec is not None:
            specs[nombre] = spec

    # Relaciones padre → hijos
    hijos: dict[str, list[str]] = {n: [] for n in specs}
    for nombre, spec in specs.items():
        if spec.padre is None:
            continue
        p = spec.padre
        if p.entidad not in specs:
            errores.append(f"[{nombre}] padre.entidad: '{p.entidad}' no está registrada.{_sugerir(p.entidad, specs)}")
            continue
        if p.fk in spec.fields and not fk_apunta_a(spec.model, p.fk, specs[p.entidad].model):
            errores.append(
                f"[{nombre}] padre.fk: '{p.fk}' no es una FK hacia {specs[p.entidad].model.__name__}"
            )
            continue
        hijos[p.entidad].append(nombre)

    if errores:
        raise MetamodeloError(errores)

    return {n: replace(s, hijos=tuple(hijos[n])) for n, s in specs.items()}


def cargar_overrides(paquete: str = PAQUETE_OVERRIDES) -> dict[str, dict]:
    """
    Junta los dicts OVERRIDES de todos los módulos del paquete de overrides.
    Agregar una entidad = agregar (o ampliar) un archivo en ese paquete.
    """
    pkg = importlib.import_module(paquete)
    resultado: dict[str, dict] = {}
    duplicados: list[str] = []

    for info in sorted(pkgutil.iter_modules(pkg.__path__), key=lambda m: m.name):
        modulo = importlib.import_module(f"{paquete}.{info.name}")
        for nombre, ov in getattr(modulo, "OVERRIDES", {}).items():
            if nombre in resultado:
                duplicados.append(f"entidad '{nombre}' definida más de una vez (en {info.name})")
            resultado[nombre] = ov

    if duplicados:
        raise MetamodeloError(duplicados)
    return resultado


def construir_desde_overrides(paquete: str = PAQUETE_OVERRIDES) -> dict[str, EntitySpec]:
    return construir_registry(cargar_overrides(paquete))
