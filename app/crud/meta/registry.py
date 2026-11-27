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

from app.crud.core.numeracion import FormatoInvalido, validar_formato
from app.crud.introspect import columnas_hacia, fk_apunta_a, inferir_entidad
from app.crud.meta.spec import (
    CeldaAltaSpec,
    ColaSpec,
    PegadoSpec,
    AUDITORIA_IGNORAR_DEFAULT,
    GENEROS,
    GRUPOS,
    AccionSpec,
    CeldaFilaSpec,
    FilasAccionSpec,
    SELECTORES,
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
    "acciones",           # [{"id", "label", "funcion", "seccion"...}] botones del detalle
    "al_guardar",         # función(registro, operacion, cambiados) tras guardar
    "completar",          # función(datos, registro) -> datos, antes de guardar
    "campos_alta",        # {campo: {...}} campos que solo se piden al crear (no son columnas)
    "orden_campos",       # [campo, ...] primeros campos del formulario, en ese orden
    "clave_natural",      # [campo, ...] identifica el registro al importar (ej: nombre)
    "edicion_en_linea",   # [campo | (campo, columna), ...] campos editables en la grilla (fase 13)
    "editable_si",        # {campo: función(registro)} si el campo se puede cambiar (fase 13.2)
    "eliminable_si",      # función(registro): si se puede eliminar
    "creable_si",         # función(datos): si se puede crear con esos datos
    "alta_en_linea",      # [{"nombre", "columnas", "interprete"...}] fila de alta de la grilla (fase 13.3)
    "alta_en_linea_padre",  # entidad padre en cuya pestaña está la fila de alta (por defecto, el principal)
    "subgrillas",         # [hijo, ...] se despliegan debajo de cada fila de la grilla (fase 13.4)
    "subgrillas_si",      # {hijo: función(registro)}: la subgrilla, solo en esas filas (fase 13.8)
    "pegado_en_linea",    # {"cantidad", "texto", "datos", "aviso", "label"} «Pegar líneas» (fase 13.5)
    "colas",              # [{"id", "label", "condicion", "columnas"...}] colas de «a revisar» (fase 13.6)
})

# Tipos de widget que por defecto aparecen en listado y filtros.
_TIPOS_LISTADO = {"text", "number", "date", "fk", "select", "datalist", "color"}
_TIPOS_FILTRO = {"text", "textarea", "fk", "select", "datalist"}
# Tipos de campo que la grilla sabe editar (un control de una línea).
TIPOS_EDICION_EN_LINEA = frozenset({"text", "textarea", "number", "date", "fk", "select", "datalist"})


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
    if "excluir_en_linea" in datos:
        datos["excluir_en_linea"] = tuple(datos["excluir_en_linea"])
    if "extensiones" in datos:
        datos["extensiones"] = tuple(e.lower() if e.startswith(".") else f".{e.lower()}"
                                     for e in datos["extensiones"])
    if datos.get("numeracion"):
        datos["required"] = False  # si llega vacío, se numera solo

    col = _columna(model, nombre)
    if col is not None:
        datos.setdefault("max_length", getattr(col.type, "length", None))
        datos.setdefault("unique", bool(getattr(col, "unique", False)))

    return FieldSpec(name=nombre, **datos)


def _campo_suelto(c: str, cfg: dict, pref: str, errores: list) -> FieldSpec:
    """
    Un campo que no es una columna: los campos de alta (ej: la cantidad de la
    línea, que crea su primer destino) y los de una acción con formulario.
    """
    desconocidas = sorted(set(cfg) - FieldSpec.claves_override())
    for k in desconocidas:
        errores.append(f"{pref}.{c}: clave desconocida '{k}'.{_sugerir(k, FieldSpec.claves_override())}")
    datos = {k: v for k, v in cfg.items() if k in FieldSpec.claves_override()}
    datos.setdefault("label", c.replace("_", " ").capitalize())
    datos.setdefault("tipo", "text")
    if "options" in datos:
        datos["options"] = tuple(dict(o) for o in datos["options"])
    if datos["tipo"] == "fk" and datos.get("fk_model") is not None:
        datos.setdefault("fk_label", getattr(datos["fk_model"], "__label_field__", None))
    if datos["tipo"] not in {"text", "textarea", "number", "select", "fk", "date"}:
        errores.append(f"{pref}.{c}: tipo '{datos['tipo']}' no admitido en un campo que no es una columna")
    if datos["tipo"] == "fk" and datos.get("fk_model") is None:
        errores.append(f"{pref}.{c}: tipo 'fk' sin 'fk_model'")
    return FieldSpec(name=c, **datos)


