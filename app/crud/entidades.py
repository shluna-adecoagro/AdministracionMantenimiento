"""
REGISTRY: la spec tipada (EntitySpec) de cada entidad, construida y validada
al importar este módulo a partir de los modelos y de app/crud/meta/overrides/.

Si un override es inconsistente con los modelos, la app no arranca y el error
dice qué corregir (ver app/crud/meta/registry.py).
"""
from app.crud.meta.registry import construir_desde_overrides

REGISTRY = construir_desde_overrides()


def servicio(entidad, *, confirmar: bool = True):
    """
    ServicioCRUD de una entidad (su nombre o su EntitySpec), con su auditoría,
    sus textos y su acción al guardar. Lo usan la web, la API, la importación y
    las acciones, así las reglas de guardado son las mismas en todos lados.
    """
    from app.crud.core.service import ServicioCRUD
    from app.crud.web.textos import etiqueta_tabla

    spec = REGISTRY[entidad] if isinstance(entidad, str) else entidad
    return ServicioCRUD(
        spec.model,
        spec.fields,
        {"enabled": spec.auditoria, "ignore_fields": list(spec.auditoria_ignorar)},
        etiqueta_tabla,
        confirmar=confirmar,
        al_guardar=spec.al_guardar,
    )
