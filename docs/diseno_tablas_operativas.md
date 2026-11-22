# Diseño de tablas: parte operativa (borrador para revisar)

*Versión 5.1, 21/11/2026. Deriva de `docs/vision_conceptual.md` y del estado del repo al commit 45e4dc7 (fase 9, planes preventivos). Reemplaza el "diseño inicial" de las fases operativas de `docs/plan_refactor_crud.md`.*

*Historial: v2 — primer tramo con pedidos, documentos de proveedores y solicitudes de OC; destinos de la línea de pedido (1 : N); tabla de adjudicaciones (N:M). v2.1 — reparto proporcional entre destinos. v3 — convivencia con el ERP; estados como opciones fijas en código. v3.1 — TSV de EAM a demanda; importadores como adaptadores; estado "Enviada a Administración". v4 — ajustes a partir de ejemplos reales (Excel de pedidos y TSV de solicitudes internas). v4.1 — estado histórico por color de pestaña, moneda por formato de celda, rol de Copilot. v5 — la OC entra al primer tramo: una OC por proveedor y, en la práctica, una por presupuesto adjudicado; el nº de OC cruza pedidos, ofertas y solicitudes. v5.1 — columnas que necesita la lectura de PDF (`docs/prompt_copilot_documentos.md`): descuento global, total en USD informado, equipo y horas del medidor en documentos; precio de lista en líneas; presupuesto citado en la OC.*

## Convenciones (las del repo)

- Tablas en plural y snake_case; PK `<entidad>_id` autoincremental; `uuid`; `creado_en` / `actualizado_en`; `AuditMixin` en todo lo operativo (la auditoría da quién, qué y cuándo de cada cambio de estado).
- Cabecera y líneas como entidad y subentidad (el framework ya lo resuelve).
- **Estados de flujo como opciones fijas en código** (decidido 21/11): select con `opciones` en el override, no catálogo editable, porque las reglas de la app dependen de ellos.
- **Cantidades derivadas sin columna:** ofertada, adjudicada, recibida y facturada se calculan sumando filas vinculadas (principio "recalcular, nunca incrementar"). Si hace falta por rendimiento, se agrega una caché que se recalcula, nunca un contador.
- **Importación idempotente:** toda tabla que recibe histórico o reportes tiene `origen` (app / histórico / reporte / PDF) y `clave_origen` única (por ejemplo, hoja y fila del Excel, o número del ERP).
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
| canal | opción | WhatsApp / mail / site / app / histórico |
| prioridad | opción | Normal / urgente |
| fecha_requerida | fecha, opcional | |
| observaciones | texto | |
| origen, clave_origen | texto | Importación (clave única: archivo + hoja) |

El estado del pedido no se guarda: es el resumen de sus líneas ("3 de 5 recibidas").

### pedido_lineas (qué se compra)

Es lo que ve Compras y lo que se cotiza: un material y una cantidad total.

| Columna | Tipo | Notas |
|---|---|---|
| pedido_id | FK, cascada | |
| nro_linea | entero | Único por pedido |
| material_id | FK materiales, opcional | Se identifica por código (por ejemplo, "84228488") o se asigna a mano |
| descripcion | texto | Columna "Producto" tal cual ("Bolillero 32217", "8605140") |
| unidad_medida_id | FK, opcional | Por defecto, la del material |
| estado | opción | Solicitado / en cotización / oferta en validación / adjudicado / OC emitida / recibido / cerrado / anulado |
| estado_salteado | sí/no | Marca cuando se saltó un estado (mide adopción) |
| sin_conformidad | sí/no | Cerrado en el histórico sin registro de recepción |
| cantidad_cancelada | decimal, 0 | Con motivo |
| motivo_operacion_id | FK motivos, opcional | Motivo de cancelación o anulación |
| nro_oc | texto, opcional | OC con la que se compró (columna "OC" del Excel, o la que carga Compras). Una línea comprada a dos proveedores tiene dos OC: en ese caso el dato sale de las adjudicaciones |
| observaciones | texto | |

Derivadas: **solicitada** (suma de los destinos), ofertada, adjudicada, recibida, pendiente de comprar, pendiente de recibir.

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
| sector_imputado_id | FK sectores | Quién paga. Sugerido: sector del activo, o el de la ubicación, o el del pedido |
| cuenta_id | FK cuentas | Sugerida: cuenta del tipo de activo, o de la categoría del material |