def _dependencias(campos: dict, overrides_campos: dict, pref: str, errores: list) -> dict:
    """
    Completa depende_de / depende_fk de cada FK.

    Inferido: el campo X (FK a M) depende del campo Y (FK a P) si M tiene una
    única columna hacia P. Ej: en activos, modelo_id → Modelo, que tiene
    marca_id → Marca y categoria_activo_id → CategoriaActivo, y el activo también
    tiene esos dos campos → modelo_id depende de marca_id y de categoria_activo_id.

    En el override: {"depende_de": None} lo desactiva; un campo o una lista de
    campos lo limita a esos (cada uno debe ser un padre posible).
    """
    resultado = dict(campos)
    for c, f in campos.items():
        if f.tipo != "fk" or f.fk_model is None or f.solo_alta:
            continue
        cfg = overrides_campos.get(c, {})
        declarado = "depende_de" in cfg
        if declarado and not cfg["depende_de"]:
            resultado[c] = replace(f, depende_de=(), depende_fk=())
            continue  # desactivado a propósito
        pedidos = None
        if declarado:
            pedidos = cfg["depende_de"]
            pedidos = [pedidos] if isinstance(pedidos, str) else list(pedidos)
        candidatos = {}
        for otro, g in campos.items():
            if otro == c or g.tipo != "fk" or g.fk_model is None or g.solo_alta:
                continue
            columnas = columnas_hacia(f.fk_model, g.fk_model)
            if len(columnas) == 1:
                candidatos[otro] = columnas[0]
        if pedidos is not None:
            for otro in pedidos:
                if otro not in candidatos:
                    errores.append(
                        f"{pref} fields.{c}: depende_de '{otro}' no es un campo FK hacia una "
                        f"tabla a la que apunte {f.fk_model.__name__}.{_sugerir(otro, campos)}"
                    )
            elegidos = [o for o in pedidos if o in candidatos]
        else:
            elegidos = list(candidatos)
        resultado[c] = replace(f, depende_de=tuple(elegidos),
                               depende_fk=tuple(candidatos[o] for o in elegidos))
    return resultado


