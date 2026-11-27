# Diseño de tablas: parte operativa (borrador para revisar)

*Versión 5.12, 25/11/2026. Deriva de `docs/vision_conceptual.md` y del estado del repo al commit 45e4dc7 (fase 9, planes preventivos). Reemplaza el "diseño inicial" de las fases operativas de `docs/plan_refactor_crud.md`.*

*Historial: v2 — primer tramo con pedidos, documentos de proveedores y solicitudes de OC; destinos de la línea de pedido (1 : N); tabla de adjudicaciones (N:M). v2.1 — reparto proporcional entre destinos. v3 — convivencia con el ERP; estados como opciones fijas en código. v3.1 — TSV de EAM a demanda; importadores como adaptadores; estado "Enviada a Administración". v4 — ajustes a partir de ejemplos reales (Excel de pedidos y TSV de solicitudes internas). v4.1 — estado histórico por color de pestaña, moneda por formato de celda, rol de Copilot. v5 — la OC entra al primer tramo: una OC por proveedor y, en la práctica, una por presupuesto adjudicado; el nº de OC cruza pedidos, ofertas y solicitudes. v5.1 — columnas que necesita la lectura de PDF (`docs/prompt_copilot_documentos.md`): descuento global, total en USD informado, equipo y horas del medidor en documentos; precio de lista en líneas; presupuesto citado en la OC. v5.2 — estados de la línea de pedido: se guarda solo lo que no deja otro rastro y el resto se calcula; sector de una distribución con centro de costo compartido; costo de un material de stock sin precio en el maestro; cambios previstos al maestro de materiales. v5.3 — unidades de las cantidades entre genérico y presentación; presentación recibida en las recepciones; códigos del ERP vacíos como NULL. v5.4 — una presentación se cuenta por envases; no se adjudica material sin identificar a una línea que pide un genérico. v5.5 — revisión del PR 10.3: el alta de la línea pide la cantidad y el destino principal; sector imputado y cuenta sugeridos y, si no hay de dónde, «a revisar»; motivos de tipo «Anulación»; canal sin «histórico»; el material se muestra como «código — descripción». v5.6 — revisión del PR 10.4: `origen` (del mixin) en lugar de `origen_carga`; proveedor y unidad tal como figuran; motivo de revisión de la lectura; `solicitud_trabajo_id` en la fase 11; acciones para vincular y adjudicar; los documentos revisados no se reimportan. v5.7 — revisión del PR 10.5: reparto con «comprada (corregida)»; material y cantidad por defecto de la recepción; recibir de más se acepta con aviso; «comprado» sin oferta; estado visible calculado; quién recibió, opcional. v5.8 — importación del Excel histórico (PR 10.6): respuestas del gestor a las dudas del análisis; «a revisar (importación)» en pedidos y líneas; reglas de OC, proveedor, estados, precios y destinos del histórico. v5.9 — estado de las ubicaciones (catálogo informativo). v5.10 — estados de proveedor y de contacto; el estado sale de `recursos`. v5.11 — nombre en el ERP de los planes preventivos. v5.12 — activos compartidos entre sectores: un solo sector por activo e imputación de la OT sugerida y editable. v5.13 — fase 13.4: tipo de destino según el dato completado, imputación sugerida de nuevo al cambiar el destino, «Redistribuir» con recepciones y «comprada (corregida)», último destino. v5.14 — fase 13.5: «Pegar líneas» desde un mail o WhatsApp (un renglón por línea, material solo por código exacto, destino «a identificar»).*

## Convenciones (las del repo)

- Tablas en plural y snake_case; PK `<entidad>_id` autoincremental; `uuid`; `creado_en` / `actualizado_en`; `AuditMixin` en todo lo operativo (la auditoría da quién, qué y cuándo de cada cambio de estado).
- Cabecera y líneas como entidad y subentidad (el framework ya lo resuelve).
- **Estados de flujo como opciones fijas en código** (decidido 21/11): select con `options` en el override, no catálogo editable, porque las reglas de la app dependen de ellos.
- **Cantidades derivadas sin columna:** ofertada, adjudicada, recibida y facturada se calculan sumando filas vinculadas (principio "recalcular, nunca incrementar"). Si hace falta por rendimiento, se agrega una caché que se recalcula, nunca un contador.
- **Importación idempotente:** toda tabla que recibe histórico o reportes tiene `origen` (app / histórico / reporte / PDF) y `clave_origen` única (por ejemplo, hoja y fila del Excel, o número del ERP).
- **Vacío es NULL:** en las importaciones, un código opcional vacío (por ejemplo, `codigo_erp` de materiales y proveedores) se guarda como NULL, nunca como texto vacío. Así la restricción de unicidad admite muchos registros sin código y solo controla los cargados.
- **Registros del ERP** (solicitudes de OC, OC, OT): columna `sistema` (EAM / SAP / app) y número del ERP, únicos juntos. Las columnas cuyo dueño es el ERP no se editan en la app: las actualiza la próxima importación. Un registro creado en la app (`sistema` = app) puede recibir después su número del ERP, y la importación lo reconoce en lugar de duplicarlo.
- **Importadores como adaptadores:** un adaptador por fuente (TSV de EAM, PDF de OC, Excel histórico de pedidos, Excel histórico de solicitudes; después, SAP) traduce el archivo a un formato interno común, y un único servicio de importación aplica las reglas de dueño y de claves. Los adaptadores son código determinístico que corre en la computadora del gestor; la IA solo interviene en las interpretaciones dudosas y en la lectura de PDF, siempre con revisión (ver "Rol de Copilot").
- **Texto original siempre guardado:** cuando un dato importado se interpreta (un activo identificado a partir de "Detalles", un material a partir de un código), se guarda también el texto tal cual vino. Lo no identificado queda "a revisar", nunca se descarta.
- **El número de OC es la llave de cruce** entre pedidos, ofertas, solicitudes internas y OC. Se guarda como texto normalizado (sin espacios) en todas las tablas donde aparece, y los vínculos por número se resuelven en consultas.
- Numeración legible generada por la app: `TRA-2026-0001`, `SOL-2026-0001` (esta última solo para solicitudes que nacen en la app). Los pedidos conservan la serie actual del Excel (1104, 1107, 1113...) y los nuevos la continúan.

## Mapa

```
pedidos ──< pedido_lineas ──< pedido_linea_destinos ──< recepciones
                  │
                  └──< adjudicaciones >── documento_lineas >── documentos_proveedor
                                                                  │       │
                                      solicitudes_trabajo ────────┘       │ nro_oc
                                                                          │
       [ERP] solicitudes_oc ──< solicitud_oc_lineas ── nro_oc ──> [ERP] ordenes_compra ──< orden_compra_lineas
                                       └──< solicitud_oc_distribuciones
```

