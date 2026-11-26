# Cómo agregar o modificar una entidad

Una **entidad** es una tabla que se gestiona desde la app (activos, sectores, estados…).
Para agregarla se escribe el **modelo**, se genera la **migración** y, si hace falta, un
**override** corto. Todo lo demás se genera solo:

- pantallas: listado con búsqueda y filtros, alta, detalle con pestañas, edición y baja;
- API REST (`/api/<entidad>`) con validación y su documentación OpenAPI (`/api/docs`);
- importación y exportación CSV (`flask importar` / `flask exportar`);
- historial de cambios (auditoría), si el modelo lo pide;
- entrada en el menú lateral, si el override lo pide.

Como ejemplo, se agrega **herramientas** con su catálogo de **estados**. El ejemplo se
probó tal cual está escrito acá.

---

## 1. Modelo (`app/models/<modulo>_models.py`)

Lo que describe el **dato** va en el modelo: tipo, obligatoriedad, largo, unicidad,
claves foráneas y etiquetas. Lo comparten la web, la API y la importación.

```python
import uuid
from datetime import datetime

from app.core.db import db
from app.crud.audit_mixin import AuditMixin
from app.crud.model_mixin import ModelMixin


class EstadoHerramienta(db.Model, ModelMixin):          # catálogo: sin auditoría
    __tablename__ = "estados_herramienta"
    __label_field__ = "nombre_estado"                    # cómo se muestra en un select

    estado_herramienta_id = db.Column(db.Integer, primary_key=True)
    nombre_estado = db.Column(db.String(50), nullable=False, unique=True, info={"label": "Nombre"})
    color_badge = db.Column(db.String(20), nullable=False)   # "color*" → selector de color


class Herramienta(db.Model, ModelMixin, AuditMixin):    # AuditMixin → pestaña Historial
    __tablename__ = "herramientas"
    __label_field__ = "nombre"

    herramienta_id = db.Column(db.Integer, primary_key=True)
    uuid = db.Column(db.String(36), default=lambda: str(uuid.uuid4()), unique=True, nullable=False)

    codigo = db.Column(db.String(30), nullable=False, unique=True, info={"label": "Código"})
    nombre = db.Column(db.String(100), nullable=False)
    observaciones = db.Column(db.String(300))            # String(300) o más → textarea

    sector_id = db.Column(db.Integer, db.ForeignKey("sectores.sector_id"), info={"label": "Sector"})
    sector = db.relationship("Sector")
    ubicacion_id = db.Column(db.Integer, db.ForeignKey("ubicaciones.ubicacion_id"), info={"label": "Ubicación"})
    ubicacion = db.relationship("Ubicacion")

    estado_herramienta_id = db.Column(
        db.Integer, db.ForeignKey("estados_herramienta.estado_herramienta_id"), nullable=False
    )
    estado = db.relationship("EstadoHerramienta")        # clase "Estado…" → badge de color

    foto = db.Column(db.String(300))                     # "foto*" → subida de imagen

    creado_en = db.Column(db.DateTime, default=datetime.utcnow)
    actualizado_en = db.Column(db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
```

### Qué se deduce del modelo

| En el modelo | En la app |
|---|---|
| `nullable=False` | campo obligatorio (web, API e importación) |
| `String(n)` | texto de hasta `n` caracteres; desde 300, área de texto |
| `Integer`, `Float` / `Date`, `DateTime` / `Boolean` | número / fecha / select Sí-No |
| `unique=True`, `db.UniqueConstraint(...)` | «Ya existe un registro con ese valor» |
| `info={"label": "Código"}` | etiqueta del campo (si no, se arma con el nombre: `nro_motor` → «Nro motor») |
| `ForeignKey` + `relationship` | select con los registros del destino |
| FK a una clase `Estado…` con `color_badge` | se muestra como badge de color |
| columna `foto*` / `archivo*` / `color*` | subida de imagen / de documento PDF / selector de color |
| `OrigenMixin` (columnas `origen` y `clave_origen`) | datos importados: las dos columnas son de solo importación y `clave_origen` es la clave natural por defecto |
| `__label_field__` | texto con el que el registro aparece en selects, listados e importación |
| `AuditMixin` (+ columna `uuid`) | cada cambio queda en el historial |
| `uuid`, `creado_en`, `actualizado_en`, columnas JSON | no se muestran en formularios |

**Selects dependientes (se infieren solos).** Si un campo apunta a una tabla que a su vez
apunta a otro campo de la entidad, quedan vinculados. En el ejemplo, `Ubicacion` tiene
`sector_id`, así que la ubicación se filtra por el sector elegido. Al elegir primero la
ubicación, el sector se completa solo, y al guardar se verifica que coincidan. Un campo
puede depender de varios: el modelo de un activo se filtra por la categoría y por la
marca, y al elegirlo se completan las dos.

