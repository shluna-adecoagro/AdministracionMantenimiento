# Administración de Mantenimiento

Sistema para **centralizar los datos del área de mantenimiento** de la empresa: qué activos
existen, dónde están, qué insumos y repuestos usan, cuánto stock hay, quiénes trabajan en
ellos y qué cambios se hicieron, con trazabilidad completa.

La idea es tener **una única fuente de verdad** consultable desde distintos lugares:

- una **interfaz web** propia (Flask + Jinja2) para cargar y consultar datos;
- una **API REST** con validación por JSON Schema, pensada para que la consuman otras
  herramientas: la sincronización desde Excel (`src/sync`) y, más adelante, apps de
  Power Apps u otras aplicaciones web;
- **análisis** de mantenimiento (MTBF, consumo de gasoil, etc.) en `ml/`.

## Qué gestiona

| Área | Entidades |
|---|---|
| Organización | Sectores, ubicaciones, cuentas contables |
| Activos | Activos (vehículos, equipos fijos, implementos), marcas y modelos, medidores y lecturas |
| Insumos | Insumos, stock, unidades de medida, listas de materiales (BOM) por modelo y por activo |
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

Este diseño está en plena refactorización. El plan y su avance están en
[`docs/plan_refactor_crud.md`](docs/plan_refactor_crud.md).

### Estructura

```
app/
├── models/      Modelos SQLAlchemy (una tabla por clase)
├── crud/        Framework CRUD: metamodelos, introspección, generación de rutas
├── routes/      Rutas web (web/) y API (api/)
├── templates/   Plantillas Jinja2 (las genéricas están en crud/)
├── schemas/     JSON Schemas para validar la API
├── services/    Lógica de negocio que no es CRUD (stock, pedidos…)
├── audit/       Registro de auditoría
└── utils/       Seed de datos iniciales y utilidades
src/sync/        Sincronización de planillas Excel contra la API
ml/              Scripts de análisis
tools/           Herramientas de desarrollo (p. ej. informe de metamodelos)
tests/           Tests automáticos (pytest)
```

## Puesta en marcha

Requiere Python 3.11 o superior.

```bash
python -m venv .venv
source .venv/bin/activate        # en Windows: .venv\Scripts\activate
pip install -r requirements-dev.txt
```

La base de datos es **SQLite**. Por defecto se crea en `instance/fallback.db`; para usar
otra ruta, definí `DATABASE_URL` en un archivo `.env`:

```
DATABASE_URL=sqlite:////ruta/absoluta/mantenimiento.db
SECRET_KEY=una-clave-larga-y-secreta
```

Levantar la aplicación (la base se crea y se cargan los datos iniciales en el primer
acceso):

```bash
python run.py
```

Comandos útiles (`flask --app run <comando>`):

| Comando | Qué hace |
|---|---|
| `create-db` | Crea las tablas que falten |
| `seed` | Carga los datos iniciales (estados, motivos, tipos…) |
| `reset-db` | Borra la base, la recrea y carga los datos iniciales |
| `inspect-db` | Muestra tablas, columnas, claves primarias y foráneas |

## Tests

```bash
python -m pytest
```

Cada test usa una base SQLite en memoria, así que no toca tus datos. Los errores ya
conocidos están marcados como `xfail` con la fase del plan en la que se corrigen: cuando
uno se arregla, pytest avisa para quitar la marca.

Para revisar la coherencia entre los metamodelos y los modelos:

```bash
python tools/crud_shadow.py          # genera informe_sombra.md
```