## Relación entre solicitud interna y OC

- **Una OC es de un solo proveedor** (sus datos están en la cabecera). Una solicitud interna, en cambio, puede tener líneas de proveedores distintos: de una solicitud con dos proveedores salen dos OC.
- Probablemente una OC pueda reunir líneas de una o varias solicitudes, siempre del mismo proveedor (a confirmar). El diseño lo admite: cada línea de solicitud guarda su `nro_oc`, y varias líneas pueden apuntar a la misma OC.
- **En la práctica, Compras genera una OC por cada presupuesto u oferta adjudicada**, que puede cubrir una o más líneas de pedido, e indica el presupuesto en las observaciones de la OC. Por eso el nº de OC permite cruzar las líneas de pedido con la oferta que se les adjudicó.

## Primer tramo: pedidos, documentos de proveedores, solicitudes internas y OC

### pedidos (cabecera)

| Columna | Tipo | Notas |
|---|---|---|
| numero | texto, único | Sigue la serie actual del Excel (1104, 1107, 1113...) |
| fecha_pedido | fecha | Fecha del aviso |
| referencia | texto | Título corto del pedido ("Rodamientos", "Filtros Case") |
| solicitante_id | FK empleados, opcional | Quién lo pidió |
| solicitante_texto | texto, opcional | En el histórico suele estar vacío |
| sector_id | FK sectores, opcional | Sector o taller que pide (sugiere el destino de las líneas) |
| canal | opción | WhatsApp / mail / site / app. En el histórico queda vacío (el origen ya dice que es histórico) |
| prioridad | opción | Normal / urgente |
| fecha_requerida | fecha, opcional | |
| observaciones | texto | En el histórico, también las filas del Excel que no son líneas (notas, cantidades sin interpretar) |
| motivo_revision | texto | «A revisar (importación)»: lo que la importación no pudo interpretar (número de la hoja distinto de «Pedido N°», columnas corridas, color sin estado). El gestor lo borra al revisarlo |
| origen, clave_origen | texto | Importación (clave única: `excel_pedidos|<hoja>`; sin el nombre del archivo, para que una versión nueva del Excel actualice en lugar de duplicar) |

El estado del pedido no se guarda: es el resumen de sus líneas ("3 de 5 recibidas").

### pedido_lineas (qué se compra)

Es lo que ve Compras y lo que se cotiza: un material y una cantidad total.

| Columna | Tipo | Notas |
|---|---|---|
| pedido_id | FK, cascada | |
| nro_linea | entero | Único por pedido |
| material_id | FK materiales, opcional | Se identifica por código (por ejemplo, "84228488") o se asigna a mano |
| descripcion | texto | Columna "Producto" tal cual ("Bolillero 32217", "8605140") |
| unidad_medida_id | FK, opcional | La del material (se completa sola); a mano solo si no hay material. Si el material es una presentación, la cantidad se cuenta en envases |
| estado | opción | **Guardado:** solicitado / en cotización / ofertas cargadas / anulado. Ver «Estado de la línea de pedido» |
| sin_conformidad | sí/no | Cierre manual: cerrada en el histórico sin registro de recepción |
| cantidad_cancelada | decimal, 0 | Con motivo |
| motivo_operacion_id | FK motivos, opcional | Motivo de cancelación o anulación: solo motivos de tipo «Anulación». Obligatorio si la línea está anulada o tiene cantidad cancelada |
| nro_oc | texto, opcional | OC con la que se compró (columna "OC" del Excel, o la que carga Compras). Una línea comprada a dos proveedores tiene dos OC: en ese caso el dato sale de las adjudicaciones |
| observaciones | texto | En el histórico, el texto original de lo que no se interpretó («Recibido?», precios ilegibles, columnas corridas) |
| motivo_revision | texto | «A revisar (importación)»: cantidad sacada del texto, dos OC en una celda, OC que no se pudo deducir, etc. El gestor lo borra al revisarlo |
| origen, clave_origen | texto | Histórico: `excel_pedidos|<hoja>|f<fila>` |
| enviada_en | fecha y hora, opcional | Vacía = borrador. La pone «Enviar a Compras» (decidido 26/11); no se edita. En el histórico, la fecha del pedido |

Derivadas: **solicitada** (suma de los destinos), ofertada, adjudicada, recibida, pendiente de comprar, pendiente de recibir y el **estado visible**.

#### Estado de la línea de pedido (decidido 22/11)

Se guarda solo lo que no deja otro rastro; lo demás se calcula de los datos.

| Estado | Cómo se obtiene |
|---|---|
| Solicitado | Guardado (al crear la línea) |
| En cotización | Guardado (lo marca Compras o el gestor) |
| Ofertas cargadas | Guardado (Compras terminó de cargar las ofertas; las revisa el gestor) |
| Anulado | Guardado, con motivo. Prevalece sobre todo lo demás |
| Adjudicado | Calculado: tiene adjudicaciones con cantidad mayor que cero |
| OC emitida | Calculado: tiene nº de OC (propio o de sus adjudicaciones) |
| Recibido parcial / recibido | Calculado: tiene recepciones, por menos o por el total adjudicado |
| Cerrado | Calculado: no queda nada pendiente de comprar ni de recibir, o `sin_conformidad` (cierre manual del histórico) |

Prioridad del estado visible (decidido 23/11; «borrador», 26/11): anulado → borrador → cerrado → recibido → recibido parcial → OC emitida → adjudicado → el guardado. **Comprado** = la adjudicada si hay adjudicaciones; si no (compra directa o histórico), la solicitada menos la cancelada, pero solo si ya hay nº de OC o recepciones. Pendiente de comprar = solicitada − cancelada − comprado; pendiente de recibir = comprado − recibido. «OC emitida»: la línea o una oferta adjudicada tiene nº de OC. En la app, el guardado se llama «Estado de seguimiento» y el visible, «Estado».

- **El estado visible es el calculado.** El guardado solo cuenta mientras no haya datos posteriores (adjudicaciones, OC, recepciones).
- **Salteo de estados:** también se calcula (por ejemplo, una línea adjudicada que nunca pasó por «en cotización»). Ya no hay columna `estado_salteado`.
- **Tiempos por etapa:** salen de la auditoría de los estados guardados y de las fechas de adjudicaciones, OC y recepciones.

#### Borrador y envío a Compras (decidido 26/11)

Se congela **cada línea al enviarla**, no el pedido entero: así se pueden agregar líneas
olvidadas a un pedido que Compras ya está cotizando. El gestor carga y supervisa los
pedidos que le mandan los mecánicos (mail, WhatsApp o, más adelante, la PWA del site de
mecánicos; los de la PWA entran en borrador) y los envía cuando están completos.

