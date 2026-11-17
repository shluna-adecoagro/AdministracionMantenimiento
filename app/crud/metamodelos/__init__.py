# app/crud/metamodelos/__init__.py
"""
ENTIDADES: el dict que consume framework.py.

Transición (ver docs/plan_refactor_crud.md):
  - Las entidades migradas salen del registry tipado (app/crud/meta/), que se
    construye y valida al importar este módulo.
  - El resto sigue con los dicts escritos a mano de este paquete, hasta que se
    revise su diseño y se migre.
"""
from app.crud.meta.registry import construir_desde_overrides

from .activos import ENTIDAD_ACTIVOS, ENTIDAD_MEDIDORES, ENTIDAD_LECTURAS_MEDIDOR
from .insumos import ENTIDAD_INSUMOS, ENTIDAD_STOCK_INSUMO
from .unidades_medida import ENTIDAD_UNIDADES_MEDIDA
from .marcas_modelos import ENTIDAD_MARCAS, ENTIDAD_MODELOS
from .recursos import (
    ENTIDAD_RECURSOS,
    ENTIDAD_EMPLEADOS,
    ENTIDAD_PROVEEDORES,
    ENTIDAD_CONTACTOS_PROVEEDOR,
)
from .bom_modelos import ENTIDAD_BOM_MODELOS
from .bom_activos import ENTIDAD_BOM_ACTIVOS

# Specs tipadas (EntitySpec) de las entidades migradas.
REGISTRY = construir_desde_overrides()

ENTIDADES = {
    "activos": ENTIDAD_ACTIVOS,
    "medidores": ENTIDAD_MEDIDORES,
    "lecturas_medidor": ENTIDAD_LECTURAS_MEDIDOR,
    "insumos": ENTIDAD_INSUMOS,
    "stock_insumo": ENTIDAD_STOCK_INSUMO,
    "unidades_medida": ENTIDAD_UNIDADES_MEDIDA,
    "marcas": ENTIDAD_MARCAS,
    "modelos": ENTIDAD_MODELOS,
    "recursos": ENTIDAD_RECURSOS,
    "empleados": ENTIDAD_EMPLEADOS,
    "proveedores": ENTIDAD_PROVEEDORES,
    "contactos_proveedor": ENTIDAD_CONTACTOS_PROVEEDOR,
    "bom_modelo": ENTIDAD_BOM_MODELOS,
    "bom_activo": ENTIDAD_BOM_ACTIVOS,
}

for _nombre, _spec in REGISTRY.items():
    # Sus pantallas las genera app/crud/web (blueprint "crud"); el dict legacy
    # se mantiene para el menú lateral, sync-db y las entidades no migradas.
    ENTIDADES[_nombre] = _spec.to_legacy(REGISTRY, bp_name="crud")