- Derivadas por destino: recibida y pendiente de recibir. Así cada taller da la conformidad de su parte.
- **Compra parcial (decidido 21/11):** si se adjudica menos de lo solicitado, la app reparte lo adjudicado entre los destinos **en proporción** a sus cantidades; el gestor lo corrige. Para materiales que se cuentan por unidad, el reparto se redondea a enteros y el resto va al primer destino.

### documentos_proveedor (cabecera)

Ofertas, presupuestos de trabajos, remitos y facturas.

| Columna | Tipo | Notas |
|---|---|---|
| tipo | opción | Oferta / presupuesto de trabajo / remito / factura |
| proveedor_id | FK proveedores | |
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
| solicitud_trabajo_id | FK, opcional | Presupuesto del trabajo de un contratista |
| nro_oc | texto, opcional | En ofertas y presupuestos: la OC que se emitió por ellos (una por presupuesto adjudicado). En remitos y facturas: la OC que referencian |
| archivo | archivo (PDF) | El framework ya permite adjuntos |
| origen_carga | opción | Manual / IA / mail / histórico |
| revisado | sí/no | "La IA propone, una persona confirma" |
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
| cantidad | decimal | En ofertas, lo ofertado (puede ser menor a lo pedido) |
| unidad_medida_id | FK | |
| precio_lista | decimal, opcional | Unitario antes de descuentos, sin IVA |
| descuento_pct | decimal, opcional | Descuento efectivo total sobre el precio de lista (de línea y global) |
| precio_unitario | decimal | Neto, sin IVA, después de todos los descuentos. Es el que usa el historial de precios |
| activo_id | FK, opcional | En presupuestos de service, si detalla el equipo |
| confianza | decimal, opcional | Extracción automática |

Derivada: subtotal = cantidad × precio_unitario (el descuento ya está aplicado en el precio neto; no se aplica dos veces).

### adjudicaciones (qué se compra de cada oferta, para qué línea de pedido)

Relación N:M entre líneas de oferta y líneas de pedido. Cubre una oferta que cotiza juntas líneas de varios pedidos y una línea de pedido comprada a dos proveedores.

| Columna | Tipo | Notas |
|---|---|---|
| documento_linea_id | FK documento_lineas | Línea de una oferta |
| pedido_linea_id | FK pedido_lineas | |
| cantidad_ofertada | decimal, opcional | Si la oferta reparte su renglón entre líneas de pedido |
| cantidad_adjudicada | decimal, 0 | Lo que el gestor confirma. 0 = cotizado, no comprado |

- Adjudicada de la línea de pedido = suma de `cantidad_adjudicada`.
- Total adjudicado de una oferta = suma de `cantidad_adjudicada × precio neto` de sus líneas.
- **En el histórico, el nº de OC reconstruye la adjudicación:** una línea de pedido con OC X se vincula con la oferta del mismo proveedor que tiene OC X (o que la OC X cita en sus observaciones).

### recepciones (conformidad de materiales)

Una fila por entrega y por destino; admite entregas parciales.

| Columna | Tipo | Notas |
|---|---|---|
| pedido_linea_destino_id | FK | Qué destino recibe |
| fecha | fecha | |
| cantidad | decimal | Por defecto, lo pendiente de recibir del destino |
| recibido_por_id | FK empleados | |
| documento_linea_id | FK, opcional | Línea del remito |
| observaciones | texto | Faltantes, roturas |

Comparando la fecha de recepción con la fecha de entrega comprometida en la OC se mide el **cumplimiento de entrega** de cada proveedor.

### solicitudes_trabajo

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
| sector_id | FK, opcional | Identificado por el centro de costo |
| cantidad | decimal | Como en el ERP: con una línea de cantidad 1, las fracciones (0,25 / 0,25 / 0,5) son los porcentajes |
| udm | texto | |
| origen | opción | ERP / app |
| clave_origen | texto | Sistema + solicitud + línea + distribución |

Derivados: porcentaje = cantidad / cantidad de la línea; importe = porcentaje × importe de la línea.

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

- `proveedores`: agregar `codigo_erp` (código interno del proveedor en el ERP, figura en la OC). El CUIT ya existe.
- `categorias_material`: agregar `cuenta_id` (opcional), para sugerir la cuenta sin activo.
- `materiales`: agregar `controla_stock` (sí/no).
- Borrar `Pedido` / `PedidoDetalle`, `pedidos_service.py`, `pedidos_routes.py` y su schema (nunca se registraron; los reemplaza este diseño).

## Importación del Excel histórico de pedidos

### Formato observado (una hoja por pedido)

