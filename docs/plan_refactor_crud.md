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
- **Números en formato argentino** (25/11), solo en las columnas numéricas que no son FK:
  «1.234,5» → 1234,5 y «1.400» (puntos en grupos de tres) → 1400; «1,5» y «1.5» siguen
  siendo decimales. Lo ambiguo o en formato inglés («1,234.5») se rechaza con un error.
  Ver `numero_csv` en `app/crud/core/coercion.py`. Los formularios web y la API no
  cambian (mandan punto decimal). La exportación escribe los decimales con coma y sin
  miles, así que exportar y reimportar conserva los valores.

Decisiones del usuario:

- Columna identificadora en SharePoint: en general `name` (único en sectores y activos;
  en ubicaciones, nombre + sector). Declarar `alias: ["name"]` cuando se conozcan los
  nombres reales de las columnas.
- Catálogos: estados, motivos y tipos de cambio de auditoría siguen en `seed.py`; tipos y
  categorías de materiales vienen de SharePoint (se importan cuando esas entidades pasen
  al registry, Fase 7).
- Interés en **mantener sincronizadas** la base local y SharePoint, como respaldo mutuo.
  Leer SharePoint directo queda como última fase (15; era la 13 hasta el 26/11).

**Dirección de la sincronización (Fase 15): decidida la opción A.** La app es la fuente de
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
- **Pestañas calculadas**: `tabs_extra` con una función que arma una tabla. Reemplazaron
  a las rutas especiales del BOM; desde el rediseño del BOM (ver «BOM: plantilla del
  modelo y copia en el activo») no las usa ninguna entidad.
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

**Tipo de activo**: no se guarda en el activo; se calcula de la categoría (un
`column_property` que trae una FK se infiere como FK de solo lectura). En el formulario
aparece como **filtro** de las categorías (sin `name`, no se envía); si se elige primero
la categoría, el tipo se completa. Se ve en listado, detalle, filtros y API.

**Cuenta de imputación**: cada tipo de activo tiene una cuenta (`tipos_activo.cuenta_id`,
obligatoria). Los tipos y categorías de activo **ya no se precargan**: los carga el
usuario, cada tipo con su cuenta. Los tipos aparecen como pestaña de la cuenta, y una
cuenta en uso no se borra.

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

## BOM: plantilla del modelo y copia en el activo

Decidido por el usuario (noviembre 2026), en reemplazo del BOM «final» calculado:

- El **BOM del modelo** es la **plantilla** (se carga desde el modelo).
- Al **crear un activo** con modelo, se **copia** la plantilla a su BOM, que después se
  edita libremente. En el detalle del activo hay una sola pestaña: «BOM».
- Si el activo se crea sin modelo y se le **asigna o cambia** después: se copia solo si su
  BOM está vacío; si ya tiene ítems, no se toca y se avisa.
- Cambiar la plantilla **no** modifica los activos existentes. La acción **«Traer ítems
  del modelo»** (en la pestaña BOM del activo) agrega los materiales que falten, sin tocar
  los editados.
- Solo hay plantilla por modelo (no por marca). Cada material figura una sola vez por
  activo y por modelo. Se quitó «reemplaza al material del modelo».
- En el material, las pestañas «Usado en modelos» y «Usado en activos» reemplazan a
  «Compatibilidad final».
- Cada ítem copiado queda en la auditoría con el motivo («Copia del BOM del modelo …»).

Framework: `al_guardar` (función del override que corre al guardar, en la misma
transacción, desde web, API e importación), `acciones` (botones del detalle), `"label"`
en `padre` (nombre de la pestaña según el padre) y mensajes en pantalla (flash).
`app.crud.entidades.servicio()` arma el servicio de una entidad en un solo lugar.

## Menú: datos maestros y catálogos

El menú lateral tiene secciones (`"grupo"` en el override; ver `GRUPOS` en
`app/crud/meta/spec.py`). **Operaciones** (`"operativos"`) ya está declarada para las
fases 10 a 12; no se muestra mientras no tenga entidades.

- **Datos maestros** (por defecto): activos, materiales, empleados, proveedores,
  sectores, cuentas, marcas.
- **Catálogos** (plegable): estados de activo, sector, ubicación, cuenta, recurso
  (empleados), proveedor y contacto; tipos de activo
  (con sus categorías); categorías de material (con sus tipos); unidades de medida; tipos
  de unidad; motivos de operación. Antes la mayoría solo se cargaba desde `seed.py`; ahora
  se editan desde la app (un valor en uso no se puede borrar). No se auditan.

Widget `color` (inferido para columnas `color*`): selector de color en el formulario y
muestra en listados. Los campos `select` se muestran con su texto (Sí/No, Alta...).

## Fase 9: planes preventivos

Diseño acordado con el usuario (noviembre 2026). Son datos maestros: definen **qué** se
hace y **cada cuánto**; **cuándo** le toca a cada activo se calcula en la fase de OT.

Ejemplo: las palas tienen un plan parcial cada 300 h (aceite de motor y filtros de
aceite, aire y combustible) y uno completo cada 1200 h, que **incluye** al parcial y le
agrega el aceite y los filtros hidráulicos. En los tractores, 350 h y 1400 h. Cuando
coinciden (cada 4 ejecuciones), se hace solo el completo.

```
categorias_activo
 └── planes_preventivos ─── incluye a ──► plan_preventivo (inferior)
      ├── plan_preventivo_tareas ──► tareas_preventivo (catálogo)
      └── planes_modelo ──► modelos
           └── plan_modelo_materiales ──► materiales (y la tarea que lo usa)
```

