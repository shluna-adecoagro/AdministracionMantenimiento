"""
Planes de mantenimiento preventivo (ver app/models/preventivos_models.py).

  * Plan preventivo: por categoría de activo (ej: «Parcial palas», cada 300 h).
    Tiene un período por uso (horas, km), uno por tiempo (meses, años) o los
    dos: lo que ocurra primero.
  * Tareas del plan: del catálogo de tareas, en orden (paso).
  * Plan del modelo: el plan aplicado a un modelo; ahí se cargan los materiales
    (que cambian según el modelo), con la tarea en la que se usa cada uno.

INCLUSIÓN. Un plan puede incluir a otro (el completo de 1200 h incluye al
parcial de 300 h). Reglas:
  * misma categoría y mismas unidades; cada período del superior es múltiplo
    del del inferior, con el mismo factor: el CICLO (1200 / 300 = 4);
  * un plan es incluido por un solo superior; se pueden encadenar niveles;
  * HERENCIA: las tareas y los materiales del superior son los del inferior más
    los propios. Cada plan carga solo lo que agrega, y una tarea o un material
    no puede figurar en dos planes de la misma cadena.

Las reglas corren en `al_guardar` (web, API e importación): si no se cumplen,
se lanza ErroresValidacion y no se guarda nada.
"""
from __future__ import annotations

from app.crud.core.coercion import ErroresValidacion
from app.models.activos_models import Activo
from app.models.preventivos_models import (
    PlanModelo,
    PlanModeloMaterial,
    PlanPreventivo,
    PlanPreventivoTarea,
    TareaPreventivo,
)
from app.models.unidadmedida_models import TipoUnidad, UnidadMedida

# Tipo de unidad de los períodos por tiempo (catálogo precargado en seed.py).
TIPO_UNIDAD_TIEMPO = "Tiempo"


def unidades_de_medidor():
    """Unidades que tienen tipo de medidor (las de los medidores y el período por uso)."""
    return UnidadMedida.tipo_medidor.isnot(None) & (UnidadMedida.tipo_medidor != "")


def unidades_de_tiempo():
    return UnidadMedida.tipo_unidad.has(TipoUnidad.nombre_tipo == TIPO_UNIDAD_TIEMPO)


# ---------------------------------------------------------------------------
# Cadena de inclusión
# ---------------------------------------------------------------------------

def superior_de(plan) -> PlanPreventivo | None:
    return PlanPreventivo.query.filter_by(plan_inferior_id=plan.plan_preventivo_id).first()


def inferiores(plan) -> list:
    """Planes que incluye `plan`, del más bajo al más cercano (sin el propio plan)."""
    resultado, actual, vistos = [], plan.plan_inferior, {plan.plan_preventivo_id}
    while actual is not None and actual.plan_preventivo_id not in vistos:
        vistos.add(actual.plan_preventivo_id)
        resultado.insert(0, actual)
        actual = actual.plan_inferior
    return resultado


def cadena(plan) -> list:
    """Todos los planes vinculados con `plan`, del más bajo al más alto."""
    resultado = inferiores(plan) + [plan]
    vistos = {p.plan_preventivo_id for p in resultado}
    actual = superior_de(plan)
    while actual is not None and actual.plan_preventivo_id not in vistos:
        vistos.add(actual.plan_preventivo_id)
        resultado.append(actual)
        actual = superior_de(actual)
    return resultado


def _tareas_propias(plan) -> list:
    return (PlanPreventivoTarea.query.filter_by(plan_preventivo_id=plan.plan_preventivo_id)
            .order_by(PlanPreventivoTarea.paso, PlanPreventivoTarea.plan_preventivo_tarea_id).all())


def tareas_completas(plan) -> list:
    """Tareas del plan: primero las heredadas (del plan más bajo) y después las propias."""
    return [t for p in inferiores(plan) + [plan] for t in _tareas_propias(p)]


def _materiales_propios(plan, modelo_id) -> list:
    pm = PlanModelo.query.filter_by(plan_preventivo_id=plan.plan_preventivo_id, modelo_id=modelo_id).first()
    if pm is None:
        return []
    return (PlanModeloMaterial.query.filter_by(plan_modelo_id=pm.plan_modelo_id)
            .order_by(PlanModeloMaterial.plan_modelo_material_id).all())


def materiales_completos(plan_modelo) -> list:
    """Materiales del plan en el modelo: primero los heredados y después los propios."""
    plan = plan_modelo.plan_preventivo
    return [m for p in inferiores(plan) + [plan] for m in _materiales_propios(p, plan_modelo.modelo_id)]


# ---------------------------------------------------------------------------
# Verificaciones
# ---------------------------------------------------------------------------

