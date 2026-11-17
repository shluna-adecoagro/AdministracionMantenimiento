"""
REGISTRY: las specs tipadas (EntitySpec) de todas las entidades, construidas y
validadas al importar este módulo (ver app/crud/meta/).

ENTIDADES: las mismas specs en el formato de dict del framework viejo. Ya no lo
usa ninguna pantalla; queda para tools/crud_shadow.py hasta la Fase 8.
"""
from app.crud.meta.registry import construir_desde_overrides

REGISTRY = construir_desde_overrides()

ENTIDADES = {
    _nombre: _spec.to_legacy(REGISTRY, bp_name="crud") for _nombre, _spec in REGISTRY.items()
}