- **«Enviar a Compras»** (acción del pedido): pone `enviada_en` en las líneas en borrador
  no anuladas. Sirve para el primer envío y para los agregados.
- **Línea en borrador:** se edita todo, se agregan y sacan destinos, y se puede
  **eliminar** (queda en la auditoría). No se anula. El estado de seguimiento no se edita.
- **Línea enviada:** material, descripción y cantidades de los destinos congelados (en la
  web, la API y la importación CSV); no se agregan ni sacan destinos sueltos. La
  **imputación sigue editable** (activo, modelo, ubicación, sector imputado, cuenta). No
  se elimina. El material vacío **se puede completar** (identificar el material de las
  líneas del histórico), pero no cambiar (decidido 26/11).
- **Importación del histórico (decidido 26/11):** queda fuera de estas reglas: sus líneas
  nacen enviadas con la fecha del pedido y, para ellas, la fuente es el Excel. Las líneas
  que existían antes de la fase 13.2 quedaron enviadas con la fecha de su pedido.
- Un pedido con líneas enviadas no se elimina.
- **Redistribuir** (línea enviada, no anulada ni cerrada): cambia todos los destinos
  juntos (entre activos, modelos y talleres), con altas y bajas de destinos, sin cambiar
  el total; tiene que quedar al menos uno. Un destino que sigue apuntando a lo mismo
  conserva su tipo, sector y cuenta; si apunta a otro, se vuelven a sugerir. Todo o nada.
  Con las recepciones (decidido 26/11): un destino con recepciones no se saca ni baja de
  lo recibido. Si un destino baja de su «comprada (corregida)», o se saca, la corrección
  se limpia con un aviso (lo comprado vuelve a repartirse en proporción).
- **Línea en borrador:** el último destino no se elimina (para eso se elimina la línea).
- **Anular o cancelar** (línea enviada), con motivo de tipo «Anulación»: sin cantidad anula
  la línea entera; con cantidad, la suma a `cantidad_cancelada`. **Si ya hay algo
  comprado no se anula entera:** solo se cancela hasta lo pendiente de comprar.
- **Para pedir más** de una línea enviada: una línea nueva (nace en borrador).
- **«Pegar líneas» (decidido 27/11):** reemplaza el paso por la planilla de pedidos.
  Se pegan solo los renglones del pedido, copiados de un mail o de WhatsApp: **un
  renglón, una línea**, «cantidad código o descripción» («4 filtros RE504836»). La
  descripción guarda el texto tal cual (sin el punto final ni espacios de más). El
  material se identifica solo si una palabra es exactamente el código de un único
  material del maestro; si no, la línea queda sin material. **El destino no se adivina:**
  cada línea nace con un solo destino «a identificar» por toda la cantidad, sin texto
  (los títulos del mensaje no se pegan): queda a revisar hasta que el gestor lo complete
  en la subgrilla o con «Redistribuir». Con tabuladores (desde una planilla), la primera
  celda con un número es la cantidad y las demás forman la descripción. Primero se ve una
  vista previa; un renglón sin cantidad al principio, con cantidad cero o sin texto
  bloquea la carga (todo o nada). Aviso, sin bloquear, si una línea es igual a otra del
  pedido (mismo material o descripción y misma cantidad): pegar dos veces el mismo
  mensaje duplicaría las líneas. Nacen en borrador, con origen «app», sin clave de
  origen; la auditoría registra «Líneas pegadas».
- **Estado visible «Borrador»** mientras la línea no se envió (decidido 26/11). El estado
  del pedido sigue sin guardarse: el resumen dice «Borrador: 3 líneas» si ninguna se
  envió, o «5 líneas: 1 en borrador, 3 solicitadas, 1 anulada».
- «Enviar a Compras» envía también las líneas con destinos «a revisar», con un aviso
  (decidido 26/11).
- Las reglas de anular y cancelar las aplica el servicio (web, API, CSV); la pantalla
  usa la acción «Anular o cancelar». La grilla no ofrece «Anulado» en el estado.

### pedido_linea_destinos (adónde va y quién paga)

Una línea de pedido tiene uno o más destinos. Ejemplos reales: "Carros de arena A1E3, A4E3, A5E3, A7E3" (cuatro activos), "Molienda" (una instalación o sector), "W20F" o "580" (un modelo), o una imputación "50% CC-01, 50% CC-02".

| Columna | Tipo | Notas |
|---|---|---|
| pedido_linea_id | FK, cascada | |
| cantidad | decimal | La suma de los destinos es la cantidad solicitada de la línea |
| destino | opción | Activo / modelo / stock / gasto general / a identificar |
| activo_id | FK activos, opcional | Obligatorio si destino = activo |
| modelo_id | FK modelos, opcional | Compras para la flota de un modelo ("filtros para las 580") |
| ubicacion_id | FK ubicaciones, opcional | Taller que recibe; obligatoria si destino = stock |
| detalle_texto | texto | Columna "Detalles" tal cual |
| sector_imputado_id | FK sectores, opcional | Quién paga. Si llega vacío se completa con la sugerencia: sector del activo, o el de la ubicación, o el del pedido |
| cuenta_id | FK cuentas, opcional | Si llega vacía se completa con la sugerencia: cuenta del tipo de activo (del activo o del modelo), o la de la categoría del material |

- Derivadas por destino: recibida y pendiente de recibir. Así cada taller da la conformidad de su parte; y **«a revisar»**: destino «a identificar», o sin sector imputado o sin cuenta (cuando no hubo de dónde sugerirlos).
- **Alta de la línea (decidido 23/11):** el alta de una línea pide la cantidad y el destino principal (activo, modelo, stock con su ubicación, gasto general o a identificar) y crea su primer destino con toda la cantidad. Para repartir entre varios destinos se usa la pestaña «Destinos» de la línea.
- El activo y la ubicación no corrigen el sector imputado: quien paga puede ser otro sector (préstamos).
- **Tipo de destino (decidido 26/11):** completar el activo o el modelo define el tipo de destino (para poder editar celda por celda); completar la ubicación, solo si el destino estaba «a identificar» (pasa a «stock»): en un activo, un modelo o un gasto general la ubicación es el taller que recibe. Cambiar el tipo limpia el activo o el modelo que ya no corresponde; la ubicación, nunca. Si cambia a qué apunta el destino (activo, modelo o ubicación), el sector imputado y la cuenta se vuelven a sugerir, salvo que se cambien en la misma operación.
- **Compra parcial (decidido 21/11):** si se adjudica menos de lo solicitado, la app reparte lo comprado entre los destinos **en proporción** a sus cantidades; el gestor lo corrige. Para materiales que se cuentan por unidad, el reparto se redondea a enteros y el resto va al primer destino.
- **Corrección del reparto (decidido 23/11):** columna `comprada_corregida` (opcional) en el destino: si está cargada manda, y el resto se reparte entre los demás. Se cuenta por unidad si el material es una presentación (envases), si la unidad es de tipo «Cantidad» o si no hay unidad. El reparto no se guarda: se calcula.

