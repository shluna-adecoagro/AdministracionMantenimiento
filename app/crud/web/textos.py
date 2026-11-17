# app/crud/web/textos.py
"""Textos que dependen de los nombres de las entidades."""
from app.crud.introspect import inicial  # noqa: F401 (se usa desde las vistas)
from app.crud.entidades import REGISTRY


def etiqueta_tabla(tabla: str, cantidad: int) -> str:
    """("ubicaciones", 2) → "2 ubicaciones"; usa los textos del registry si existen."""
    for spec in REGISTRY.values():
        if spec.tabla == tabla:
            texto = spec.label_plural if cantidad != 1 else spec.label_singular
            return f"{cantidad} {texto}"
    nombre = tabla.replace("_", " ")
    return f"{cantidad} registro{'s' if cantidad != 1 else ''} de {nombre}"
