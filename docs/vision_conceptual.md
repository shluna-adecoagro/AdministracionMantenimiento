# Visión conceptual del sistema de mantenimiento

*Documento vivo. Última actualización: 21/11/2026. Nivel conceptual: no define tablas ni tecnología de alojamiento. El diseño de tablas está en `diseno_tablas_operativas.md`.*

## Propósito

Centralizar en un solo lugar la información que el área de mantenimiento genera a diario, para estimar costos, registrar intervenciones y consumos, seguir pedidos y solicitudes de OC, planificar compras y predecir services.

## Posicionamiento

- No es otro CMMS que compite con EAM (Oracle EBS R12) ni con SAP PM. Cubre lo que esos sistemas no resuelven en la práctica: **el circuito de materiales de un taller sin pañol** y el seguimiento de pedidos, solicitudes y conformidades, que hoy se resuelven con Excel, papel y WhatsApp.
- **Convive con el ERP** (ver "Convivencia con el ERP"): lo que nace en el ERP se importa y se completa en la app, sin cargarlo dos veces.
- Estrategia: es la "bala de plata" para conseguir infraestructura (servidor o Dataverse). El primer tramo tiene que funcionar sin TI, resolver un dolor visible para otros y producir números que la gerencia entienda. El pedido de servidor surge de los resultados.
- Fortaleza central: la **auditoría** ya registra qué cambió, quién lo cambió y cuándo. Es la base de la trazabilidad y de las métricas de tiempos.
- El diseño de listas para SharePoint (octubre 2026) queda reemplazado por este documento. De él se tomaron los principios y las reglas que no dependen de la tecnología.

## Principios de diseño

1. **Cada dato tiene un dueño:** el ERP o la app. Las importaciones solo actualizan los datos cuyo dueño es el ERP.
2. **Recalcular, nunca incrementar:** las cantidades compradas, recibidas y facturadas se obtienen sumando las líneas vinculadas, nunca con contadores aparte.
3. **Claves únicas en todo lo que se importa,** para poder repetir una importación sin duplicar.
4. **La IA propone, una persona confirma:** cada documento registra cómo se cargó (manual, IA, reporte, mail) y si ya se revisó.
5. **Decisiones por actor, aritmética derivada:** los estados que expresan una decisión los cambia una persona; los que surgen de comparar cantidades se calculan.
6. **La app sugiere, la persona decide:** los valores por defecto (imputación, distribución, materiales previstos) son sugerencias editables, y cada corrección queda auditada.

## Circuito general

Pedido → Cotización y OC → Recepción → Stock interno → Intervención (OT) → Costos y predicción.

Los datos maestros (activos, materiales, BOM, planes preventivos, proveedores, sectores, cuentas, medidores) ya están en la app y son la base del circuito.

## Convivencia con el ERP

**SAP reemplaza a Oracle en toda la empresa.** Hasta el cambio, el ERP es EAM (Oracle EBS R12); después, SAP PM. Los registros de EAM quedan como histórico, identificados por su sistema.

Decisión (21/11): **las cabeceras de las OT, de las solicitudes de OC y de las OC se crean en el ERP**, se importan a la app marcadas con su origen, y en la app se completa lo que el ERP no registra.

| Qué | Dueño | Qué completa la app |
|---|---|---|
| OT | ERP (importada) | Operaciones, materiales utilizados, recursos ejecutantes, vínculo con solicitudes de trabajo y planes preventivos |
| Solicitud de OC | ERP (importada: cabecera, líneas y distribuciones) | Vínculo con los documentos (ofertas adjudicadas, presupuestos), control contra lo adjudicado y seguimiento |
| OC | ERP (importada desde el PDF o un reporte) | Vínculo con la oferta o el presupuesto, con las líneas de pedido y con las recepciones |
| Pedidos, documentos de proveedor, recepciones, solicitudes de trabajo | App | Todo |

