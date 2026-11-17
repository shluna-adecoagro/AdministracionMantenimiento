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
      listado / filtros                         columnas y búsqueda
      padre                                     si es subentidad de otra
      sidebar / orden                           menú lateral
      fields: {campo: {...}}                    widget, oculto, opciones, alias
                                                (otros nombres de columna al importar)
      excluir: [campo, ...]                     campos inferidos que no se exponen
      clave_natural: [campo, ...]               cómo se identifica el registro al
                                                importar (ej: el nombre), ya que los
                                                IDs de otras fuentes no coinciden

Lo mínimo es {"model": MiModelo}; todo lo demás tiene un valor por defecto.
La lista completa de claves está en registry.CLAVES_ENTIDAD.
"""
