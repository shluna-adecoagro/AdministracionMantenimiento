"""
REGISTRY: la spec tipada (EntitySpec) de cada entidad, construida y validada
al importar este módulo a partir de los modelos y de app/crud/meta/overrides/.

Si un override es inconsistente con los modelos, la app no arranca y el error
dice qué corregir (ver app/crud/meta/registry.py).
"""
from app.crud.meta.registry import construir_desde_overrides

REGISTRY = construir_desde_overrides()