- **Reportes de EAM:** se pueden descargar en TSV cuando se quiera (cabeceras, líneas y distribuciones de solicitudes). Por eso la importación puede hacerse apenas se carga la solicitud, sin esperar.
- **Importadores como adaptadores:** cada fuente tiene su adaptador (TSV de EAM, PDF de OC; SAP después) que traduce a un formato interno común. Al pasar a SAP se agrega un adaptador; el resto de la app no cambia.
- Clave de lo importado: **sistema + número** (por ejemplo, EAM + nº de OT).
- Los datos que vienen del ERP no se editan en la app; la próxima importación los actualiza.
- **La app sirve antes del ERP:** después de adjudicar, propone las líneas y las distribuciones que se cargan en EAM. Al importar la solicitud, la app la vincula y compara lo cargado con lo propuesto.
- **La app reemplaza el paso manual de hoy:** actualmente, después de cargar en EAM, se descarga el reporte, se arma un Excel y se manda un mail a Administración con el detalle para que genere la OC. Con la solicitud importada y vinculada a sus documentos, la app puede generar ese detalle (y adjuntar los presupuestos) sin armarlo a mano.
- **No todo pasa por el ERP:** las solicitudes de OC que hoy se hacen por el Excel compartido (jefatura) y las OT que todavía no se cargaron en el ERP se pueden crear en la app con origen propio y vincularse después con su número del ERP.

## Dos tipos de solicitud

Todo empieza con una solicitud, que expresa una necesidad.

| | Solicitud de materiales | Solicitud de trabajo |
|---|---|---|
| Quién la origina | Mecánicos (hoy por mail o WhatsApp) | Mecánicos, que llaman al contratista (hoy solo queda en el celular) |
| Qué sigue | Compras cotiza → ofertas → adjudicación → OC → recepción | El contratista ejecuta → presupuesto → OC |
| Conformidad | **Después** de la OC: el mecánico registra lo recibido | **Antes** de la OC: el jefe de taller valida el trabajo hecho |

- El trabajo de un contratista es una **intervención con recurso externo**, el mismo objeto que una intervención de un mecánico. Así el historial del activo queda completo.
- La solicitud de trabajo es un registro liviano (activo, qué pasa, contratista llamado), no un paso de aprobación. Tiene que ser más fácil que el WhatsApp.
- Si llega un presupuesto sin solicitud previa, la solicitud se crea a partir de él y queda marcada como **regularizada**. La proporción de regularizadas mide la adopción.
- Registrar la solicitud aporta la **fecha del aviso**, con la que se pueden medir tiempos de respuesta, trabajos pendientes y correctivo hecho por contratistas.

## Conformidad

Pieza central y hoy inexistente. Regla propuesta: **nada se paga ni se cierra sin conformidad registrada.**

- En materiales, la conformidad es **registrar la cantidad recibida** (por defecto, la comprada), no un sí o un no. Si es menor, el faltante surge solo y Compras reclama.
- El site para mecánicos (consultar el estado de los pedidos y registrar la recepción) es, en esencia, la pantalla de conformidad.
- **El hueco que cubre:** para pagar, la factura del proveedor tiene que indicar el número de OC, y alguien de Administración hace la recepción de sus ítems en el ERP sin saber si se recibió completo, ni si se recibió. Con la conformidad registrada en la app, mantenimiento puede informar qué llegó realmente antes de que se registre esa recepción. Es uno de los "después" más relevantes.

## Cantidades por línea de pedido

Cada línea de pedido acumula una cadena de cantidades. Cada diferencia cuenta algo distinto.

| Cantidad | De dónde sale |
|---|---|
| Solicitada | La carga quien pide (suma de sus destinos) |
| Ofertada | Suma de las líneas de oferta (puede ser menor por falta de disponibilidad del proveedor) |
| Adjudicada (comprada) | Suma de lo que el gestor confirma de las ofertas |
| Recibida | Suma de lo registrado en la conformidad |
| Facturada | Suma de las líneas de factura (etapa posterior) |
| Cancelada | La carga el gestor, con motivo |

| Diferencia | Qué indica |
|---|---|
| Solicitada − adjudicada − cancelada | Pendiente de comprar. Ejemplo: se pidieron 10 filtros, el proveedor tenía 7, se compraron 7. Los 3 restantes quedan pendientes hasta que el gestor los vuelva a cotizar o los cancele. No se pierden. |
| Adjudicada − recibida | Pendiente de recibir: faltante de entrega, Compras reclama |
| Adjudicada − facturada | Control contra la factura del proveedor |

