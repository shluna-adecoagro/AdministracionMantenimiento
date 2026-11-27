# Propuesta: edición en línea (tipo planilla) con htmx

Estado: **acordada (26/11)**; es la fase 13 de `plan_refactor_crud.md`. La demo
(`herramientas/demo_edicion_en_linea/`, Flask + htmx con datos en memoria) muestra cómo se
usa sobre líneas de pedido y destinos, con las mismas reglas de `overrides/pedidos.py`.
Sus `grilla.js` y `grilla.css` son el punto de partida del PR 13.1. Se corre aparte
(`python herramientas/demo_edicion_en_linea/demo.py`); sus pruebas no están en `tests/`.

## Qué resuelve

Cargar y corregir líneas (de pedido hoy; de OT y de solicitudes después) sin abrir un
formulario por fila: moverse con el teclado, editar la celda, guardar al salir. Tres
pantallas lo justifican: **líneas de pedido y sus destinos**, **operaciones y materiales
de la OT** (cuando exista el tramo), y **colas de «a revisar»** de las importaciones.

No reemplaza los formularios: altas de cabecera, datos maestros y todo lo que tenga
pocos registros siguen como están.

## Cómo entra en el metamodelo

Sin rutas a mano (regla del CLAUDE.md): se extiende el framework.

1. **Override:** una clave nueva en la spec, con los campos editables en la grilla.

   ```python
   "pedido_lineas": {
       ...
       "edicion_en_linea": ["material_id", "descripcion", "estado", "motivo_operacion_id", "nro_oc"],
   },
   "pedido_linea_destinos": {
       ...
       "edicion_en_linea": ["cantidad", "destino", "activo_id", "modelo_id", "ubicacion_id",
                            "sector_imputado_id", "cuenta_id"],
   },
   ```

   `EntitySpec` gana `edicion_en_linea: tuple[str, ...] = ()`; el registry verifica que
   sean campos editables (no `solo_lectura`, no `file`).

2. **Rutas genéricas** en `VistasEntidad.registrar`, solo si la spec tiene
   `edicion_en_linea`:

   | Ruta | Devuelve |
   |---|---|
   | `GET /<entidad>/<id>/celda/<campo>` | la celda en edición (`<td>`) |
   | `POST /<entidad>/<id>/celda/<campo>` | la fila entera (`<tr>`), o la fila con la celda en edición y el error (422) |
   | `GET /<entidad>/<id>/fila` | la fila en lectura (para Esc) |

   El POST usa **el mismo camino que el formulario y la API**:
   `coercion.datos_de_entrada(parcial=True)` → `fk.validar_existencia` →
   `servicio.actualizar(registro, {campo: valor}, motivo)`. Así se aplican `completar`,
   `al_guardar`, la auditoría y la traducción de errores de integridad, sin duplicar
   reglas. Se devuelve la fila entera porque cambian las columnas calculadas
   (solicitada, estado visible, «a revisar»).

3. **Plantillas:** `crud/partials/_fila.html` (una fila de listado, reutilizada por
   `listado_subentidad.html` y `listado_entidad.html`) y `crud/partials/_celda_edicion.html`.
   El tipo de control sale del `FieldSpec` (select, fk, number, date, text), con las
   opciones de `fk.opciones_de` (respetando `fk_filtro` y `depende_de`).

4. **JS:** `static/js/grilla.js` (teclado y foco, unas 150 líneas, sin dependencias) y
   **htmx copiado en `static/vendor/`** (sin CDN: la app tiene que andar en la red
   corporativa). No es una dependencia de Python, así que no toca `requirements.txt`.

5. **Tests:** como `test_web_generada.py`: editar, error 422 con la celda abierta, campo
   no editable → 404, auditoría registrada, columna calculada actualizada.

## Borrador y envío a Compras (decidido 26/11)

Lo que se congela es **cada línea al enviarla**, no el pedido entero: así se pueden
agregar líneas olvidadas a un pedido que Compras ya está cotizando.

- **Columna nueva:** `pedido_lineas.enviada_en` (fecha y hora, vacía = borrador). Es lo
  único que se guarda; el estado del pedido sigue siendo el resumen de sus líneas
  («Borrador», «Enviado a Compras · 1 línea sin enviar»). En el histórico se importa con
  la fecha del pedido.
- **Acción del pedido «Enviar a Compras»:** pone `enviada_en` en las líneas en borrador
  no anuladas. El mismo botón sirve para el primer envío y para los agregados.
- **Línea en borrador:** se edita todo, se agregan y sacan destinos, y se puede
  **eliminar** (queda en la auditoría). No se anula.
