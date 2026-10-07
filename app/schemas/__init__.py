# backend/app/schemas/__init__.py

import json
from pathlib import Path

# Carpeta base de schemas
BASE = Path(__file__).resolve().parent

# Cache interno para evitar relecturas
_cache = {}

def load_schema(relative_path: str):
    """
    Carga un JSON Schema desde la carpeta de schemas.
    Usa cache para evitar lecturas repetidas.
    """
    if relative_path in _cache:
        return _cache[relative_path]

    schema_path = BASE / relative_path

    if not schema_path.exists():
        raise FileNotFoundError(f"Schema no encontrado: {schema_path}")

    with open(schema_path, "r", encoding="utf-8") as f:
        schema = json.load(f)

    _cache[relative_path] = schema
    return schema


# Schemas expuestos como variables listas para importar
auditoria_schema = load_schema("auditoria/auditoria.schema.json")
sectores_schema = load_schema("sectores/sectores.schema.json")

# Si querés, podés agregar más:
# activos_general_schema = load_schema("activos/activos_general.schema.json")
# pedidos_input_schema = load_schema("pedidos/pedido_input.schema.json")