**Valores por defecto.** El `default` de una columna (ej: `vigente = db.Column(db.Boolean,
nullable=False, default=True)`) aparece preseleccionado en el alta y, si el campo no es
obligatorio (`"required": False` en el override), se usa cuando no se envía (API, CSV).
Una FK obligatoria a un catálogo puede tener un valor por defecto **calculado** por
nombre, con `app/crud/por_defecto.py`: `default=id_por_nombre("estados_proveedor",
"estado_proveedor_id", "nombre_estado_proveedor", "Activo")` en la columna (también se
preselecciona en el alta), y en el override `"fields": {campo: {"required": False}}`
con `"completar": mantener_si_vacio(campo)`, para que una modificación que no lo trae
mantenga el valor. Ejemplos: estados de ubicación, proveedor y contacto.

**Campos calculados.** Un `column_property` del modelo (ej: `Material.stock_total`) se
muestra en listado, detalle y API, pero no se edita. Si el cálculo es más fácil en Python,
se escribe una propiedad y se declara en `__calculados__ = {"resumen": "Resumen"}` (ej:
`Pedido.resumen`): se ve en listado, detalle, API y exportación, pero no sirve de filtro.

**Búsqueda al importar.** Una FK se busca por la etiqueta del destino (`__label_field__`)
y, si el modelo declara `__buscar_por__` (ej: `Material`: código y descripción; `Activo`:
número y descripción), también
por esos atributos. Un texto que coincide con varios registros es ambiguo.
 Si trae una FK (ej:
`Activo.tipo_activo_id`, el tipo de la categoría), además funciona como filtro en el
formulario.

**Datos importados (`OrigenMixin`, `app/crud/origen_mixin.py`).** Toda tabla que recibe
histórico o reportes del ERP hereda `origen` (app / histórico / reporte / PDF) y
`clave_origen` (cómo se identifica en la fuente: archivo + hoja, sistema + número). Así
la importación es idempotente: repetirla actualiza en lugar de duplicar. Lo cargado en la
app queda con origen «app» y sin clave; una fila importada sin clave se rechaza.

### Qué pasa al borrar

La regla se declara en la relación del **hijo** (ver `app/crud/core/dependencias.py`):

| Quiero que… | En el hijo | Ejemplo |
|---|---|---|
| los hijos se borren con el padre | `backref=db.backref("hijos", cascade="all, delete")` | sector → ubicaciones |
| no se pueda borrar el padre si tiene hijos | relación **sin** `backref` (la FK lo impide) | estado → herramientas |
| idem, pero necesito el `backref` | `backref=db.backref("hijos", passive_deletes="all")` | ubicación → stock |

Un `backref` **sin** regla es un error silencioso: SQLAlchemy deja los hijos sin padre.
La pantalla de confirmación avisa qué se borra en cascada o qué impide la baja.

## 2. Migración

```bash
flask --app run db migrate -m "agrega herramientas"
```

Revisar el archivo generado en `migrations/versions/` y aplicarlo:

```bash
flask --app run db upgrade
```

En desarrollo (`AUTO_MIGRATE`), la app aplica las migraciones pendientes al primer acceso.
Para renombrar una columna sin perder datos, Alembic genera «borrar + agregar»: hay que
cambiarlo a mano por `batch_op.alter_column("vieja", new_column_name="nueva")`.

## 3. Override (`app/crud/meta/overrides/<modulo>.py`)

Lo que describe la **pantalla** va en el override. El registry descubre solo los
archivos de esta carpeta: no hay que registrarlos en ningún otro lado.

```python
from app.models.herramientas_models import EstadoHerramienta, Herramienta

OVERRIDES = {
    "herramientas": {                       # nombre de la entidad = URL (/herramientas)
        "model": Herramienta,
        "label_singular": "herramienta",
        "label_plural": "herramientas",
        "genero": "f",                      # «Nueva herramienta»
        "sidebar": True,                    # entrada en el menú
        "orden": 50,
        "clave_natural": ["codigo"],        # para importar sin duplicar
    },
    "estados_herramienta": {
        "model": EstadoHerramienta,
        "label_singular": "estado de herramienta",
        "label_plural": "estados de herramienta",
        "genero": "m",
        "sidebar": True,
        "grupo": "catalogos",               # sección «Catálogos» del menú
        "orden": 200,
        "clave_natural": ["nombre_estado"],
    },
}
```

Lo mínimo es `{"model": MiModelo}`. Claves disponibles:

