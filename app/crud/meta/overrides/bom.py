"""
BOM (lista de materiales/repuestos) de modelos y de activos.

  * BOM del modelo: los materiales que lleva un modelo (ej: filtro de aceite X
    para el tractor modelo Y). Vale para todos los activos de ese modelo.
  * BOM del activo: ajustes de un activo puntual: materiales propios, o un
    material que reemplaza a uno del modelo (`reemplaza_material_modelo_id`).

Cada ítem se ve desde los dos lados: en el modelo/activo ("BOM") y en el
material (dónde se usa). Las pestañas calculadas combinan ambos:

  * Activo → "BOM final": el BOM del modelo con los ajustes del activo.
  * Material → "Compatibilidad final": los activos en los que se usa.
"""
from __future__ import annotations

from app.models.activos_models import Activo
from app.models.bom_activo_models import BOMActivo
from app.models.bom_modelo_models import BOMModelo

OVERRIDES = {
    "bom_modelo": {
        "model": BOMModelo,
        "label_singular": "ítem del BOM de modelo",
        "label_plural": "BOM de modelos",
        "genero": "m",
        # Se gestiona desde el modelo (principal) y se ve también en el material.
        "padre": [
            {"entidad": "modelos", "fk": "modelo_id"},
            {"entidad": "materiales", "fk": "material_id"},
        ],
        "clave_natural": ["modelo_id", "material_id"],
    },
    "bom_activo": {
        "model": BOMActivo,
        "label_singular": "ítem del BOM de activo",
        "label_plural": "BOM de activos",
        "genero": "m",
        "padre": [
            {"entidad": "activos", "fk": "activo_id"},
            {"entidad": "materiales", "fk": "material_id"},
        ],
        "listado": ["activo_id", "material_id", "cantidad", "es_equivalencia", "reemplaza_material_modelo_id"],
        "clave_natural": ["activo_id", "material_id"],
    },
}


# ---------------------------------------------------------------------------
# Pestañas calculadas
# ---------------------------------------------------------------------------

def _material(material) -> str:
    return f"{material.codigo} · {material.descripcion}" if material else "—"


def _si_no(valor) -> str:
    return "Sí" if valor else "No"


def bom_del_modelo(activo: Activo) -> dict:
    columnas = ["Material", "Cantidad", "Equivalencia", "Nota"]
    if activo.modelo_id is None:
        return {"columnas": columnas, "filas": [], "vacio": "El activo no tiene modelo asignado."}
    items = BOMModelo.query.filter_by(modelo_id=activo.modelo_id).order_by(BOMModelo.bom_modelo_id).all()
    return {
        "columnas": columnas,
        "filas": [[_material(b.material), b.cantidad, _si_no(b.es_equivalencia), b.nota_equivalencia] for b in items],
        "nota": f"Modelo {activo.modelo.nombre_modelo}. Se edita desde el modelo.",
        "vacio": "El modelo no tiene BOM cargado.",
    }


def bom_final(activo: Activo) -> dict:
    """
    BOM del modelo con los ajustes del activo:
      * un ítem del activo que reemplaza a un material del modelo lo saca de la lista;
      * un ítem del activo con el mismo material que uno del modelo lo pisa;
      * el resto de los ítems del activo se agregan.
    """
    finales: dict[int, list] = {}
    if activo.modelo_id is not None:
        for b in BOMModelo.query.filter_by(modelo_id=activo.modelo_id).order_by(BOMModelo.bom_modelo_id):
            finales[b.material_id] = [_material(b.material), b.cantidad, _si_no(b.es_equivalencia), "Modelo", None]

    for b in BOMActivo.query.filter_by(activo_id=activo.activo_id).order_by(BOMActivo.bom_activo_id):
        nota = None
        if b.reemplaza_material_modelo_id is not None:
            finales.pop(b.reemplaza_material_modelo_id, None)
            nota = f"Reemplaza a {_material(b.reemplaza_material_modelo)}"
        finales[b.material_id] = [_material(b.material), b.cantidad, _si_no(b.es_equivalencia), "Activo", nota]

    return {
        "columnas": ["Material", "Cantidad", "Equivalencia", "Origen", "Nota"],
        "filas": list(finales.values()),
        "vacio": "Ni el modelo ni el activo tienen BOM cargado.",
    }


def compatibilidad_final(material) -> dict:
    """
    Activos en los que se usa el material: los de los modelos que lo llevan
    (salvo que el activo lo reemplace por otro) y los que lo tienen en su BOM propio.
    """
    filas: dict[int, list] = {}

    modelos = [b.modelo_id for b in BOMModelo.query.filter_by(material_id=material.material_id)]
    if modelos:
        reemplazado_en = {
            b.activo_id for b in BOMActivo.query.filter_by(reemplaza_material_modelo_id=material.material_id)
        }
        for a in Activo.query.filter(Activo.modelo_id.in_(modelos)).order_by(Activo.descripcion):
            if a.activo_id not in reemplazado_en:
                filas[a.activo_id] = [a.descripcion, a.numero_activo, a.modelo.nombre_modelo, "BOM del modelo"]

    for b in BOMActivo.query.filter_by(material_id=material.material_id):
        a = b.activo
        modelo = a.modelo.nombre_modelo if a.modelo else None
        filas[a.activo_id] = [a.descripcion, a.numero_activo, modelo, "BOM del activo"]

    return {
        "columnas": ["Activo", "Número de activo", "Modelo", "Según"],
        "filas": sorted(filas.values(), key=lambda f: f[0] or ""),
        "vacio": "El material no figura en el BOM de ningún modelo ni activo.",
    }