Una línea puede tener varios destinos (por ejemplo, 5 filtros para cada uno de dos talleres). Si se compra menos de lo pedido, lo comprado se reparte en proporción entre los destinos y el gestor lo corrige según lo que confirmen los mecánicos.

La frecuencia de compras parciales por falta de disponibilidad es un indicador de falta de planificación.

## Documentos de proveedor

Ofertas comerciales, presupuestos, remitos y facturas son un mismo concepto: un documento con cabecera y líneas, vinculado a una solicitud o a una intervención. De ahí sale el historial de precios por proveedor y por material.

- Las líneas de una oferta se vinculan con las líneas de pedido que cubren (una oferta puede cubrir líneas de varios pedidos).
- **Adjudicación por línea y por cantidad:** de una oferta se pueden confirmar algunos ítems y otros no (quedan cotizados sin comprar), y un mismo pedido se puede repartir entre proveedores.
- Cada documento registra su origen de carga y si fue revisado. Las líneas extraídas automáticamente pueden llevar un nivel de confianza.
- El **detalle vive en la app**. Hacia el ERP alcanza con el total.

## Solicitud de OC y su relación con los documentos

- Cada **línea de la solicitud de OC corresponde a un documento** y lleva el **total adjudicado** de ese documento: en trabajos, el total del presupuesto; en materiales, la suma de las líneas confirmadas de la oferta.
- Una solicitud de OC puede tener una línea (lo habitual: una OC por presupuesto) o varias (por ejemplo, un contratista que manda a fin de mes todos los presupuestos de los trabajos que hizo).
- Las líneas de una misma solicitud pueden ser de proveedores distintos.
- Cadena de trazabilidad: línea de pedido o solicitud de trabajo → documento de proveedor → línea de solicitud de OC → OC → factura.
- Tipo **regularización** para las solicitudes de trabajos hechos sin OC previa.

## OC: el ERP es la fuente

- La OC la emite en el ERP cualquier persona de Administración con rol de comprador (Compras es una subdivisión de Administración), tanto para servicios como para materiales. La aprueba la jefatura del área.
- **Una OC corresponde a un solo proveedor**, cuyos datos están en la cabecera. De una solicitud interna con líneas de dos proveedores salen dos OC. Probablemente una OC pueda reunir líneas de varias solicitudes del mismo proveedor (a confirmar).
- **En la práctica, Compras genera una OC por cada presupuesto u oferta adjudicada**, que cubre una o más líneas de pedido, y cita el presupuesto en las observaciones. Por eso **el número de OC es la llave de cruce** entre líneas de pedido, ofertas, solicitudes internas y OC.
- La OC es un reflejo de la solicitud interna, pero con otra jerarquía: es el documento contra el que se pagan las facturas. La factura tiene que indicar el número de OC; si no, el pago no se procesa.
- Estructura de la OC: cabecera (número, fecha, proveedor con razón social, CUIT, dirección, localidad, contacto y código del ERP, comprador, plazo de pago, moneda, observaciones y total) y líneas (ítem, descripción, unidad, cantidad, lugar y fecha de entrega, precio unitario y total).
- La app **no replica** la OC ni su aprobación: guarda una copia de referencia, desde el PDF que Compras envía por mail (leído con IA y revisado) o desde un reporte del ERP.
- La **fecha de entrega comprometida** en la OC, comparada con la recepción registrada, mide el cumplimiento de entrega de cada proveedor.
- La conciliación por número de OC detecta: OC sin pedido ni solicitud (compras fuera del circuito), pedidos con un número de OC que no existe y diferencias entre lo adjudicado y lo ordenado.

## Imputación contable

Tres coordenadas, como en el ERP: **centro de costo, cuenta y cantidad (o importe)**.

### Dónde vive cada cosa

