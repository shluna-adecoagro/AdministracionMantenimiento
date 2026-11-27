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

# Cómo se elige una opción (FieldSpec.selector): un <select> o un campo con lista.
SELECTORES = frozenset({"select", "lista"})

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

    # Cómo se elige una opción (FK, "select" de opciones fijas o filtro Sí/No):
    # None = según el largo de la lista (hasta fk.UMBRAL_LISTA opciones, un
    # <select>; con más, un campo con lista para buscar tipeando); "select" o
    # "lista" lo fijan.
    selector: str | None = None
    # Opciones de un "select" que la grilla no ofrece ni acepta (ej: «Anulado»
    # en el estado de una línea: se anula con su acción, que pide el motivo).
    excluir_en_linea: tuple = ()

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
    # La serie se cuenta dentro de cada valor de este campo (ej: el número de
    # línea, dentro de cada pedido: numeracion_por="pedido_id").
    numeracion_por: str | None = None

    # Dato cuyo dueño es otro sistema (el ERP): se ve en la app, pero solo lo
    # carga o lo actualiza la importación (no se edita en la web ni en la API).
    solo_importacion: bool = False

    # Campo que solo existe en el alta (no es una columna): se pide al crear y lo
    # usa al_guardar, en registro.datos_alta (ej: la cantidad y el destino
    # principal de una línea de pedido, que crean su primer destino).
    solo_alta: bool = False

    # Calculado en Python: propiedad del modelo declarada en __calculados__
    # (ej: el resumen de un pedido). Se ve en listado, detalle y API.
    calculado_python: bool = False

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
    # visible(registro_padre) -> bool: si la pestaña se muestra en ese padre
    # (ej: «Presentaciones» solo en los materiales genéricos). Por defecto, siempre.
    visible: object = None


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
    # Acción con formulario (ej: «Anular o cancelar», que pide el motivo y la
    # cantidad): {campo: FieldSpec}, armados como los campos de alta. Si hay
    # campos, el botón lleva a una página con el formulario y la función recibe
    # además los datos ya convertidos: funcion(registro, datos).
    campos: dict = field(default_factory=dict)
    # También se muestra como botón en la fila del listado y de la pestaña del
    # padre (además de en el detalle).
    en_fila: bool = False
    # Texto de ayuda arriba del formulario de la acción.
    ayuda: str | None = None
    # Acción de varias filas (FilasAccionSpec, ej: «Redistribuir» los destinos de
    # una línea): el formulario es una tabla, con una fila por registro hijo, y la
    # función recibe la lista de filas ya interpretadas: funcion(registro, filas).
    filas: "FilasAccionSpec | None" = None


@dataclass(frozen=True)
class CeldaFilaSpec:
    """
    Una celda de cada fila de una acción de varias filas.

    nombre      name del input (y clave en la fila que recibe la función).
    label       encabezado de la columna (y aria-label).
    interprete  cómo se convierte lo escrito, con la spec de la entidad de las
                filas (app/crud/core/interpretes.py; por defecto, Campo(nombre)).
    sumar       la columna muestra su total en vivo (ej: la cantidad, que tiene
                que sumar lo mismo que antes).
    """

    nombre: str
    label: str
    interprete: object
    sumar: bool = False


@dataclass(frozen=True)
class FilasAccionSpec:
    """
    Formulario de una acción de varias filas (fase 13.4).

    entidad    la entidad de las filas (un hijo del registro): sus campos
               interpretan las celdas.
    celdas     CeldaFilaSpec, en el orden de las columnas.
    iniciales  función(registro) -> [{"id": pk, <celda>: texto, "_nota": texto}]:
               las filas con las que se abre el formulario (una por hijo). La
               nota se muestra al lado, sin editarse.
    total      función(registro) -> número (opcional): lo que tiene que sumar la
               celda con `sumar` (se muestra junto al total en vivo).

    La función de la acción recibe [{"id": pk o None (fila nueva), "fila": n,
    <campos interpretados>}], sin las filas vacías, y rechaza con
    ErroresValidacion({"fila_<n>": ..., "_general": ...}). Todo o nada.
    """

    entidad: str
    celdas: tuple[CeldaFilaSpec, ...]
    iniciales: object
    total: object = None