def _es_entero(x: float) -> bool:
    return abs(x - round(x)) < 1e-9


def _problemas_inclusion(sup, inf) -> list[str]:
    """Por qué `sup` no puede incluir a `inf` (lista vacía si puede)."""
    if sup.categoria_activo_id != inf.categoria_activo_id:
        return [f"«{inf.nombre_plan}» es de otra categoría de activo."]
    problemas, factores = [], []
    for nombre, periodo, unidad in (("uso", "periodo_uso", "unidad_uso_id"),
                                    ("tiempo", "periodo_tiempo", "unidad_tiempo_id")):
        ps, pi = getattr(sup, periodo), getattr(inf, periodo)
        if (ps is None) != (pi is None) or getattr(sup, unidad) != getattr(inf, unidad):
            problemas.append(f"el período por {nombre} tiene que estar en los dos planes y con la misma unidad")
            continue
        if ps is None:
            continue
        factor = ps / pi
        if not _es_entero(factor) or round(factor) < 2:
            problemas.append(f"el período por {nombre} ({ps:g}) tiene que ser un múltiplo del de "
                             f"«{inf.nombre_plan}» ({pi:g}): el doble, el triple...")
        else:
            factores.append(round(factor))
    if len(set(factores)) > 1:
        problemas.append(f"los dos períodos tienen que guardar la misma proporción con los de "
                         f"«{inf.nombre_plan}» ({' y '.join(f'{f}' for f in factores)} veces)")
    return problemas


def _duplicados_en_cadena(plan) -> list[str]:
    """Tareas o materiales que figuran en dos planes de la misma cadena."""
    planes = cadena(plan)
    mensajes = []

    vistas: dict[int, str] = {}
    for p in planes:
        for t in _tareas_propias(p):
            if t.tarea_preventivo_id in vistas:
                mensajes.append(f"la tarea «{t.tarea.nombre_tarea}» está en «{vistas[t.tarea_preventivo_id]}» "
                                f"y en «{p.nombre_plan}»")
            vistas.setdefault(t.tarea_preventivo_id, p.nombre_plan)

    ids = [p.plan_preventivo_id for p in planes]
    modelos = {pm.modelo_id for pm in PlanModelo.query.filter(PlanModelo.plan_preventivo_id.in_(ids))}
    for modelo_id in modelos:
        vistos: dict[int, str] = {}
        for p in planes:
            for m in _materiales_propios(p, modelo_id):
                if m.material_id in vistos:
                    mensajes.append(f"el material «{m.material.descripcion}» está en «{vistos[m.material_id]}» "
                                    f"y en «{p.nombre_plan}» para el modelo «{m.plan_modelo.modelo.nombre_modelo}»")
                vistos.setdefault(m.material_id, p.nombre_plan)
    return mensajes


def _error_cadena(plan, campo: str):
    duplicados = _duplicados_en_cadena(plan)
    if duplicados:
        raise ErroresValidacion({campo: (
            "Cada plan carga solo lo que agrega a los que incluye: " + "; ".join(duplicados) + "."
        )})


# ---------------------------------------------------------------------------
# al_guardar
# ---------------------------------------------------------------------------

def al_guardar_plan(plan, operacion: str, cambiados: set):
    errores = {}

    # Períodos: cada uno con su unidad, al menos uno.
    for periodo, unidad, nombre in (("periodo_uso", "unidad_uso_id", "por uso"),
                                    ("periodo_tiempo", "unidad_tiempo_id", "por tiempo")):
        valor = getattr(plan, periodo)
        if (valor is None) != (getattr(plan, unidad) is None):
            errores[periodo] = f"El período {nombre} va con su unidad (los dos o ninguno)."
        elif valor is not None and valor <= 0:
            errores[periodo] = f"El período {nombre} tiene que ser mayor que cero."
    if plan.periodo_uso is None and plan.periodo_tiempo is None and not errores:
        errores["periodo_uso"] = "Cargá al menos un período: por uso (ej: 300 horas), por tiempo (ej: 1 año) o los dos."
    if errores:
        raise ErroresValidacion(errores)

    # Inclusión: con su inferior y con su superior.
    inf = plan.plan_inferior
    if inf is not None:
        if plan in inferiores(inf) or inf.plan_preventivo_id == plan.plan_preventivo_id:
            raise ErroresValidacion({"plan_inferior_id": f"«{inf.nombre_plan}» ya incluye a este plan."})
        problemas = _problemas_inclusion(plan, inf)
        if problemas:
            raise ErroresValidacion({"plan_inferior_id": "No puede incluir a ese plan: " + "; ".join(problemas) + "."})
    sup = superior_de(plan)
    if sup is not None:
        problemas = _problemas_inclusion(sup, plan)
        if problemas:
            raise ErroresValidacion({"_general": (
                f"«{sup.nombre_plan}» incluye a este plan y dejaría de cumplir las reglas: "
                + "; ".join(problemas) + "."
            )})

    # Cambiar la categoría: los modelos del plan tienen que seguir siendo de ella.
    if operacion == "UPDATE" and "categoria_activo_id" in cambiados:
        otros = [pm.modelo.nombre_modelo for pm in plan.planes_modelo
                 if pm.modelo.categoria_activo_id != plan.categoria_activo_id]
        if otros:
            raise ErroresValidacion({"categoria_activo_id": (
                f"El plan se aplica a modelos de otra categoría ({', '.join(otros)}). "
                "Sacalos de la pestaña «Modelos» primero."
            )})

    if "plan_inferior_id" in cambiados:
        _error_cadena(plan, "plan_inferior_id")
    return None