- **El propósito vive en el destino de la línea de pedido** (o en la solicitud de trabajo): para qué activo o sector, y con qué fin. Es información operativa y es correcto que esté ahí. Incluye el **sector imputado** (quién paga).
- **La distribución contable vive en la línea de la solicitud de OC**, con relación 1 línea : N distribuciones. Se carga en el ERP y se importa desde su reporte.
- **La app propone las distribuciones:** agrupa lo adjudicado por centro de costo y cuenta y suma los importes. El gestor las revisa, las carga en EAM, y al importar la solicitud la app compara lo cargado con lo propuesto.
- Lo importado queda fijo: si un activo cambia de sector, las solicitudes viejas conservan la imputación de su momento.

### Sugerencia por defecto (siempre editable)

- **Centro de costo:** el del **sector imputado**. Por defecto es el sector del activo, o el sector que recibe la compra si no hay activo (por ejemplo, el taller). El sector ya tiene su centro de costo en la app.
- **Cuenta, según el propósito:**
  - Con activo: la cuenta del tipo de activo (ya existe en la app: `TipoActivo.cuenta`). Maquinaria y Vehículo → rodados; Instalación → instalaciones. Aplica también a materiales detallados en el presupuesto de un service (por ejemplo, un bidón de aceite usado en un tractor → rodados).
  - Sin activo (stock o gasto general): la cuenta asociada a la categoría del material. Ejemplos: tambores de lubricante para stock → lubricantes; herramientas → instalaciones; filtros para stock → rodados; también gastos de oficina, seguridad e higiene, etc.
- Una línea que va a varios destinos se reparte por cantidad entre ellos.

### Préstamos de activos entre sectores

Un sector puede prestarle una máquina a otro. Si se rompe, paga el **sector que la usa**, aunque el activo pertenezca a otro centro de costo. Por eso:

- El sector imputado se sugiere desde el activo, pero se puede cambiar. La corrección queda auditada.
- **El costo operativo siempre va al activo** (su historial de costos no depende de quién pagó). El sector imputado responde a la pregunta "quién paga".
- Más adelante: registrar los préstamos (activo, sector que lo usa, desde y hasta), cuando exista la costumbre de informarlos.

### Contable y operativo pueden diferir, y está bien

Sin materiales inventariables no hay cuenta de inventario: lo que se compra para stock queda contablemente consumido al comprarse. Operativamente, en cambio, se consume cuando se usa en una intervención. Ejemplo: se compran 10 filtros por taller; contablemente se imputan a rodados y al centro de costo del sector del taller, pero recién se imputan a un activo cuando se usan en una OT. **El taller funciona como un pañol.** Mostrar el costo real por activo aunque contablemente haya ido a otro lado es parte del valor de la app.

## Estados (propuesta)

Dos tipos de estado, en campos separados:

- **Estado de seguimiento (propio):** lo define la app y lo cambia cada actor desde su interfaz. Son opciones fijas en el código, no un catálogo editable (decidido 21/11), porque las reglas de la app dependen de ellos.
- **Estado corporativo (espejo):** el que asigna el ERP a la OT, la solicitud y la OC. Llega con el reporte y se guarda tal cual.

### Pedido de materiales (estado por línea; el pedido muestra un resumen, por ejemplo "3 de 5 recibidas")

| Estado | Quién lo cambia | Significa |
|---|---|---|
| Solicitado | Mecánico o gestor | Se registró la necesidad |
| En cotización | Compras | Pidió precios a proveedores |
| Oferta en validación | Compras | Cargó las ofertas; las revisa el gestor |
| Adjudicado | Gestor | Confirmó qué ítems y cantidades se compran a quién |
| OC emitida | Compras | Vinculó el número de OC |
| Recibido | Mecánico | Conformidad: registró la cantidad recibida |
| Cerrado | Automático | No queda nada pendiente de comprar ni de recibir |
| Anulado | Gestor | Ya no hace falta, con motivo |

Indicadores derivados (no son estados): pendiente de comprar, pendiente de recibir, con faltante.

### Solicitud de trabajo

| Estado | Quién lo cambia | Significa |
|---|---|---|
| Registrada | Mecánico | Llamó al contratista (o "regularizada" si nace del presupuesto) |
| Presupuesto recibido | Gestor o Compras | El contratista mandó el presupuesto del trabajo hecho |
| Validada | Jefe de taller | Conformidad: el trabajo se hizo como dice el presupuesto |
| Observada | Jefe de taller | Hay diferencias; se vuelve al contratista |
| Con solicitud de OC | Gestor o jefatura | Ya se pidió el pago |
| Cerrada | Automático | Se emitió la OC |
| Anulada | Gestor | Con motivo |