### documentos_proveedor (cabecera)

Ofertas, presupuestos de trabajos, remitos y facturas.

| Columna | Tipo | Notas |
|---|---|---|
| tipo | opción | Oferta / presupuesto de trabajo / remito / factura |
| proveedor_id | FK proveedores, opcional | Identificado por CUIT, código del ERP o razón social. Sin él, el documento no se puede marcar revisado |
| proveedor_texto, proveedor_cuit | texto | Tal como figuran (decidido 23/11: si no se identifica, no se descarta) |
| numero | texto, opcional | Único por proveedor y tipo cuando existe. Las ofertas reconstruidas del histórico no tienen número |
| fecha | fecha | |
| moneda | opción | ARS / USD |
| moneda_inferida | sí/no | La moneda se dedujo (histórico) y conviene revisarla |
| tipo_cambio | decimal, opcional | |
| total_sin_iva, iva, total | decimal | Tal cual figuran en el documento |
| descuento_global_pct | decimal, opcional | Descuento general del documento (por ejemplo, 26,20 % en las ofertas de Lange) |
| total_usd_informado | decimal, opcional | Total equivalente en dólares que informa el documento; con `total` da el tipo de cambio implícito |
| equipo_texto | texto, opcional | Patente, serie, modelo o código de equipo tal como figura; sirve para identificar el activo |
| horas_medidor | decimal, opcional | Horas del equipo al hacer el service ("SERVICIO 15644 HS"); alimenta la última ejecución del plan |
| plazo_entrega_dias, validez_hasta | opcionales | Ofertas |
| solicitud_trabajo_id | FK, opcional | Presupuesto del trabajo de un contratista. **Se agrega en la fase 11**, con la tabla de solicitudes de trabajo |
| nro_oc | texto, opcional | En ofertas y presupuestos: la OC que se emitió por ellos (una por presupuesto adjudicado). En remitos y facturas: la OC que referencian |
| archivo | archivo (PDF) | El framework ya permite adjuntos |
| origen, clave_origen | | Del mixin (decidido 23/11, reemplaza a `origen_carga`): manual o mail → app; IA → PDF (clave = `clave_documento` de Copilot); histórico → histórico |
| revisado | sí/no | "La IA propone, una persona confirma". Pide proveedor identificado, fecha y moneda. **Un documento revisado no se reimporta** |
| motivo_revision | texto | La columna `revisar` de la lectura con Copilot |
| observaciones | texto | |

Derivadas: total de líneas, diferencia con el total (control de carga), total adjudicado.

### documento_lineas

| Columna | Tipo | Notas |
|---|---|---|
| documento_id | FK, cascada | |
| nro_linea | entero | |
| tipo_linea | opción | Material / mano de obra / traslado / otro |
| material_id | FK, opcional | Vacía si no se identificó: queda "a revisar" |
| codigo_proveedor, descripcion_proveedor | texto | Tal cual vienen |
| cantidad | decimal | En ofertas, lo ofertado (puede ser menor a lo pedido). Si el material es una presentación, en envases |
| udm_texto | texto | La unidad tal como figura |
| unidad_medida_id | FK, opcional | La del material (se completa sola). Una línea de oferta nunca tiene un genérico |
| precio_lista | decimal, opcional | Unitario antes de descuentos, sin IVA |
| descuento_pct | decimal, opcional | Descuento efectivo total sobre el precio de lista (de línea y global) |
| precio_unitario | decimal | Neto, sin IVA, después de todos los descuentos. Es el que usa el historial de precios |
| activo_id | FK, opcional | En presupuestos de service, si detalla el equipo |
| confianza | decimal, opcional | Extracción automática |
| motivo_revision | texto | La columna `revisar` de la lectura; también «el material sugerido no está en el maestro» |

Derivada: subtotal = cantidad × precio_unitario (el descuento ya está aplicado en el precio neto; no se aplica dos veces).

### adjudicaciones (qué se compra de cada oferta, para qué línea de pedido)

Relación N:M entre líneas de oferta y líneas de pedido. Cubre una oferta que cotiza juntas líneas de varios pedidos y una línea de pedido comprada a dos proveedores.

| Columna | Tipo | Notas |
|---|---|---|
| documento_linea_id | FK documento_lineas | Línea de una oferta |
| pedido_linea_id | FK pedido_lineas | |
| cantidad_ofertada | decimal, opcional | Si la oferta reparte su renglón entre líneas de pedido |
| cantidad_adjudicada | decimal, 0 | Lo que el gestor confirma, en la unidad de la línea de oferta (envases, si es una presentación). 0 = cotizado, no comprado |

- `cantidad_adjudicada` está en la unidad de la línea de oferta (la presentación ofertada). La adjudicada de la línea de pedido es la suma de esas cantidades **convertidas a la unidad de la línea de pedido** (ver «Unidades: genérico y presentación»).
- Total adjudicado de una oferta = suma de `cantidad_adjudicada × precio neto` de sus líneas.
- **Acciones del documento (decidido 23/11):** «Vincular con pedidos» crea en 0 las adjudicaciones con las líneas de pedido abiertas del mismo material (o del genérico de la presentación); «Adjudicar lo vinculado» pone lo que falta comprar, sin superar lo ofertado y en envases enteros si es una presentación. El gestor corrige después.
- **Reparto entre destinos:** lo adjudicado se calcula por línea; el reparto proporcional por destino llega con las recepciones (PR 10.5).
- **En el histórico, el nº de OC reconstruye la adjudicación:** una línea de pedido con OC X se vincula con la oferta del mismo proveedor que tiene OC X (o que la OC X cita en sus observaciones).

### Unidades: genérico y presentación (decidido 23/11)