@dataclass(frozen=True)
class CeldaAltaSpec:
    """
    Una celda de la fila de alta de la grilla (alta rápida, fase 13.3).

    nombre      name del input (y clave del error).
    label       texto de ayuda (placeholder y aria-label).
    columnas    columnas consecutivas del listado que ocupa (colspan).
    interprete  cómo se convierte lo escrito en datos (app/crud/core/interpretes.py):
                interpretar(texto, spec) -> dict, sugerencias(spec) -> [texto],
                control ("text" | "number" | "lista" | "select") y campos (los que
                produce: ubican los errores del servicio en esta celda).
    repetir     lo escrito queda en la fila de alta siguiente (ej: el destino, que
                suele ser el mismo para varias líneas seguidas).
    """

    nombre: str
    label: str
    columnas: tuple[str, ...]
    interprete: object
    repetir: bool = False


@dataclass(frozen=True)
class PegadoSpec:
    """
    «Pegar líneas» (fase 13.5): varias altas de una vez, una por renglón del texto
    pegado (de un mail, de WhatsApp o de una planilla), en la pestaña del padre de
    la alta rápida. Cada renglón es «cantidad texto»; lo lee app/crud/core/pegado.py.

    cantidad  campo (de la entidad o de alta) que recibe el número del principio.
    texto     intérprete del resto del renglón: campos (los que produce) y
              leer(texto, spec) -> (datos, avisos). Nunca rechaza: lo que no
              reconoce queda como texto (ej: CodigoEnTexto).
    datos     datos fijos de cada alta (ej: el destino «a identificar»).
    aviso     función(datos, padre_id) -> texto o None (opcional): un aviso que no
              bloquea (ej: una línea igual a otra que ya está en el pedido).
    label     texto del botón (por defecto, «Pegar <label_plural>»).
    """

    cantidad: str
    texto: object
    datos: dict = field(default_factory=dict)
    aviso: object = None
    label: str = ""