### Solicitud de OC

| Estado (propio) | Quién lo cambia | Significa |
|---|---|---|
| Solicitud generada | Gestor o jefatura | Solo para las que nacen en la app (canal Excel): preparada, sin número del ERP |
| Cargada en ERP | Importación o gestor | Tiene número de solicitud del ERP (las importadas nacen en este estado) |
| Enviada a Administración | Gestor | Se mandó el detalle para que se genere la OC |
| OC emitida | Compras o el reporte | Todas sus líneas tienen número de OC |

Desde "Cargada en ERP", el estado corporativo corre en paralelo como espejo.

### Criterios

1. Cada cambio de estado queda registrado con fecha y usuario (auditoría). De ahí salen los tiempos de cada etapa.
2. Los estados se pueden saltear, pero el salto queda marcado. Mide la adopción en lugar de bloquear.
3. Pocos estados. Las situaciones intermedias van en comentarios o salen de las cantidades.

## Destino de cada línea de pedido

El destino se define **por línea** (y una línea puede tener varios), no por pedido.

| Destino | Ejemplos | Cuándo se imputa el costo operativo |
|---|---|---|
| Activo | Filtros para un tractor puntual | Al recibir |
| Stock del taller | Repuestos, filtros y tambores de lubricante para services | Al consumir en una intervención, que lo imputa al activo |
| Gasto general | Ferretería, bulonería, madera, hierro, herramientas menores | Al recibir, al sector |

- **No todo controla stock.** Cada material del maestro tiene una marca de "controla stock" (lo caro, lo crítico y lo que se usa en los services). El resto se da por consumido al recibirlo.
- **Planificación de compras:** planes preventivos + materiales por modelo + horas de medidores = services próximos y materiales a comprar. Genera solicitudes con destino a stock.

## Intervención: materiales y costos

- La cabecera de la OT viene del ERP; la app completa operaciones, recursos y materiales.
- Cada material de una intervención tiene **cantidad prevista** (desde el plan o el BOM) y **cantidad utilizada**. Comparar plan contra realidad permite corregir los planes de mantenimiento y alimenta la predicción de services.
- Origen del material: de stock, comprado para la intervención o provisto por el contratista.
- **Costo de un material de stock:** el último precio de factura; si no hay, el del maestro.
- **Regla anti doble conteo:** en un trabajo interno, el costo es la suma de los materiales utilizados más la mano de obra. En un trabajo de contratista, el costo sale de su presupuesto o factura, y los materiales que trajo el contratista no se vuelven a sumar.

## Reportes previstos

Historial de precios por material y proveedor, comparativo de cotizaciones por línea de pedido, materiales nuevos a dar de alta en el maestro, diferencias de precio entre factura y OC, mano de obra por service, consumo por activo, tiempos por etapa, compras parciales por falta de disponibilidad, cumplimiento de entrega por proveedor, costo contable contra costo operativo por sector, costos pagados por un sector sobre activos de otro (préstamos), diferencias entre la distribución propuesta y la cargada en el ERP, conformidad de lo recibido por OC (para Administración).

## Roles

| Rol | Participación |
|---|---|
| Responsable de datos (gestor) | Recibe y carga solicitudes, recibe las ofertas antes de que se confirme la compra (con aval de la jefatura), adjudica, revisa imputaciones y distribuciones, crea las solicitudes de OC y las OT en el ERP y las completa en la app, envía el detalle de las solicitudes a Administración. Es el nodo central de los dos circuitos. |
| Mecánicos | Originan solicitudes de materiales y de trabajo, registran recepciones. |
| Jefes de taller | Validan los trabajos de contratistas. |
| Compras (subdivisión de Administración) | Cotiza; cualquier persona con rol de comprador emite la OC en el ERP, para servicios o materiales; reclama faltantes. Administración registra la recepción de las facturas para el pago. |
| Jefatura del área (2 personas) | Solicitudes de OC de trabajos (hoy por el Excel compartido). Aprueba las OC en el ERP. |

