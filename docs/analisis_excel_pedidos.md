# Análisis del Excel histórico de pedidos (PR 10.6)

*23/11/2026. Hecho sobre el Excel completo anonimizado (`Pedidos_Anonimizado.xlsx`), antes de
codificar el adaptador. Complementa la sección «Importación del Excel histórico de pedidos» de
`diseno_tablas_operativas.md`. Las dudas del final están pendientes de respuesta del gestor.*

## Lo que hay

- **393 hojas:** «Plantilla pedidos» (se ignora) y 392 pedidos, del 717 al 1123.
- **Cabecera** igual en todas: `A1` «Pedido N°:» y el número en `B1`; `D1` «Fecha:» y la fecha
  en `E1` (siempre una fecha de Excel); `A2` «Referencia:» → `B2`; `A4` «Solicitante(s):» → `B4`.
- **Encabezado de la tabla** en las filas 6 y 7 (en una hoja, en la 8), datos desde la fila 8.
  Columnas: A cantidad, B producto, C detalles, D cuenta, E sector (D6:E6 «Imputación»),
  F proveedor, y después importe, OC, «Recibido?» y observaciones.
- **La anonimización cambió algunos encabezados:** «Cantidad», «Producto» y «PROVEEDOR»
  aparecen como códigos (`PROV-…`, `SOL-…`). El adaptador no se guía por esos textos sino por
  la posición y por los encabezados que sí se conservan («Detalles», «Imputación», «IMPORTE»,
  «OC», «Recibido?», «Observaciones»).

### Formatos

| Formato | Hojas | Notas |
|---|---|---|
| Estándar: G «IMPORTE», H «OC», I «Recibido?», J «Observaciones» | 373 (95 %) | Algunas sin «Observaciones» o sin «Recibido?» |
| «PU» + «IMPORTE» (precio unitario y total) | ~9 | |
| Columnas de otros proveedores a la derecha (cotizaciones que no se compraron) | ~12 | A veces como texto: «USD 1.429,7520» |
| Una columna de precio por proveedor (como el pedido 1104) | pocas | |
| Encabezados corridos (ej: 1103: «PROVEEDOR» tiene la OC, «OC» tiene el proveedor, «Recibido?» tiene el precio de lista) | algunas | No se pueden interpretar por encabezado |

- **Celdas combinadas** en detalles, cuenta, sector, proveedor, OC y «Recibido?»: el valor está
  solo en la primera fila; hay que repetirlo en las demás.
- **Fórmulas:** 175 cantidades o importes son fórmulas (`=SUMIF(...)`, `=A8*G8`,
  `=I8*(1-26.2%)`); todas tienen su valor calculado guardado. El adaptador lee los valores.
- **«IMPORTE» unitario o total:** 347 hojas no tienen fila de total; 23 suman con
  `SUMPRODUCT(cantidad; importe)` (unitario) y 3 con `SUM(importe)` (total de línea).
- **Moneda por formato de celda:** `"$"` 541 celdas, `[$USD]` 11, sin símbolo 69. En el pedido
  1103, una columna sin símbolo tiene precios de lista en pesos (no en dólares).

### Contenido de las filas

- **Productos:** solo ~5 % parecen un código (ej: `RE504836`, `8605140`); el resto es texto libre
  («Lámparas galponeras LED…»). Lo no identificado va a equivalencias (Copilot).
- **Detalles:** texto libre («Sala de balanza»), un equipo («580 - EQ-027») o un modelo con
  varios equipos («5090D - EQ-017 EQ-026 EQ-020…»).
- **Sector con porcentajes** en 106 filas: «40% CC-02, 30% CC-08, 15% CTA-004, 15% CC-07».
- **OC:** 390 números de 9 dígitos (100…); 13 raros (dos OC en una celda «100777817 - 100777819»,
  fórmulas, «Solicitada», un espacio).
- **«Recibido?»:** «ok»/«OK» en ~230 filas; también números y fórmulas (columnas corridas).
- **116 filas con producto y sin cantidad:** la cantidad dentro del texto («2 tambor plus 50»),
  notas («faltaría 1 cuchilla para…»), totales o `#VALUE!`.
