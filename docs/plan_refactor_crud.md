# Plan: modularización del framework CRUD

Objetivo: reemplazar `app/crud/framework.py` (una sola clase que mezcla rutas, consultas,
formularios, archivos, auditoría y navegación) por un framework modular que genere
**automáticamente** la interfaz web y la API a partir de los modelos.

```
Modelos SQLAlchemy ──► introspección ──┐
                                       ├──► Metamodelo final ──┬──► Rutas web (Flask + Jinja2)
Overrides (solo lo no inferible) ──────┘                       └──► API REST (validada con JSON Schema)
```

## Decisiones tomadas

| Tema | Decisión |
|---|---|
| Base de datos | **SQLite**. Se quita el respaldo automático MariaDB → SQLite y el comando `sync-db`. El código se mantiene portable (sin SQL específico de SQLite) por si más adelante se usa MariaDB. |
| API | Sin autenticación por ahora. La consumirán Power Apps y otras apps web. Por eso: contrato REST estable, errores JSON uniformes, paginación, CORS configurable y una **especificación OpenAPI** (los conectores personalizados de Power Apps se crean a partir de ella). La autenticación se diseña como un punto de extensión para agregarla después sin rehacer nada. |
| Entidades piloto | **Sectores, ubicaciones y cuentas**. El resto sigue con el framework actual hasta revisar su diseño, y después se migra. |
| Forma de trabajo | Una rama y un *pull request* por fase; cada fase deja la app funcionando y con los tests en verde. |

## Diagnóstico (noviembre 2026)

Errores confirmados ejecutando la app:

1. No se pueden guardar fechas: el formulario envía texto y SQLite exige `date`/`datetime`
   (crear una lectura de medidor da 500).
2. No se pueden guardar booleanos: llega `"False"` como texto (crear un BOM da 500).
3. Las subentidades (ubicaciones, lecturas, stock, modelos, contactos, medidores) dan 500 si
   se abre su listado o formulario sin el ID del padre; su listado propio falla siempre
   (`'sub' is undefined` en la plantilla).
4. `/bom_modelo` falla siempre: el metamodelo dice `bp_name: "modelos"` y se registra en el
   blueprint `activos`.
5. `/recursos` da 404: la entidad existe pero nunca se registra.
6. La API de sectores no puede crear ni actualizar: su decorador de auditoría no completa
   `RegistroUUID` (columna `NOT NULL`).

Encontrados leyendo el código:

- El detalle de una subentidad arma el enlace al padre con el blueprint propio en vez del
  del padre.
- `editar` recorre todos los campos (incluidos `virtual`/`oculto`): lo que no viene en el
  formulario queda en `None`.
- `sync-db` compara `updated_at`, pero los modelos usan `actualizado_en` (se elimina).
- `routes/api/activos_routes.py` importa una función inexistente y no está registrado.
- No hay validación en el servidor (`required` solo en el HTML) y un `IntegrityError` da 500.
- Rendimiento: cada pantalla carga tablas FK completas, `listar` ejecuta la consulta dos
  veces y las relaciones se resuelven una por fila (N+1).
- Seguridad: subida de archivos sin lista de extensiones y con ruta relativa al directorio
  actual; sin CSRF; `SECRET_KEY` con valor por defecto.
- La base se crea con `create_all()` en `before_request`; `flask-migrate` está instalado
  pero no se usa.

Diseño:

- `fk_data` copiado 3 veces, labels de entidad 5 veces, subida de archivos 2 veces.
- La navegación depende de `bp_name` escritos a mano (origen de los errores 3 y 4).
- Un archivo `routes/web/*_web.py` por módulo solo para instanciar `CRUDResource`.
- La auditoría usa el nombre de la entidad como nombre de tabla (hoy coinciden de casualidad).

## Notas de la Fase 2

- **Claves foráneas en SQLite activadas** (`PRAGMA foreign_keys=ON` en `app/core/db.py`):
  la base rechaza referencias a registros inexistentes y borrados de registros en uso,
  igual que lo haría MariaDB.