## Interfaces previstas

Todas consumen la misma API. Cada actor actualiza solo los estados que le corresponden.

| Interfaz | Usuarios | Qué hace |
|---|---|---|
| App web (Flask + Jinja2) | Gestor, jefatura | Gestión completa, datos maestros, adjudicación, propuesta de solicitudes de OC y distribuciones, importaciones del ERP, detalle para Administración, conciliación, análisis. |
| Site de mecánicos | Mecánicos, jefes de taller | Solicitudes de materiales y de trabajo, estado de pedidos, conformidad. |
| Site de Compras (idea, 17/11) | Compras | Cargar ofertas y presupuestos, vincular el número de OC, actualizar el estado de los pedidos (cotizando, OC emitida, reclamo), consultar la conformidad antes de registrar la recepción de una factura. Reemplaza el Excel compartido y el mail de ofertas al gestor. |

Para el site de Compras, la carga tiene que ser mínima: adjuntar el PDF y completar proveedor, total, moneda y plazo. Las líneas las completa el gestor o una extracción automática. Cuando otras áreas escriban en el sistema, la API va a necesitar autenticación y roles (hoy está previsto como punto de extensión).

## Medir el antes y el después

- **El "antes" se documenta ahora**, mientras siguen los Excel: un documento y una presentación derivada que muestren cómo se trabaja hoy. Material disponible: el Excel de pedidos, el Excel de solicitudes internas de Oracle, grabaciones de pantalla de cómo se genera una OT y una solicitud interna en EAM, y el circuito actual de reporte TSV → Excel → mail a Administración.
- Números del "antes" a relevar: pedidos abiertos, tiempo desde que se pide hasta que llega, solicitudes de OC por mes, horas por semana dedicadas a estas tareas.
- **El "después"** cuenta cómo cambió esa forma de trabajar con la app, la API y los sites, con los mismos números. Incluye que la recepción administrativa de las facturas pase a apoyarse en una conformidad real.
- **Datos para compartir:** antes de subir planillas o reportes reales a un chat externo, se anonimizan localmente (proveedores, empleados, sectores, centros de costo, cuentas) con alias consistentes; la tabla de equivalencias queda solo en la computadora del gestor. Con Copilot (cuenta corporativa) se pueden usar datos reales.

## Datos históricos

Decisión (21/11): **se importa todo el histórico** del Excel de pedidos (una hoja por pedido) y del Excel de solicitudes de OC, además de las solicitudes de EAM desde sus reportes. Muestra el valor del sistema desde el primer día: seguimiento y consulta histórica centralizados. Los registros importados se marcan con su origen y una clave de la fuente, para poder repetir la importación sin duplicar.

## Primer tramo

Pedidos, documentos de proveedores, solicitudes internas (importadas de EAM y completadas en la app) y OC (desde el PDF o un reporte), operados por el gestor, para reemplazar el Excel de una hoja por pedido, el Excel compartido de solicitudes de OC y el armado manual del mail a Administración, con su histórico importado. Funciona en forma local. Durante la transición, la app puede generarle a Compras la vista que hoy usa, para evitar la doble carga.

Segundo paso: los sites de mecánicos y de Compras consumiendo la API. Requieren servidor, y ese es el pedido a TI. Un prototipo de los sites funcionando sobre la app local refuerza la presentación.

Más adelante: OT importadas del ERP y completadas en la app, stock, facturas, costos por activo y predicción de services. La predicción va al final de la presentación como lo que se habilita con algunos meses de datos reales.

## Pendientes

- Dónde se alojan los datos.
- Ejemplos de TSV de OT de EAM.
- Reporte de OC emitidas de Oracle: pedido a Administración y consulta a TI para poder generarlo desde EAM (semana del 23/11).
- Estructura del Excel histórico de solicitudes de OC (el compartido).
- Revisión de los materiales dudosos del maestro (en otra conversación).
- Qué deja de cargarse en EAM (por ejemplo, los materiales utilizados en las OT pasan a cargarse solo en la app).
- Documento y presentación del "antes".
