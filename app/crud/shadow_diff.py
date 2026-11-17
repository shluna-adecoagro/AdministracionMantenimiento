# app/crud/shadow_diff.py
"""
Modo sombra: compara los metamodelos escritos a mano (ENTIDADES) contra lo que
el introspector infiere de los modelos SQLAlchemy, y genera un informe Markdown.

No depende de SQLAlchemy: recibe como parámetros las funciones de introspección,
de modo que la lógica de comparación se puede probar con datos sintéticos.

Niveles de hallazgo:
  ERROR     inconsistencia probable (bug, typo, FK que no existe, NOT NULL sin required...)
  REVISAR   requiere una decisión tuya (regla de negocio vs. desfase del esquema)
  OVERRIDE  no es inferible: va a un override (labels con acento, widgets, options...)
  MEJORA    lo inferido aporta algo que el metamodelo no declaraba
  INFO      dato útil, sin acción obligatoria
"""
from __future__ import annotations

import difflib
from collections import Counter, defaultdict
from dataclasses import dataclass

# ---------------------------------------------------------------------------
# Vocabulario conocido del metamodelo actual (ajustar si el framework crece)
# ---------------------------------------------------------------------------

CLAVES_ENTIDAD = {
    "model", "pk", "label_singular", "label_plural", "genero", "bp_name",
    "es_subentidad", "entidad_padre", "fk_padre",
    "template_detalle", "template_listado",
    "fields", "listado", "filtros", "auditoria",
    "mostrar_en_sidebar", "orden", "subentidades", "tabs_extra",
}
OBLIGATORIAS = {"model", "pk", "label_singular", "label_plural", "genero", "bp_name", "fields"}

CLAVES_CAMPO = {
    "label", "tipo", "fk_model", "fk_label", "relacion", "required",
    "es_estado", "oculto", "virtual", "solo_lectura", "options", "subcarpeta",
}
TIPOS_VALIDOS = {"text", "number", "textarea", "date", "fk", "datalist", "file", "select"}
NO_INFERIBLES_CAMPO = ("es_estado", "oculto", "subcarpeta")

NIVELES = ["ERROR", "REVISAR", "OVERRIDE", "MEJORA", "INFO"]
ICONOS = {"ERROR": "🔴", "REVISAR": "🟠", "OVERRIDE": "🟡", "MEJORA": "🟢", "INFO": "⚪"}


@dataclass
class Hallazgo:
    nivel: str
    ambito: str                 # "entidad", "campo:xxx", "subentidad:xxx"...
    mensaje: str
    sugerencia: tuple | None = None   # (campo, clave, valor) para armar el override


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _norm(texto) -> str:
    import re
    import unicodedata
    t = "".join(
        c for c in unicodedata.normalize("NFD", str(texto or ""))
        if unicodedata.category(c) != "Mn"
    )
    return re.sub(r"\s+", " ", t.strip().lower())


def _fmt(valor) -> str:
    """repr legible: las clases se muestran por nombre."""
    if isinstance(valor, type):
        return valor.__name__
    if isinstance(valor, list):
        return "[" + ", ".join(_fmt(v) for v in valor) + "]"
    if isinstance(valor, dict):
        return "{" + ", ".join(f"{_fmt(k)}: {_fmt(v)}" for k, v in valor.items()) + "}"
    return repr(valor)


# ---------------------------------------------------------------------------
# Comparación de una entidad
# ---------------------------------------------------------------------------