- **Del lado del pedido, todo se expresa en la unidad de la línea de pedido:** solicitada, cantidades de los destinos, adjudicada, recibida y pendientes.
- **La oferta y la recepción guardan su cantidad en su propia unidad** (la de la presentación ofertada o recibida).
- Si la línea pide un **genérico** y se adjudica o se recibe una **presentación**, la cantidad se convierte con `presentacion_cantidad`: 2 bidones de 20 L = 40 L.
- Si la línea pide la misma presentación que se adjudica, no hay conversión.
- Para que la conversión sea posible, la unidad de una presentación es la de su genérico (se verifica en el maestro de materiales).
- **Una presentación se cuenta por envases.** Su `unidad_medida` es la del **contenido** y `presentacion_cantidad` es cuánto contiene cada envase: «bidón 20 L» tiene unidad L y `presentacion_cantidad` 20. En una oferta o una recepción de esa presentación, «2» son **dos bidones** (40 L). Por eso, cuando el material es una presentación, la pantalla de ofertas y de recepciones rotula la cantidad **«Cantidad (envases)»**.
- **Material sin identificar:** una línea de oferta sin `material_id` («a revisar») **no se puede adjudicar a una línea de pedido que pide un genérico**, porque no hay de dónde convertir; primero hay que identificar el material. Si la línea de pedido pide un material concreto (no genérico), sí se puede, y la cantidad se toma tal cual (sin conversión).

### recepciones (conformidad de materiales)

Una fila por entrega y por destino; admite entregas parciales.

| Columna | Tipo | Notas |
|---|---|---|
| pedido_linea_destino_id | FK | Qué destino recibe |
| fecha | fecha | |
| material_id | FK materiales | Lo que llegó: nunca un genérico. Si se deja vacío: la presentación adjudicada (si hay una sola) o el material de la línea (si es concreto); si no, se pide |
| cantidad | decimal | **En la unidad de `material_id`** (por ejemplo, 2 bidones). Por defecto, lo pendiente de recibir del destino, convertido |
| recibido_por_id | FK empleados, opcional | El gestor puede cargarla sin saber quién recibió |
| documento_linea_id | FK, opcional | Línea del remito (solo líneas de remitos) |
| observaciones | texto | Faltantes, roturas |

- **Recibir de más (decidido 23/11):** se acepta, con un aviso: la conformidad es registrar lo que llegó.
- Comparando la fecha de recepción con la fecha de entrega comprometida en la OC se mide el **cumplimiento de entrega** de cada proveedor (fase 11, cuando llegan las OC).

### solicitudes_trabajo

Aviso de un mecánico de que hay que llamar a un contratista (equivalente al aviso de SAP PM). Se implementa en la fase 11, junto con los presupuestos de trabajo.

| Columna | Tipo | Notas |
|---|---|---|
| numero | texto, único | TRA-AAAA-NNNN |
| fecha_aviso | fecha | Cuando se llamó al contratista |
| solicitante_id / solicitante_texto | | |
| activo_id | FK, opcional | Opcional para trabajos en instalaciones sin activo cargado |
| proveedor_id | FK proveedores | Contratista llamado |
| descripcion | texto | Qué pasa |
| sector_imputado_id, cuenta_id | FK | Sugeridos como en los destinos de pedido |
| regularizada | sí/no | Nació del presupuesto |
| estado | opción | Registrada / presupuesto recibido / validada / observada / con solicitud de OC / cerrada / anulada |
| validado_por_id, fecha_validacion, observacion_validacion | | Conformidad del jefe de taller |
| origen, clave_origen | | Histórico |

Cuando exista la OT, se agrega `ot_id`.

### solicitudes_oc (cabecera)

**Dueño de la cabecera: el ERP.** Se crea en EAM (después SAP), se importa desde el TSV de cabeceras y se completa en la app. Las que hoy se hacen por el Excel compartido nacen en la app (`sistema` = app).

| Columna | Tipo | Dueño | Notas (columna del TSV) |
|---|---|---|---|
| sistema | opción | — | EAM / SAP / app / Excel histórico |
| nro_solicitud_erp | texto | ERP | "Número". Único junto con `sistema` |
| numero_app | texto, único con blancos | App | SOL-AAAA-NNNN, solo si nace en la app |
| descripcion | texto | ERP | "Descripción" ("Reparaciones de motos", "Flete por pedido 1086") |
| fecha_creacion | fecha/hora | ERP | "Fecha Creación" (formato dd-mm-aaaa hh:mm:ss) |
| estado_aprobacion | texto | ERP | "Estado Aprobación" (espejo) |
| cancelada, cerrada | texto / sí-no | ERP | "Cancelado", "Cerrado" |
| tipo | opción | App | Materiales / servicio / regularización |
| estado | opción | App | Solicitud generada (solo app) / cargada en ERP / enviada a Administración / OC emitida / anulada |
| fecha_envio_administracion | fecha | App | |
| pedido_id | FK, opcional | App | Sugerido si la descripción menciona un pedido ("por pedido 1086") |
| fecha_importacion | fecha/hora | — | Última importación |
| origen, clave_origen | | — | |
| observaciones | texto | App | |

Derivados: total (suma de líneas), proveedores (de las líneas), "OC emitida" cuando todas las líneas tienen número de OC.

**Detalle para Administración:** reemplaza el armado manual (TSV → Excel → mail). La app genera, desde la solicitud importada, el detalle de cabecera, líneas y distribuciones con los documentos adjuntos, listo para enviar.

### solicitud_oc_lineas

| Columna | Tipo | Dueño | Notas (columna del TSV) |
|---|---|---|---|
| solicitud_oc_id | FK, cascada | — | Por "Número" |
| nro_linea | entero | ERP | "Línea". Único por solicitud |
| org_solicitante | texto | ERP | "Org Solicitante" |
| nro_ot_erp | texto | ERP | "Trabajo/Lote": nº de OT de EAM. Cuando exista la OT en la app, se vincula (y a su operación) |
| descripcion | texto | ERP | "Descripción" |
| cantidad, udm | | ERP | "Cantidad", "UDM" |
| precio, importe | decimal | ERP | "Precio", "Importe" (en moneda local; el TSV trae miles con coma: 1,090,000.00) |
| precio_divisa, importe_divisa, divisa | | ERP | "Precio Divisa", "Importe Divisa", "Divisa" |
| proveedor_texto | texto | ERP | "Proveedor" (razón social) |
| proveedor_id | FK, opcional | App | Identificado por la razón social |
| nro_oc | texto | ERP | "Número Pedido" = nº de OC (confirmado). Llega con el reporte cuando se emite |
| documento_id | FK documentos_proveedor, opcional | App | El gestor vincula la línea con la oferta adjudicada o el presupuesto |
| importe_adjudicado | decimal | App | **Copiado** del total adjudicado del documento al vincular |
| clave_origen | texto | — | Sistema + nº de solicitud + nº de línea |

- Proveedor y nº de OC están **por línea**: una misma solicitud puede tener líneas de distintos proveedores y generar más de una OC.
- Diferencia entre `importe` e `importe_adjudicado`: control de lo cargado en el ERP contra lo adjudicado.
- Regla: un documento no puede estar vinculado a dos líneas activas.
- **Antes de cargar en el ERP**, la app ofrece una vista de "solicitud propuesta" (líneas, importes y distribución desde lo adjudicado) para copiar en EAM. No se guarda como registro.