def _filtros_antes_de_su_hijo(campos: dict) -> dict:
    """
    Un campo de solo lectura del que depende otro (ej: el tipo de activo, del
    que depende la categoría) es un filtro en el formulario: se ubica justo
    antes del campo que filtra.
    """
    orden = list(campos)
    for c, f in campos.items():
        for padre in f.depende_de:
            if campos[padre].solo_lectura and orden.index(padre) > orden.index(c):
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
        if f.fk_filtro is not None and (f.tipo != "fk" or not callable(f.fk_filtro)):
            errores.append(f"{pref} fields.{c}: fk_filtro debe ser una función, en un campo FK")
        if f.selector is not None and f.selector not in SELECTORES:
            errores.append(f"{pref} fields.{c}: selector '{f.selector}' inválido (válidos: {sorted(SELECTORES)})")
        elif f.selector is not None and f.tipo not in ("fk", "select"):
            errores.append(f"{pref} fields.{c}: selector solo aplica a un campo 'fk' o 'select'")
        if f.excluir_en_linea and (f.tipo != "select" or not set(f.excluir_en_linea)
                                   <= {o["value"] for o in f.options}):
            errores.append(f"{pref} fields.{c}: excluir_en_linea son valores de las opciones de un 'select'")
        if f.extensiones and f.tipo != "file":
            errores.append(f"{pref} fields.{c}: extensiones solo aplica a un campo de tipo 'file'")
        if f.numeracion:
            try:
                validar_formato(f.numeracion)
            except FormatoInvalido as e:
                errores.append(f"{pref} fields.{c}: numeracion '{f.numeracion}' {e}")
            if f.tipo not in ("text", "number"):
                errores.append(f"{pref} fields.{c}: numeracion solo aplica a un campo de texto o número")
        if f.numeracion_por and (not f.numeracion or f.numeracion_por not in inferidos):
            errores.append(f"{pref} fields.{c}: numeracion_por necesita numeracion y un campo de la entidad")
        if f.solo_importacion and f.solo_lectura:
            errores.append(f"{pref} fields.{c}: un campo calculado no puede ser también de solo importación")
        if f.tipo == "select" and not f.options:
            errores.append(f"{pref} fields.{c}: tipo 'select' sin 'options'")
        if f.tipo == "datalist" and not (f.options or f.fk_model):
            errores.append(f"{pref} fields.{c}: tipo 'datalist' sin 'options' ni 'fk_model'")
        campos[c] = f

    # --- campos de alta (no son columnas: los usa al_guardar) ---------------
    for c, cfg in (ov.get("campos_alta") or {}).items():
        if c in campos:
            errores.append(f"{pref} campos_alta: '{c}' ya es un campo de {model.__name__}")
            continue
        campos[c] = replace(_campo_suelto(c, cfg, f"{pref} campos_alta", errores), solo_alta=True)

    # --- orden del formulario ---------------------------------------------
    primeros = list(ov.get("orden_campos") or [])
    for c in primeros:
        if c not in campos:
            errores.append(f"{pref} orden_campos: '{c}' no es un campo de la entidad.{_sugerir(c, campos)}")
    primeros = [c for c in primeros if c in campos]
    campos = {**{c: campos[c] for c in primeros}, **{c: f for c, f in campos.items() if c not in primeros}}

    # --- selects dependientes (ej: modelo según la marca) -----------------
    campos = _dependencias(campos, overrides_campos, pref, errores)
    campos = _filtros_antes_de_su_hijo(campos)

    # --- listado y filtros ----------------------------------------------
    listado = tuple(ov.get("listado") or [
        c for c, f in campos.items() if f.tipo in _TIPOS_LISTADO and not f.oculto and not f.solo_alta
    ])
    filtros = tuple(ov.get("filtros") or [
        c for c, f in campos.items()
        if f.tipo in _TIPOS_FILTRO and not f.oculto and not f.solo_lectura and not f.solo_alta
    ])
    for clave, lista in (("listado", listado), ("filtros", filtros)):
        for c in lista:
            if c in campos and campos[c].solo_alta:
                errores.append(f"{pref} {clave}: '{c}' es un campo de alta (no se guarda)")
            elif c not in campos:
                errores.append(f"{pref} {clave}: '{c}' no es un campo de la entidad.{_sugerir(c, campos)}")

    # --- padres (se validan contra el resto del registry más adelante) ---
    padres: list[ParentSpec] = []
    declarados = ov.get("padre", [])
    for p in (declarados if isinstance(declarados, (list, tuple)) else [declarados]):
        if not isinstance(p, dict) or not {"entidad", "fk"} <= set(p) <= {"entidad", "fk", "label", "visible"}:
            errores.append(f"{pref} padre debe ser {{'entidad': ..., 'fk': ..., 'label' y 'visible' "
                           "(opcionales)}} (o una lista de ellos)")
            continue
        if p.get("visible") is not None and not callable(p["visible"]):
            errores.append(f"{pref} padre.visible debe ser una función (registro del padre) -> bool")
        padre = ParentSpec(entidad=p["entidad"], fk=p["fk"], label=p.get("label"), visible=p.get("visible"))
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

    # --- acciones y al_guardar --------------------------------------------
    acciones: list[AccionSpec] = []
    claves_accion = {"id", "label", "funcion", "seccion", "confirmar", "visible", "campos", "en_fila", "ayuda",
                     "filas"}
    for a in ov.get("acciones", ()):
        if (not isinstance(a, dict) or not {"id", "label", "funcion"} <= set(a) <= claves_accion
                or not callable(a["funcion"])):
            errores.append(f"{pref} acciones: cada acción es {{'id', 'label', 'funcion'}} "
                           f"(opcionales: {sorted(claves_accion - {'id', 'label', 'funcion'})})")
            continue
        a = dict(a)
        a["campos"] = {c: _campo_suelto(c, cfg, f"{pref} acciones.{a['id']}.campos", errores)
                       for c, cfg in (a.get("campos") or {}).items()}
        if a.get("filas") is not None:
            a["filas"] = _filas_accion(a["filas"], f"{pref} acciones.{a['id']}.filas", errores)
            if a["campos"]:
                errores.append(f"{pref} acciones.{a['id']}: 'campos' y 'filas' no van juntos")
        acciones.append(AccionSpec(**a))
    al_guardar = ov.get("al_guardar")
    if al_guardar is not None and not callable(al_guardar):
        errores.append(f"{pref} al_guardar debe ser una función")
    completar = ov.get("completar")
    if completar is not None and not callable(completar):
        errores.append(f"{pref} completar debe ser una función")

    # --- clave natural ---------------------------------------------------
    # Por defecto, la clave de origen de lo importado (OrigenMixin), si la hay.
    por_defecto = ("clave_origen",) if "clave_origen" in campos else ()
    clave_natural = tuple(ov.get("clave_natural", por_defecto))
    for c in clave_natural:
        if c not in campos:
            errores.append(f"{pref} clave_natural: '{c}' no es un campo de la entidad.{_sugerir(c, campos)}")

    # --- edición en línea -------------------------------------------------
    # El padre principal no se edita en la grilla (sería mover el registro a otro
    # padre). Los otros sí (ej: el material de una línea, que también cuelga del
    # material): en la pestaña de cada padre se oculta la columna de ese padre.
    fk_principal = padres[0].fk if padres else None
    edicion_en_linea, columna_en_linea = _edicion_en_linea(
        ov.get("edicion_en_linea") or (), listado, campos, fk_principal, f"{pref} edicion_en_linea:", errores)

    alta_en_linea, alta_en_linea_padre = _alta_en_linea(ov, campos, listado, padres, pref, errores)

    pegado_en_linea = _pegado_en_linea(ov, campos, alta_en_linea, alta_en_linea_padre, padres, pref, errores)

    subgrillas = tuple(ov.get("subgrillas") or ())
    colas = _colas(ov, campos, edicion_en_linea, columna_en_linea, pref, errores)
    if subgrillas and not edicion_en_linea:
        errores.append(f"{pref} subgrillas: la entidad no tiene edicion_en_linea (las subgrillas van en su grilla)")
    subgrillas_si = dict(ov.get("subgrillas_si") or {})
    for hijo, regla in subgrillas_si.items():
        if hijo not in subgrillas:
            errores.append(f"{pref} subgrillas_si: '{hijo}' no está en subgrillas")
        elif not callable(regla):
            errores.append(f"{pref} subgrillas_si: la regla de '{hijo}' no es una función")

    # --- reglas de edición según el registro (fase 13.2) --------------------
    editable_si = dict(ov.get("editable_si") or {})
    for c, regla in editable_si.items():
        if c not in campos or campos[c].solo_alta:
            errores.append(f"{pref} editable_si: '{c}' no es un campo de la entidad.{_sugerir(c, campos)}")
        elif not callable(regla):
            errores.append(f"{pref} editable_si.{c} debe ser una función (registro) -> bool")
    for clave in ("eliminable_si", "creable_si"):
        if ov.get(clave) is not None and not callable(ov[clave]):
            errores.append(f"{pref} {clave} debe ser una función")

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
        acciones=tuple(acciones),
        al_guardar=al_guardar,
        completar=completar,
        clave_natural=clave_natural,
        edicion_en_linea=edicion_en_linea,
        columna_en_linea=columna_en_linea,
        alta_en_linea=alta_en_linea,
        alta_en_linea_padre=alta_en_linea_padre,
        subgrillas=subgrillas,
        subgrillas_si=subgrillas_si,
        pegado_en_linea=pegado_en_linea,
        colas=colas,
        editable_si=editable_si,
        eliminable_si=ov.get("eliminable_si"),
        creable_si=ov.get("creable_si"),
    )
    return spec, errores