- **Qué pasa con los registros relacionados al borrar** (`app/crud/core/dependencias.py`).
  La regla se declara en el modelo, en la relación del hijo, y la pantalla de
  confirmación avisa antes de borrar:
  - *Cascada*: `backref=db.backref("hijos", cascade="all, delete")`. Los hijos se
    borran con el padre y cada uno queda en la auditoría.
  - *Bloqueo*: si otros registros apuntan al que se borra (o a sus hijos en cascada),
    no se borra nada y se informa cuántos y de qué tipo.
  - Por defecto SQLAlchemy *desvincula en silencio* (pone la FK en `NULL`) cuando
    existe un `backref` sin reglas: evitarlo con `passive_deletes="all"`.

  | Relación | Regla | Decidido |
  |---|---|---|
  | Sector → ubicaciones | Cascada | ✅ |
  | Sector / ubicación → activos, empleados, stock | Bloqueo | ✅ (Fase 7) |
  | Resto de las entidades | — | Ver «Notas de la Fase 7» |

- Al reemplazar un archivo subido, el anterior queda en disco (pendiente de definir).

## Notas de la Fase 3

- Todas las entidades migradas comparten el blueprint `crud`; las URLs no cambiaron
  (`/sectores`, `/ubicaciones/crear?sector_id=3`, ...).
- Las subentidades funcionan en dos contextos: desde la pestaña del padre (al guardar
  se vuelve a esa pestaña) o por su cuenta (`/ubicaciones` lista todas, con el padre
  como columna y filtro).
- El detalle de una subentidad ahora también muestra su historial de auditoría.
- Los valores vacíos se muestran como "—" (filtro `mostrar`).
- Las subentidades no migradas (medidores, lecturas, stock, modelos, contactos) siguen
  dando error 500 si se abren sin el padre; se corrige al migrarlas.
- Código sin uso para borrar en la Fase 8: `app/templates/sectores/`,
  `app/services/sectores_service.py`, `app/routes/api/cuentas_routes.py`.

## Notas de la Fase 4

- `GET /api/<entidad>` sigue devolviendo un array JSON simple (compatible con
  `src/sync`); la paginación es opcional y el total va en `X-Total-Count`.
- Validación en dos pasos: JSON Schema (forma y tipos, mensajes por campo) y luego la
  misma conversión y verificación de FKs que usa la web.
- Códigos: 400 datos inválidos (incluye FK inexistente), 404, 405, 409 duplicado o
  registro en uso.
- **`src/sync` necesita ajustes** (no se tocó): `config.py` apunta a `/sectores` (la página
  web) en lugar de `/api/sectores`, y `sync_engine.py` envía `estado_sector`, que no existe
  (debe ser `estado_sector_id`).
- Código sin uso para borrar en la Fase 8: `app/utils/auditoria_decorator.py` y
  `validar_sector` en `app/utils/json_validator.py`.

## Notas de la Fase 5

- **Migraciones**: el esquema está en `migrations/versions/` (Flask-Migrate / Alembic). La
  primera migración (`esquema inicial`) crea las 30 tablas de los modelos.
- Las restricciones (FK, únicos) tienen nombres predecibles (`CONVENCION_NOMBRES` en
  `app/core/db.py`); sin eso, SQLite no permite modificarlas en migraciones futuras.
- **Desarrollo** (`AUTO_MIGRATE`): el primer acceso aplica migraciones pendientes y carga
  catálogos. **Producción**: `flask db upgrade` como paso del despliegue.
- Una base creada antes de las migraciones (con `create_all`) se adopta sola si su esquema
  coincide con los modelos; si no, la app avisa y sugiere `flask reset-db`.
- La base por defecto pasó de `instance/fallback.db` a `instance/mantenimiento.db`.
- Se quitaron el respaldo MariaDB → SQLite, `sync-db` y `create-db` (lo reemplaza
  `flask db upgrade`).
