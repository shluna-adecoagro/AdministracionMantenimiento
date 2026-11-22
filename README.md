# Administración de Mantenimiento

Sistema para **centralizar los datos del área de mantenimiento** de la empresa: qué activos
existen, dónde están, qué materiales y repuestos usan, cuánto stock hay, quiénes trabajan en
ellos y qué cambios se hicieron, con trazabilidad completa.

La idea es tener **una única fuente de verdad** consultable desde distintos lugares:

- una **interfaz web** propia (Flask + Jinja2) para cargar y consultar datos;
- una **API REST** con validación por JSON Schema, pensada para que la consuman otras
  herramientas (Power Apps u otras aplicaciones web);
- **análisis** de mantenimiento (MTBF, consumo de gasoil, etc.) en `ml/`.

## Qué gestiona

| Área | Entidades |
|---|---|
| Organización | Sectores, ubicaciones, cuentas contables |
| Activos | Activos (vehículos, equipos fijos, implementos), marcas y modelos, medidores y lecturas |
| Materiales | Materiales, stock, unidades de medida, listas de materiales (BOM) por modelo y por activo |
| Recursos | Empleados, proveedores y sus contactos |
| Trazabilidad | Auditoría de cada alta, modificación y baja, con versión, motivo y usuario |

## Cómo está construido

Las pantallas y endpoints CRUD **no se escriben a mano**: se generan a partir de un
*metamodelo* por entidad.

```
Modelos SQLAlchemy ──► introspección ──┐
                                       ├──► Metamodelo ──┬──► Rutas web (Flask + Jinja2)
Overrides (lo no inferible) ───────────┘                 └──► API REST (JSON Schema)
```

Agregar una entidad nueva consiste en definir su modelo y, si hace falta, un override con
lo que no se puede deducir del modelo (textos, columnas del listado, subentidades…).

- **Cómo agregar o modificar una entidad**: [`docs/agregar_entidad.md`](docs/agregar_entidad.md)
  (modelo, migración, override y pruebas, con un ejemplo completo).
- Diseño del framework, decisiones tomadas y fases: [`docs/plan_refactor_crud.md`](docs/plan_refactor_crud.md).
La visión del sistema y el diseño de la parte operativa (pedidos, documentos de
proveedores, solicitudes internas, OC y OT) están en
[`docs/vision_conceptual.md`](docs/vision_conceptual.md) y
[`docs/diseno_tablas_operativas.md`](docs/diseno_tablas_operativas.md).

### Estructura

```
app/
├── models/      Modelos SQLAlchemy (una tabla por clase)
├── crud/        Framework CRUD: meta/ (registry y overrides), core/ (servicio,
│                consultas), web/ y api/ (pantallas y API generadas), intercambio/ (CSV)
├── routes/      Rutas que no son CRUD (inicio, motivos, auditoría)
├── templates/   Plantillas Jinja2 (las genéricas están en crud/)
├── schemas/     JSON Schemas de lo que no es CRUD (auditoría, pedidos, activos)
├── services/    Lógica de negocio que no es CRUD (pedidos)
├── audit/       Registro de auditoría
└── utils/       Seed de datos iniciales y utilidades
ml/              Scripts de análisis
tests/           Tests automáticos (pytest)
```

## Puesta en marcha

Requiere Python 3.11 o superior. Se puede usar **conda** (recomendado; incluye las
librerías de análisis de `ml/`) o un **entorno virtual** de Python.

### Con conda (Miniforge) en Debian / Ubuntu

1. **Instalar Miniforge** (una sola vez por máquina). Si ya está instalado, saltear.

   ```bash
   sudo apt update && sudo apt install -y curl git
   curl -fsSLO "https://github.com/conda-forge/miniforge/releases/latest/download/Miniforge3-$(uname)-$(uname -m).sh"
   bash Miniforge3-$(uname)-$(uname -m).sh
   ```

   Aceptar la licencia y la carpeta propuesta (`~/miniforge3`), y responder **yes**
   cuando pregunta si inicializar conda. Cerrar y volver a abrir la terminal.

2. **Bajar el proyecto y crear el entorno**:

   ```bash
   git clone https://github.com/shluna-adecoagro/AdministracionMantenimiento.git
   cd AdministracionMantenimiento
   conda env create -f environment.yml
   conda activate adminmant
   ```

3. **Verificar** que todo esté bien (unos 30 segundos):

   ```bash
   python -m pytest
   ```

4. **Levantar la aplicación** y abrir http://127.0.0.1:5000 en el navegador:

   ```bash
   python run.py
   ```

   En desarrollo, el primer acceso crea la base (`instance/mantenimiento.db`), aplica las
   migraciones y carga los catálogos iniciales. Se detiene con Ctrl+C.

Cada vez que se abre una terminal nueva: `cd AdministracionMantenimiento` y
`conda activate adminmant`.

**Actualizar** después de bajar cambios (`git pull`):

```bash
conda env update -f environment.yml   # por si cambiaron las dependencias
flask --app run db upgrade            # por si hay migraciones nuevas
```

Con `--prune`, `conda env update` además quita del entorno los paquetes que no están en
`environment.yml` (por ejemplo, Jupyter, si se instaló aparte).

