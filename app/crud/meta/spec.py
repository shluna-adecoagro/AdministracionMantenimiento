# app/crud/meta/spec.py
"""
Metamodelo tipado: la descripción completa de una entidad CRUD.

`EntitySpec` y `FieldSpec` los construye el registry (registry.py) combinando lo
que se infiere del modelo SQLAlchemy con los overrides de cada entidad.

Son objetos de solo lectura: todo lo que el framework necesita saber de una
entidad está acá, con nombres y tipos explícitos.
"""
from __future__ import annotations

from dataclasses import dataclass, field, fields as dc_fields

# Vocabulario de widgets que entienden las plantillas (crud/form.html).
TIPOS_CAMPO = frozenset(
    {"text", "number", "textarea", "date", "fk", "datalist", "file", "select"}
)
GENEROS = frozenset({"m", "f"})

# Columnas que nunca se auditan como cambio (además de las globales de registrar.py).
AUDITORIA_IGNORAR_DEFAULT = ("uuid", "creado_en", "actualizado_en")


@dataclass(frozen=True)
class FieldSpec:
    """Un campo editable de la entidad (una columna del modelo)."""

    name: str
    label: str
    tipo: str
    required: bool = False

    # Claves foráneas
    fk_model: type | None = None   # clase destino
    fk_label: str | None = None    # atributo del destino que se muestra
    relacion: str | None = None    # relationship del modelo que lleva al destino
    es_estado: bool = False        # se muestra como badge de color
    # Select dependiente: este campo depende de otro de la misma entidad (ej:
    # modelo_id depende de marca_id). `depende_fk` es la columna del destino que
    # apunta al otro (Modelo.marca_id). El formulario filtra las opciones y al
    # guardar se verifica que coincidan (o se completa el otro si está vacío).
    # Lo infiere el registry; un override {"depende_de": None} lo desactiva.
    depende_de: str | None = None
    depende_fk: str | None = None

    # Presentación
    oculto: bool = False           # no se muestra en el formulario
    # Calculado (column_property) o mantenido por el sistema: se muestra en el
    # listado y el detalle, pero no se edita ni se recibe por la API o el CSV.
    solo_lectura: bool = False
    # "select": ({"value":..., "label":...}, ...). "datalist": sugerencias fijas
    # (o, con fk_model, los nombres de ese modelo; el valor sigue siendo texto libre).
    options: tuple = ()
    subcarpeta: str | None = None  # para tipo "file"

    # Otros nombres de columna que se aceptan al importar un CSV, además del
    # nombre del campo y su etiqueta (ej: ("name",) para una columna de SharePoint).
    alias: tuple[str, ...] = ()

    # Restricciones del dato (las usa el JSON Schema de la API)
    max_length: int | None = None
    unique: bool = False

    # Acceso tipo dict (cfg.get("label"), cfg["fk_model"]), para que la capa core
    # y las plantillas acepten indistintamente un FieldSpec o un dict de metamodelo.
    def get(self, clave, default=None):
        return getattr(self, clave, default)

    def __getitem__(self, clave):
        try:
            return getattr(self, clave)
        except AttributeError:
            raise KeyError(clave) from None

    def __contains__(self, clave):
        return hasattr(self, clave)

    @classmethod
    def claves_override(cls) -> frozenset[str]:
        """Claves que se pueden sobrescribir desde un override de campo."""
        return frozenset(f.name for f in dc_fields(cls)) - {"name"}


@dataclass(frozen=True)
class ParentSpec:
    """Relación con la entidad padre, para subentidades (ej: ubicación → sector)."""

    entidad: str  # nombre de la entidad padre en el registry
    fk: str       # columna del hijo que apunta al padre


@dataclass(frozen=True)
class TabSpec:
    """
    Pestaña extra del detalle, con una tabla de solo lectura calculada.
    `funcion(registro)` devuelve {"columnas": [...], "filas": [[...], ...]} y
    opcionalmente "vacio" (texto si no hay filas) y "nota".
    """

    id: str
    label: str
    funcion: object


@dataclass(frozen=True)
class EntitySpec:
    name: str
    model: type
    pk: str
    label_singular: str
    label_plural: str
    genero: str
    fields: dict[str, FieldSpec]
    listado: tuple[str, ...]
    filtros: tuple[str, ...]
    auditoria: bool
    auditoria_ignorar: tuple[str, ...] = AUDITORIA_IGNORAR_DEFAULT
    # Subentidades: padres de los que cuelga (ej: el BOM de un modelo cuelga del
    # modelo y también del insumo). El primero es el principal.
    padres: tuple[ParentSpec, ...] = ()
    hijos: tuple[str, ...] = ()        # lo completa el registry a partir de `padres`
    sidebar: bool = False
    orden: int = 999
    tabs_extra: tuple[TabSpec, ...] = ()
    # Campos que identifican un registro fuera de la base (ej: en SharePoint),
    # donde los IDs no coinciden. Los usa la importación para actualizar en vez
    # de duplicar. Ej: ("nombre_sector",) o ("nombre_ubicacion", "sector_id").
    clave_natural: tuple[str, ...] = ()

    @property
    def padre(self) -> ParentSpec | None:
        """Padre principal (el primero declarado)."""
        return self.padres[0] if self.padres else None

    @property
    def es_subentidad(self) -> bool:
        return bool(self.padres)

    def padre_de_tipo(self, entidad: str) -> ParentSpec | None:
        """Relación con un padre concreto (ej: "insumos" → fk "insumo_id")."""
        return next((p for p in self.padres if p.entidad == entidad), None)

    @property
    def tabla(self) -> str:
        return self.model.__tablename__