- Tests: config `testing` (base en memoria). Un test verifica que las migraciones generen
  exactamente el esquema de los modelos (avisa si falta una migración).

## Carga de datos (Fase 6)

Hecho:

- `flask importar <entidad> archivo.csv [--simular]` y `flask exportar <entidad> archivo.csv`
  (`app/crud/intercambio/csv_entidades.py`). Usan el mismo servicio que la web y la API:
  validación, auditoría (usuario «importación», motivo = nombre del archivo) y reglas de
  integridad.
- **Clave natural** por entidad (`clave_natural` en el override): `nombre_sector`;
  `nombre_ubicacion` + `sector_id`; `numero_cuenta` (único en la base, tercera migración). Reimportar actualiza en lugar de
  duplicar, y las filas sin cambios no se tocan (el historial no se ensucia).
- Ubicaciones: restricción única (nombre, sector) en la base (segunda migración).
- **FK por nombre** en el CSV («Activo», «Taller»); por ID solo con la columna `*_id`.
- **Alias de columnas** por campo (`"fields": {"nombre_sector": {"alias": ["name"]}}`)
  para los nombres de columna de SharePoint.
- **Todo o nada**: se informan todos los errores con su fila y no se guarda nada.
- Lee CSV con `,` `;` o tabulación, en UTF-8 (con o sin BOM) o Windows-1252.

Decisiones del usuario:

- Columna identificadora en SharePoint: en general `name` (único en sectores y activos;
  en ubicaciones, nombre + sector). Declarar `alias: ["name"]` cuando se conozcan los
  nombres reales de las columnas.
- Catálogos: estados, motivos y tipos de cambio de auditoría siguen en `seed.py`; tipos y
  categorías de materiales vienen de SharePoint (se importan cuando esas entidades pasen
  al registry, Fase 7).
- Interés en **mantener sincronizadas** la base local y SharePoint, como respaldo mutuo.
  Leer SharePoint directo queda como última fase (9).

**Dirección de la sincronización (Fase 9): decidida la opción A.** La app es la fuente de
verdad, donde se gestionan los datos; SharePoint es una copia para mostrar, que se
actualiza exportando desde la app. El respaldo se completa con copias periódicas del
archivo de la base.

| Opción | Cómo funciona | Riesgo |
|---|---|---|
| A. La app es la fuente; SharePoint es una copia | Se carga y edita en la app; se exporta periódicamente a SharePoint | Bajo. SharePoint queda de solo lectura |
| B. SharePoint es la fuente; la app es una copia | Se edita en SharePoint; se importa periódicamente | Bajo, pero la app no se usaría para cargar |
| C. Bidireccional | Se edita en ambos lados y se concilian los cambios | Alto: conflictos (mismo registro editado en los dos lados), bajas que hay que propagar, renombres que cambian la clave natural |

Se eligió **A** (noviembre 2026): «SharePoint es más para mostrar que para gestionar».

## Notas de la Fase 7

Todas las entidades están en el registry (18). Ya no queda ninguna pantalla en
`framework.py` ni en `app/routes/web/*_web.py` (salvo inicio y motivos); el menú lateral
sale del registry.

Decisiones del usuario (noviembre 2026):

- **Stock**: sin sector (es el de la ubicación) y una sola fila por insumo + ubicación.
  La migración suma las filas repetidas.
- **Medidores**: el valor actual se calcula de la lectura más reciente (o el valor
  inicial si no hay lecturas); ya no se edita.
- **Usuario asignado** del activo: texto libre, con los empleados como sugerencias.
- **Borrar un activo**: su BOM se borra en cascada; si tiene medidores, no se borra (para
  retirarlo se usa el estado «Baja»).

Reglas de borrado (decididas en esta fase, a confirmar con el uso):