| Entidad | Campos | Borrado | Menú / pestañas |
|---|---|---|---|
| `planes_preventivos` | `nombre_plan` (único, clave natural), `categoria_activo_id`, `periodo_uso` + `unidad_uso_id` (unidad de un medidor: h, km), `periodo_tiempo` + `unidad_tiempo_id` (tipo Tiempo: días, meses, años), `plan_inferior_id` «Incluye a» (opcional), `ciclo` (calculado), `vigente` | Cascada con la categoría; no se borra si otro plan lo incluye | Datos maestros; pestaña en la categoría de activo |
| `tareas_preventivo` | `nombre_tarea` (único, clave natural), `descripcion`, `horas_estimadas` | No se borra si un plan la usa | Catálogos |
| `plan_preventivo_tareas` | plan, tarea, `paso`; único y clave natural (plan, tarea) | Cascada con el plan | «Tareas» en el plan; «Usada en planes» en la tarea |
| `planes_modelo` | plan, modelo, marca (calculada), `vigente`; único y clave natural (plan, modelo); se muestra «Parcial palas — JD 6110» | Cascada con el plan y con el modelo | «Modelos» en el plan; «Planes preventivos» en el modelo |
| `plan_modelo_materiales` | plan del modelo, material, tarea (opcional), `cantidad`; unidad calculada del material; único y clave natural (plan del modelo, material) | Cascada con el plan del modelo; un material en uso no se borra | «Materiales» en el plan del modelo; «Usado en planes» en el material |

Reglas:

- **Período, no frecuencia**: se guarda cada cuánto (300 h), no cuántas veces.
- **Lo que ocurra primero**: el plan tiene un período por uso, uno por tiempo o los dos
  (vehículos: 10.000 km o 1 año). Cada período va con su unidad; al menos uno es obligatorio.
- **Incluye a**: el plan superior es de la misma categoría, con las mismas unidades, y sus
  períodos son múltiplos de los del inferior con el mismo factor, que es el **ciclo**
  (1200 / 300 = 4). Un plan es incluido por un solo superior; se pueden encadenar niveles.
- **Herencia**: las tareas y los materiales del superior son los del inferior más los
  propios. Cada plan carga solo lo que agrega; una tarea o un material no puede figurar en
  dos planes de la misma cadena. Pestañas calculadas «Todas las tareas» y «Todos los
  materiales» muestran la lista completa (primero lo heredado).
- **Período por categoría**: es el mismo para todos los modelos de la categoría (lo
  definen los mecánicos); el plan del modelo solo agrega los materiales.
- El modelo de un plan del modelo debe ser de la categoría del plan; la tarea de un
  material debe estar en el plan (propia o heredada).

Cambios en entidades existentes (decididos por el usuario):

- **Modelo → categoría de activo** (`modelos.categoria_activo_id`, **obligatoria**). El
  plan del modelo une un plan (que sabe su categoría) con un modelo: sin la categoría en el
  modelo no se podría verificar que coincidan. En el activo, el modelo debe ser de su
  categoría (si falta la categoría, se completa desde el modelo). Cambiar la categoría de
  un modelo que tiene activos o planes de la anterior se rechaza.
- **Tipo de medidor**: columna de texto `unidades_medida.tipo_medidor` (opcional; horas →
  «Horómetro», km → «Odómetro», litros → «Caudalímetro», arranques → «Contador de
  arranques»), con sugerencias: los habituales y los ya cargados. El medidor lo muestra
  como campo calculado desde su unidad. Solo las unidades con tipo de medidor se ofrecen
  en el medidor y en el período por uso del plan; el período por tiempo ofrece las de tipo
  «Tiempo».

## Notas de la Fase 9

- Modelos en `app/models/preventivos_models.py`; reglas, pestañas calculadas y overrides
  en `app/crud/meta/overrides/preventivos.py`; tests en `tests/test_preventivos.py`.
- Menú: «Planes preventivos» en datos maestros, «Tareas de preventivo» en catálogos. El
  plan del modelo y las tareas del plan son pestañas (del plan, del modelo, de la tarea y
  del material).
- Las reglas corren en `al_guardar` (web, API e importación) y rechazan el cambio con el
  campo y el motivo: períodos, inclusión (misma categoría y unidades, múltiplos, sin
  círculos), tareas o materiales repetidos en la cadena, categoría del modelo, tarea del
  material. Cambiar el período del inferior también se verifica contra su superior.
- **Migración**: la categoría de los modelos existentes se toma de sus activos (si son
  todos de una categoría). Si queda alguno sin categoría, se detiene antes de tocar la base
  y los lista.

Framework (lo nuevo que se puede usar en cualquier entidad):

- **Selects dependientes con varios padres**: `FieldSpec.depende_de` es una tupla. El
  modelo del activo depende de la categoría y de la marca; el formulario filtra con todos
  los elegidos y completa los vacíos al elegir el hijo. Antes, con dos candidatos no se
  infería ninguno. En el override, `"depende_de"` acepta un campo, una lista o `None`.
- **Opciones restringidas** (`fk_filtro` en el campo): una función que devuelve la
  condición que deben cumplir las opciones de una FK (ej: unidades con tipo de medidor).
  Filtra el select y se verifica al guardar.
- **Valores por defecto**: un campo no obligatorio que no se envía toma el `default` de
  su columna (ej: «Vigente» = Sí), y el formulario de alta lo muestra preseleccionado.

Para la fase de OT: el aviso de service compara el medidor del activo de la misma unidad
con la última ejecución del plan, y la fecha estimada se proyecta con la tasa de uso
diario (como en `ml/scripts/horas_gasoil.py`). Con «lo que ocurra primero», qué nivel
toca se decide **contando ejecuciones** (la 4.ª es el completo), no por coincidencia de
horas: por eso el ciclo se guarda en el plan como dato calculado.