- **Línea enviada:** material, descripción y cantidades de los destinos congelados; no se
  agregan ni sacan destinos sueltos. La **imputación sigue editable** (activo,
  ubicación, sector, cuenta). No se elimina.
- **Redistribuir** (línea enviada): edita todos los destinos juntos, entre activos y
  talleres; se pueden sumar o sacar destinos, pero el total tiene que seguir igual. Si un
  destino sigue apuntando a lo mismo, conserva su sector y cuenta corregidos. Todo o nada.
- **Anular o cancelar** (línea enviada), siempre con motivo: sin cantidad anula la línea
  entera; con cantidad, la suma a `cantidad_cancelada`. **Si ya hay algo comprado
  (adjudicado), no se anula entera:** solo se cancela hasta lo pendiente de comprar.
- **Para pedir más** de una línea enviada: una línea nueva (queda en borrador).
- El estado de seguimiento (en cotización, ofertas cargadas) solo se edita en líneas
  enviadas.
- Con las recepciones (decidido 26/11, PR 13.4): un destino con recepciones no se saca
  al redistribuir ni baja de lo recibido. Si baja de su `comprada_corregida` (o se
  saca), la corrección se limpia y se avisa: lo comprado vuelve a repartirse en proporción.

## Fases sugeridas

| PR | Alcance |
|---|---|
| A | Framework: spec, rutas, parciales, grilla.js, htmx vendorizado. Se activa en `pedido_lineas` (pestaña «Líneas» del pedido) |
| B | Borrador y envío: `enviada_en` (migración), «Enviar a Compras», campos editables según la línea (`editable_si` en la spec), eliminar en borrador, anular o cancelar con motivo |
| C | Alta rápida (última fila) usando `campos_alta`: material o descripción, cantidad y destino |
| D | Subgrilla de destinos (fila de la línea actualizada fuera de banda, `hx-swap-oob`) y «Redistribuir» |
| E | Pegar líneas (desde un mail o WhatsApp; antes «Pegar desde Excel»): vista previa y confirmación «todo o nada» (`servicio(confirmar=False)`), con un adaptador «pegado» al formato interno común. Ver las notas del PR 13.5 |
| F | Colas de «a revisar» (destinos sin sector o cuenta, materiales sin identificar) |

`editable_si` es una segunda clave de la spec: `{campo: función(registro) → bool}`. La usan
la grilla (celda en gris), las rutas de celda (404) y **también el formulario y la API**
(`servicio.actualizar` rechaza cambiar un campo congelado), para que la regla no dependa
de la pantalla.

## Decisiones (26/11)

1. **Motivo de la modificación:** la edición en línea no pide motivo; la auditoría
   registra el texto fijo «Edición en línea», escrito en el código. **No se agrega al
   catálogo de motivos:** el catálogo es lo que se ofrece en el modal de los formularios,
   y ahí no corresponde. Anular y cancelar siguen pidiendo un motivo de tipo «Anulación»
   (por ejemplo, «Se consiguió por otro canal», que conviene cargar en el catálogo).

2. **Reglas que cruzan campos:** completar el activo (o la ubicación) define el tipo de
   destino, y cambiar el tipo limpia el dato que ya no corresponde. Cambia
   `completar_destino`.

3. **Concurrencia: sin control por ahora.** Los pedidos los carga y edita solo el gestor:
   los mecánicos le mandan lo que necesitan (mail, WhatsApp o, más adelante, la PWA del
   site de mecánicos) y él los supervisa (pide lo que falta) antes de enviarlos a
   Compras. Un pedido que llega desde la PWA entraría en borrador, con su canal, para esa
   revisión. Cuando Compras escriba en la app (estado de seguimiento, nº de OC) toca
   campos distintos de los del gestor; se revisa en ese momento.

4. **Columnas del ERP:** el registry rechaza al arrancar una spec que incluya en
   `edicion_en_linea` una columna cuyo dueño es el ERP (por ejemplo, el importe de una
   línea de solicitud de OC importada). Es una protección del código, no una pantalla.

## Qué se probó en la demo

29 pruebas con el cliente de Flask: edición y normalización del nº de OC, unidad y cuenta
que cambian con el material, error con la celda abierta (422), destino que actualiza su
línea fuera de banda, activo que define el tipo y la sugerencia, alta rápida, pegado con
vista previa; y del 26/11: celdas congeladas en líneas enviadas, imputación editable,
eliminar en borrador (y no en enviadas), envío y agregados posteriores, anular, cancelar
hasta lo pendiente cuando hay compras, y redistribuir (entre activos y talleres, sin
cambiar el total). La primera versión la probó el gestor en el navegador; lo agregado
el 26/11 (botones, «Redistribuir», suma en vivo) solo tiene las pruebas de rutas.
