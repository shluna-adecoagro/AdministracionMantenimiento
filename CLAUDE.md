# Instrucciones para Claude Code

Sistema de gestión de mantenimiento (Flask + Jinja2 + API REST, SQLite) para el área de
mantenimiento de una empresa agropecuaria. Lo usa y mantiene una sola persona (el
"gestor"), que es quien revisa y mergea los PR.

## Dónde está el diseño

Leé estos documentos antes de tocar la parte operativa:

- `docs/vision_conceptual.md`: qué es el sistema, circuitos, conformidad, imputación
  contable, convivencia con el ERP (EAM hoy, SAP después), estados.
- `docs/diseno_tablas_operativas.md`: tablas, columnas, dueño de cada dato (ERP o app) y
  reglas de importación. **Ante una contradicción entre documentos, manda este.**
- `docs/plan_refactor_crud.md`: fases, decisiones tomadas y notas de cada fase.
- `docs/agregar_entidad.md`: cómo agregar o modificar una entidad (modelo, migración,
  override, tests).
- `docs/prompt_copilot_*.md`: prompts que el gestor usa en Copilot. Sus columnas de salida
  tienen que coincidir con lo que leen los importadores.

Si el código y el diseño no coinciden, o falta una decisión, preguntá antes de elegir.

## Forma de trabajo

- Una rama y un PR por fase (o por parte de una fase grande). Cada PR deja la app
  funcionando y los tests en verde.
- Cada fase empieza revisando su diseño con el gestor: dudas y contradicciones primero,
  código después.
- Al terminar una fase, agregá sus notas en `docs/plan_refactor_crud.md` y actualizá el
  estado en la tabla de fases. Si cambiaste el diseño, actualizá
  `docs/diseno_tablas_operativas.md`.
- Textos de la app, mensajes, comentarios, commits y documentación en español
  (rioplatense, sin voseo forzado en la interfaz).
- **Sesiones cortas:** avisale al gestor cuando convenga empezar una sesión nueva (por
  ejemplo, al cerrar un PR después de varios en la misma sesión, o antes de arrancar
  un tema que no depende de lo anterior), para que una sesión larga no afecte las
  respuestas. Lo importante de cada tema tiene que quedar en los docs y en los PR, no
  solo en la conversación.

## Convenciones

- Las pantallas, la API y la importación CSV **se generan desde el metamodelo**
  (introspección del modelo + override en `app/crud/meta/overrides/`). No escribas rutas
  CRUD a mano; si el framework no alcanza, extendelo.
- Tablas en plural y snake_case, PK `<entidad>_id`, `uuid`, `creado_en` / `actualizado_en`,
  `AuditMixin` en todo lo operativo.
- **Estados de flujo como opciones fijas en código** (no catálogos editables): las reglas
  dependen de ellos.
- **Cantidades derivadas sin columna** (ofertada, adjudicada, recibida, facturada): se
  calculan sumando filas vinculadas. Nunca contadores que se incrementan.
- **Datos del ERP:** columna `sistema` + número, únicos juntos; las columnas cuyo dueño es
  el ERP no se editan en la app, solo por importación.
- **Importadores:** un adaptador por fuente que traduce a un formato interno común;
  idempotentes (`origen` + `clave_origen`); guardan siempre el texto original y dejan "a
  revisar" lo que no pueden interpretar, nunca lo descartan.
- El esquema cambia solo con migraciones de Alembic (`flask --app run db migrate` /
  `upgrade`).
- Dependencias nuevas: en `requirements.txt` **y** en `environment.yml` (un test verifica
  que coincidan).

## Comandos

```bash
conda activate adminmant       # entorno del proyecto (environment.yml)
python -m pytest               # tests (xfail_strict: un xfail que pasa es una falla)
python run.py                  # app en http://127.0.0.1:5000
flask --app run db upgrade     # aplicar migraciones
flask --app run importar ...   # importación CSV (ver docs)
```

## Datos

- No hay datos reales en el repo. Los ejemplos que pase el gestor vienen anonimizados.
- Nunca subas `.env`, bases de datos (`instance/`) ni archivos subidos (`app/static/uploads/`).