# ---------------------------------------------------------------------------
# Construcción del registry completo
# ---------------------------------------------------------------------------

def _edicion_en_linea(items, columnas, campos, fk_principal, pref, errores) -> tuple[tuple, dict]:
    """
    (campos, {campo: columna}) de una lista de edición en línea: campo o (campo,
    columna). La usan la grilla de la entidad y las de sus colas (fase 13.6):
    cada campo tiene que ser un dato propio (ni calculado, ni archivo, ni de solo
    importación, ni el padre principal) y estar en las `columnas` de esa grilla.
    """
    edicion, columna_en_linea = [], {}
    for item in items:
        if isinstance(item, (tuple, list)):
            if len(item) != 2:
                errores.append(f"{pref} {item!r} debe ser un campo o (campo, columna)")
                continue
            item, columna = item
            if columna not in columnas:
                errores.append(f"{pref} la columna '{columna}' de '{item}' no está en el listado")
            elif columna in edicion or columna in columna_en_linea.values():
                errores.append(f"{pref} la columna '{columna}' ya edita otro campo")
            columna_en_linea[item] = columna
        elif item in columna_en_linea.values():
            errores.append(f"{pref} la columna '{item}' ya edita otro campo")
        edicion.append(item)
    for c in edicion:
        f = campos.get(c)
        motivo = None
        if f is None:
            motivo = f"no es un campo de la entidad.{_sugerir(c, campos)}"
        elif f.solo_lectura or f.calculado_python:
            motivo = "es calculado"
        elif f.tipo == "file":
            motivo = "es un archivo"
        elif f.solo_importacion:
            motivo = "es de solo importación (su dueño es el ERP u otra fuente)"
        elif f.solo_alta:
            motivo = "es un campo de alta (no se guarda)"
        elif f.oculto:
            motivo = "está oculto"
        elif c == fk_principal:
            motivo = "es la entidad padre principal"
        elif f.tipo not in TIPOS_EDICION_EN_LINEA:
            motivo = f"tiene tipo '{f.tipo}' (admitidos: {sorted(TIPOS_EDICION_EN_LINEA)})"
        elif c not in columnas and c not in columna_en_linea:
            motivo = "no está en el listado (la grilla muestra las columnas del listado)"
        if motivo:
            errores.append(f"{pref} '{c}' {motivo}")
    return tuple(edicion), columna_en_linea


