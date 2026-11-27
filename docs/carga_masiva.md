# Instructivo: carga masiva de datos

Cómo cargar muchos registros de una vez desde planillas (Excel, SharePoint) en lugar de
hacerlo pantalla por pantalla. La carga se hace desde la consola, con el entorno activado:

```bash
conda activate adminmant
```

Hay tres caminos, según qué se carga:

| Qué se carga | Comando | Ver |
|---|---|---|
| Datos maestros (sectores, activos, materiales, proveedores, planes…) | `flask --app run importar <entidad> archivo.csv` | este instructivo |
| Excel histórico de pedidos (una hoja por pedido) | `flask --app run importar-pedidos Pedidos.xlsx` | [`prompt_copilot_equivalencias.md`](prompt_copilot_equivalencias.md) |
| Presupuestos y facturas leídos con Copilot | `flask --app run importar-documentos documentos.csv documento_lineas.csv` | [`prompt_copilot_documentos.md`](prompt_copilot_documentos.md) |

## Orden de carga (lo más importante)

Una referencia a otra tabla («Sector», «Marca») solo funciona si ese registro **ya está en
la base**. Si no, la importación da `no existe «…»` y no guarda nada. Por eso hay que
cargar en este orden, de arriba hacia abajo. Dentro de un mismo paso, el orden da igual.

| Paso | Entidad (nombre para el comando) | Necesita cargado antes |
|---|---|---|
| 0 | Estados, motivos, tipos de unidad, categorías y tipos de material | Los carga `flask --app run seed` |
| 1 | `cuentas` | — |
| 1 | `sectores` | — |
| 1 | `marcas` | — |
| 1 | `tipos_unidad` (si faltan tipos) | — |
| 1 | `tareas_preventivo` | — |
| 1 | `proveedores` | — |
| 2 | `ubicaciones` | sectores |
| 2 | `unidades_medida` | tipos de unidad |
| 2 | `tipos_activo` | **cuentas** (obligatoria) |
| 2 | `categorias_material` | cuentas (opcional) |
| 2 | `empleados` | sectores (opcional) |
| 2 | `contactos_proveedor` | proveedores |
| 3 | `categorias_activo` | tipos de activo |
| 3 | `tipos_material` | categorías de material |
| 4 | `modelos` | marcas y **categorías de activo** (las dos obligatorias) |
| 4 | `materiales` | categorías de material; opcionales: marcas, tipos, unidades |
| 4 | `planes_preventivos` | categorías de activo; opcional: unidades |
| 5 | `activos` | categorías de activo; opcionales: marcas, modelos, sectores, ubicaciones |
| 5 | `stock_material` | materiales y ubicaciones |
| 5 | `bom_modelo` | modelos y materiales |
| 5 | `planes_modelo` | planes y modelos |
| 5 | `plan_preventivo_tareas` | planes y tareas |
| 6 | `medidores` | activos y unidades |
| 6 | `bom_activo` | activos y materiales |
| 6 | `plan_modelo_materiales` | planes por modelo y materiales |
| 7 | `lecturas_medidor` | medidores |

«Opcional» quiere decir que la columna puede quedar vacía; pero si se completa, ese
registro ya tiene que existir.

**Ojo con `--simular`:** la simulación no guarda nada, así que no sirve para preparar el
paso siguiente. Para simular `ubicaciones`, los sectores tienen que estar importados de
verdad (sin `--simular`). Lo práctico es, paso por paso: simular, corregir, importar, y
recién ahí pasar a la tabla siguiente.

**Referencias dentro de la misma tabla: dos pasadas.** El material genérico
(`materiales`, columna «Genérico») y el plan inferior (`planes_preventivos`, «plan
inferior») apuntan a otra fila de la misma tabla, y el importador no las ve aunque estén
en el mismo archivo. Se hace así:

1. Importar el archivo con esa columna **vacía** (o sin ella).
2. Completarla y volver a importar el mismo archivo: los registros ya existen, así que
   solo se actualiza esa columna.

**Lo operativo va por otro camino.** Pedidos, documentos de proveedores, adjudicaciones y
recepciones no se cargan con `importar`: tienen sus propios importadores (ver la tabla
del principio), y necesitan cargados antes los datos maestros (sectores, empleados,
proveedores, materiales, activos).

## Paso a paso (datos maestros)