def al_guardar_plan_tarea(item, operacion: str, cambiados: set):
    _error_cadena(item.plan_preventivo, "tarea_preventivo_id")
    return None


def al_guardar_plan_modelo(pm, operacion: str, cambiados: set):
    if pm.modelo.categoria_activo_id != pm.plan_preventivo.categoria_activo_id:
        raise ErroresValidacion({"modelo_id": (
            f"Modelo: «{pm.modelo.nombre_modelo}» es de la categoría "
            f"«{pm.modelo.categoria_activo.nombre_categoria}» y el plan, de "
            f"«{pm.plan_preventivo.categoria_activo.nombre_categoria}»."
        )})
    _error_cadena(pm.plan_preventivo, "modelo_id")
    return None


def al_guardar_plan_modelo_material(item, operacion: str, cambiados: set):
    plan = item.plan_modelo.plan_preventivo
    if item.cantidad is not None and item.cantidad <= 0:
        raise ErroresValidacion({"cantidad": "La cantidad tiene que ser mayor que cero."})
    if item.tarea_preventivo_id is not None:
        tareas = {t.tarea_preventivo_id for t in tareas_completas(plan)}
        if item.tarea_preventivo_id not in tareas:
            raise ErroresValidacion({"tarea_preventivo_id": (
                f"Tarea: «{item.tarea.nombre_tarea}» no está en el plan «{plan.nombre_plan}» "
                "(ni en los que incluye)."
            )})
    _error_cadena(plan, "material_id")
    return None


def al_guardar_modelo(modelo, operacion: str, cambiados: set):
    """Cambiar la categoría de un modelo: sus activos y sus planes tienen que acompañarla."""
    if operacion != "UPDATE" or "categoria_activo_id" not in cambiados:
        return None
    activos = Activo.query.filter(Activo.modelo_id == modelo.modelo_id,
                                  Activo.categoria_activo_id != modelo.categoria_activo_id).count()
    planes = [pm.plan_preventivo.nombre_plan for pm in modelo.planes_modelo
              if pm.plan_preventivo.categoria_activo_id != modelo.categoria_activo_id]
    problemas = []
    if activos:
        problemas.append(f"{activos} activo{'s' if activos != 1 else ''} de este modelo "
                         f"{'son' if activos != 1 else 'es'} de otra categoría")
    if planes:
        problemas.append(f"tiene planes de otra categoría ({', '.join(planes)})")
    if problemas:
        raise ErroresValidacion({"categoria_activo_id": (
            "No se puede cambiar la categoría: " + " y ".join(problemas) + "."
        )})
    return None


# ---------------------------------------------------------------------------
# Pestañas calculadas
# ---------------------------------------------------------------------------

def _origen(p, plan) -> str:
    return "Propia" if p.plan_preventivo_id == plan.plan_preventivo_id else p.nombre_plan


def tab_todas_las_tareas(plan) -> dict:
    filas, n = [], 0
    for t in tareas_completas(plan):
        n += 1
        filas.append([n, t.tarea.nombre_tarea, _origen(t.plan_preventivo, plan),
                      t.tarea.horas_estimadas if t.tarea.horas_estimadas is not None else "—"])
    return {
        "columnas": ["N.º", "Tarea", "De", "Horas estimadas"],
        "filas": filas,
        "vacio": "El plan no tiene tareas.",
        "nota": ("Las tareas de los planes que este incluye, y después las propias. "
                 "Las propias se cargan en la pestaña «Tareas»."),
    }


