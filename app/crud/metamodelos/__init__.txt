# app/crud/metamodelos/__init__.py

from .activos import ENTIDAD_ACTIVOS, ENTIDAD_MEDIDORES, ENTIDAD_LECTURAS_MEDIDOR
from .insumos import ENTIDAD_INSUMOS, ENTIDAD_STOCK_INSUMO
from .unidades_medida import ENTIDAD_UNIDADES_MEDIDA
from .sectores import ENTIDAD_SECTORES, ENTIDAD_UBICACIONES
from .cuentas import ENTIDAD_CUENTAS
from .marcas_modelos import ENTIDAD_MARCAS, ENTIDAD_MODELOS
from .recursos import (
    ENTIDAD_RECURSOS,
    ENTIDAD_EMPLEADOS,
    ENTIDAD_PROVEEDORES,
    ENTIDAD_CONTACTOS_PROVEEDOR,
)
from .bom_modelos import ENTIDAD_BOM_MODELOS
from .bom_activos import ENTIDAD_BOM_ACTIVOS

ENTIDADES = {
    "activos": ENTIDAD_ACTIVOS,
    "medidores": ENTIDAD_MEDIDORES,
    "lecturas_medidor": ENTIDAD_LECTURAS_MEDIDOR,
    "insumos": ENTIDAD_INSUMOS,
    "stock_insumo": ENTIDAD_STOCK_INSUMO,
    "unidades_medida": ENTIDAD_UNIDADES_MEDIDA,
    "sectores": ENTIDAD_SECTORES,
    "ubicaciones": ENTIDAD_UBICACIONES,
    "cuentas": ENTIDAD_CUENTAS,
    "marcas": ENTIDAD_MARCAS,
    "modelos": ENTIDAD_MODELOS,
    "recursos": ENTIDAD_RECURSOS,
    "empleados": ENTIDAD_EMPLEADOS,
    "proveedores": ENTIDAD_PROVEEDORES,
    "contactos_proveedor": ENTIDAD_CONTACTOS_PROVEEDOR,
    "bom_modelo": ENTIDAD_BOM_MODELOS,
    "bom_activo": ENTIDAD_BOM_ACTIVOS,
}
