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
| API | Sin autenticación por ahora. Hoy la consume `src/sync`; más adelante, Power Apps y otras apps web. Por eso: contrato REST estable, errores JSON uniformes, paginación, CORS configurable y una **especificación OpenAPI** (los conectores personalizados de Power Apps se crean a partir de ella). La autenticación se diseña como un punto de extensión para agregarla después sin rehacer nada. |
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
  | Sector / ubicación → activos, empleados, stock | Bloqueo | Provisorio: revisar en Fase 7 |
  | Resto de las entidades | — | **Revisar al migrar cada una (Fase 7)** |

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

## Carga de datos (Fase 6, a definir)

Necesidades:

1. **Carga inicial en producción** de los datos reales, que hoy están en SharePoint
   (exportables a CSV).
2. **Datos de prueba** reutilizables para tests y para probar la app a mano.
3. **Catálogos** (estados, motivos, tipos): hoy en `app/utils/seed.py` (`flask seed`).

Propuesta:

- Comando `flask importar <entidad> archivo.csv` que use el registry y el **mismo
  servicio** que la web y la API: misma validación, mensajes por fila y campo, y
  auditoría con usuario "importación" y el nombre del archivo como motivo.
- Modo **simulación** (`--simular`): valida todo el archivo y muestra los errores sin
  guardar nada. Si una fila falla, no se guarda ninguna (todo o nada).
- **Claves foráneas por nombre**: en el CSV, `estado_sector` = "Activo" en lugar del ID
  (los IDs de SharePoint no coinciden con los de la base).
- **Clave natural** por entidad (ej: `nombre_sector`) para que reimportar actualice en
  lugar de duplicar.
- Orden de carga según dependencias (sectores antes que ubicaciones).
- Los mismos CSV, más chicos, sirven como datos de prueba.
- `src/sync` (Excel → API) se puede rehacer sobre esta base o reemplazar por este comando.

Para decidir antes de implementar:

- ¿La carga desde SharePoint es única (migración inicial) o periódica (sincronización)?
- ¿Qué columna identifica cada registro en SharePoint (clave natural)?
- ¿Se podría leer SharePoint directo (Microsoft Graph) en lugar de exportar CSV?
- ¿Los catálogos (estados, motivos) también vienen de SharePoint o quedan en `seed.py`?

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

Compatibilidad: `src/sync/backend_client.py` usa `GET/POST {url}` y `PUT/DELETE {url}/{id}`;
la API generada respeta ese contrato.

## Fases

| Fase | Contenido | Estado |
|---|---|---|
| **0. Red de seguridad** | Tests con pytest para sectores, ubicaciones y cuentas (web y API). Errores conocidos marcados como `xfail`. README. `.gitignore` permite `requirements*.txt`. | ✅ Hecha |
| **1. Metamodelo tipado** | `EntitySpec`/`FieldSpec`, registry (inferido + overrides) y un adaptador para que los dicts actuales sigan funcionando. Overrides de las 3 entidades piloto. `shadow_diff` pasa a ser validación al arrancar. | ✅ Hecha |
| **2. Capa core** | Coerción, FK, repositorio, servicio (transacción + auditoría) y archivos. `framework.py` delega en ellos. Validación en servidor y manejo de `IntegrityError`. | ✅ Hecha |
| **3. Web generada** | Vistas genéricas y navegación por registry (`app/crud/web/views.py`). Se eliminan `sectores_web.py` y `cuentas_web.py`. Las rutas especiales (`bom_final`, `compatibilidad_final`) se resuelven al migrar activos e insumos (Fase 7). | ✅ Hecha |
| **4. API generada** | Generador de JSON Schema, endpoints REST genéricos con paginación y errores JSON, especificación OpenAPI (3.0 y 2.0 para Power Apps) y página `/api/docs`. Reemplaza `sectores_routes.py`; se elimina `activos_routes.py`. | ✅ Hecha |
| **5. Base de datos** | Quitar el respaldo automático y `sync-db`. Flask-Migrate (Alembic) y fuera `create_all` de `before_request`. Configuración por `.env`. Comandos de consola a `app/cli.py`. | ✅ Hecha |
| **6. Carga de datos** | Importar los datos reales desde CSV exportados de SharePoint, y datos de prueba reutilizables. Ver «Carga de datos» más abajo. | Pendiente |
| **7. Migrar el resto** | Tras revisar su diseño: activos, medidores, lecturas, insumos, stock, unidades, marcas, modelos, recursos, BOM. | Pendiente |
| **8. Limpieza** | Borrar los metamodelos viejos y `framework.py`, los `.txt` duplicados y el código sin uso listado en las notas. | Pendiente |

## Cómo agregar o modificar una entidad (desde la Fase 1)

1. **Modelo** (`app/models/`): columnas, obligatoriedad (`nullable`), largo, FKs,
   relaciones y etiquetas de los campos con `info={"label": "..."}`.
2. **Override** (`app/crud/meta/overrides/<modulo>.py`): solo lo que no se deduce del
   modelo. Lo mínimo es `{"model": MiModelo}`; las claves posibles están documentadas en
   `app/crud/meta/overrides/__init__.py`.
3. Nada más: las pantallas (listado, alta, detalle, edición y baja) se generan solas.
   Si la entidad migrada estaba en `app/crud/metamodelos/`, borrar su dict y su
   `CRUDResource` de `app/routes/web/`.

Si algo no cierra (un campo mal escrito, un padre inexistente, una FK que no apunta al
padre), la app **no arranca** y el error dice qué corregir, con una sugerencia.

## Cómo verificar cada fase

```bash
python -m pytest                     # todos los tests en verde (los xfail cuentan como esperados)
python tools/crud_shadow.py          # coherencia de metamodelos
```

Al corregir un error conocido, su test `xfail` empieza a pasar y pytest lo informa como
falla (`xfail_strict = true`): en ese momento se quita la marca.
