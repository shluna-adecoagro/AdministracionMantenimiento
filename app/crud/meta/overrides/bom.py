"""
BOM (lista de materiales) de modelos y de activos.

  * BOM del modelo: la PLANTILLA. Los materiales que lleva un modelo (ej: filtro
    de aceite X para el tractor modelo Y). Se carga desde el modelo.
  * BOM del activo: el BOM REAL de cada activo. Al crear el activo (o al
    asignarle o cambiarle el modelo, si su BOM está vacío) se copia la plantilla
    de su modelo; después se edita libremente sin tocar la plantilla.

Cambiar la plantilla no modifica los activos existentes. Para traer a un activo
los materiales nuevos de su modelo está la acción «Traer ítems del modelo», que
agrega solo los que falten (lo ya cargado no se modifica).

Cada ítem se ve desde los dos lados: en el modelo/activo («BOM») y en el
material («Usado en modelos» / «Usado en activos»).
"""
from __future__ import annotations

from app.models.bom_activo_models import BOMActivo
from app.models.bom_modelo_models import BOMModelo

# Datos de un ítem de la plantilla que se copian al BOM del activo.
CAMPOS_COPIA = ("material_id", "cantidad", "es_equivalencia", "nota_equivalencia", "origen_equivalencia")

OVERRIDES = {
    "bom_modelo": {
        "model": BOMModelo,
        "label_singular": "ítem del BOM",
        "label_plural": "BOM de modelos",
        "genero": "m",
        "padre": [
            {"entidad": "modelos", "fk": "modelo_id", "label": "BOM"},
            {"entidad": "materiales", "fk": "material_id", "label": "Usado en modelos"},
        ],
        "clave_natural": ["modelo_id", "material_id"],
    },
    "bom_activo": {
        "model": BOMActivo,
        "label_singular": "ítem del BOM",
        "label_plural": "BOM de activos",
        "genero": "m",
        "padre": [
            {"entidad": "activos", "fk": "activo_id", "label": "BOM"},
            {"entidad": "materiales", "fk": "material_id", "label": "Usado en activos"},
        ],
        "clave_natural": ["activo_id", "material_id"],
    },
}


# ---------------------------------------------------------------------------
# Copia de la plantilla al activo
# ---------------------------------------------------------------------------

def copiar_del_modelo(activo, motivo: str) -> int:
    """
    Agrega al BOM del activo los ítems del BOM de su modelo que todavía no
    tiene (por material). Lo que ya está no se modifica. Cada ítem copiado queda
    en la auditoría. No confirma la transacción: lo hace quien llama.
    Devuelve cuántos ítems agregó.
    """
    from app.crud.entidades import servicio

    if activo.modelo_id is None:
        return 0
    ya_tiene = {b.material_id for b in BOMActivo.query.filter_by(activo_id=activo.activo_id)}
    plantilla = (
        BOMModelo.query.filter_by(modelo_id=activo.modelo_id)
        .order_by(BOMModelo.bom_modelo_id)
        .all()
    )
    s = servicio("bom_activo", confirmar=False)
    agregados = 0
    for item in plantilla:
        if item.material_id in ya_tiene:
            continue
        datos = {campo: getattr(item, campo) for campo in CAMPOS_COPIA}
        s.crear({**datos, "activo_id": activo.activo_id}, motivo)
        agregados += 1
    return agregados


def _items(n: int) -> str:
    return f"{n} ítem{'s' if n != 1 else ''}"


def al_guardar_activo(activo, operacion: str, cambiados: set):
    """
    Al crear un activo con modelo, o al asignarle o cambiarle el modelo, se copia
    el BOM del modelo, pero solo si el BOM del activo está vacío: nunca se pisa
    lo cargado a mano.
    """
    if activo.modelo_id is None:
        return None
    if operacion == "UPDATE" and "modelo_id" not in cambiados:
        return None

    modelo = activo.modelo.nombre_modelo
    if BOMActivo.query.filter_by(activo_id=activo.activo_id).count():
        return ("aviso", f"El activo pasó al modelo {modelo}, pero su BOM ya tenía ítems y no se "
                         "modificó. Si corresponde, usá «Traer ítems del modelo» en la pestaña BOM.")

    copiados = copiar_del_modelo(activo, f"Copia del BOM del modelo {modelo}")
    return ("ok", f"Se copió el BOM del modelo {modelo}: {_items(copiados)}.") if copiados else None


def traer_items_del_modelo(activo) -> str:
    """Acción «Traer ítems del modelo»: agrega los materiales del modelo que falten."""
    modelo = activo.modelo.nombre_modelo
    agregados = copiar_del_modelo(activo, f"Ítems traídos del BOM del modelo {modelo}")
    if not agregados:
        return f"El BOM ya tiene todos los materiales del modelo {modelo}."
    return f"Se agregaron {_items(agregados)} del modelo {modelo}."


ACCION_TRAER_DEL_MODELO = {
    "id": "traer_bom_modelo",
    "label": "Traer ítems del modelo",
    "funcion": traer_items_del_modelo,
    "seccion": "bom_activo",
    "confirmar": ("¿Agregar al BOM de este activo los materiales de su modelo que le falten? "
                  "Lo ya cargado no se modifica."),
    "visible": lambda activo: activo.modelo_id is not None,
}