### solicitud_oc_distribuciones

Se importan del TSV de distribuciones (dueño: ERP). En las solicitudes que nacen en la app, se guardan con origen app.

| Columna | Tipo | Notas (columna del TSV) |
|---|---|---|
| solicitud_oc_linea_id | FK, cascada | Por número de solicitud + línea |
| nro_distribucion | entero | Tercera columna |
| combinacion_contable | texto | La cadena completa, tal cual (XXX-cuenta-XX-XXX-XXXXX-centro_costo-000000-0) |
| numero_cuenta | texto | Segmento 2 de la combinación |
| centro_costo | texto | Segmento 6 de la combinación |
| cuenta_id | FK, opcional | Identificada por el número |
| sector_id | FK, opcional | Identificado por el centro de costo **solo si corresponde a un único sector**; si no, vacío (decidido 22/11) |
| cantidad | decimal | Como en el ERP: con una línea de cantidad 1, las fracciones (0,25 / 0,25 / 0,5) son los porcentajes |
| udm | texto | |
| origen | opción | ERP / app |
| clave_origen | texto | Sistema + solicitud + línea + distribución |

Derivados: porcentaje = cantidad / cantidad de la línea; importe = porcentaje × importe de la línea.

**Centro de costo compartido:** dos sectores pueden compartir centro de costo (contablemente son lo mismo). En ese caso `sector_id` queda vacío y se conserva el texto (`centro_costo`); el sector para el análisis sale del destino del pedido o de la solicitud de trabajo.

**Distribución propuesta:** la app la calcula (no se guarda) desde los destinos de lo adjudicado, agrupando por sector imputado y cuenta. Se muestra para cargarla en EAM y, después de importar, se compara con la real.

### ordenes_compra (cabecera, espejo del ERP)

Dueño: el ERP. Fuentes: el PDF de la OC que Compras manda por mail (leído con Copilot y revisado) y, si se consigue, el reporte de OC emitidas. Es el documento contra el que se pagan las facturas.

| Columna | Tipo | Notas |
|---|---|---|
| sistema, nro_oc | texto | Únicos juntos |
| fecha | fecha | |
| proveedor_id | FK proveedores, opcional | Identificado por CUIT o código del ERP |
| proveedor_texto, proveedor_cuit, proveedor_codigo_erp | texto | Tal cual la OC (también dirección, localidad y contacto si se quieren guardar) |
| comprador | texto | Nombre del comprador |
| plazo_pago | texto | |
| moneda | opción | |
| total | decimal | |
| observaciones | texto | Suelen citar el presupuesto u oferta |
| presupuesto_citado | texto, opcional | Referencia al presupuesto tal como figura en las observaciones |
| documento_id | FK documentos_proveedor, opcional | Presupuesto u oferta citada en las observaciones (sugerida; la confirma el gestor) |
| archivo | archivo (PDF), opcional | La OC recibida por mail |
| origen | opción | PDF / reporte |
| revisado | sí/no | Para las leídas con IA |
| fecha_importacion | fecha/hora | |

### orden_compra_lineas

| Columna | Tipo | Notas |
|---|---|---|
| orden_compra_id | FK, cascada | |
| item | entero | Único por OC |
| descripcion | texto | |
| udm | texto | |
| cantidad | decimal | |
| lugar_entrega | texto | |
| fecha_entrega | fecha | Fecha comprometida: base del cumplimiento de entrega |
| precio_unitario | decimal | |
| total | decimal | Precio × cantidad |
| solicitud_oc_linea_id | FK, opcional | Si se puede identificar la línea de la solicitud de origen |

**Cruces por nº de OC:** líneas de pedido (`pedido_lineas.nro_oc`), ofertas y presupuestos (`documentos_proveedor.nro_oc`) y líneas de solicitud (`solicitud_oc_lineas.nro_oc`). Con esos cruces se detectan OC sin pedido ni solicitud, pedidos con un nº de OC que no existe y diferencias entre lo adjudicado y lo ordenado.

### Cambios a tablas existentes

- `proveedores`: agregar `codigo_erp` (código interno del proveedor en el ERP, figura en la OC; vacío = NULL). El CUIT ya existe.
- `categorias_material`: agregar `cuenta_id` (opcional), para sugerir la cuenta sin activo.
- `materiales`: agregar `controla_stock` (sí/no). **El maestro no guarda precios** (ver «Costo de un material de stock»).
- **Maestro de materiales (decidido 22/11; se implementa en la fase 10):**
  - `codigo` es el **número de parte** (código del fabricante) y sigue siendo la clave natural. Se agrega `codigo_erp` (código en EAM/SAP, opcional, único cuando está cargado; vacío = NULL).
  - **Genérico y presentaciones:** el genérico es una fila de `materiales` marcada `es_generico` («Aceite 15W-40», en litros, sin envase; código con prefijo `GEN-`). Sus presentaciones comprables apuntan a él con `material_generico_id` («Aceite 15W-40 bidón 20 L», `presentacion_cantidad` 20 en litros). Un genérico no tiene genérico propio, la FK de una presentación solo acepta genéricos y la unidad de la presentación es la del genérico (base de la conversión de cantidades).
  - **Dónde se usa cada uno:** el BOM y los planes preventivos pueden usar el genérico (la cantidad no depende del envase). Ofertas, stock y recepciones usan siempre la presentación. Una línea de pedido puede pedir cualquiera de los dos; la presentación se define al adjudicar.
  - Los modelos aplicables no son una columna: salen del BOM por modelo.
  - Después, los prompts de Copilot usan el export de la app (`flask exportar materiales`) en lugar del maestro anterior.
- `ubicaciones` (decidido 25/11): agregar `estado_ubicacion_id` (FK a `estados_ubicacion`, obligatorio): **Operativa**, **En mantenimiento** o **Inactiva**. Es un **catálogo editable** (nombre y color, como los estados de sector, activo, cuenta y recurso) y no una opción fija en código, porque es **informativo**: ninguna regla depende de él (una ubicación inactiva sigue pudiendo ser destino de stock o tener activos). Si más adelante alguna regla lo usa, pasa a opción fija. Sin estado, la ubicación queda «Operativa» (alta web preseleccionada, API, CSV y altas desde el código); al modificar, un estado vacío mantiene el que tenía. El porqué de cada cambio queda en la auditoría con su motivo de operación; no hay columna de observaciones.
- `proveedores` y `contactos_proveedor` (decidido 25/11): estado propio, obligatorio, en catálogos editables e **informativos**, como el de las ubicaciones.
  - Proveedor: `estado_proveedor_id` → `estados_proveedor`: **Activo** (por defecto), **Retenido**, **Inactivo**. «Retenido» significa que no se le puede adjudicar una oferta ni emitir una OC; **por ahora no se controla** (ver «Abierto»).
  - Contacto: `estado_contacto_id` → `estados_contacto`: **Disponible** (por defecto), **No disponible**. También se agrega `division` (texto, opcional).
  - El estado deja de estar en `recursos` (común a empleados y proveedores, «Activo / Suspendido / Inactivo»): los empleados conservan `estados_recurso`, ahora en `empleados.estado_recurso_id`. Al migrar, cada proveedor toma el estado del mismo nombre y «Suspendido» pasa a «Retenido».