@dataclass(frozen=True)
class ColaSpec:
    """
    Cola de «a revisar» (fase 13.6): una lista editable con nombre de los
    registros de una entidad que cumplen una condición (ej: los destinos de
    pedido sin sector imputado o sin cuenta), para resolverlos en la grilla. Se
    ve en /<entidad>/cola/<id> y en el menú, en «A revisar», con la cantidad.

    id                identifica la cola en la URL (único en la entidad).
    label             título de la pantalla y del menú («Destinos a revisar»).
    condicion         función sin argumentos -> condición SQLAlchemy sobre el
                      modelo: qué registros están en la cola.
    columnas          columnas de la grilla (campos de la entidad).
    edicion_en_linea  campos que se editan en la grilla, como en la spec
                      (campo o (campo, columna)). Por defecto, los de la
                      edicion_en_linea de la entidad que están en `columnas`.
                      Puede incluir el padre principal (la cola no está en su
                      pestaña): ej: el proveedor de un documento sin revisar.
    columna_en_linea  {campo: columna} (lo arma el registry).
    por_defecto       función sin argumentos -> condición que se agrega salvo
                      que se pida ver todo (?todas=1): ej: sin las líneas
                      cerradas. El menú cuenta con ella.
    label_todas       texto del control que la quita («Incluir las cerradas»).
    ayuda             texto arriba de la grilla: cómo se resuelve.
    orden             posición en el menú.

    Una fila que deja de cumplir la condición al editarla queda en la grilla,
    marcada como resuelta, hasta recargar (para que no salten las filas
    mientras se edita con el teclado).
    """

    id: str
    label: str
    condicion: object
    columnas: tuple[str, ...]
    edicion_en_linea: tuple[str, ...] = ()
    columna_en_linea: dict = field(default_factory=dict)
    por_defecto: object = None
    label_todas: str = ""
    ayuda: str = ""
    orden: int = 999


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
    # Se ejecuta ANTES de guardar, para completar o normalizar datos (así la
    # auditoría ya los registra): completar(datos, registro) -> datos.
    # registro es None en un alta; en una modificación, `datos` trae solo lo que
    # cambia (lo demás está en el registro).
    completar: object = None
    # Campos que identifican un registro fuera de la base (ej: en SharePoint),
    # donde los IDs no coinciden. Los usa la importación para actualizar en vez
    # de duplicar. Ej: ("nombre_sector",) o ("nombre_ubicacion", "sector_id").
    clave_natural: tuple[str, ...] = ()
    # Campos que se editan en la grilla (edición en línea, fase 13). Tienen que
    # estar en `listado` y ser datos propios: ni calculados, ni archivos, ni de
    # solo importación (dueño: el ERP). Lo valida el registry.
    edicion_en_linea: tuple[str, ...] = ()
    # Columna de la grilla en la que se edita cada campo, si no es la suya (ej:
    # el estado de seguimiento se edita sobre la columna «Estado», el visible).
    columna_en_linea: dict[str, str] = field(default_factory=dict)
    # Alta rápida (fase 13.3): última fila de la grilla, en la pestaña del padre
    # `alta_en_linea_padre` (la entidad padre; por defecto, el principal). Cada
    # celda es un CeldaAltaSpec; el alta va por servicio.crear, como el formulario.
    alta_en_linea: tuple[CeldaAltaSpec, ...] = ()
    alta_en_linea_padre: str | None = None
    # Subgrillas (fase 13.4): hijos que se despliegan debajo de cada fila de la
    # grilla de esta entidad (ej: los destinos, bajo cada línea de pedido). Cada
    # hijo tiene que tener edicion_en_linea. Al cambiar un hijo, la fila de esta
    # entidad se actualiza fuera de banda (cambian sus columnas calculadas).
    subgrillas: tuple[str, ...] = ()
    # «Pegar líneas» (fase 13.5): altas desde texto pegado, una por renglón, en la
    # pestaña del padre de la alta rápida (requiere alta_en_linea). Ver PegadoSpec.
    pegado_en_linea: PegadoSpec | None = None
    # Colas de «a revisar» (fase 13.6): listas editables de los registros que
    # cumplen una condición. Ver ColaSpec.
    colas: tuple[ColaSpec, ...] = ()

    # Reglas de edición según el registro (fase 13.2). Las aplica el servicio, así
    # que valen en la grilla, el formulario, la API y la importación CSV:
    #   editable_si   {campo: función(registro) -> True | False | texto}: si el
    #                 campo se puede cambiar en ese registro. False o un texto (el
    #                 porqué) = congelado. Solo se rechazan los cambios reales:
    #                 mandar el mismo valor no es un error.
    #   eliminable_si función(registro) -> True | False | texto: si se puede borrar.
    #   creable_si    función(datos) -> True | False | texto: si se puede crear
    #                 con esos datos (ej: un destino en una línea ya enviada, no).
    # El importador del histórico de pedidos las saltea (para esas líneas, la
    # fuente es el Excel): ver servicio(..., reglas_de_edicion=False).
    editable_si: dict = field(default_factory=dict)
    eliminable_si: object = None
    creable_si: object = None

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

    def cola(self, id: str) -> ColaSpec | None:
        return next((c for c in self.colas if c.id == id), None)

    @property
    def tiene_celdas(self) -> bool:
        """Si alguna grilla de la entidad edita celdas (la suya o la de una cola)."""
        return bool(self.edicion_en_linea) or any(c.edicion_en_linea for c in self.colas)

    @property
    def tabla(self) -> str:
        return self.model.__tablename__