1. **Base al día y catálogos cargados** (solo la primera vez, o después de actualizar):

   ```bash
   flask --app run db upgrade
   flask --app run seed
   ```

   `seed` carga los estados, motivos y tipos que usan las demás tablas.

2. **Bajar una plantilla** con las columnas exactas de la entidad. Aunque esté vacía,
   trae los encabezados:

   ```bash
   flask --app run exportar activos activos.csv
   ```

3. **Completar la planilla** en Excel y guardarla como CSV (separado por `;` o `,`).
   Ver «Cómo completar las columnas» más abajo.

4. **Simular** la importación. Valida todo y no guarda nada:

   ```bash
   flask --app run importar activos activos.csv --simular
   ```

5. **Corregir** los errores que informe (cada uno dice la fila y la columna) y volver a
   simular hasta que diga `✔`.

6. **Importar** de verdad:

   ```bash
   flask --app run importar activos activos.csv
   ```

   El resultado dice cuántos registros se crearon, se actualizaron o quedaron sin cambios.

## Cómo completar las columnas

- **Encabezados:** sirve el nombre del campo (`nombre_sector`) o la etiqueta que se ve
  en la app («Nombre del Sector»); no importan mayúsculas ni tildes. Las columnas que no
  reconoce (por ejemplo, las que agrega SharePoint: ID, Creado por…) se ignoran, y el
  resultado las lista en «Columnas ignoradas». Si falta una obligatoria, el error dice
  cómo se tiene que llamar.
- **Referencias a otras tablas:** por **nombre**, no por ID (Sector = «Taller central»,
  Estado = «Activo»). Materiales y activos también se encuentran por código o número.
  Si el nombre coincide con más de un registro (por ejemplo, dos ubicaciones «Depósito»
  en sectores distintos), da error de ambiguo.
- **Números:** formato argentino o con punto decimal: `1.234,5`, `1400`, `12,5`. Lo
  ambiguo o en formato inglés (`1,234.5`) se rechaza.
- **Fechas:** `2026-11-27` o `27/11/2026`.
- **Sí / No:** `Sí`, `No` (también `1`/`0`, `true`/`false`).
- **Celdas vacías:** quedan vacías (si el campo es obligatorio, da error).
- **Codificación:** UTF-8 o la de Excel en Windows; las dos andan.

## Qué pasa al importar

- **No duplica:** cada fila se busca por su clave natural (ej.: el nombre del sector; el
  número de activo; nombre de ubicación + sector). Si ya existe, se actualiza; si no
  cambió, no se toca; si no existe, se crea. Se puede reimportar el mismo archivo las
  veces que haga falta.
- **No borra:** los registros de la base que no están en el archivo quedan como están
  (el resultado avisa cuántos son).
- **Todo o nada:** si una sola fila tiene error, no se guarda ninguna. Se informan todos
  los errores juntos.
- **Queda auditado:** cada cambio figura en la auditoría con usuario «importación» y el
  nombre del archivo como motivo (se cambian con `--usuario` y `--motivo`).

## Ejemplo

`sectores.csv`:

```text
Nombre del Sector;Centro de Costo;Estado
Taller central;CC-100;Activo
Galpón;CC-200;Inexistente
```

```text
$ flask --app run importar sectores sectores.csv --simular
Importación de sectores desde sectores.csv (SIMULACIÓN: no se guardó nada)
  ✘ 1 error/es. No se guardó nada:
    Fila 3 [estado_sector_id]: Estado: no existe «Inexistente».
```

La «Fila» es la línea del archivo (el encabezado es la 1). Se corrige el estado, se
vuelve a simular y, con `✔`, se importa sin `--simular`.

## Problemas frecuentes

| Mensaje | Qué hacer |
|---|---|
| `«xxx» no existe. Disponibles: …` | El nombre de la entidad está mal escrito; usar uno de la lista |
| `falta la columna «…»` | Agregar esa columna o renombrar el encabezado como indica |
| `no existe «…»` en una referencia | Cargar antes ese registro (ver el orden) o corregir el texto |
| ambiguo | Usar un texto más específico (código, número) que identifique un solo registro |
| `debe ser un número` / `una fecha válida` | Revisar el formato de la celda (ver arriba) |

Detalles técnicos del importador: `app/crud/intercambio/csv_entidades.py` y «Carga de
datos (Fase 6)» en [`plan_refactor_crud.md`](plan_refactor_crud.md).