### Con un entorno virtual (venv)

```bash
python3 -m venv .venv
source .venv/bin/activate        # en Windows: .venv\Scripts\activate
pip install -r requirements-dev.txt
python -m pytest
python run.py
```

En Debian / Ubuntu, `python3 -m venv` necesita el paquete `python3-venv`
(`sudo apt install python3-venv`).

### Configuración (opcional)

La base de datos es **SQLite**. Por defecto se crea en `instance/mantenimiento.db`. Para
cambiar la ruta o la clave de la sesión, crear un archivo `.env` en la carpeta del
proyecto (no se sube a git):

```
DATABASE_URL=sqlite:////ruta/absoluta/mantenimiento.db
SECRET_KEY=una-clave-larga-y-secreta
```

Las dependencias están en dos lugares que deben coincidir: `requirements*.txt` (pip) y
`environment.yml` (conda). Un test avisa si falta alguna en `environment.yml`.

Comandos útiles (`flask --app run <comando>`):

| Comando | Qué hace |
|---|---|
| `db upgrade` | Crea o actualiza el esquema aplicando las migraciones pendientes |
| `db migrate -m "descripción"` | Genera una migración después de cambiar un modelo |
| `db check` | Avisa si hay cambios en los modelos sin migración |
| `seed` | Carga los catálogos iniciales (estados, motivos, tipos…) en tablas vacías |
| `reset-db` | Borra la base, la recrea y carga los catálogos (pide confirmación) |
| `inspect-db` | Muestra tablas, columnas, claves primarias y foráneas |
| `importar <entidad> <archivo.csv>` | Carga datos desde CSV (`--simular` para revisar sin guardar) |
| `exportar <entidad> <archivo.csv>` | Descarga los datos de una entidad a CSV |

### Importar y exportar datos (CSV)

```bash
flask --app run importar sectores sectores.csv --simular   # revisa sin guardar
flask --app run importar sectores sectores.csv             # guarda
flask --app run exportar sectores sectores.csv             # descarga a CSV
```

- Las columnas se reconocen por el nombre del campo o por su etiqueta («Nombre del
  Sector»), sin importar mayúsculas ni tildes. Las columnas desconocidas (como las que
  agrega SharePoint) se ignoran.
- Las referencias a otras tablas van **por nombre** («Activo», «Taller»), no por ID.
- Cada fila se busca por la **clave natural** de la entidad (ej: el nombre del sector, o
  nombre de ubicación + sector): si existe se actualiza, si no se crea, y si no cambió no
  se toca.
- **Todo o nada**: si alguna fila tiene errores se listan todos (con número de fila) y no
  se guarda nada. Cada cambio queda en la auditoría con el nombre del archivo.
- El CSV exportado usa `;` y UTF-8 con BOM (se abre bien en Excel) y se puede volver a
  importar.
- Importar entidades en orden de dependencia: sectores antes que ubicaciones.

### Cambios en el esquema (migraciones)

El esquema de la base está versionado en `migrations/versions/`. Para cambiar un modelo:

1. Editar el modelo en `app/models/`.
2. `flask --app run db migrate -m "qué cambió"` genera la migración. **Revisarla**: Alembic
   no detecta todo (por ejemplo, un renombre lo ve como borrar y crear).
3. `flask --app run db upgrade` la aplica. En desarrollo también se aplica sola al
   levantar la app; en producción es un paso explícito del despliegue.
4. Subir la migración junto con el cambio del modelo. Un test falla si un modelo cambió
   y falta su migración.

## API

Cada entidad migrada al registry tiene una API REST en `/api/<entidad>`:

| Método | Ruta | Qué hace |
|---|---|---|
| `GET` | `/api/sectores` | Lista (array JSON). Filtros: `?q=texto`, `?<campo>=valor`, `?limit=&offset=`; el total va en el encabezado `X-Total-Count` |
| `POST` | `/api/sectores` | Alta (devuelve 201 y el registro creado) |
| `GET` | `/api/sectores/<id>` | Un registro |
| `PUT` | `/api/sectores/<id>` | Reemplazo completo |
| `PATCH` | `/api/sectores/<id>` | Cambio parcial (solo los campos enviados) |
| `DELETE` | `/api/sectores/<id>?motivo=...` | Baja |

Los datos se validan con JSON Schema y los errores vuelven en JSON, con un mensaje por
campo. El encabezado `X-Usuario` indica quién hizo el cambio en la auditoría.

Documentación generada automáticamente:

- `/api/docs`: página para explorar y probar la API desde el navegador.
- `/api/openapi.json`: OpenAPI 3.0 (clientes estándar, acciones de ChatGPT).
- `/api/swagger.json`: OpenAPI 2.0, para crear un **conector personalizado de
  Power Apps / Power Automate** (Importar → "Importar desde URL").

## Tests

```bash
python -m pytest
```

Cada test usa una base SQLite en memoria, así que no toca tus datos. Los errores ya
conocidos están marcados como `xfail` con la fase del plan en la que se corrigen: cuando
uno se arregla, pytest avisa para quitar la marca.