## Fases operativas (10 en adelante)

Tercera sección del menú, **Operaciones**, para los datos del día a día. Se apoyan en los
datos maestros (activos, recursos, materiales) y en los catálogos.

El diseño se acordó con el usuario y reemplaza el diseño inicial que estaba acá:

- [`vision_conceptual.md`](vision_conceptual.md): qué es el sistema, los circuitos de
  pedidos y solicitudes de trabajo, la conformidad, la imputación contable, la
  convivencia con el ERP (EAM hoy, SAP después) y los estados.
- [`diseno_tablas_operativas.md`](diseno_tablas_operativas.md): tablas, columnas, dueño
  de cada dato (ERP o app) y reglas de importación del histórico y de los reportes del ERP.
- [`prompt_copilot_equivalencias.md`](prompt_copilot_equivalencias.md): prompt para que
  Copilot proponga equivalencias (activos, modelos, materiales) que el importador no
  resuelve con reglas.
- [`prompt_copilot_documentos.md`](prompt_copilot_documentos.md): prompt para que Copilot
  lea los PDF de ofertas, presupuestos, remitos, facturas y OC con las columnas del diseño.

Cambios principales respecto del diseño inicial:

- **Orden:** primero pedidos, documentos de proveedores, solicitudes internas y OC (es lo
  que reemplaza los Excel); las OT van después.
- Lo que se cotiza es el **pedido**; la solicitud de OC viene después de adjudicar una
  oferta, y su cabecera nace en el ERP y se importa.
- Las cabeceras de OT, solicitudes internas y OC son del ERP: se importan (adaptador por
  fuente) y la app completa lo que el ERP no registra.
- Cada fase empieza revisando el diseño con el usuario.

### Fase 10: división en PR (acordada 22/11)

Cada PR deja la app funcionando y los tests en verde, y agrega sus notas acá. 10.1 y 10.2
son independientes entre sí; los demás van en orden.

| PR | Cubre |
|---|---|
| **10.1 Framework y limpieza** | Borrar `Pedido` / `PedidoDetalle`, su servicio, rutas y schema, y quitar las tablas viejas `pedidos` y `pedido_detalle` en la migración (las nuevas usan el nombre `pedidos`). `accept` del campo archivo según lo que admite (PDF). Numeración automática (serie continua para pedidos; `TRA-AAAA-NNNN` para después). Columnas «solo por importación»: se ven, no se editan en la web ni en la API, sí se importan (se usan desde la fase 11). `origen` + `clave_origen` como clave natural de lo importado. |
| **10.2 Maestro de materiales** | `codigo_erp`, `es_generico` + `material_generico_id` (con sus reglas: un genérico no tiene genérico, la FK solo acepta genéricos, misma unidad), `controla_stock`; `proveedores.codigo_erp`; `categorias_material.cuenta_id`. Códigos del ERP vacíos como NULL. Los dos prompts de Copilot pasan a las columnas del export de la app. |
| **10.3 Pedidos** | `pedidos`, `pedido_lineas` y `pedido_linea_destinos`. Sugerencia de sector imputado y cuenta. Estados guardados (solicitado, en cotización, ofertas cargadas, anulado), anulación y cancelación con motivo. Resumen del pedido («3 de 5…»). |
| **10.4 Documentos y adjudicación** | `documentos_proveedor` (con el PDF), `documento_lineas` y `adjudicaciones`, con reparto proporcional entre destinos y conversión de unidades genérico → presentación. Ofertada y adjudicada calculadas. Adaptador para la salida de Copilot (bloques A y B de `prompt_copilot_documentos.md`). |
| **10.5 Recepciones y estado calculado** | `recepciones` por destino, con la presentación recibida y la conversión a la unidad de la línea. Recibido, pendientes y estado visible completo (adjudicado → cerrado), con el salteo de estados calculado. |
| **10.6 Importación del Excel histórico** | Adaptador del Excel de pedidos: celdas combinadas, colores de pestaña, moneda por formato de celda, una columna por proveedor. Exportación de `pendientes.csv` y lectura de `equivalencias_revisadas.csv`. Agrega `openpyxl` a `requirements.txt` y a `environment.yml`. |

#### Notas del PR 10.1 (framework y limpieza)

- **Limpieza:** se borraron `Pedido` / `PedidoDetalle`, `pedidos_service.py`,
  `pedidos_routes.py` y su schema. La migración `c3f0a6b2d1e4` quita las tablas `pedidos`
  y `pedido_detalle`; si alguna tiene filas, se detiene sin borrar nada. El nombre
  `pedidos` queda libre para el PR 10.3.
- **Archivos:** `FieldSpec.extensiones`. Las columnas `archivo*` se infieren como
  documentos PDF (`.pdf`); las `foto*`, como imágenes. El formulario arma el `accept` y el
  servidor verifica la extensión del campo. El detalle muestra como imagen solo las
  imágenes (un PDF queda como enlace «Ver archivo»).
- **Numeración automática:** `FieldSpec.numeracion` (`app/crud/core/numeracion.py`),
  con `{n}` y `{año}`. Si el campo llega vacío al crear, toma el mayor de la serie + 1;
  lo cargado a mano se respeta y lo que no sigue el formato no cuenta.
- **Solo importación:** `FieldSpec.solo_importacion`. Se ve en listado, detalle y API; el
  formulario lo muestra deshabilitado (sin enviarlo), la API lo rechaza con un mensaje
  («lo carga la importación») y la importación lo carga. Se usa desde la fase 11.
- **Origen de lo importado:** `OrigenMixin` (`origen` + `clave_origen`, única). Las dos
  columnas son de solo importación y `clave_origen` es la clave natural por defecto. La
  importación rechaza una fila con la clave natural toda vacía (se crearía un registro
  nuevo en cada importación).