| Clave | Para qué | Ejemplo en el proyecto |
|---|---|---|
| `label_singular`, `label_plural`, `genero` | textos de las pantallas | todas |
| `sidebar`, `orden` | entrada en el menú y su posición | `activos` |
| `grupo` | sección del menú: `"operativos"`, `"maestros"` (por defecto) o `"catalogos"` | `overrides/catalogos.py` |
| `listado`, `filtros` | columnas del listado y campos de búsqueda (por defecto, se eligen solas). De los `filtros`, las FK, las opciones fijas y los Sí/No son selects combinables en el panel «Filtros» del listado (`?campo=valor` en la URL); los demás, campos de la búsqueda de texto, que en una FK busca por el nombre de lo vinculado | `activos` |
| `padre` | subentidad: pestaña en el detalle del padre. Puede ser una lista de padres; `"label"` cambia el nombre de la pestaña en ese padre y `"visible"` (función del registro padre) la muestra solo en algunos | `ubicaciones`; `bom_activo` («BOM» en el activo, «Usado en activos» en el material) |
| `clave_natural` | campos que identifican el registro al importar | `["nombre_ubicacion", "sector_id"]` |
| `fields: {campo: {...}}` | cambiar lo inferido de un campo (ver abajo) | `lecturas_medidor.origen` |
| `excluir` | campos que no se exponen | — |
| `tabs_extra` | pestañas con una tabla de solo lectura calculada por una función `funcion(registro) → {"columnas", "filas"}` | — |
| `al_guardar` | función `(registro, operacion, cambiados)` que corre al crear o modificar, en la misma transacción (web, API e importación). Puede devolver un aviso para el usuario, o rechazar el cambio con `raise ErroresValidacion({campo: mensaje})` (no se guarda nada) | copia del BOM del modelo al activo, `overrides/bom.py`; reglas de los planes, `overrides/preventivos.py` |
| `acciones` | botones del detalle que ejecutan una función sobre el registro (`id`, `label`, `funcion`, `seccion`, `confirmar`, `visible`). Con `campos` (como los de `campos_alta`) el botón abre un formulario y la función recibe `(registro, datos)`; `en_fila` también lo muestra en la fila del listado y de la pestaña del padre; `ayuda` es el texto del formulario. La función devuelve un texto, una tupla `(categoría, texto)` o una lista de ellas | «Traer ítems del modelo» en `overrides/bom.py`; «Enviar a Compras» y «Anular o cancelar» en `overrides/pedidos.py` |
| `completar` | función `(datos, registro) -> datos` que corre **antes** de guardar (web, API e importación), para completar o normalizar datos; así la auditoría ya los registra. `registro` es `None` en un alta | sector y cuenta sugeridos del destino de un pedido, `overrides/pedidos.py` |
| `campos_alta` | campos que solo se piden al crear (no son columnas): `{campo: {label, tipo, required, options, fk_model}}`. Llegan a `al_guardar` en `registro.datos_alta` | cantidad y destino principal de una línea de pedido |
| `orden_campos` | primeros campos del formulario, en ese orden | la cantidad y el destino junto al material |
| `edicion_en_linea` | campos que se editan en la grilla (listado y pestaña del padre), sin abrir el formulario: guardan con el mismo servicio (`completar`, `al_guardar`, auditoría con el motivo «Edición en línea»). Tienen que estar en `listado`; el registry rechaza calculados, archivos, campos de alta, de solo importación (ERP) y el padre principal. Una FK con más de 15 registros se edita escribiendo (código, etiqueta o el comienzo) | material, descripción y nº de OC de las líneas de pedido. Un elemento `(campo, columna)` edita el campo sobre otra columna del listado (el estado de seguimiento, sobre «Estado»). En un campo `select`, `excluir_en_linea` quita opciones de la grilla («Anulado») |
| `editable_si` | `{campo: función(registro)}`: si el campo se puede cambiar en ese registro. Devuelve `True`, o `False` o un texto con el porqué. La aplica el servicio (grilla, formulario, API, CSV): solo rechaza cambios reales. La grilla muestra la celda en gris (y da 404) y el formulario, el campo deshabilitado | material y descripción congelados en una línea enviada a Compras |
| `alta_en_linea` | fila de alta al final de la grilla, en la pestaña del padre (`alta_en_linea_padre`; por defecto, el principal). Cada celda: `nombre`, `columnas` (consecutivas de la pestaña, para el colspan), `label`, `interprete` y `repetir` (lo escrito queda para la fila siguiente). Sin intérprete, la celda es el campo `nombre` (de la entidad o de alta). Intérpretes en `core/interpretes.py`: `Campo`, `FkOTexto` (un registro o, si no se reconoce, texto libre) y `FkEntre` (uno de varios registros relacionados). El alta va por `servicio.crear` con el motivo «Alta en línea» | líneas de pedido: material o descripción, cantidad y destino (activo o ubicación) |
| `eliminable_si` | `función(registro)`, igual que la anterior: si se puede eliminar. El servicio lo rechaza (409 en la API) y la web oculta «Eliminar» | una línea enviada no se elimina |
| `creable_si` | `función(datos)`: si se puede crear con esos datos | no se agregan destinos a una línea enviada |
| `auditoria`, `auditoria_ignorar` | activar o no el historial; campos que no se registran | — |