- `planes_preventivos` (decidido 25/11): agregar `nombre_erp` (texto, opcional, **único cuando está cargado**; vacío = NULL): la descripción del plan en el ERP, para reconocerlo en las OT importadas. Equivalencia **1:1**: en EAM los planes se definen por grupos de activos, que hoy coinciden con los planes de la app. La carga el gestor (dueño: la app), en la app o por CSV (la columna «NombreERP» de la planilla de SharePoint es alias). EAM y SAP no conviven: con SAP PM se reemplaza por la descripción de SAP, sin columna `sistema`.
- Borrar `Pedido` / `PedidoDetalle`, `pedidos_service.py`, `pedidos_routes.py` y su schema (nunca se registraron; los reemplaza este diseño).

## Importación del Excel histórico de pedidos

### Formato observado (una hoja por pedido)

- Cabecera con etiquetas y valor al lado: "Pedido N°", "Fecha", "Referencia", "Solicitante(s)".
- Tabla desde la fila de encabezado que empieza con "Cantidad": Cantidad, Producto, Detalles, Imputación (Cuenta, Sector), PROVEEDOR, IMPORTE **o una columna por proveedor cotizado**, OC, Recibido?, Observaciones.
- **Celdas combinadas:** "Detalles", "Cuenta", "Sector", "PROVEEDOR" y "OC" suelen abarcar varias filas; el adaptador repite el valor en cada fila que cubre.
- Fila de totales al final (se ignora). "Recibido?" y "Observaciones" casi no se usan.
- **El color de la pestaña indica el estado del pedido.**

### Reglas (actualizadas 23/11 con las respuestas del gestor; ver `docs/analisis_excel_pedidos.md`)

Comando: `flask --app run importar-pedidos Pedidos.xlsx [--equivalencias equivalencias_revisadas.csv] [--simular]`. Deja `pendientes.csv` (para Copilot) e `informe_pedidos.csv` (avisos por hoja y fila). Adaptador en `app/crud/intercambio/excel_pedidos.py`; reglas en `app/crud/intercambio/pedidos_historicos.py`.

| Dato | Regla |
|---|---|
| Número | El del nombre de la hoja; si «Pedido N°» no coincide, se avisa («a revisar»). El sufijo del nombre («- NO», «hierros») va a observaciones. Si el número ya existe en un pedido cargado en la app, la hoja no se importa |
| Estado por color de pestaña | Por tono, sin importar la tonalidad. **Verdes y azules → cerradas**: `sin_conformidad` (cierre manual, sin recepciones), salvo que «Recibido?» diga que no llegó («NO», «KO», «falta…»): entonces quedan abiertas y a revisar. **Amarillo y naranja → en proceso**: se guarda «en cotización»; con OC, el estado visible es «OC emitida». **Rojos → anuladas**, con el motivo «Anulado en el Excel histórico» (lo crea la importación). **Sin color → solicitado**, aunque el pedido sea viejo. Otro color → solicitado y a revisar |
| «Recibido?» | «ok» (también «OK 20-05») → cierre manual, sin recepción (no hay fecha y falsearía los tiempos). El texto siempre se guarda en las observaciones de la línea |
| OC | El número de la columna «OC» va a `pedido_lineas.nro_oc` y a la oferta adjudicada. **En las hojas cerradas, la OC escrita en una fila vale para las demás**: con una sola OC en la hoja, para todas; con varias, para las filas del mismo proveedor si ese proveedor tiene una sola; si no, la fila queda sin OC y a revisar. En las hojas en proceso no se completa (la línea sin OC puede no estar comprada). Dos OC en una celda: la primera, a revisar. Textos («Solicitada») → observaciones y a revisar |
| Proveedor | Una OC es de un solo proveedor: la fila sin proveedor toma el de su OC, si en la hoja esa OC tiene uno solo |
| Precios | «IMPORTE» es unitario, salvo que la hoja lo sume con `SUM(importe)` (entonces es el total de la línea) o que haya «PU» (el unitario es «PU»). Un precio en texto («USD 1.429,7520») se lee; si no se puede, va a observaciones y a revisar |
| Ofertas | Una oferta reconstruida por proveedor y OC, con la fecha del pedido, origen histórico y sin número. El precio de la columna de precio es del proveedor de «PROVEEDOR»: se adjudica toda la cantidad. Las columnas de otros proveedores (a la derecha, o una por proveedor como en el 1104) son ofertas sin OC adjudicadas en 0 (cotizado, no comprado); una columna con el mismo precio que el elegido es el mismo proveedor escrito de otra forma. Sin proveedor, el precio va a observaciones. Las líneas anuladas no generan ofertas (los precios van a observaciones). Una oferta revisada no se reimporta |
| Moneda | Por el formato de la celda: «$» → ARS; «[$USD]» → USD; sin símbolo → USD inferida, salvo que otra celda de precio de la fila tenga «$» (ARS inferida). Siempre `moneda_inferida` cuando no hay símbolo; se termina de resolver al cruzar con las OC (fase 11) |
| Hojas con columnas corridas | (Encabezados que no coinciden con el contenido, como el 1103.) Se importan cantidad, producto, detalles e imputación; precios, proveedor y OC quedan sin interpretar, con el texto original en las observaciones de la línea, y la hoja a revisar |
| Filas sin cantidad | Si el texto del producto empieza con un número, esa es la cantidad («2 tambor plus 50» → 2 × «tambor plus 50»); también «40m» en la columna Cantidad. Quedan a revisar. Si no, la fila entera va a las observaciones del pedido. Totales (un número suelto en «Producto») y errores (`#VALUE!`) se ignoran |
| Material | «Producto» se busca por código (número de parte o código del ERP), el texto entero o una palabra del texto que sea un código del maestro; si no, por la tabla de equivalencias revisada; si no, queda la descripción y va a `pendientes.csv`. Si la línea pide un genérico, la oferta no se adjudica (falta la presentación) |
| Destinos | «Detalles» se busca por número de activo, número de serie, código de gasoil o descripción del activo; después, modelo, ubicación o sector con el nombre exacto; después, equivalencias. Varios activos → un destino por activo con la cantidad repartida (enteros con el resto al primero; si no alcanza, partes iguales). Ubicación o sector → gasto general (con la ubicación). Sin coincidencia → «a identificar» con el texto, y a `pendientes.csv`. **Sin «Detalles»** (decidido 23/11; la imputación de la fila dice igual quién paga): si el material está en el maestro, es un repuesto para **stock** del taller del sector imputado, si ese sector tiene una sola ubicación; si no tiene ninguna o tiene varias, «a identificar» con la nota «repuesto para stock, falta el taller». Si el material no está en el maestro (ferretería, insumos) → **gasto general** |
| Imputación | «Cuenta» se busca por número o nombre; «Sector», por nombre o centro de costo (si no se repite). Porcentajes («40% CC-02, 30% CC-08») → un destino por centro de costo con cantidad = cantidad × porcentaje (si no suman 100, en proporción y con aviso), y mandan sobre el reparto por activos: el destino es el modelo común de esos activos o «a identificar». Lo que no está en el maestro queda vacío (se completa con la sugerencia o queda a revisar) y se lista agrupado en el resumen |
| Reimportación | Actualiza por `clave_origen`. No pisa con un vacío lo ya identificado (material, activo, modelo, ubicación, sector, cuenta, proveedor) ni vuelve a «a identificar» un destino identificado. Si la línea tiene destinos cargados en la app, no los toca. «A revisar (importación)» se carga solo al crear. Todo o nada |