- La API distingue, al recibir un campo que no se envía, entre un dato de solo
  importación, uno calculado y uno desconocido.
- Tests: `tests/test_framework_fase10.py`, con una entidad de prueba en una metadata
  propia (ninguna entidad real usa todavía estas piezas).

#### Notas del PR 10.2 (maestro de materiales)

- `materiales`: `codigo` es el número de parte (etiqueta «Código (número de parte)») y
  sigue siendo la clave natural. Nuevos: `codigo_erp`, `es_generico`,
  `material_generico_id` y `controla_stock`. `presentacion_cantidad` pasa a llamarse en
  pantalla «Contenido por envase».
- **Genérico y presentaciones** (reglas en `app/crud/meta/overrides/materiales.py`, al
  guardar):
  - un genérico no tiene genérico, ni envase, ni stock; necesita la unidad y su código
    empieza con `GEN-`;
  - una presentación elige su genérico de un select que solo ofrece genéricos, necesita
    el contenido por envase y toma la unidad del genérico (select dependiente);
  - un genérico con presentaciones no deja de serlo, no cambia de unidad y no se borra;
  - el stock solo admite presentaciones; el BOM y los planes aceptan el genérico.
- Las presentaciones son una pestaña del genérico («Presentaciones», solo en los
  genéricos); «Nuevo» desde ahí llega con el genérico elegido.
- `proveedores.codigo_erp` y `categorias_material.cuenta_id` (cuenta sugerida al comprar
  sin activo; una cuenta en uso no se borra).
- Códigos del ERP vacíos como NULL (la coerción ya lo hacía): la unicidad solo controla
  los cargados.
- La migración `90998dc6cc41` deja los materiales existentes como no genéricos y sin
  control de stock.
- Framework: `"visible"` en `padre` (la pestaña del hijo solo en algunos registros del
  padre).
- Prompts de Copilot: usan `flask exportar materiales` (y `bom_modelo` para los modelos
  aplicables) con las etiquetas de la app. En equivalencias, un fluido sin envase en el
  texto se resuelve al genérico; en documentos, nunca se sugiere un genérico.
- Tests: `tests/test_materiales_fase10.py`.

#### Notas del PR 10.3 (pedidos)

- Tablas `pedidos`, `pedido_lineas` y `pedido_linea_destinos` (`app/models/pedidos_models.py`;
  reglas en `app/crud/meta/overrides/pedidos.py`), con `OrigenMixin` para el histórico.
  Menú «Operaciones» → Pedidos; las líneas son pestaña del pedido (y del material) y los
  destinos, de la línea (y del activo).
- **Pedido:** número de la serie continua (se numera solo), prioridad «normal» por
  defecto, canal sin «histórico». Se identifica por el número al importar. El resumen
  («3 líneas: 2 solicitadas, 1 en cotización») cuenta por estado guardado hasta el 10.5.
- **Línea:** se numera sola dentro del pedido. Material o descripción tal como se pidió;
  la unidad es la del material («Se cuenta en»: envases si es una presentación). El alta
  pide la cantidad y el destino principal y crea el primer destino; la solicitada es la
  suma de los destinos. Anular o cancelar pide un motivo de tipo «Anulación» (tres
  precargados, también por la migración). El nº de OC se guarda sin espacios y en mayúsculas.
- **Destino:** cada tipo pide su dato (activo, modelo, ubicación para stock). Sector
  imputado y cuenta vacíos se completan con la sugerencia; si no hay de dónde, el
  destino queda «a revisar».
- **Material como «código — descripción»** en selects, listados y exportaciones (las
  descripciones se repiten). Al importar, una FK a un material acepta el código, esa
  forma o la descripción, si no se repite. El prompt de equivalencias ya lo aprovecha.
- Framework: `completar` (antes de guardar), `campos_alta` (solo en el alta),
  `orden_campos`, `numeracion_por`, `__calculados__` (calculados en Python) y
  `__buscar_por__` (búsqueda al importar). La auditoría registra las fechas sin hora como
  texto ISO.
- Tests: `tests/test_pedidos.py`.

#### Notas del PR 10.4 (documentos y adjudicación)

- Tablas `documentos_proveedor`, `documento_lineas` y `adjudicaciones`
  (`app/models/documentos_models.py`; reglas en `app/crud/meta/overrides/documentos.py`).
  Menú «Operaciones» → Documentos de proveedores; el documento es pestaña del proveedor,
  sus líneas también del material («Ofertas y documentos») y las adjudicaciones, de la
  línea de oferta y de la línea de pedido.
- **Documento:** los cuatro tipos; solo las ofertas se adjudican. El proveedor se
  identifica por CUIT o razón social (si no, queda el texto); «revisado» pide proveedor,
  fecha y moneda. Número único por proveedor y tipo; nº de OC normalizado. Calculados:
  total de líneas, diferencia con el total sin IVA y total adjudicado.
- **Línea:** se numera dentro del documento; nunca un genérico; unidad del material
  («Se cuenta en»: envases si es una presentación); subtotal; «a revisar» sin material.
- **Adjudicación:** solo líneas de ofertas; no a líneas anuladas; conversión genérico →
  presentación calculada en la consulta (`factor_conversion`); sin material identificado
  no se adjudica a un genérico; no se supera lo ofertado. En la línea de pedido:
  ofertada, adjudicada y pendiente de comprar (en su unidad). Acciones «Vincular con
  pedidos» y «Adjudicar lo vinculado» (envases enteros).
- **Lectura con Copilot:** `flask importar-documentos documentos.csv documento_lineas.csv
  [--simular]` (`app/crud/intercambio/documentos_copilot.py`). Idempotente por
  `clave_documento`; saltea los revisados; borra las líneas que ya no vienen (salvo con
  adjudicaciones); todo o nada.