Dentro de `fields`, cada campo acepta, entre otras: `label`, `tipo` (`text`, `number`,
`textarea`, `date`, `select`, `fk`, `datalist`, `file`, `color`), `required`,
`options` (para `select`), `alias` (otros nombres de columna al importar),
`solo_lectura`, `oculto`, `depende_de` (`None` para desactivar un select dependiente
inferido, o un campo o una lista para limitarlo a esos), `fk_filtro` (función que
devuelve la condición que deben cumplir las opciones de una FK), `selector` (`"lista"`
o `"select"`: cómo se elige una FK o un `select`; por defecto, un campo con lista si hay
más de 15 opciones y un select si hay menos), `extensiones` (las de
un campo de archivo, ej: `[".pdf"]`: arman el `accept` del formulario y se verifican al
guardar), `numeracion` (ver abajo) y `solo_importacion` (dato cuyo dueño es el ERP: se ve
en la app, pero solo lo carga la importación; la web lo muestra deshabilitado y la API
lo rechaza con un mensaje). Ejemplos:

```python
"fields": {
    # select con opciones fijas
    "origen": {"tipo": "select", "options": [{"value": "manual", "label": "Manual"},
                                             {"value": "iot", "label": "IoT"}]},
    # texto libre con sugerencias tomadas de otra tabla
    "usuario_asignado": {"tipo": "datalist", "fk_model": Empleado, "fk_label": "nombre_completo"},
    # se muestra pero no se edita
    "fecha_actualizacion": {"solo_lectura": True},
    # solo las unidades que tienen tipo de medidor (filtra el select y se verifica al guardar)
    "unidad_medida_id": {"fk_filtro": lambda: UnidadMedida.tipo_medidor.isnot(None)},
}
```

**Numeración automática.** `"numeracion"` completa el campo al crear, si llega vacío
(web, API o importación), con el siguiente número de su serie. `{n}` es el número y
`{año}` reinicia la serie cada año:

```python
"numero": {"numeracion": "{n}"},                     # 1104, 1105... (serie continua)
"numero": {"numeracion": "TRA-{año}-{n:04d}"},       # TRA-2026-0001, TRA-2026-0002...
```

El campo deja de ser obligatorio en el formulario y en la API (se completa solo), y un
valor cargado a mano se respeta.
Con `"numeracion_por": "pedido_id"` la serie se cuenta dentro de cada pedido (ej: el
número de línea).

## 4. Probar

```bash
python -m pytest
```

- Si un override no cierra con el modelo (un campo mal escrito, un padre inexistente, una
  FK que no apunta al padre), **la app no arranca** y el error dice qué corregir, con una
  sugerencia («¿Quisiste decir 'sector_id'?»).
- `tests/test_migraciones.py` falla si se cambió un modelo sin generar la migración.
- Los tests genéricos ya verifican que el listado y el alta de cada entidad respondan
  (`tests/test_entidades_fase7.py`). Conviene agregar tests propios para las reglas de la
  entidad: qué se borra en cascada, qué bloquea, qué es único.

## 5. Cargar datos

Desde la app, o desde un CSV (separado por `,`, `;` o tabulación). Las FK se escriben
por nombre («Disponible»), no por ID:

```bash
flask --app run importar herramientas herramientas.csv --simular   # valida sin guardar
flask --app run importar herramientas herramientas.csv
flask --app run exportar herramientas herramientas.csv
```

Los números se escriben en formato argentino («1.234,5», «1.400»), como los exporta
Excel; también se acepta «1,5» o «1.5». La exportación usa coma decimal y no agrega
miles.

Si una fila tiene errores, se informan todos juntos y no se guarda nada.

---

## Resumen

1. Modelo en `app/models/`, con etiquetas en `info={"label": ...}` y las reglas de borrado.
2. `flask --app run db migrate -m "..."`, revisar y `flask --app run db upgrade`.
3. Override en `app/crud/meta/overrides/` (lo mínimo: `{"model": ...}`).
4. `python -m pytest`.