- **Número de pedido:** en 5 hojas `B1` no coincide con el nombre de la hoja (ej: hoja
  «Pedido 770» con `B1` = 769), lo que deja 4 números repetidos. Nombres irregulares:
  «Pedido 762 - NO», «Pedido 847 hierros», «pedido 959», «PEDIDO 966».

### Colores de pestaña

| Color | RGB | Hojas | Filas | Con OC | «Recibido?» ok |
|---|---|---|---|---|---|
| Verde (del tema, `accent6`) y `00B050` | `70AD47` | 306 | 1628 | 1016 | 229 |
| Verde claro | `92D050` | 26 | 101 | 35 | 40 |
| Naranja | `FFC000` | 29 | 85 | 43 | 0 |
| Amarillo | `FFFF00` | 7 | 52 | 27 | 1 |
| Rojo y rojo oscuro («762 - NO») | `FF0000`, `C00000` | 8 | 59 | 0 | 0 |
| Azul | `0070C0` | 1 | 12 | 0 | 0 |
| Sin color | — | 15 | 63 | 0 | 0 |

(Filas y OC del formato estándar, con las celdas combinadas expandidas.)

## Dudas para el gestor (con recomendación)

1. **Colores:** el diseño previó verde, amarillo, rojo y sin color. ¿Qué significan el **verde
   claro**, el **naranja** (distinto del amarillo) y el **azul**? Recomendación provisoria:
   verdes → cerradas; naranja y amarillo → en proceso; rojos → anuladas; sin color → solicitadas;
   el resto se lista para revisar.
2. **Verdes sin OC** (~600 de 1628 filas): ¿se compraron sin OC, no se compraron, se resolvieron
   de otra forma? Recomendación: cierre manual (`sin_conformidad`) y sin cantidad comprada.
3. **«Recibido?» = ok:** recomendación: no crear recepciones (no hay fecha y falsearía los
   tiempos); cierre manual, guardando el texto. Alternativa: recepción con la fecha del pedido,
   marcada como histórica.
4. **«IMPORTE»:** recomendación: precio unitario, salvo que la hoja sume con `SUM(importe)` o
   tenga «PU» (entonces «PU» es el unitario).
5. **Moneda:** `"$"` → ARS; `[$USD]` → USD; sin símbolo → USD inferida (regla del diseño),
   salvo que otra columna de la misma fila tenga `"$"` (como en el 1103), en cuyo caso ARS
   inferida. Siempre `moneda_inferida` cuando no hay símbolo.
6. **Hojas que no encajan** (encabezados corridos): recomendación: importar la cabecera y las
   líneas (cantidad, producto, detalles, imputación) y dejar precios, proveedor y OC «a revisar»
   con el texto original, listando esas hojas en el informe. No adivinar columnas corridas.
7. **Cotizaciones de otros proveedores** (columnas a la derecha): crear una oferta por proveedor
   (sin adjudicar) cuando el importe se pueda leer; si es texto ilegible, guardarlo en
   observaciones.
8. **Número de pedido:** usar el del nombre de la hoja y avisar cuando `B1` no coincide. El
   sufijo («- NO», «hierros») va a observaciones.
9. **Filas sin cantidad:** si el texto empieza con un número, ese es la cantidad («2 tambor plus
   50» → 2 × «tambor plus 50»), marcada «a revisar»; si no, va a las observaciones del pedido.
   Totales y errores (`#VALUE!`) se ignoran.
10. **Modelo con varios equipos + sector con porcentajes:** recomendación: si «Detalles» nombra
    varios equipos, un destino por equipo con la cantidad repartida (enteros, el resto al
    primero); si además el sector trae porcentajes, mandan los porcentajes (un destino por
    centro de costo, con el modelo o «a identificar» y el texto de detalles).
11. **Dos OC en una celda** («100777817 - 100777819»): la primera en `nro_oc` y la celda completa
    en observaciones, «a revisar».