- Framework: la pestaña de una subentidad muestra las columnas de su listado (antes,
  todas: la tabla desbordaba).
- Tests: `tests/test_documentos.py`.

#### Notas del PR 10.5 (recepciones y estado calculado)

- Tabla `recepciones` (`app/models/recepciones_models.py`; reglas en
  `app/crud/meta/overrides/recepciones.py`): pestaña del destino (y de la línea de un
  remito); la línea de pedido tiene la pestaña calculada «Recepciones» con todas.
- **Recepción:** material por defecto, el adjudicado (si hay uno solo) o el de la línea;
  cantidad por defecto, lo pendiente del destino (envases enteros). Conversión a la
  unidad de la línea como en la adjudicación. Recibir de más se acepta con aviso. Quién
  recibió es opcional. Un destino con recepciones no se borra.
- **Reparto entre destinos:** proporcional y calculado; `comprada_corregida` en el destino
  manda sobre el cálculo. Redondeo a enteros con el resto al primero cuando se cuenta por
  unidad. El destino muestra comprada, recibida y pendiente de recibir.
- **Línea de pedido:** comprado (adjudicada; o, sin oferta, solicitada − cancelada si ya
  hay OC o recepciones), recibida, pendientes de comprar y de recibir, **estado visible**
  (en SQL: se puede filtrar y listar) y salteo de estados. El guardado se llama ahora
  «Estado de seguimiento». El resumen del pedido cuenta por estado visible.
- Importación: un encabezado que es la etiqueta de un calculado (ej: «Estado») se ignora,
  aunque coincida con el nombre de otro campo.
- Rendimiento: los calculados de la línea son subconsultas por fila; con los volúmenes
  actuales no se nota, pero si los listados crecen mucho conviene paginar.
- Tests: `tests/test_recepciones.py`.

#### Notas del PR 10.6 (importación del Excel histórico)

- Antes de codificar se analizó el Excel completo (`docs/analisis_excel_pedidos.md`) y el
  gestor respondió las dudas (23/11): todos los verdes y el azul son cerrados; el naranja
  equivale al amarillo; la OC escrita en una fila vale para el resto de la hoja (cerrada);
  «Recibido?» = ok es cierre manual sin recepción; la moneda se termina de resolver al
  cruzar con las OC. En las demás dudas se aceptaron las recomendaciones. Reglas
  completas en «Importación del Excel histórico de pedidos» de
  `diseno_tablas_operativas.md`.
- `flask --app run importar-pedidos Pedidos.xlsx [--equivalencias equivalencias_revisadas.csv]
  [--pendientes pendientes.csv] [--informe informe_pedidos.csv] [--simular]`.
- **Adaptador** (`app/crud/intercambio/excel_pedidos.py`, sin base): lee con openpyxl dos
  veces (valores calculados y fórmulas). Encabezado = la fila con «Detalles» en C;
  columnas G en adelante por su encabezado, y cualquier otro encabezado es un proveedor
  cotizado. Celdas combinadas repetidas; color de pestaña por tono (HSV), resuelto con el
  tema del propio libro; moneda por formato; OC y proveedor completados en las hojas
  cerradas; columnas corridas detectadas por contenido (la «OC» sin números de OC y
  «PROVEEDOR» con ellos).
- **Servicio** (`app/crud/intercambio/pedidos_historicos.py`): carga con los servicios de
  cada entidad (validación, sugerencias, auditoría). Pedido, líneas, destinos, ofertas
  reconstruidas (una por proveedor y OC) y adjudicaciones. Idempotente por
  `clave_origen` (`excel_pedidos|<hoja>|f<fila>`); no pisa con vacíos lo identificado ni
  toca destinos cargados en la app ni ofertas revisadas. Todo o nada.
- **Equivalencias:** `pendientes.csv` con las columnas del prompt (`id` estable: tipo + hash
  del texto); `equivalencias_revisadas.csv` se lee por `tipo` + `texto` (`resultado` y
  `codigos`). `material_nuevo` no crea materiales: el gestor los da de alta y reimporta.
- Esquema (migración `fc476eabc431`): `motivo_revision` («A revisar (importación)») en
  pedidos y líneas; observaciones más largas (2000 en pedidos, 1000 en líneas).
- Línea sin «Detalles» (decidido con el gestor, 23/11): con un material del maestro es un
  repuesto para stock del taller de su sector imputado (si el sector tiene una sola
  ubicación; si no, «a identificar» con nota); sin material del maestro (ferretería,
  insumos), gasto general. Al reimportar, si el material se identificó después, el gasto
  general automático pasa a stock o a «a identificar».
- Decisiones menores tomadas al codificar (a confirmar en la revisión): la oferta
  reconstruida lleva la fecha del pedido; la clave del pedido no incluye el nombre del
  archivo.
- Con el Excel anonimizado (maestros vacíos): 392 pedidos, 2096 líneas (1841 cerradas,
  71 con OC emitida, 58 anuladas), 2643 destinos, 462 ofertas; 334 líneas con la OC tomada
  de otra fila y 111 en hojas con varias OC que no se pudieron deducir. Unos 35 s.
- `openpyxl` en `requirements.txt` y `environment.yml`.
- Tests: `tests/test_pedidos_historicos.py`.

#### Notas: estado de las ubicaciones (25/11, fuera de fase)

- Catálogo `estados_ubicacion` (Operativa, En mantenimiento, Inactiva; con color) y
  `ubicaciones.estado_ubicacion_id` obligatorio. Informativo: no limita destinos de
  stock ni activos. Ver `docs/diseno_tablas_operativas.md`, «Cambios a tablas existentes».