| Relación | Regla |
|---|---|
| Activo → BOM del activo | Cascada |
| Activo → medidores; medidor → lecturas | Bloqueo (las lecturas son historial) |
| Marca → modelos → BOM del modelo | Cascada (bloquea si un modelo está en un activo) |
| Categoría de insumo → tipos | Cascada (bloquea si un tipo está en uso) |
| Proveedor → contactos | Cascada |
| Insumo con stock o en algún BOM | Bloqueo |
| Marca, categoría, tipo, unidad o sector en uso | Bloqueo (antes algunos dejaban el dato vacío en silencio) |

Framework (lo nuevo que se puede usar en cualquier entidad):

- **Calculados**: un `column_property` del modelo (ej: `Insumo.stock_total`,
  `Medidor.valor_actual`) aparece solo como campo de solo lectura: listado, detalle y
  API, pero no en el formulario, la entrada de la API ni la importación. También se
  puede marcar una columna con `{"solo_lectura": True}` (ej: fecha de actualización del stock).
- **Varios padres**: `"padre": [{...}, {...}]`. El BOM de un modelo se carga desde el
  modelo y se ve también en el insumo; el padre activo sale de la URL.
- **Pestañas calculadas**: `tabs_extra` con una función que arma una tabla. Reemplazan a
  las rutas especiales: «BOM del modelo» y «BOM final» en el activo, «Compatibilidad
  final» en el insumo (`app/crud/meta/overrides/bom.py`).
- **Sugerencias**: `"tipo": "datalist"` con `fk_model` (texto libre con lista de ayuda).
- `recursos` no tiene pantallas: es la base común de empleados y proveedores.
- Nuevos catálogos editables (e importables desde SharePoint): categorías y tipos de insumo.
- Modelos: nombre único dentro de la marca. BOM: «es equivalencia» obligatorio.
- Migraciones en SQLite: ahora desactivan las claves foráneas mientras recrean tablas y
  verifican al final que no quede ninguna referencia rota (antes una migración que
  tocara una tabla referenciada, como `modelos`, fallaba con datos).

**Nuevo diseño de activos** (decidido por el usuario):

| Campo | Notas |
|---|---|
| `numero_activo` | Identifica al activo: obligatorio, único y clave natural. Era `patente` |
| `descripcion`, `observaciones`, `año` | `observaciones` era `observacion` |
| `categoria_activo_id` | El tipo de activo es el de la categoría (se quitó `tipo_activo_id`) |
| `marca_id`, `modelo_id` | El modelo debe ser de la marca; si falta la marca, se completa |
| `numero_serie`, `numero_motor` | Únicos cuando están cargados. Eran `nro_serie_chasis` y `nro_motor` |
| `sector_id`, `ubicacion_id` | La ubicación debe ser del sector; si falta el sector, se completa |
| `usuario_asignado` | Texto libre con los empleados como sugerencias |
| `codigo_carga_gasoil` | Era `codigo_brescia` |
| `estado_activo_id`, `foto_path`, `detalles_tecnicos` | Sin cambios |

La migración renombra sin perder datos; los activos sin patente reciben `ACT-<id>`. Si
hay números de activo, serie o motor repetidos, se detiene y los lista.

**Selects dependientes** (genérico, `FieldSpec.depende_de`). Se infieren del modelo: si
un campo apunta a un modelo que a su vez apunta a otro campo de la entidad, quedan
vinculados (modelo → marca, ubicación → sector, tipo de insumo → categoría). Se guarda
también el «padre» porque puede existir sin el hijo (marca sin modelo conocido, sector
sin ubicación precisa). Entonces:

- en el formulario, el hijo muestra solo las opciones del padre elegido; sin padre,
  muestra todas con el padre entre paréntesis («Galpón 1 (Taller)») y al elegir una se
  completa el padre;
- al guardar (web, API o importación) se verifica que coincidan, o se completa el padre;
- un override `{"depende_de": None}` lo desactiva.

**SharePoint** será un reflejo de la base: las columnas se definen acá, no hace falta
mapear nombres de SharePoint.

Pendientes:

- Claves naturales provisorias: empleados (apellido + nombre), proveedores (razón social),
  unidades (nombre).
- `app/schemas/activos/` (detalles técnicos por tipo de activo, columna JSON): la columna
  se conserva; falta decidir cómo se cargan (Fase 8 o una fase propia).

## Notas de la Fase 8

- Se borró el framework viejo (`framework.py`, metamodelos escritos a mano, modo sombra,
  `ENTIDADES`, `to_legacy()`) y el código sin uso listado en las fases anteriores. El
  registry está en `app/crud/entidades.py`.
- **Insumos → Materiales** (pedido del usuario): modelos (`Material`, `CategoriaMaterial`,
  `TipoMaterial`, `StockMaterial`), tablas, columnas (`material_id`,
  `reemplaza_material_modelo_id` en el BOM), URLs (`/materiales`, `/api/materiales`...) y textos.
- **Migraciones unificadas** en una sola («esquema inicial»): el proyecto todavía no tiene
  datos reales. Una base local anterior avisa que hay que recrearla: `flask reset-db`.
- Los archivos subidos (`app/static/uploads/`) ya no se versionan en git.
- Se borró **`src/sync`** (carga desde planillas Excel): los datos se cargan en la app o
  con `flask importar`.
- **Pedidos** (modelo, servicio y rutas sin registrar) queda para una fase posterior.

## Menú: datos maestros y catálogos

El menú lateral tiene dos secciones (`"grupo"` en el override; ver `GRUPOS` en
`app/crud/meta/spec.py`):

- **Datos maestros** (por defecto): activos, materiales, empleados, proveedores,
  sectores, cuentas, marcas.
- **Catálogos** (plegable): estados de activo, sector, cuenta y recurso; tipos de activo
  (con sus categorías); categorías de material (con sus tipos); unidades de medida; tipos
  de unidad; motivos de operación. Antes la mayoría solo se cargaba desde `seed.py`; ahora
  se editan desde la app (un valor en uso no se puede borrar). No se auditan.

Widget `color` (inferido para columnas `color*`): selector de color en el formulario y
muestra en listados. Los campos `select` se muestran con su texto (Sí/No, Alta...).

## Próximo: órdenes de trabajo (OT)

Idea inicial (a diseñar): cada OT tiene una o más **operaciones**; a cada operación se
le asignan **recursos** (empleados o proveedores, vía la tabla común `recursos`) y
**materiales**.

## Arquitectura objetivo

```
app/crud/
├── meta/
│   ├── spec.py          # EntitySpec / FieldSpec: dataclasses tipadas en lugar de dicts
│   ├── introspect.py    # modelo → FieldSpec (ya existe)
│   ├── overrides/       # un archivo por entidad, solo con lo no inferible
│   └── registry.py      # inferido + overrides = EntitySpec, validado al arrancar
├── core/                # sin Flask: reutilizable desde web, API y CLI
│   ├── coercion.py      # texto del formulario → tipos Python ("" → None, fechas, booleanos…)
│   ├── fk.py            # opciones y labels de FK, en un solo lugar
│   ├── repository.py    # consultas, búsqueda, filtros, paginación, eager loading
│   ├── service.py       # alta/modificación/baja en una transacción + auditoría + hooks
│   └── files.py         # almacenamiento de archivos
├── schema/
│   └── jsonschema.py    # EntitySpec → JSON Schema (alta / modificación) + validación
├── web/
│   ├── views.py         # listar / crear / editar / eliminar / detalle genéricos
│   ├── navigation.py    # padre/hijo resuelto por el registry, no por bp_name
│   └── register.py      # register_web(app, registry)
└── api/
    ├── views.py         # GET lista/uno, POST, PUT, PATCH, DELETE → JSON
    ├── openapi.py       # especificación OpenAPI generada desde el registry
    └── register.py
```