def _colas(ov, campos, edicion_entidad, columna_entidad, pref, errores) -> tuple[ColaSpec, ...]:
    """
    Colas de «a revisar» (fase 13.6): ver ColaSpec. A diferencia de la grilla de
    la entidad, una cola puede editar el padre principal: no está en la pestaña de
    ese padre (ej: identificar el proveedor de un documento sin revisar).
    """
    claves = {"id", "label", "condicion", "columnas", "edicion_en_linea", "por_defecto", "label_todas",
              "ayuda", "orden"}
    colas, ids = [], set()
    for cfg in ov.get("colas") or ():
        if not isinstance(cfg, dict) or not {"id", "label", "condicion", "columnas"} <= set(cfg) <= claves:
            errores.append(f"{pref} colas: cada cola es un dict con id, label, condicion y columnas "
                           f"(opcionales: {sorted(claves - {'id', 'label', 'condicion', 'columnas'})})")
            continue
        p = f"{pref} colas.{cfg['id']}:"
        if cfg["id"] in ids:
            errores.append(f"{p} id repetido")
        ids.add(cfg["id"])
        if not str(cfg["id"]).replace("_", "").isalnum():
            errores.append(f"{p} el id solo lleva letras, números y _ (va en la URL)")
        for clave in ("condicion", "por_defecto"):
            if cfg.get(clave) is not None and not callable(cfg[clave]):
                errores.append(f"{p} {clave} debe ser una función sin argumentos (la condición SQL)")
        columnas = tuple(cfg["columnas"])
        for c in columnas:
            if c not in campos:
                errores.append(f"{p} columna '{c}' no es un campo de la entidad.{_sugerir(c, campos)}")
        if "edicion_en_linea" in cfg:
            items = cfg["edicion_en_linea"] or ()
        else:  # los de la grilla de la entidad que se ven en la cola
            items = [(c, columna_entidad[c]) if c in columna_entidad else c for c in edicion_entidad
                     if columna_entidad.get(c, c) in columnas]
        edicion, columna_en_linea = _edicion_en_linea(items, columnas, campos, None,
                                                      f"{p} edicion_en_linea:", errores)
        if cfg.get("por_defecto") is not None and not cfg.get("label_todas"):
            errores.append(f"{p} con por_defecto hace falta label_todas (el texto para ver todo)")
        colas.append(ColaSpec(
            id=cfg["id"], label=cfg["label"], condicion=cfg["condicion"], columnas=columnas,
            edicion_en_linea=edicion, columna_en_linea=columna_en_linea,
            por_defecto=cfg.get("por_defecto"), label_todas=cfg.get("label_todas", ""),
            ayuda=cfg.get("ayuda", ""), orden=cfg.get("orden", 999),
        ))
    return tuple(colas)