- Migración `5c7c85247e05`: crea el catálogo, **inserta los tres estados** y deja las
  ubicaciones existentes en «Operativa». El seed los carga solo en una base sin
  migraciones (tests). Lección del seed de motivos (PR 34): si una migración inserta
  valores de un catálogo, que inserte el catálogo completo, o el seed por «tabla vacía»
  saltea el resto.
- Valor por defecto: función del modelo (`estado_ubicacion_por_defecto`) que busca
  «Operativa» (o el primer estado, si se renombró). El override marca el campo como no
  obligatorio y, con `completar`, mantiene el estado actual si una modificación lo trae
  vacío (PUT de la API).
- Framework: el formulario de alta ahora preselecciona también los valores por defecto
  **calculados** de las FK (antes, solo los fijos). Las fechas (`date.today`) siguen sin
  preseleccionarse.
- Tests: `tests/test_estado_ubicacion.py`.

#### Notas: estados de proveedor y de contacto (25/11, fuera de fase)

- Catálogos `estados_proveedor` (Activo, Retenido, Inactivo) y `estados_contacto`
  (Disponible, No disponible), informativos. «Retenido» todavía no bloquea
  adjudicaciones ni OC (punto abierto en `docs/diseno_tablas_operativas.md`).
- El estado sale de `recursos`: `empleados.estado_recurso_id` (sigue con
  `estados_recurso`) y `proveedores.estado_proveedor_id`. Ya no se pasa
  `estado_recurso_id` al crear un proveedor.
- Migración `dda0f1c78dee`: inserta los catálogos completos, copia el estado de cada
  empleado, pasa el de cada proveedor por nombre («Suspendido» → «Retenido»), deja los
  contactos en «Disponible» y agrega `contactos_proveedor.division` (estaba en el modelo
  sin migración). Si un proveedor tiene un estado de recurso sin equivalente, se frena
  **antes** de tocar el esquema: SQLite no deshace el DDL de una migración que falla a
  mitad de camino. La bajada es simétrica.
- Valores por defecto generalizados en `app/crud/por_defecto.py`: `id_por_nombre(...)`
  (default de la columna) y `mantener_si_vacio(...)` (`completar` del override). Los
  usan ubicaciones, proveedores y contactos.
- Tests: `tests/test_estados_proveedor_contacto.py` y
  `test_estados_de_proveedor_desde_los_de_recurso` en `tests/test_migraciones.py`.

#### Notas: nombre en el ERP de los planes preventivos (25/11, fuera de fase)

- `planes_preventivos.nombre_erp` (migración `1d89261de669`), opcional y único cuando
  está cargado; alias «NombreERP» para importar la planilla de SharePoint. Ver
  `docs/diseno_tablas_operativas.md`. El uso (reconocer el plan en la OT) es de la fase 12.
- Error encontrado al probarlo: el CSV tomaba el punto siempre como decimal y «1.400»
  se importaba como 1,4. Corregido en el PR siguiente (ver «Carga de datos (Fase 6)»).

#### Notas: filtros combinables en los listados (25/11, fuera de fase)

- Filtros **a demanda** en todos los listados: «+ Agregar filtro» suma una fila (campo,
  select y «×» para quitarla) por cada campo de los `filtros` con opciones (FK, opciones
  fijas, Sí/No), combinados con Y y con la búsqueda de texto. Las filas van una debajo de
  la otra (al principio era un panel con todos los selects en grilla, que con la hoja de
  estilos en caché se veía en una sola línea y se cortaba). Al volver a una búsqueda se
  ven las filas de los filtros aplicados. Cantidad de resultados y «Limpiar». Ejemplo:
  tractores 5090E del Feedlot.
- La hoja de estilos se pide con `?v=<fecha de modificación>` (`version_estatico` en
  `app/__init__.py`): después de una actualización el navegador no usa la copia vieja.
- Selects dependientes, como en el formulario (los modelos de la categoría elegida).
- Filtros en la URL con el nombre del campo (`/activos?categoria_activo_id=2&sector_id=3`),
  como en la API; los vacíos no se envían. Un valor inválido se ignora. Los enlaces
  viejos (`?campo=<fk>&valor_fk=<id>`) siguen andando. Sí/No va como `Sí` / `No`.
- La búsqueda de texto busca en una FK por el nombre de lo vinculado (antes, por el
  ID): «5090» encuentra el modelo 5090E. Vale también para la API. Si el nombre es una
  propiedad de Python (ej: el nombre completo del empleado), esa FK no participa.
- Rendimiento medido con 3000 activos: sin filtros, ~43 ms; texto en todos los campos y
  FK, ~6 ms; tres filtros combinados, ~3 ms.
- `repository.consulta_listado(valores=...)` y `campos_de_filtro(...)`.
- Tests: `tests/test_filtros_listado.py`.

#### Notas: campos con lista y activo como «número — descripción» (26/11, fuera de fase)

- **Campo con lista** (`<datalist>`) en formularios y filtros cuando una FK, un `select`
  de opciones fijas o un filtro Sí/No tiene más de `fk.UMBRAL_LISTA` (15) opciones; con
  menos, sigue el `<select>`. `FieldSpec.selector` (`"lista"` o `"select"`) lo fija en un
  campo. Al tipear, la lista se acorta a las opciones que contienen el texto (por
  número, código o descripción).
- Cómo funciona: el campo visible no se envía; el ID va en un oculto (`<campo>__valor`).
  Cada opción se identifica por su texto (`fk.con_texto`): la etiqueta más los padres
  entre paréntesis en un dependiente («5090E (Tractor, John Deere)») y, si aun así se
  repite, «(ID n)». Un texto que no es una opción deja el campo inválido: el formulario
  no pide el motivo y el filtro no busca.