def tab_todos_los_materiales(pm) -> dict:
    plan = pm.plan_preventivo
    filas = []
    for m in materiales_completos(pm):
        unidad = m.material.unidad_medida.abreviatura if m.material.unidad_medida else ""
        filas.append([m.material.codigo, m.material.descripcion, f"{m.cantidad:g} {unidad}".strip(),
                      m.tarea.nombre_tarea if m.tarea else "—",
                      _origen(m.plan_modelo.plan_preventivo, plan)])
    return {
        "columnas": ["Código", "Material", "Cantidad", "Tarea", "De"],
        "filas": filas,
        "vacio": "El plan no tiene materiales para este modelo.",
        "nota": ("Los materiales de los planes que este incluye (para el mismo modelo), y después "
                 "los propios. Los propios se cargan en la pestaña «Materiales»."),
    }


# ---------------------------------------------------------------------------
# Entidades
# ---------------------------------------------------------------------------

# «Vigente»: Sí por defecto (si no se envía, vale Sí).
VIGENTE = {"required": False, "options": [{"value": True, "label": "Sí"}, {"value": False, "label": "No"}]}

OVERRIDES = {
    "planes_preventivos": {
        "model": PlanPreventivo,
        "label_singular": "plan preventivo",
        "label_plural": "planes preventivos",
        "genero": "m",
        "sidebar": True,
        "orden": 15,
        # También es pestaña de la categoría de activo (se borra con ella).
        "padre": {"entidad": "categorias_activo", "fk": "categoria_activo_id", "label": "Planes preventivos"},
        "fields": {
            "unidad_uso_id": {"fk_filtro": unidades_de_medidor},
            "unidad_tiempo_id": {"fk_filtro": unidades_de_tiempo},
            "vigente": VIGENTE,
            # Columna «NombreERP» de la planilla de equivalencias de SharePoint.
            "nombre_erp": {"alias": ["NombreERP"]},
        },
        "listado": ["nombre_plan", "nombre_erp", "categoria_activo_id", "plan_inferior_id", "ciclo", "vigente"],
        "clave_natural": ["nombre_plan"],
        "al_guardar": al_guardar_plan,
        "tabs_extra": [{"id": "todas_las_tareas", "label": "Todas las tareas", "funcion": tab_todas_las_tareas}],
    },
    "plan_preventivo_tareas": {
        "model": PlanPreventivoTarea,
        "label_singular": "tarea del plan",
        "label_plural": "tareas de planes",
        "genero": "f",
        "padre": [
            {"entidad": "planes_preventivos", "fk": "plan_preventivo_id", "label": "Tareas"},
            {"entidad": "tareas_preventivo", "fk": "tarea_preventivo_id", "label": "Usada en planes"},
        ],
        "listado": ["paso", "tarea_preventivo_id", "plan_preventivo_id"],
        "clave_natural": ["plan_preventivo_id", "tarea_preventivo_id"],
        "al_guardar": al_guardar_plan_tarea,
    },
    "tareas_preventivo": {
        "model": TareaPreventivo,
        "label_singular": "tarea de preventivo",
        "label_plural": "tareas de preventivo",
        "genero": "f",
        "sidebar": True,
        "grupo": "catalogos",
        "orden": 130,
        "clave_natural": ["nombre_tarea"],
    },
    "planes_modelo": {
        "model": PlanModelo,
        "label_singular": "plan del modelo",
        "label_plural": "planes de modelos",
        "genero": "m",
        "padre": [
            {"entidad": "planes_preventivos", "fk": "plan_preventivo_id", "label": "Modelos"},
            {"entidad": "modelos", "fk": "modelo_id", "label": "Planes preventivos"},
        ],
        "fields": {"vigente": VIGENTE},
        "listado": ["plan_preventivo_id", "categoria_activo_id", "marca_id", "modelo_id", "vigente"],
        "filtros": ["plan_preventivo_id", "categoria_activo_id", "marca_id", "modelo_id", "vigente"],
        "clave_natural": ["plan_preventivo_id", "modelo_id"],
        "al_guardar": al_guardar_plan_modelo,
        "tabs_extra": [{"id": "todos_los_materiales", "label": "Todos los materiales",
                        "funcion": tab_todos_los_materiales}],
    },
    "plan_modelo_materiales": {
        "model": PlanModeloMaterial,
        "label_singular": "material del plan",
        "label_plural": "materiales de planes",
        "genero": "m",
        "padre": [
            {"entidad": "planes_modelo", "fk": "plan_modelo_id", "label": "Materiales"},
            {"entidad": "materiales", "fk": "material_id", "label": "Usado en planes"},
        ],
        "fields": {
            # La unidad es la del material: no filtra los materiales.
            "material_id": {"depende_de": None},
        },
        "listado": ["material_id", "cantidad", "unidad_medida_id", "tarea_preventivo_id", "plan_modelo_id"],
        "clave_natural": ["plan_modelo_id", "material_id"],
        "al_guardar": al_guardar_plan_modelo_material,
    },
}