def _alta_en_linea(ov, campos, listado, padres, pref, errores):
    """
    Celdas de la fila de alta de la grilla (fase 13.3) y el padre en cuya pestaña
    está. Cada celda ocupa columnas consecutivas de esa pestaña (el listado sin la
    columna del padre) y sus campos tienen que ser datos que se cargan.
    """
    from app.crud.core.interpretes import Campo

    items = ov.get("alta_en_linea") or ()
    if not items:
        if ov.get("alta_en_linea_padre"):
            errores.append(f"{pref} alta_en_linea_padre sin alta_en_linea")
        return (), None
    if not padres:
        errores.append(f"{pref} alta_en_linea: solo en una subentidad (el alta va en la pestaña del padre)")
        return (), None
    nombre_padre = ov.get("alta_en_linea_padre") or padres[0].entidad
    padre = next((p for p in padres if p.entidad == nombre_padre), None)
    if padre is None:
        errores.append(f"{pref} alta_en_linea_padre: '{nombre_padre}' no es un padre de la entidad")
        return (), None

    columnas_tab = [c for c in listado if c != padre.fk]
    ocupadas: set[str] = set()
    celdas = []
    for item in items:
        if not isinstance(item, dict) or "nombre" not in item or "columnas" not in item:
            errores.append(f"{pref} alta_en_linea: cada celda es {{'nombre', 'columnas', ...}}, no {item!r}")
            continue
        sobrantes = set(item) - {"nombre", "label", "columnas", "interprete", "repetir"}
        if sobrantes:
            errores.append(f"{pref} alta_en_linea.{item['nombre']}: claves desconocidas {sorted(sobrantes)}")
        nombre = item["nombre"]
        columnas = (item["columnas"],) if isinstance(item["columnas"], str) else tuple(item["columnas"])
        faltan = [c for c in columnas if c not in columnas_tab]
        if faltan or not columnas:
            errores.append(f"{pref} alta_en_linea.{nombre}: las columnas {faltan or '()'} no están en la "
                           f"pestaña de '{nombre_padre}' (el listado sin '{padre.fk}')")
            continue
        i = columnas_tab.index(columnas[0])
        if list(columnas) != columnas_tab[i:i + len(columnas)]:
            errores.append(f"{pref} alta_en_linea.{nombre}: las columnas {list(columnas)} no son consecutivas")
        if ocupadas & set(columnas):
            errores.append(f"{pref} alta_en_linea.{nombre}: la columna {sorted(ocupadas & set(columnas))} "
                           "ya es de otra celda")
        ocupadas |= set(columnas)

        interprete = item.get("interprete")
        if interprete is None:
            if nombre not in campos:
                errores.append(f"{pref} alta_en_linea.{nombre}: no es un campo; indicá el 'interprete'."
                               f"{_sugerir(nombre, campos)}")
                continue
            interprete = Campo(nombre)
        elif not all(hasattr(interprete, a) for a in ("campos", "control", "opciones", "interpretar")):
            errores.append(f"{pref} alta_en_linea.{nombre}: el intérprete no es válido (ver core/interpretes.py)")
            continue
        for c in interprete.campos:
            f = campos.get(c)
            motivo = None
            if f is None:
                motivo = f"no es un campo de la entidad.{_sugerir(c, campos)}"
            elif f.solo_lectura or f.calculado_python:
                motivo = "es calculado"
            elif f.tipo == "file":
                motivo = "es un archivo"
            elif f.solo_importacion:
                motivo = "es de solo importación (su dueño es el ERP u otra fuente)"
            elif c == padre.fk:
                motivo = "es el padre (viene de la pestaña)"
            if motivo:
                errores.append(f"{pref} alta_en_linea.{nombre}: '{c}' {motivo}")
        label = item.get("label") or (campos[nombre].label if nombre in campos else nombre)
        celdas.append(CeldaAltaSpec(nombre=nombre, label=label, columnas=columnas, interprete=interprete,
                                    repetir=bool(item.get("repetir"))))
    if len({c.nombre for c in celdas}) != len(celdas):
        errores.append(f"{pref} alta_en_linea: hay celdas con el mismo nombre")
    return tuple(celdas), nombre_padre


