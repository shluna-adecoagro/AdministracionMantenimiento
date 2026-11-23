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
    {"text", "number", "textarea", "date", "fk", "datalist", "file", "select", "color"}
)

# Grupos del menú lateral, en el orden en que se muestran.
GRUPOS = {
    "operativos": "Operaciones",    # el día a día: OT, pedidos, solicitudes de OC, documentos
    "maestros": "Datos maestros",   # activos, recursos, materiales, sectores...
    "catalogos": "Catálogos",       # listas de valores: estados, tipos, categorías...
}
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
    # Select dependiente: este campo depende de otros de la misma entidad (ej:
    # modelo_id depende de marca_id y de categoria_activo_id). `depende_fk` son
    # las columnas del destino que apuntan a cada uno, en el mismo orden
    # (Modelo.marca_id, Modelo.categoria_activo_id). El formulario filtra las
    # opciones y al guardar se verifica que coincidan (o se completan los que
    # estén vacíos). Lo infiere el registry; en un override, {"depende_de": None}
    # lo desactiva y {"depende_de": "marca_id"} (o una lista) lo limita a esos.
    depende_de: tuple[str, ...] = ()
    depende_fk: tuple[str, ...] = ()
    # Solo se aceptan las opciones que cumplen una condición: función sin
    # argumentos que devuelve la condición SQLAlchemy sobre fk_model (ej: las
    # unidades que tienen tipo de medidor). Filtra el select y se verifica al guardar.
    fk_filtro: object = None

    # Presentación
    oculto: bool = False           # no se muestra en el formulario
    # Calculado (column_property) o mantenido por el sistema: se muestra en el
    # listado y el detalle, pero no se edita ni se recibe por la API o el CSV.
    solo_lectura: bool = False
    # "select": ({"value":..., "label":...}, ...). "datalist": sugerencias fijas
    # (o, con fk_model, los nombres de ese modelo; el valor sigue siendo texto libre).
    options: tuple = ()
    subcarpeta: str | None = None  # para tipo "file"
    # Tipo "file": extensiones admitidas (ej: (".pdf",)). Arman el `accept` del
    # formulario y se verifican al guardar. Vacío = las que admite la app.
    extensiones: tuple[str, ...] = ()

    # Numeración automática: si el campo llega vacío al crear, se completa con el
    # siguiente número de la serie. Formato con {n} (el número) y, opcional,
    # {año}: "{n}" (serie continua: 1104, 1105...) o "TRA-{año}-{n:04d}"
    # (TRA-2026-0001, se reinicia cada año). Ver app/crud/core/numeracion.py.
    numeracion: str | None = None

    # Dato cuyo dueño es otro sistema (el ERP): se ve en la app, pero solo lo
    # carga o lo actualiza la importación (no se edita en la web ni en la API).
    solo_importacion: bool = False

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
    # Nombre de la pestaña en el detalle del padre (por defecto, el plural del
    # hijo). Ej: el BOM de un activo se ve como «BOM» en el activo y como
    # «Usado en activos» en el material.
    label: str | None = None


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
class AccionSpec:
    """
    Botón del detalle que ejecuta una operación sobre el registro (ej: «Traer
    ítems del modelo» en el BOM de un activo).

    funcion(registro) hace el trabajo y devuelve el mensaje para el usuario; la
    vista confirma la transacción. seccion: pestaña donde aparece el botón.
    visible(registro) -> bool: si se muestra (por defecto, siempre).
    """

    id: str
    label: str
    funcion: object
    seccion: str = "datos"
    confirmar: str | None = None   # pregunta antes de ejecutar
    visible: object = None


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
    # modelo y también del material). El primero es el principal.
    padres: tuple[ParentSpec, ...] = ()
    hijos: tuple[str, ...] = ()        # lo completa el registry a partir de `padres`
    sidebar: bool = False
    grupo: str = "maestros"            # grupo del menú lateral (ver GRUPOS)
    orden: int = 999
    tabs_extra: tuple[TabSpec, ...] = ()
    acciones: tuple[AccionSpec, ...] = ()
    # Se ejecuta al guardar, en la misma transacción (web, API e importación):
    # al_guardar(registro, operacion, cambiados) -> aviso o None. El aviso es un
    # texto (advertencia) o una tupla ("ok" | "aviso", texto).
    # operacion: "INSERT" | "UPDATE"; cambiados: campos que cambiaron.
    al_guardar: object = None
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
        """Relación con un padre concreto (ej: "materiales" → fk "material_id")."""
        return next((p for p in self.padres if p.entidad == entidad), None)

    @property
    def tabla(self) -> str:
        return self.model.__tablename__