def comparar_entidad(nombre, cfg, inf, entidades, fk_apunta_a) -> list[Hallazgo]:
    out: list[Hallazgo] = []

    def add(nivel, ambito, msg, sug=None):
        out.append(Hallazgo(nivel, ambito, msg, sug))

    meta = inf["meta"]
    excluidos = dict(inf.get("excluidos", []))
    campos_cfg = cfg.get("fields", {})
    campos_inf = meta["fields"]
    modelo = cfg["model"]

    # --- 0. Metadata del modelo (info mal escrita en las columnas) ---------
    for attr, msg in inf.get("avisos", []):
        add("ERROR", f"campo:{attr}", msg)

    # --- 1. Estructura del metamodelo -------------------------------------
    for k in cfg:
        if k not in CLAVES_ENTIDAD:
            sug = difflib.get_close_matches(k, CLAVES_ENTIDAD, n=1)
            extra = f" (¿quisiste '{sug[0]}'?)" if sug else ""
            add("ERROR", "entidad", f"clave desconocida '{k}'{extra}: probablemente el framework la ignora (verificar)")
    for k in sorted(OBLIGATORIAS - set(cfg)):
        add("ERROR", "entidad", f"falta la clave obligatoria '{k}'")
    if cfg.get("genero") not in ("m", "f"):
        add("ERROR", "entidad", f"genero={cfg.get('genero')!r} (se espera 'm' o 'f')")
    if cfg.get("pk") != meta["pk"]:
        add("ERROR", "entidad", f"pk='{cfg.get('pk')}' pero el modelo tiene '{meta['pk']}'")

    # --- 2. Campos ---------------------------------------------------------
    for fname, fcfg in campos_cfg.items():
        amb = f"campo:{fname}"

        for k in fcfg:
            if k not in CLAVES_CAMPO:
                add("ERROR", amb, f"clave de campo desconocida '{k}'")
        tipo = fcfg.get("tipo")
        if tipo not in TIPOS_VALIDOS:
            add("ERROR", amb, f"tipo '{tipo}' fuera del vocabulario {sorted(TIPOS_VALIDOS)}")

        if fname not in campos_inf:
            if fcfg.get("virtual"):
                add("INFO", amb, "campo virtual (no existe como columna)")
            elif fname in excluidos:
                add("REVISAR", amb,
                    f"el metamodelo expone '{fname}', que el introspector excluye por: {excluidos[fname]}")
            else:
                add("ERROR", amb, "no existe en el modelo")
            continue

        finf = campos_inf[fname]

        # tipo (widget)
        if tipo != finf["tipo"]:
            add("OVERRIDE", amb, f"tipo: metamodelo='{tipo}' vs inferido='{finf['tipo']}'",
                (fname, "tipo", tipo) if tipo in TIPOS_VALIDOS else None)

        # required
        req_cfg, req_inf = bool(fcfg.get("required", False)), finf["required"]
        if req_inf and not req_cfg:
            # Sin sugerencia: la inferencia ya devuelve required=True, no hace falta override.
            add("ERROR", amb, "la columna es NOT NULL pero el formulario no la exige (falla recién en la base)")
        elif req_cfg and not req_inf:
            add("REVISAR", amb, "el metamodelo exige más que el esquema (¿regla de negocio o desfase?)",
                (fname, "required", True))

        # label
        if _norm(fcfg.get("label")) != _norm(finf["label"]):
            add("OVERRIDE", amb, f"label: '{fcfg.get('label')}' (inferido: '{finf['label']}')",
                (fname, "label", fcfg.get("label")))

        # opciones de select
        if "options" in fcfg and fcfg["options"] != finf.get("options"):
            add("OVERRIDE", amb, "options propias", (fname, "options", fcfg["options"]))

        # claves que solo algunas convenciones infieren (es_estado, subcarpeta) o ninguna (oculto)
        for k in NO_INFERIBLES_CAMPO:
            if k in fcfg and fcfg[k] != finf.get(k):
                add("OVERRIDE", amb, f"{k}={fcfg[k]!r} (no inferible)", (fname, k, fcfg[k]))
            elif k not in fcfg and finf.get(k):
                add("MEJORA", amb, f"{k}={finf[k]!r} inferible por convención")

        # FKs
        if tipo == "fk" and finf["tipo"] == "fk":
            m_cfg, m_inf = fcfg.get("fk_model"), finf.get("fk_model")
            if m_inf is not None and m_cfg is not m_inf:
                add("ERROR", amb,
                    f"fk_model={_fmt(m_cfg)} pero la FK apunta a {_fmt(m_inf)}")

            r_cfg, r_inf = fcfg.get("relacion"), finf.get("relacion")
            if r_cfg and r_inf and r_cfg != r_inf:
                add("ERROR", amb, f"relacion='{r_cfg}' pero el modelo usa '{r_inf}' para esta columna")
            elif r_cfg and not r_inf:
                add("REVISAR", amb, f"declara relacion='{r_cfg}' pero ninguna relationship usa esta columna")
            elif r_inf and not r_cfg:
                add("MEJORA", amb, f"relacion inferible: '{r_inf}'")

            l_cfg, l_inf = fcfg.get("fk_label"), finf.get("fk_label")
            if l_cfg and l_inf and l_cfg != l_inf:
                add("REVISAR", amb,
                    f"fk_label='{l_cfg}' difiere del __label_field__ del destino ('{l_inf}')",
                    (fname, "fk_label", l_cfg))
            elif l_inf and not l_cfg:
                add("MEJORA", amb, f"fk_label inferible: '{l_inf}'")
            elif not l_cfg and not l_inf:
                add("REVISAR", amb,
                    "sin fk_label y el destino no define __label_field__: probablemente el select "
                    "use el fallback de ModelMixin.label (primera columna con length, p. ej. uuid)")
        elif tipo == "fk" and finf["tipo"] != "fk":
            add("ERROR", amb, "declarado como fk pero la columna no tiene ForeignKey")

    # campos del modelo que el metamodelo no expone
    for fname, finf in campos_inf.items():
        if fname in campos_cfg:
            continue
        if fname == cfg.get("fk_padre"):
            add("INFO", f"campo:{fname}", "FK al padre (la inyecta el framework)")
            continue
        nn = ", NOT NULL" if finf["required"] else ""
        add("REVISAR", f"campo:{fname}",
            f"el modelo tiene '{fname}' ({finf['tipo']}{nn}) que el metamodelo no expone",
            (fname, "excluir", True))

    # --- 3. Listado y filtros ----------------------------------------------
    for bloque, clave in (("listado", "columns"), ("filtros", "campos")):
        for c in cfg.get(bloque, {}).get(clave, []):
            if c not in campos_cfg:
                add("REVISAR", "entidad", f"{bloque}.{clave} usa '{c}', que no está en fields")

    # --- 4. Jerarquía padre / hijo -----------------------------------------
    for sub in cfg.get("subentidades", []):
        ent = sub.get("entidad")
        amb = f"subentidad:{ent}"
        hijo = entidades.get(ent)
        if hijo is None:
            add("ERROR", amb, "no existe en ENTIDADES")
            continue
        fk = sub.get("fk")
        if not fk_apunta_a(hijo["model"], fk, modelo):
            add("ERROR", amb,
                f"'{fk}' no es una FK de {hijo['model'].__name__} hacia {modelo.__name__}")
        if not hijo.get("es_subentidad"):
            add("REVISAR", amb, f"'{ent}' cuelga de '{nombre}' pero tiene es_subentidad=False")
        elif hijo.get("entidad_padre") != nombre:
            add("REVISAR", amb,
                f"entidad_padre de '{ent}' es '{hijo.get('entidad_padre')}': el esquema "
                f"admite un solo padre y '{nombre}' también la lista")
        for c in sub.get("campos_listado", []):
            if c not in hijo.get("fields", {}):
                add("INFO", amb, f"campos_listado usa '{c}', que no es un field de '{ent}' (¿se resuelve por relación?)")

    if cfg.get("es_subentidad"):
        padre = entidades.get(cfg.get("entidad_padre"))
        if padre is None:
            add("ERROR", "entidad", f"entidad_padre='{cfg.get('entidad_padre')}' no existe")
        else:
            if not fk_apunta_a(modelo, cfg.get("fk_padre"), padre["model"]):
                add("ERROR", "entidad",
                    f"fk_padre='{cfg.get('fk_padre')}' no es una FK hacia {padre['model'].__name__}")
            if not any(s.get("entidad") == nombre for s in padre.get("subentidades", [])):
                add("REVISAR", "entidad", f"el padre '{cfg.get('entidad_padre')}' no la lista en subentidades")

    # --- 5. Auditoría -------------------------------------------------------
    tiene_mixin = meta["auditoria"]["enabled"]
    aud = cfg.get("auditoria")
    if aud is None:
        if tiene_mixin:
            add("REVISAR", "entidad", "el modelo tiene AuditMixin pero el metamodelo no define 'auditoria'")
    elif aud.get("enabled") and not tiene_mixin:
        add("ERROR", "entidad", "auditoría activada pero el modelo no tiene AuditMixin")
    elif not aud.get("enabled") and tiene_mixin:
        add("REVISAR", "entidad", "auditoría desactivada aunque el modelo tiene AuditMixin")

    return out


