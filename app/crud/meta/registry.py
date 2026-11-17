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

from app.crud.introspect import columnas_hacia, fk_apunta_a, inferir_entidad
from app.crud.meta.spec import (
    AUDITORIA_IGNORAR_DEFAULT,
    GENEROS,
    GRUPOS,
    TIPOS_CAMPO,
    EntitySpec,
    FieldSpec,
    ParentSpec,
    TabSpec,
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
                          # (o una lista, si cuelga de varias entidades)
    "sidebar",            # True para mostrarla en el menú lateral
    "grupo",              # "maestros" (por defecto) o "catalogos": sección del menú
    "orden",              # posición en el menú lateral
    "auditoria",          # True/False (por defecto: si el modelo usa AuditMixin)
    "auditoria_ignorar",  # columnas que no se registran en el historial
    "tabs_extra",         # [{"id", "label", "funcion"}] pestañas calculadas en el detalle
    "clave_natural",      # [campo, ...] identifica el registro al importar (ej: nombre)
})

# Tipos de widget que por defecto aparecen en listado y filtros.
_TIPOS_LISTADO = {"text", "number", "date", "fk", "select", "datalist", "color"}
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
    if "alias" in datos:
        datos["alias"] = tuple(datos["alias"])

    col = _columna(model, nombre)
    if col is not None:
        datos.setdefault("max_length", getattr(col.type, "length", None))
        datos.setdefault("unique", bool(getattr(col, "unique", False)))

    return FieldSpec(name=nombre, **datos)


def _dependencias(campos: dict, overrides_campos: dict, pref: str, errores: list) -> dict:
    """
    Completa depende_de / depende_fk de cada FK.

    Inferido: el campo X (FK a M) depende del campo Y (FK a P) si M tiene una
    única columna hacia P. Ej: en activos, modelo_id → Modelo, que tiene
    marca_id → Marca, y el activo también tiene marca_id → modelo_id depende de marca_id.
    """
    resultado = dict(campos)
    for c, f in campos.items():
        if f.tipo != "fk" or f.fk_model is None:
            continue
        declarado = "depende_de" in overrides_campos.get(c, {})
        if declarado and f.depende_de is None:
            continue  # desactivado a propósito
        candidatos = []
        for otro, g in campos.items():
            if otro == c or g.tipo != "fk" or g.fk_model is None:
                continue
            if declarado and otro != f.depende_de:
                continue
            columnas = columnas_hacia(f.fk_model, g.fk_model)
            if len(columnas) == 1:
                candidatos.append((otro, columnas[0]))
        if declarado and not candidatos:
            errores.append(
                f"{pref} fields.{c}: depende_de '{f.depende_de}' no es un campo FK hacia una "
                f"tabla a la que apunte {f.fk_model.__name__}.{_sugerir(f.depende_de, campos)}"
            )
        elif len(candidatos) == 1:
            otro, columna = candidatos[0]
            resultado[c] = replace(f, depende_de=otro, depende_fk=columna)
    return resultado


def _filtros_antes_de_su_hijo(campos: dict) -> dict:
    """
    Un campo de solo lectura del que depende otro (ej: el tipo de activo, del
    que depende la categoría) es un filtro en el formulario: se ubica justo
    antes del campo que filtra.
    """
    orden = list(campos)
    for c, f in campos.items():
        padre = f.depende_de
        if padre and campos[padre].solo_lectura and orden.index(padre) > orden.index(c):
            orden.remove(padre)
            orden.insert(orden.index(c), padre)
    return {c: campos[c] for c in orden}


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
        if f.tipo == "datalist" and not (f.options or f.fk_model):
            errores.append(f"{pref} fields.{c}: tipo 'datalist' sin 'options' ni 'fk_model'")
        campos[c] = f

    # --- selects dependientes (ej: modelo según la marca) -----------------
    campos = _dependencias(campos, overrides_campos, pref, errores)
    campos = _filtros_antes_de_su_hijo(campos)

    # --- listado y filtros ----------------------------------------------
    listado = tuple(ov.get("listado") or [
        c for c, f in campos.items() if f.tipo in _TIPOS_LISTADO and not f.oculto
    ])
    filtros = tuple(ov.get("filtros") or [
        c for c, f in campos.items()
        if f.tipo in _TIPOS_FILTRO and not f.oculto and not f.solo_lectura
    ])
    for clave, lista in (("listado", listado), ("filtros", filtros)):
        for c in lista:
            if c not in campos:
                errores.append(f"{pref} {clave}: '{c}' no es un campo de la entidad.{_sugerir(c, campos)}")

    # --- padres (se validan contra el resto del registry más adelante) ---
    padres: list[ParentSpec] = []
    declarados = ov.get("padre", [])
    for p in (declarados if isinstance(declarados, (list, tuple)) else [declarados]):
        if not isinstance(p, dict) or set(p) != {"entidad", "fk"}:
            errores.append(f"{pref} padre debe ser {{'entidad': ..., 'fk': ...}} (o una lista de ellos)")
            continue
        padre = ParentSpec(entidad=p["entidad"], fk=p["fk"])
        if padre.fk not in campos:
            errores.append(f"{pref} padre.fk: '{padre.fk}' no es un campo de la entidad.{_sugerir(padre.fk, campos)}")
        if any(x.entidad == padre.entidad for x in padres):
            errores.append(f"{pref} padre: '{padre.entidad}' está declarada dos veces")
        padres.append(padre)

    # --- pestañas extra ----------------------------------------------------
    tabs: list[TabSpec] = []
    for t in ov.get("tabs_extra", ()):
        if not isinstance(t, dict) or set(t) != {"id", "label", "funcion"} or not callable(t.get("funcion")):
            errores.append(f"{pref} tabs_extra: cada pestaña es {{'id', 'label', 'funcion'}} con una función")
            continue
        tabs.append(TabSpec(**t))

    # --- clave natural ---------------------------------------------------
    clave_natural = tuple(ov.get("clave_natural", ()))
    for c in clave_natural:
        if c not in campos:
            errores.append(f"{pref} clave_natural: '{c}' no es un campo de la entidad.{_sugerir(c, campos)}")

    # --- textos ----------------------------------------------------------
    label_plural = ov.get("label_plural", nombre.replace("_", " "))
    genero = ov.get("genero", "m")
    if genero not in GENEROS:
        errores.append(f"{pref} genero '{genero}' inválido (válidos: {sorted(GENEROS)})")

    grupo = ov.get("grupo", "maestros")
    if grupo not in GRUPOS:
        errores.append(f"{pref} grupo '{grupo}' inválido (válidos: {sorted(GRUPOS)}).{_sugerir(grupo, GRUPOS)}")

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
        padres=tuple(padres),
        sidebar=bool(ov.get("sidebar", False)),
        grupo=grupo,
        orden=ov.get("orden", 999),
        tabs_extra=tuple(tabs),
        clave_natural=clave_natural,
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
        for p in spec.padres:
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
