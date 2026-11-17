# app/crud/web/textos.py
"""Textos que dependen de los nombres de las entidades."""
from app.crud.metamodelos import ENTIDADES


def etiqueta_tabla(tabla: str, cantidad: int) -> str:
    """("ubicaciones", 2) → "2 ubicaciones"; usa los textos del metamodelo si existen."""
    for cfg in ENTIDADES.values():
        if cfg["model"].__tablename__ == tabla:
            texto = cfg.get("label_plural" if cantidad != 1 else "label_singular", tabla)
            return f"{cantidad} {texto}"
    nombre = tabla.replace("_", " ")
    return f"{cantidad} registro{'s' if cantidad != 1 else ''} de {nombre}"
