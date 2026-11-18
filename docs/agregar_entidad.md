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
| columna `foto*` / `color*` | subida de imagen / selector de color |
| `__label_field__` | texto con el que el registro aparece en selects, listados e importación |
| `AuditMixin` (+ columna `uuid`) | cada cambio queda en el historial |
| `uuid`, `creado_en`, `actualizado_en`, columnas JSON | no se muestran en formularios |

**Selects dependientes (se infieren solos).** Si un campo apunta a una tabla que a su vez
apunta a otro campo de la entidad, quedan vinculados. En el ejemplo, `Ubicacion` tiene
`sector_id`, así que la ubicación se filtra por el sector elegido. Al elegir primero la
ubicación, el sector se completa solo, y al guardar se verifica que coincidan.

**Campos calculados.** Un `column_property` del modelo (ej: `Material.stock_total`) se
muestra en listado, detalle y API, pero no se edita. Si trae una FK (ej:
`Activo.tipo_activo_id`, el tipo de la categoría), además funciona como filtro en el
formulario.

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
| `listado`, `filtros` | columnas del listado y campos de búsqueda (por defecto, se eligen solas) | `activos` |
| `padre` | subentidad: pestaña en el detalle del padre. Puede ser una lista de padres | `ubicaciones`; `bom_modelo` (dos padres) |
| `clave_natural` | campos que identifican el registro al importar | `["nombre_ubicacion", "sector_id"]` |
| `fields: {campo: {...}}` | cambiar lo inferido de un campo (ver abajo) | `lecturas_medidor.origen` |
| `excluir` | campos que no se exponen | — |
| `tabs_extra` | pestañas con una tabla calculada por una función | «BOM final» en `overrides/bom.py` |
| `auditoria`, `auditoria_ignorar` | activar o no el historial; campos que no se registran | — |

Dentro de `fields`, cada campo acepta, entre otras: `label`, `tipo` (`text`, `number`,
`textarea`, `date`, `select`, `fk`, `datalist`, `file`, `color`), `required`,
`options` (para `select`), `alias` (otros nombres de columna al importar),
`solo_lectura`, `oculto` y `depende_de` (`None` para desactivar un select dependiente
inferido). Ejemplos:

```python
"fields": {
    # select con opciones fijas
    "origen": {"tipo": "select", "options": [{"value": "manual", "label": "Manual"},
                                             {"value": "iot", "label": "IoT"}]},
    # texto libre con sugerencias tomadas de otra tabla
    "usuario_asignado": {"tipo": "datalist", "fk_model": Empleado, "fk_label": "nombre_completo"},
    # se muestra pero no se edita
    "fecha_actualizacion": {"solo_lectura": True},
}
```

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

Si una fila tiene errores, se informan todos juntos y no se guarda nada.

---

## Resumen

1. Modelo en `app/models/`, con etiquetas en `info={"label": ...}` y las reglas de borrado.
2. `flask --app run db migrate -m "..."`, revisar y `flask --app run db upgrade`.
3. Override en `app/crud/meta/overrides/` (lo mínimo: `{"model": ...}`).
4. `python -m pytest`.