# ---------------------------------------------------------------------------
# Informe
# ---------------------------------------------------------------------------

def _override_sugerido(hallazgos: list[Hallazgo]) -> dict:
    por_campo: dict[str, dict] = defaultdict(dict)
    for h in hallazgos:
        if h.sugerencia and h.nivel in ("OVERRIDE", "ERROR", "REVISAR"):
            campo, clave, valor = h.sugerencia
            por_campo[campo][clave] = valor
    return dict(por_campo)


def generar_informe(entidades, modelos_registrados, inferir_entidad, fk_apunta_a):
    """Devuelve (texto_markdown, resultados) donde resultados = {entidad: [Hallazgo]}."""
    resultados: dict[str, list[Hallazgo]] = {}
    for nombre, cfg in entidades.items():
        inf = inferir_entidad(cfg["model"])
        resultados[nombre] = comparar_entidad(nombre, cfg, inf, entidades, fk_apunta_a)

    L: list[str] = []
    L.append("# Informe modo sombra: metamodelos manuales vs. inferidos\n")
    L.append(f"Entidades analizadas: **{len(entidades)}**\n")

    # Resumen
    L.append("## Resumen\n")
    L.append("| Entidad | " + " | ".join(f"{ICONOS[n]} {n}" for n in NIVELES) + " |")
    L.append("|---|" + "---|" * len(NIVELES))
    total = Counter()
    for nombre, hs in resultados.items():
        c = Counter(h.nivel for h in hs)
        total.update(c)
        L.append(f"| {nombre} | " + " | ".join(str(c.get(n, 0)) for n in NIVELES) + " |")
    L.append("| **TOTAL** | " + " | ".join(f"**{total.get(n, 0)}**" for n in NIVELES) + " |\n")

    # Detalle
    L.append("## Detalle por entidad\n")
    for nombre, hs in resultados.items():
        if not hs:
            L.append(f"### {nombre}\n\n✅ Sin diferencias.\n")
            continue
        L.append(f"### {nombre}  (`{entidades[nombre]['model'].__name__}`)\n")
        for nivel in NIVELES:
            sel = [h for h in hs if h.nivel == nivel]
            if not sel:
                continue
            L.append(f"**{ICONOS[nivel]} {nivel}**\n")
            for h in sel:
                L.append(f"- `{h.ambito}`: {h.mensaje}")
            L.append("")
        sug = _override_sugerido(hs)
        if sug:
            L.append("Override sugerido (hace que lo inferido iguale al metamodelo actual):\n")
            L.append("```python")
            L.append(f"override({entidades[nombre]['model'].__name__},")
            L.append("    campos={")
            for campo, claves in sug.items():
                L.append(f"        {campo!r}: " + "{" + ", ".join(
                    f"{k!r}: {_fmt(v)}" for k, v in claves.items()) + "},")
            L.append("    })")
            L.append("```\n")

    # Global
    L.append("## Modelos sin metamodelo\n")
    usados = {c["model"] for c in entidades.values()}
    sin_meta = sorted(m.__name__ for m in modelos_registrados if m not in usados)
    L.append("Pueden ser catálogos (solo se usan como destino de FK) o modelos que se manejan solo por API:\n")
    L.append(", ".join(f"`{n}`" for n in sin_meta) or "_ninguno_")
    L.append("")

    L.append("## Blueprints compartidos (`bp_name`)\n")
    por_bp = defaultdict(list)
    for n, c in entidades.items():
        por_bp[c.get("bp_name")].append(n)
    for bp, ents in sorted(por_bp.items(), key=lambda x: str(x[0])):
        L.append(f"- `{bp}`: {', '.join(ents)}")
    L.append("")

    return "\n".join(L), resultados