- Formularios: antes de pedir el motivo se validan los campos (`reportValidity`), así
  que ahora también se avisan en el navegador los obligatorios vacíos.
- Filtros: se busca al tomar una opción de la lista o al salir del campo, no mientras se
  tipea; vaciar un filtro aplicado lo quita.
- Selects y campos con lista comparten el código (`app/static/js/selectores.js`): misma
  interfaz para los dependientes (el hijo se acota a lo elegido en los padres; en el
  formulario, elegir el hijo completa los padres vacíos, aunque sean de distinto tipo).
  Plantilla del campo: `crud/partials/_selector.html`.
- **Activo como «número — descripción»** (`Activo.etiqueta`, como `Material.etiqueta`)
  en selectores, listados, detalle, exportación, API (`activo_id_label`) y nombre del
  destino de un pedido. La búsqueda de texto lo encuentra por número. Al importar, una FK
  a un activo acepta el número, esa forma o la descripción, si no se repite. El historial
  ya guardado sigue mostrando solo la descripción.
- La grilla de la fase 13 usa el mismo umbral y el mismo `selector` (`fk.usa_busqueda`),
  pero envía el texto y el servidor lo busca con `fk.BuscadorFK`, que reconoce la
  etiqueta, el número de activo o el código de material.
- Tests: `tests/test_selector_lista.py`.

## Fase 13: edición en línea (acordada 26/11)

Diseño completo y decisiones: [`propuesta_edicion_en_linea.md`](propuesta_edicion_en_linea.md).
Reglas de borrador y envío: «Borrador y envío a Compras» en
[`diseno_tablas_operativas.md`](diseno_tablas_operativas.md). Demo de referencia:
`herramientas/demo_edicion_en_linea/`.

Principio: **sin rutas a mano**. La grilla se genera desde la spec y guarda con el mismo
camino que el formulario y la API (`coercion` → `fk.validar_existencia` →
`servicio.actualizar`), así que `completar`, `al_guardar`, la auditoría y los mensajes de
error valen igual. Las reglas de qué se puede editar (`editable_si`) también las aplica el
servicio, no solo la pantalla.

| PR | Cubre |
|---|---|
| **13.1 Framework** | `EntitySpec.edicion_en_linea` (validada por el registry: ni calculados, ni archivos, ni columnas del ERP). Rutas genéricas `GET/POST /<entidad>/<id>/celda/<campo>` y `GET /<entidad>/<id>/fila`; error de validación = 422 con la celda abierta. Parciales `_fila.html` y `_celda_edicion.html`. `static/js/grilla.js` (teclado y foco) y htmx en `static/vendor/` (sin CDN). Auditoría con el motivo fijo «Edición en línea» (no va al catálogo de motivos). Se activa en la pestaña «Líneas» del pedido. |
| **13.2 Borrador y envío** | `pedido_lineas.enviada_en` (migración; el histórico, con la fecha del pedido). `editable_si` en la spec, aplicado por la grilla, el formulario, la API y el servicio. Acción «Enviar a Compras». Eliminar en borrador. «Anular o cancelar» con motivo, sin anular entera una línea con compras. Resumen del pedido con «Borrador» / «N líneas sin enviar». |
| **13.3 Alta rápida** | Última fila de la grilla con `campos_alta` (material o descripción, cantidad, destino). |
| **13.4 Destinos y «Redistribuir»** | Subgrilla de destinos bajo cada línea, con la fila de la línea actualizada fuera de banda. Completar el activo, el modelo o la ubicación define el tipo de destino (`completar_destino`). «Redistribuir» en líneas enviadas: todo o nada, sin cambiar el total. |
| **13.5 Pegar desde Excel** | Vista previa y confirmación todo o nada (`servicio(confirmar=False)`), con un adaptador «pegado» al formato interno común. Lo no identificado queda como descripción o «a identificar». |
| **13.6 Colas de «a revisar»** | Destinos sin sector o cuenta, líneas sin material identificado: listas editables para resolverlas. |

Sin control de concurrencia por ahora: los pedidos los carga y edita solo el gestor. Se
revisa en la fase 14, cuando Compras escriba en la app.

#### Notas del PR 13.1 (framework de edición en línea)

- **Spec:** `EntitySpec.edicion_en_linea`. El registry exige que cada campo esté en
  `listado` (la grilla muestra esas columnas) y rechaza calculados (`solo_lectura`,
  `calculado_python`), archivos, campos de alta, ocultos, de solo importación (la marca de
  las columnas cuyo dueño es el ERP: hoy `origen` y `clave_origen`; las de la fase 11 la
  llevarán al crearse) y el **padre principal** (sería mover el registro). Un padre
  secundario sí se edita: el material de una línea, que en la pestaña del material no se
  muestra porque se oculta la columna del padre visitado.
- **Rutas** (`web/views.py`, solo con `edicion_en_linea`): `GET/POST
  /<entidad>/<id>/celda/<campo>` y `GET /<entidad>/<id>/fila`. Un campo que no está en la
  lista da 404. El padre viaja en la URL (`?pedido_id=3`), como en el resto de las
  pantallas, y define qué columna se oculta y a dónde apuntan los enlaces.
- **Guardar:** `coercion.datos_de_entrada(parcial=True)` → `fk.validar_existencia` →
  `servicio.actualizar(registro, {campo: valor}, "Edición en línea")`. El motivo es una
  constante (`MOTIVO_EDICION_EN_LINEA`), no está en el catálogo. Error = 422 con la fila
  y la celda abierta, con lo escrito. Lo que una regla marca en **otro** campo se muestra
  en la celda editada con la etiqueta de ese campo («Material: Elegí el material…»).