- Cabecera con etiquetas y valor al lado: "Pedido N°", "Fecha", "Referencia", "Solicitante(s)".
- Tabla desde la fila de encabezado que empieza con "Cantidad": Cantidad, Producto, Detalles, Imputación (Cuenta, Sector), PROVEEDOR, IMPORTE **o una columna por proveedor cotizado**, OC, Recibido?, Observaciones.
- **Celdas combinadas:** "Detalles", "Cuenta", "Sector", "PROVEEDOR" y "OC" suelen abarcar varias filas; el adaptador repite el valor en cada fila que cubre.
- Fila de totales al final (se ignora). "Recibido?" y "Observaciones" casi no se usan.
- **El color de la pestaña indica el estado del pedido.**

### Reglas

| Dato | Regla |
|---|---|
| Estado por color de pestaña | Verde → líneas **cerradas**, marcadas `sin_conformidad` (salvo que "Recibido?" diga lo contrario). Amarillo → **en proceso**: con OC, "OC emitida" (pendiente de confirmar la recepción); sin OC, "en cotización". Rojo → **anulado**. Sin color → **solicitado** (novedad). Colores que no encajen se listan para revisar. |
| Ofertas | Con una columna por proveedor (GRUMAQ, JMG en el pedido 1104): una oferta por proveedor con sus precios unitarios; la adjudicación sale de "PROVEEDOR". Con una sola columna "IMPORTE": una oferta del proveedor elegido. La oferta adjudicada recibe el nº de OC de sus líneas. |
| Moneda | Por el formato de la celda: con "$" → ARS; sin símbolo → USD (repuestos de John Deere y otras marcas de maquinaria), marcada `moneda_inferida` para revisar. |
| Material | "Producto" se busca por código en el maestro (por ejemplo, 84228488); si no coincide, queda la descripción "a revisar". |
| Destinos | "Detalles" se busca contra activos (nombre o código) y modelos. Varios activos → un destino por activo con la cantidad repartida. Sin coincidencia → "a identificar" con el texto. |
| Imputación | "Cuenta" y "Sector" se buscan en el maestro. Porcentajes ("50% CC-01, 50% CC-02") → un destino por centro de costo con cantidad = cantidad × porcentaje. |
| OC | El número de la columna "OC" va a `pedido_lineas.nro_oc` y a la oferta adjudicada, y se cruza con las solicitudes y las OC importadas. |

### Rol de Copilot (decidido 21/11)

La cuenta corporativa de Microsoft permite usar Copilot con datos reales. Se usa **solo para interpretar**, nunca como importador:

- El adaptador (código) lee el Excel y los TSV: estructura, celdas combinadas, colores de pestaña, formatos y claves. Es repetible e idempotente.
- Lo que el adaptador no puede resolver con reglas (textos de "Detalles" sin coincidencia exacta, productos sin código) se exporta a una tabla de **equivalencias a revisar**. Copilot propone el activo, modelo o material con un nivel de confianza (ver `docs/prompt_copilot_equivalencias.md`); el gestor revisa; la importación usa la tabla revisada.
- Los PDF de ofertas, presupuestos, remitos, facturas y OC se leen con Copilot (ver `docs/prompt_copilot_documentos.md`) y entran con `revisado` = no hasta que el gestor confirme.

## Tramos siguientes (esquema, a detallar en su momento)

- **OT:** cabecera del ERP (sistema, nº de OT, activo, descripción, tipo, fechas, estado corporativo), importada y no editable en la app; la app agrega operaciones → recursos ejecutantes y materiales (cantidad prevista y utilizada, origen: stock / comprado / provisto por el contratista), el vínculo con solicitudes de trabajo y con planes preventivos y medidores (fase 9). En EAM, una solicitud interna puede crearse desde la OT, y una o varias líneas pueden vincularse con una operación: la app replica ese vínculo con `solicitud_oc_lineas.nro_ot_erp` (y la operación, si el reporte la trae).
- **material_proveedor:** equivalencias de códigos (material, proveedor, código y descripción del proveedor).
- **Stock:** `movimientos_stock` (material, ubicación, fecha, cantidad con signo, tipo, vínculo con la recepción o el consumo). El stock pasa a ser la suma de movimientos.
- **Facturas:** documentos tipo factura vinculados a la OC y a las adjudicaciones, para el control ordenado contra recibido contra facturado.
- **Préstamos de activos:** activo, sector usuario, desde, hasta.

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

## Abierto

1. TSV de OT (pendiente de envío).
2. Estructura del Excel histórico de solicitudes de OC (el compartido).
3. Confirmar si una OC puede reunir líneas de varias solicitudes del mismo proveedor.
4. Si existe un reporte de OC emitidas descargable (además del PDF por mail).
