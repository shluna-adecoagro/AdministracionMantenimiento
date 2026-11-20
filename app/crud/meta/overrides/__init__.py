# app/crud/meta/overrides/__init__.py
"""
Overrides de entidades: solo lo que NO se puede deducir del modelo SQLAlchemy.

Cada módulo de este paquete define un dict OVERRIDES = {nombre_entidad: {...}}.
El registry los descubre solo: para agregar una entidad, se crea o amplía un
archivo acá; no hay que registrarla en ningún otro lado.

Dónde va cada dato:

  * Lo que describe el DATO va en el modelo, en la columna:
      nombre = db.Column(db.String(100), nullable=False, info={"label": "Nombre"})
    (obligatoriedad, largo máximo, FKs y etiquetas). Así lo comparten la web,
    la API y la documentación.

  * Lo que describe la PANTALLA va en el override:
      label_singular / label_plural / genero   textos de la entidad
      sidebar / grupo / orden                   menú lateral (grupo: "operativos",
                                                "maestros" o "catalogos")
      listado / filtros                         columnas y búsqueda
      padre                                     si es subentidad de otra (o una lista
                                                de padres, ej: el BOM de un modelo)
      fields: {campo: {...}}                    widget, opciones, alias (otros nombres
                                                de columna al importar), solo_lectura,
                                                depende_de (None desactiva un select
                                                dependiente inferido)...
      excluir: [campo, ...]                     campos inferidos que no se exponen
      clave_natural: [campo, ...]               cómo se identifica el registro al
                                                importar (ej: el nombre)
      tabs_extra: [{id, label, funcion}]        pestañas con una tabla calculada
      al_guardar: funcion(registro, op, cambiados) se ejecuta al crear o modificar
                                                (ej: copiar el BOM del modelo al activo)
      acciones: [{id, label, funcion, ...}]     botones del detalle (ej: «Traer ítems
                                                del modelo»)
      auditoria / auditoria_ignorar             historial de cambios

Lo mínimo es {"model": MiModelo}; todo lo demás tiene un valor por defecto.
La lista completa de claves está en registry.CLAVES_ENTIDAD.

Guía paso a paso, con un ejemplo: docs/agregar_entidad.md
"""