- **Campos que dependen de otro** (`depende_de`): al editar en línea el hijo, los padres
  que no están en `edicion_en_linea` se vacían y el servicio los completa con los del
  valor nuevo. Así, cambiar el material de una línea trae su unidad, en vez de dar «no
  pertenece».
- **FK por texto:** `_BuscadorFK` del importador CSV pasó a `core/fk.py` (`BuscadorFK`,
  con `NoEncontrado` y `Ambiguo`), compartido por el CSV y la grilla. En la grilla además
  vale el comienzo si corresponde a un solo registro (`por_prefijo`); el CSV sigue
  pidiendo el texto exacto. Una FK con más de `UMBRAL_LISTA` (15) registros se edita
  con `<input list>` (sugerencias que filtran por cualquier parte del texto); con menos,
  con un `<select>`. Se cuenta al abrir la celda, respetando `fk_filtro`; `FieldSpec.selector`
  lo fija, igual que en formularios y filtros (era `UMBRAL_BUSQUEDA`; se unificó al juntar
  esta fase con los campos con lista).
- **Plantillas:** `crud/partials/_fila.html` (una fila; la usan `listado_entidad.html`,
  `listado_subentidad.html` y las rutas de celda) y `_celda_edicion.html`. Las filas se
  arman con `item_fila` (solo las columnas del listado, con etiqueta y color de cada FK).
  De paso: los estados se ven como badge también en la pestaña del padre, los botones de
  la pestaña quedan como en el listado («Ver detalles», «Editar») y se corrigió el
  `colspan` de «No hay registros». El listado propio de la entidad (`/pedido_lineas`)
  también es grilla.
- **JS y htmx:** `static/js/grilla.js` (de la demo, sin destinos, redistribuir ni pegado)
  y htmx 2.0.4 en `static/vendor/htmx/` con su licencia (0BSD), cargados en `layout.html`
  con `defer`. El `meta htmx-config` hace que el 422 también reemplace la fila. Cambio
  respecto de la demo: lo que se escribe mientras la celda se está abriendo queda en un
  búfer (escribiendo rápido se perdían las primeras teclas) y un Enter o Tab apretado en
  ese momento guarda al llegar el control. Estilos en la sección «Edición en línea» de
  `estilos.css`; la celda en edición anula el `overflow: hidden` de las `td` para que se
  vea el mensaje de error.
- **Activada en** `pedido_lineas`: material, descripción y nº de OC. El estado y el motivo
  pasan al PR 13.2, con `editable_si` (el estado solo se edita en líneas enviadas).
- **Probado en el navegador** (Chromium, Playwright): escribir sobre la celda, Enter, Tab,
  flechas, Esc, doble clic, clic afuera, error 422 y búsqueda por código y por comienzo.
- Tests: `tests/test_edicion_en_linea.py`.

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
| **9. Planes preventivos** | Planes por categoría de activo (período por uso y/o por tiempo, plan que incluye a otro), tareas, materiales por modelo; categoría en el modelo y tipo de medidor. Ver «Fase 9: planes preventivos». | ✅ Hecha |
| **10. Pedidos y documentos de proveedores** | Pedidos con líneas y destinos (imputación), ofertas y presupuestos (cabecera + líneas), adjudicación por cantidad, recepciones (conformidad). Importación del Excel histórico de pedidos. Ver «Fases operativas». | ✅ Hecha |
| **11. Solicitudes de trabajo, solicitudes internas y OC** | Solicitudes de trabajo (avisos de los mecánicos para llamar a un contratista) y su vínculo con los presupuestos (`documentos_proveedor.solicitud_trabajo_id`). Importación de los TSV de EAM (cabeceras, líneas, distribuciones) y de las OC; vínculo con los documentos adjudicados; distribución propuesta; detalle para Administración; conciliación por nº de OC. | Pendiente |
| **12. Órdenes de trabajo** | Cabecera importada del ERP; la app agrega operaciones, recursos y materiales (previsto y utilizado). Incluye cuándo le toca un plan a cada activo. | Pendiente |
| **13. Edición en línea, borrador y envío a Compras** | Listados editables tipo planilla con htmx, generados desde la spec (`edicion_en_linea`, `editable_si`). En pedidos: líneas en borrador y «Enviar a Compras» (`enviada_en`), eliminar en borrador, anular o cancelar con motivo, destinos desplegados y «Redistribuir», alta rápida, pegar desde Excel. Ver «Fase 13: edición en línea». Puede ir antes que la 11: trabaja sobre los pedidos de la fase 10. | En curso (13.1 hecho) |
| **14. Circuito con Compras** | Usuarios, roles y auditoría con usuario; despliegue en un servidor. Vista de Compras (para cotizar, para emitir OC, reclamos), comparativo por línea, adjudicación y «Pedir OC». Ver [`propuesta_circuito_compras.md`](propuesta_circuito_compras.md). | En diseño |
| **15. Sincronización con SharePoint** | Opción A: exportar periódicamente de la app a SharePoint, más copias de seguridad automáticas de la base. Al final, escribir en SharePoint directo (Microsoft Graph) en lugar de pasar por CSV. | Pendiente |

## Cómo agregar o modificar una entidad

Ver la guía [`docs/agregar_entidad.md`](agregar_entidad.md): modelo, migración, override
y pruebas, con un ejemplo completo.

## Cómo verificar cada fase

```bash
python -m pytest                     # todos los tests en verde (los xfail cuentan como esperados)
```

La coherencia entre overrides y modelos la valida el registry al arrancar (la app no
arranca si algo no cierra).

Al corregir un error conocido, su test `xfail` empieza a pasar y pytest lo informa como
falla (`xfail_strict = true`): en ese momento se quita la marca.