def _pegado_en_linea(ov, campos, alta_en_linea, nombre_padre, padres, pref, errores):
    """«Pegar líneas» (fase 13.5): va en la misma pestaña que la alta rápida."""
    cfg = ov.get("pegado_en_linea")
    if not cfg:
        return None
    pref = f"{pref} pegado_en_linea:"
    claves = {"cantidad", "texto", "datos", "aviso", "label"}
    if not isinstance(cfg, dict) or not {"cantidad", "texto"} <= set(cfg) <= claves:
        errores.append(f"{pref} es {{'cantidad', 'texto'}} (opcional: 'datos', 'aviso', 'label')")
        return None
    if not alta_en_linea:
        errores.append(f"{pref} requiere alta_en_linea (va en la misma pestaña)")
        return None
    padre = next(p for p in padres if p.entidad == nombre_padre)
    ok = True
    f = campos.get(cfg["cantidad"])
    if f is None or f.tipo != "number":
        errores.append(f"{pref} 'cantidad' tiene que ser un campo numérico.{_sugerir(cfg['cantidad'], campos)}")
        ok = False
    texto = cfg["texto"]
    if not all(hasattr(texto, a) for a in ("campos", "leer")):
        errores.append(f"{pref} el intérprete de 'texto' no es válido (necesita campos y leer)")
        return None
    datos = dict(cfg.get("datos") or {})
    for c in (cfg["cantidad"], *texto.campos, *datos):
        f = campos.get(c)
        motivo = None
        if f is None:
            motivo = f"no es un campo de la entidad.{_sugerir(c, campos)}"
        elif f.solo_lectura or f.calculado_python:
            motivo = "es calculado"
        elif f.tipo == "file":
            motivo = "es un archivo"
        elif f.solo_importacion:
            motivo = "es de solo importación (su dueño es el ERP u otra fuente)"
        elif c == padre.fk:
            motivo = "es el padre (viene de la pestaña)"
        if motivo:
            errores.append(f"{pref} '{c}' {motivo}")
            ok = False
    if cfg.get("aviso") is not None and not callable(cfg["aviso"]):
        errores.append(f"{pref} 'aviso' debe ser una función (datos, padre_id)")
        ok = False
    if not ok:
        return None
    return PegadoSpec(cantidad=cfg["cantidad"], texto=texto, datos=datos, aviso=cfg.get("aviso"),
                      label=cfg.get("label") or "")


