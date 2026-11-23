# app/crud/core/files.py
"""
Almacenamiento de archivos subidos (fotos, documentos).

Los archivos se guardan con un nombre aleatorio (UUID) bajo
<static>/uploads/<entidad>[/<subcarpeta>] y en la base queda la ruta pública.
"""
from __future__ import annotations

import os
import uuid

EXTENSIONES_PERMITIDAS = frozenset({".jpg", ".jpeg", ".png", ".gif", ".webp", ".pdf"})


class ArchivoInvalido(ValueError):
    pass


def _segmento_seguro(nombre: str) -> str:
    if not nombre or "/" in nombre or "\\" in nombre or nombre in (".", ".."):
        raise ValueError(f"segmento de ruta inválido: {nombre!r}")
    return nombre


def guardar(archivo, carpeta_static: str, entidad: str, subcarpeta: str | None = None,
            extensiones=()) -> str:
    """
    Guarda un archivo (werkzeug FileStorage o similar) y devuelve su ruta pública,
    por ejemplo "/static/uploads/activos/fotos/<uuid>.jpg".
    Lanza ArchivoInvalido si la extensión no está permitida: las del campo
    (`extensiones`, ej: solo PDF) o, si no declara ninguna, las de la app.
    """
    admitidas = (set(extensiones) & EXTENSIONES_PERMITIDAS) if extensiones else EXTENSIONES_PERMITIDAS
    extension = os.path.splitext(archivo.filename or "")[1].lower()
    if extension not in admitidas:
        permitidas = ", ".join(sorted(admitidas))
        raise ArchivoInvalido(f"tipo de archivo no permitido (se aceptan: {permitidas})")

    partes = ["uploads", _segmento_seguro(entidad)]
    if subcarpeta:
        partes.append(_segmento_seguro(subcarpeta))

    destino = os.path.join(carpeta_static, *partes)
    os.makedirs(destino, exist_ok=True)

    nombre = f"{uuid.uuid4()}{extension}"
    archivo.save(os.path.join(destino, nombre))
    return "/static/" + "/".join(partes + [nombre])