Principio central: **web y API comparten el mismo servicio y el mismo JSON Schema**. El
formulario web se convierte a un dict tipado, se valida con el schema de la API y recién
entonces se guarda. Las reglas se escriben una sola vez.

La API generada usa `GET/POST {url}` y `PUT/PATCH/DELETE {url}/{id}`.

## Fases

| Fase | Contenido | Estado |
|---|---|---|
| **0. Red de seguridad** | Tests con pytest para sectores, ubicaciones y cuentas (web y API). Errores conocidos marcados como `xfail`. README. `.gitignore` permite `requirements*.txt`. | ✅ Hecha |
| **1. Metamodelo tipado** | `EntitySpec`/`FieldSpec`, registry (inferido + overrides) y un adaptador para que los dicts actuales sigan funcionando. Overrides de las 3 entidades piloto. `shadow_diff` pasa a ser validación al arrancar. | ✅ Hecha |
| **2. Capa core** | Coerción, FK, repositorio, servicio (transacción + auditoría) y archivos. `framework.py` delega en ellos. Validación en servidor y manejo de `IntegrityError`. | ✅ Hecha |
| **3. Web generada** | Vistas genéricas y navegación por registry (`app/crud/web/views.py`). Se eliminan `sectores_web.py` y `cuentas_web.py`. Las rutas especiales (`bom_final`, `compatibilidad_final`) se resuelven al migrar activos e insumos (Fase 7). | ✅ Hecha |
| **4. API generada** | Generador de JSON Schema, endpoints REST genéricos con paginación y errores JSON, especificación OpenAPI (3.0 y 2.0 para Power Apps) y página `/api/docs`. Reemplaza `sectores_routes.py`; se elimina `activos_routes.py`. | ✅ Hecha |
| **5. Base de datos** | Quitar el respaldo automático y `sync-db`. Flask-Migrate (Alembic) y fuera `create_all` de `before_request`. Configuración por `.env`. Comandos de consola a `app/cli.py`. | ✅ Hecha |
| **6. Carga de datos** | `flask importar` / `flask exportar` en CSV, con clave natural, FK por nombre, simulación y todo o nada. Ver «Carga de datos» más abajo. | ✅ Hecha |
| **7. Migrar el resto** | Tras revisar su diseño: activos, medidores, lecturas, insumos, stock, unidades, marcas, modelos, recursos, BOM. Ver «Notas de la Fase 7». | ✅ Hecha |
| **8. Limpieza** | Borrar los metamodelos viejos y `framework.py`, los `.txt` duplicados y el código sin uso listado en las notas. Ver «Notas de la Fase 8». | ✅ Hecha |
| **9. Sincronización con SharePoint** | Opción A: exportar periódicamente de la app a SharePoint, más copias de seguridad automáticas de la base. Al final, escribir en SharePoint directo (Microsoft Graph) en lugar de pasar por CSV. | Pendiente |

## Cómo agregar o modificar una entidad (desde la Fase 1)

1. **Modelo** (`app/models/`): columnas, obligatoriedad (`nullable`), largo, FKs,
   relaciones y etiquetas de los campos con `info={"label": "..."}`.
2. **Override** (`app/crud/meta/overrides/<modulo>.py`): solo lo que no se deduce del
   modelo. Lo mínimo es `{"model": MiModelo}`; las claves posibles están documentadas en
   `app/crud/meta/overrides/__init__.py`.
3. Nada más: las pantallas (listado, alta, detalle, edición y baja) se generan solas.

Si algo no cierra (un campo mal escrito, un padre inexistente, una FK que no apunta al
padre), la app **no arranca** y el error dice qué corregir, con una sugerencia.

## Cómo verificar cada fase

```bash
python -m pytest                     # todos los tests en verde (los xfail cuentan como esperados)
```

La coherencia entre overrides y modelos la valida el registry al arrancar (la app no
arranca si algo no cierra).

Al corregir un error conocido, su test `xfail` empieza a pasar y pytest lo informa como
falla (`xfail_strict = true`): en ese momento se quita la marca.