def _filas_accion(cfg, pref, errores) -> FilasAccionSpec | None:
    """El formulario de una acción de varias filas (fase 13.4). Lo que cruza entidades se valida después."""
    from app.crud.core.interpretes import Campo

    claves = {"entidad", "celdas", "iniciales", "total"}
    if (not isinstance(cfg, dict) or not {"entidad", "celdas", "iniciales"} <= set(cfg) <= claves
            or not callable(cfg["iniciales"]) or (cfg.get("total") is not None and not callable(cfg["total"]))):
        errores.append(f"{pref}: es {{'entidad', 'celdas', 'iniciales'}} (opcional: 'total'), con funciones")
        return None
    celdas = []
    for item in cfg["celdas"]:
        if not isinstance(item, dict) or "nombre" not in item or not set(item) <= {"nombre", "label", "interprete",
                                                                                    "sumar"}:
            errores.append(f"{pref}.celdas: cada celda es {{'nombre', 'label', 'interprete', 'sumar'}}, no {item!r}")
            continue
        interprete = item.get("interprete") or Campo(item["nombre"])
        if not all(hasattr(interprete, a) for a in ("campos", "control", "opciones", "interpretar")):
            errores.append(f"{pref}.celdas.{item['nombre']}: el intérprete no es válido (ver core/interpretes.py)")
            continue
        celdas.append(CeldaFilaSpec(nombre=item["nombre"], label=item.get("label") or item["nombre"],
                                    interprete=interprete, sumar=bool(item.get("sumar"))))
    if not celdas:
        errores.append(f"{pref}.celdas: hace falta al menos una celda")
    if len({c.nombre for c in celdas}) != len(celdas) or any(c.nombre in ("id", "fila") for c in celdas):
        errores.append(f"{pref}.celdas: nombres repetidos (o 'id' / 'fila', que son de la fila)")
    if sum(c.sumar for c in celdas) > 1:
        errores.append(f"{pref}.celdas: solo una celda se suma")
    return FilasAccionSpec(entidad=cfg["entidad"], celdas=tuple(celdas), iniciales=cfg["iniciales"],
                           total=cfg.get("total"))


def _validar_entre_entidades(specs: dict[str, EntitySpec], errores: list[str]) -> None:
    """Subgrillas y acciones de varias filas: apuntan a un hijo de la entidad."""
    for nombre, spec in specs.items():
        for hijo in spec.subgrillas:
            h = specs.get(hijo)
            if h is None or h.padre_de_tipo(nombre) is None:
                errores.append(f"[{nombre}] subgrillas: '{hijo}' no es una subentidad de '{nombre}'."
                               f"{_sugerir(hijo, specs)}")
            elif not h.edicion_en_linea:
                errores.append(f"[{nombre}] subgrillas: '{hijo}' no tiene edicion_en_linea")
        for a in spec.acciones:
            if a.filas is None:
                continue
            h = specs.get(a.filas.entidad)
            pref = f"[{nombre}] acciones.{a.id}.filas"
            if h is None or h.padre_de_tipo(nombre) is None:
                errores.append(f"{pref}: '{a.filas.entidad}' no es una subentidad de '{nombre}'")
                continue
            for c in a.filas.celdas:
                for campo in c.interprete.campos:
                    f = h.fields.get(campo)
                    if f is None or f.solo_lectura or f.calculado_python or f.solo_importacion:
                        errores.append(f"{pref}.celdas.{c.nombre}: '{campo}' no es un dato de '{h.name}'")


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
    _validar_entre_entidades(specs, errores)

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
