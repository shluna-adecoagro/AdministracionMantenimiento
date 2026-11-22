# Prompt para Copilot: equivalencias de pedidos históricos

Uso: abrí Copilot (con tu cuenta corporativa), adjuntá los tres archivos indicados abajo y pegá el texto del recuadro. Si la lista de pendientes es larga, Copilot va a procesarla en tandas: pedile "seguí" hasta que termine.

**Archivos a adjuntar**

1. `pendientes.csv`: los textos a resolver. Columnas: `id`, `tipo` (destino o material), `texto`, `contexto`, `veces`. Lo va a generar el importador de la app; mientras tanto, para probar, podés armarlo a mano copiando algunas filas de "Producto" (tipo material) y de "Detalles" (tipo destino) de pedidos reales. En `contexto` va la referencia del pedido y la otra columna de la misma fila (por ejemplo, para un destino, el producto; para un material, el detalle).
2. `activos.csv`: la lista de activos exportada de la app con `flask --app run exportar activos activos.csv` (número de activo, descripción, categoría, tipo, marca, modelo, número de serie, número de motor, año, sector, ubicación, usuario asignado, código de carga de gasoil, estado).
3. `maestro_materiales.csv`: el maestro de materiales.

> La lista de SharePoint solo sirvió para la carga inicial: la fuente es la app. Las columnas de `maestro_materiales.csv` que usa este prompt (`numero_parte`, `codigo_erp`, `codigo_generico`, `presentaciones_disponibles`, `modelos_aplicables`) corresponden al maestro anterior; el prompt se ajusta al export de la app cuando el maestro cambie en la fase 10 (ver `diseno_tablas_operativas.md`, «Cambios a tablas existentes»).

---

```text
Sos un asistente que ayuda a ordenar datos de mantenimiento de maquinaria agrícola. Tu tarea es proponer equivalencias entre textos escritos a mano en pedidos de compra y los registros de dos listas maestras. Una persona va a revisar todas tus propuestas antes de usarlas, así que es mucho mejor dejar algo sin resolver que adivinar.

ARCHIVOS
- pendientes.csv: textos a resolver. Columnas: id, tipo (destino o material), texto, contexto, veces.
- activos.csv: activos de la empresa (número de activo, descripción, categoría, tipo, marca, modelo, número de serie, número de motor, sector, ubicación, entre otras).
- maestro_materiales.csv: materiales. Columnas relevantes: numero_parte, descripcion, categoria, tipo_material, unidad_medida, marca, codigo_erp, codigo_generico, presentacion, presentaciones_disponibles, modelos_aplicables.

QUÉ HACER CON CADA FILA DE pendientes.csv

Si tipo = destino (el texto dice para qué equipo o lugar es la compra):
1. Buscá en activos.csv por número de activo, descripción, número de serie y código de carga de gasoil. Ignorá mayúsculas, acentos y espacios de más.
2. Si el texto nombra varios activos (por ejemplo, una lista de códigos separados por comas, o "3 y 4" después de un nombre), proponé todos los que encuentres.
3. Si el texto es solo un modelo (por ejemplo "580" o "W20F") y coincide con la columna modelo de activos.csv, el resultado es "modelo" con el nombre exacto del modelo tal como figura en activos.csv. Si la coincidencia es parcial (por ejemplo "580" y el modelo es "580N"), la confianza es media.
4. Si el texto nombra un sector o una ubicación de activos.csv y ningún activo en particular, el resultado es "sector" o "ubicacion".
5. Si nada coincide, el resultado es "sin_resolver".

Si tipo = material (el texto es el producto pedido):
1. Normalizá el código: sin espacios, puntos ni guiones, sin distinguir mayúsculas, conservando los ceros iniciales. Buscalo en numero_parte, en codigo_erp y en los códigos que aparecen dentro de presentaciones_disponibles.
2. Si el texto es una descripción sin código, buscá por descripción, y usá el contexto (equipo o modelo) para elegir entre candidatos con modelos_aplicables.
3. Para fluidos (aceites, refrigerantes), proponé una presentación concreta (por ejemplo, la de 20 L), nunca un código genérico que empiece con "GEN-". Si no se puede saber la presentación, confianza baja.
4. Si no existe en el maestro, el resultado es "material_nuevo": proponé una descripción en español con lo que dice el texto (sin agregar medidas ni especificaciones que no estén escritas), y una categoria, un tipo_material y una unidad_medida elegidos SOLO entre los valores que ya existen en maestro_materiales.csv. Si ninguno encaja, poné "A definir".

REGLAS
- Usá únicamente códigos que existan literalmente en los archivos. Nunca inventes un número de activo, de parte ni un modelo.
- Confianza alta: coincidencia exacta de código o de nombre sin ambigüedad.
- Confianza media: coincidencia parcial o deducida del contexto, con un solo candidato razonable.
- Confianza baja: varios candidatos posibles o deducción débil. En "motivo", listá los candidatos.
- No saltees filas ni cambies su orden. Una fila de salida por cada fila de entrada.

FORMATO DE SALIDA
Devolvé una tabla con estas columnas, en este orden, separadas por punto y coma, con una fila de encabezado:
id;tipo;texto;resultado;codigos;descripcion_propuesta;categoria_propuesta;tipo_material_propuesto;unidad_propuesta;confianza;motivo

- resultado: activo, varios_activos, modelo, sector, ubicacion, material_existente, material_nuevo o sin_resolver.
- codigos: números de activo, nombre de modelo, sector, ubicación o numero_parte. Si son varios, separados por " | ".
- Las columnas de "propuesta" solo se completan para material_nuevo.
- motivo: una frase corta que explique la equivalencia o la duda.

Si son más de 50 filas, procesá de a 50 y al final de cada tanda escribí "Faltan N filas. Escribí 'seguí' para continuar."
Al terminar todas, agregá un resumen: cantidad de filas por resultado y por confianza.
```

---

**Qué revisar después**

- Todas las filas de confianza media y baja, y todas las de `material_nuevo`.
- Una muestra de las de confianza alta (por ejemplo, 1 de cada 10), para confirmar que no se equivoca en lo "seguro".
- Pegá la tabla en Excel (Datos → Texto en columnas, separador punto y coma), corregí lo que haga falta y guardala como `equivalencias_revisadas.csv`. Eso es lo que va a leer el importador.
