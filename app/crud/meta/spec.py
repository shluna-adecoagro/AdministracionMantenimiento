# app/crud/meta/spec.py
"""
Metamodelo tipado: la descripción completa de una entidad CRUD.

`EntitySpec` y `FieldSpec` reemplazan a los dicts escritos a mano en
app/crud/metamodelos/. Los construye el registry (registry.py) combinando lo que
se infiere del modelo SQLAlchemy con los overrides de cada entidad.

Son objetos de solo lectura: todo lo que el framework necesita saber de una
entidad está acá, con nombres y tipos explícitos. Mientras conviva el framework
viejo, `to_legacy()` los traduce al formato de dict que espera framework.py.
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

    # Presentación
    oculto: bool = False           # no se muestra en el formulario
    options: tuple = ()            # para tipo "select": ({"value":..., "label":...}, ...)
    subcarpeta: str | None = None  # para tipo "file"

    # Restricciones del dato (las usará el JSON Schema en la Fase 4)
    max_length: int | None = None
    unique: bool = False

    @classmethod
    def claves_override(cls) -> frozenset[str]:
        """Claves que se pueden sobrescribir desde un override de campo."""
        return frozenset(f.name for f in dc_fields(cls)) - {"name"}

    def to_legacy(self) -> dict:
        d = {"label": self.label, "tipo": self.tipo, "required": self.required}
        if self.tipo == "fk":
            d["fk_model"] = self.fk_model
            if self.fk_label:
                d["fk_label"] = self.fk_label
            if self.relacion:
                d["relacion"] = self.relacion
        if self.es_estado:
            d["es_estado"] = True
        if self.oculto:
            d["oculto"] = True
        if self.options:
            d["options"] = [dict(o) for o in self.options]
        if self.subcarpeta:
            d["subcarpeta"] = self.subcarpeta
        return d


@dataclass(frozen=True)
class ParentSpec:
    """Relación con la entidad padre, para subentidades (ej: ubicación → sector)."""

    entidad: str  # nombre de la entidad padre en el registry
    fk: str       # columna del hijo que apunta al padre


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
    padre: ParentSpec | None = None
    hijos: tuple[str, ...] = ()        # lo completa el registry a partir de `padre`
    sidebar: bool = False
    orden: int = 999
    tabs_extra: tuple = ()

    @property
    def es_subentidad(self) -> bool:
        return self.padre is not None

    @property
    def tabla(self) -> str:
        return self.model.__tablename__

    # ------------------------------------------------------------------
    # Compatibilidad con framework.py (se elimina en la Fase 3)
    # ------------------------------------------------------------------
    def to_legacy(self, specs: dict[str, "EntitySpec"], bp_name: str) -> dict:
        """
        Traduce la spec al dict que espera CRUDResource.

        `specs` es el registry completo (para resolver hijos) y `bp_name` el
        blueprint donde se registran las rutas, que todavía depende de cómo
        estén armados los archivos de app/routes/web/.
        """
        d = {
            "model": self.model,
            "pk": self.pk,
            "label_singular": self.label_singular,
            "label_plural": self.label_plural,
            "genero": self.genero,
            "bp_name": bp_name,
            "es_subentidad": self.es_subentidad,
            "fields": {n: f.to_legacy() for n, f in self.fields.items()},
            "listado": {"columns": list(self.listado)},
            "filtros": {"campos": list(self.filtros)},
            "auditoria": {
                "enabled": self.auditoria,
                "ignore_fields": list(self.auditoria_ignorar),
            },
            "mostrar_en_sidebar": self.sidebar,
            "orden": self.orden,
        }
        if self.padre:
            d["entidad_padre"] = self.padre.entidad
            d["fk_padre"] = self.padre.fk
        if self.hijos:
            d["subentidades"] = [
                {
                    "entidad": h,
                    "label": specs[h].label_plural.capitalize(),
                    "label_singular": specs[h].label_singular,
                    "label_plural": specs[h].label_plural,
                    "fk": specs[h].padre.fk,
                    "template_listado": "crud/listado_subentidad.html",
                }
                for h in self.hijos
            ]
        if self.tabs_extra:
            d["tabs_extra"] = [dict(t) for t in self.tabs_extra]
        return d
