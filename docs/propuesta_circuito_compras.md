# Propuesta: circuito con Compras (del pedido a la OC)

Estado: **borrador para discutir**; es la fase 14 de `plan_refactor_crud.md`. Parte de lo ya decidido en `vision_conceptual.md`
(roles, «Site de Compras», documentos de proveedor) y `diseno_tablas_operativas.md`
(adjudicaciones, solicitud de OC propuesta). Lo nuevo es cómo se articula el día a día.

## Hoy

El gestor carga el pedido en el Excel compartido; Compras lo abre y completa proveedor
adjudicado, nº de OC y notas. Algunos pedidos van por mail. Las ofertas llegan al gestor
por mail. Nadie avisa a nadie: hay que abrir el Excel para ver qué cambió.

## Propuesta

Cada actor trabaja en una bandeja con lo que le toca, y cada paso deja la línea en un
estado que el otro ve. Los estados son los ya diseñados (guardados o calculados).

| # | Quién | Qué hace | La línea queda |
|---|---|---|---|
| 1 | Gestor | Carga el pedido (borrador) y aprieta **Enviar a Compras** | Solicitado (enviada) |
| 2 | Compras | En su bandeja ve las líneas enviadas sin cotizar, agrupadas por pedido. Marca **En cotización** | En cotización |
| 3 | Compras | **Carga cada oferta:** adjunta el PDF y completa proveedor, total, moneda y plazo (carga mínima). Marca qué líneas cubre la oferta (casillas). La app crea el documento y lo vincula con esas líneas (adjudicaciones en 0) | En cotización |
| 4 | Compras | Cuando terminó de cotizar un pedido: **Ofertas cargadas** (le aparece al gestor) | Ofertas cargadas |
| 5 | Gestor | Las líneas de cada oferta se leen del PDF (Copilot o extracción) y se revisan. **Comparativo por línea**: ofertas lado a lado (precio neto, cantidad ofertada, plazo, proveedor) | Ofertas cargadas |
| 6 | Gestor (con aval de la jefatura) | **Elige** la oferta por línea, o una oferta entera para todo el pedido. Puede repartir entre proveedores o adjudicar menos | Adjudicado (calculado) |
| 7 | Gestor | **Pedir OC:** la app arma la solicitud propuesta (una línea por oferta adjudicada, con importe y distribución). El gestor la carga en EAM; la importación del TSV la vincula y la compara con lo propuesto. La app genera el detalle para Administración con los PDF adjuntos | Adjudicado |
| 8 | Compras | Emite la OC en el ERP y, en su bandeja, **carga el nº de OC y el PDF** sobre la oferta adjudicada. El número se propaga a las líneas (es la llave de cruce) | OC emitida (calculado) |
| 9 | Mecánicos / gestor | Conformidad de lo recibido | Recibido (calculado) |

### La vista de Compras

Una pantalla con tres bandejas, no el CRUD completo:

- **Para cotizar:** líneas enviadas en «solicitado» o «en cotización». Acciones: marcar en
  cotización, cargar oferta, marcar ofertas cargadas, nota para el gestor.
- **Para emitir OC:** ofertas adjudicadas con la solicitud de OC cargada y sin nº de OC.
  Acción: cargar nº de OC y PDF.
- **Reclamos:** OC emitidas con entrega vencida y pendiente de recibir.

Compras **no edita** cantidades, destinos ni imputación. Ve las líneas tal como se
congelaron al enviarlas, y las anuladas o canceladas aparecen marcadas.

Los pedidos que hoy llegan por mail entran igual: el gestor los carga en la app (o los
pega desde Excel) y los envía. El mail deja de ser un canal entre el gestor y Compras.

## Lo que hace falta antes

1. **Autenticación y roles.** Hoy la app no tiene usuarios y la API no tiene
   autenticación (quedó como punto de extensión). Una vista para Compras necesita, como
   mínimo, usuarios con rol gestor o compras, y que la auditoría registre quién hizo cada
   cambio (hoy dice «sistema»).
2. **Dónde corre la app.** Para que Compras entre, la app tiene que estar en un servidor
   de la red corporativa, no en la PC del gestor.
3. **Documentos de proveedor con carga mínima:** el alta de una oferta sin líneas
   (cabecera + PDF), con las líneas completadas después por el gestor o la extracción.

## Fases sugeridas

| Fase | Alcance |
|---|---|
| 1 | Edición en línea, borrador y envío (ver `propuesta_edicion_en_linea.md`) |
| 2 | Usuarios, roles y auditoría con usuario. Despliegue en un servidor |
| 3 | Vista de Compras: «Para cotizar» (estados, carga mínima de oferta, vínculo con líneas) |
| 4 | Comparativo por línea y adjudicación desde el comparativo |
| 5 | «Pedir OC» (solicitud propuesta, ya diseñada) y bandeja «Para emitir OC» |
| 6 | Reclamos y cumplimiento de entrega |

Mientras tanto, la app puede exportar el estado de los pedidos al Excel compartido
(sincronización de la fase 15, opción A: la app es la fuente) para que Compras siga
viendo los pedidos nuevos donde los ve hoy.

## Preguntas

1. ¿Dónde puede correr la app para que Compras entre? ¿Hay un servidor o VM en la red,
   o lo resolvemos con Power Apps contra la API (ya prevista)?
2. ¿Cómo se identifican los usuarios? ¿Cuentas corporativas de Microsoft (inicio de
   sesión único) o usuarios propios de la app?
3. **Aval de la jefatura al adjudicar:** ¿queda registrado en la app (un «aprobar» de la
   jefatura sobre la adjudicación) o sigue por fuera?
4. ¿Cuántas personas de Compras participan y cotizan todas lo mismo, o cada una tiene
   pedidos asignados?
5. **Avisos:** ¿alcanza con las bandejas, o hace falta un mail cuando se envía un pedido
   o se cargan ofertas?
6. ¿Compras completaría la carga mínima de la oferta, o prefieren seguir mandando el PDF
   por mail y que lo cargue el gestor (con Copilot)? La propuesta funciona igual; cambia
   quién carga.