### Rol de Copilot (decidido 21/11)

La cuenta corporativa de Microsoft permite usar Copilot con datos reales. Se usa **solo para interpretar**, nunca como importador:

- El adaptador (código) lee el Excel y los TSV: estructura, celdas combinadas, colores de pestaña, formatos y claves. Es repetible e idempotente.
- Lo que el adaptador no puede resolver con reglas (textos de "Detalles" sin coincidencia exacta, productos sin código) se exporta a una tabla de **equivalencias a revisar**. Copilot propone el activo, modelo o material con un nivel de confianza (ver `docs/prompt_copilot_equivalencias.md`); el gestor revisa; la importación usa la tabla revisada.
- Los PDF de ofertas, presupuestos, remitos, facturas y OC se leen con Copilot (ver `docs/prompt_copilot_documentos.md`) y entran con `revisado` = no hasta que el gestor confirme.

## Tramos siguientes (esquema, a detallar en su momento)

- **OT:** cabecera del ERP (sistema, nº de OT, activo, descripción, tipo, fechas, estado corporativo), importada y no editable en la app. El plan preventivo de la OT (descripción) se reconoce por `planes_preventivos.nombre_erp`: texto exacto sin distinguir mayúsculas ni espacios de más; sin coincidencia, la OT queda «a revisar» con el texto original; la app agrega operaciones → recursos ejecutantes y materiales (cantidad prevista y utilizada, origen: stock / comprado / provisto por el contratista), el vínculo con solicitudes de trabajo y con planes preventivos y medidores (fase 9). En EAM, una solicitud interna puede crearse desde la OT, y una o varias líneas pueden vincularse con una operación: la app replica ese vínculo con `solicitud_oc_lineas.nro_ot_erp` (y la operación, si el reporte la trae). **Imputación (decidido 25/11):** la OT tiene sector imputado y cuenta, sugeridos como en los destinos de pedido (el sector del activo) y editables; la corrección queda auditada. Así se resuelven los activos que se comparten o se prestan entre sectores con distinto centro de costo, según la demanda: el gestor lo ve en el reporte de la reparación y corrige la imputación de esa OT.
- **material_proveedor:** equivalencias de códigos (material, proveedor, código y descripción del proveedor).
- **Costo de un material de stock (decidido 22/11):** el último precio de factura; si no hay, el de la OC o la oferta adjudicada; si no hay ninguno, el consumo queda **«sin precio»** y marcado para revisar. El maestro de materiales no guarda precios.
- **Stock:** `movimientos_stock` (material, ubicación, fecha, cantidad con signo, tipo, vínculo con la recepción o el consumo). El stock pasa a ser la suma de movimientos.
- **Facturas:** documentos tipo factura vinculados a la OC y a las adjudicaciones, para el control ordenado contra recibido contra facturado.
- **Préstamos de activos:** activo, sector usuario, desde, hasta. **Postergado (25/11):** hoy son pocos activos y los préstamos surgen según la demanda; alcanza con corregir la imputación de cada OT o destino. Se descartó también una tabla de sectores por activo con porcentajes (`activo_sectores`).

## Decidido

- Orden (21/11): primero pedidos, documentos de proveedores, solicitudes internas y OC; después las OT.
- Imputación de la línea de pedido en una tabla de destinos (21/11).
- Compra parcial: reparto proporcional entre destinos, editable por el gestor (21/11).
- Estados de flujo como opciones fijas en código (21/11).
- Cabeceras de solicitudes de OC, OC y OT en el ERP, importadas y completadas en la app (21/11).
- Importadores como adaptadores por fuente; SAP reemplaza a Oracle (21/11).
- Estado histórico de los pedidos por color de pestaña; moneda por formato de celda; "Número Pedido" = nº de OC (21/11).
- Copilot solo para interpretar (equivalencias y PDF), con revisión del gestor (21/11).
- La OC entra al primer tramo; el nº de OC es la llave de cruce (21/11).
- Estado de las ubicaciones como catálogo editable e informativo, «Operativa» por defecto (25/11).
- Estados de proveedor (Activo / Retenido / Inactivo) y de contacto (Disponible / No disponible), informativos; el de los empleados queda en `empleados` (25/11).
- `planes_preventivos.nombre_erp`: equivalencia 1:1 con el plan del ERP, cargada por el gestor (25/11).
- Activos compartidos entre sectores: cada activo tiene un solo sector; la OT (como los destinos de pedido) sugiere la imputación desde el activo y se puede editar. Sin tabla de préstamos ni de sectores por activo por ahora (25/11).

## Abierto

1. TSV de OT (pendiente de envío).
2. Estructura del Excel histórico de solicitudes de OC (el compartido).
3. Confirmar si una OC puede reunir líneas de varias solicitudes del mismo proveedor.
4. Si existe un reporte de OC emitidas descargable (además del PDF por mail).
5. Regla de «Retenido» (25/11, pendiente): impedir (o avisar) adjudicar ofertas y emitir OC a un proveedor retenido. Cuando se implemente, el estado del proveedor tiene que dejar de ser un nombre editable en un catálogo (opción fija en código, o una marca «bloquea compras» en el estado), porque la regla dependería de él.
