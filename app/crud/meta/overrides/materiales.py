"""
Materiales, su stock y sus catálogos (categorías y tipos).

GENÉRICO Y PRESENTACIONES. El genérico («Aceite 15W-40», en litros, sin envase)
agrupa las presentaciones que se compran («Aceite 15W-40 bidón 20 L»: unidad L,
contenido por envase 20). El BOM y los planes preventivos pueden usar el
genérico (la cantidad no depende del envase); ofertas, stock y recepciones usan
siempre la presentación. Reglas (se verifican al guardar, en la web, la API y la
importación):

  * un genérico no tiene genérico propio, ni envase, ni stock; necesita la
    unidad (es la base para convertir cantidades) y su código empieza con GEN-;
  * una presentación apunta a un genérico (el select solo ofrece genéricos),
    tiene contenido por envase y la unidad de su genérico (se completa sola);
  * un genérico con presentaciones no puede dejar de serlo ni cambiar de unidad.
"""
from app.crud.core.coercion import ErroresValidacion
from app.models.materiales_models import CategoriaMaterial, Material, StockMaterial, TipoMaterial

PREFIJO_GENERICO = "GEN-"


def solo_genericos():
    return Material.es_generico.is_(True)


def sin_genericos():
    return Material.es_generico.is_(False)


def _presentaciones(material) -> list:
    return Material.query.filter_by(material_generico_id=material.material_id).all()


def al_guardar_material(m, operacion: str, cambiados: set):
    errores = {}
    if m.es_generico:
        if m.material_generico_id is not None:
            errores["material_generico_id"] = "Un genérico no tiene genérico propio."
        if m.presentacion_cantidad is not None:
            errores["presentacion_cantidad"] = ("Un genérico no tiene envase: el contenido por envase "
                                                "va en sus presentaciones.")
        if m.unidad_medida_id is None:
            errores["unidad_medida_id"] = ("El genérico necesita la unidad (por ejemplo, litros): es la "
                                           "base para convertir las cantidades de sus presentaciones.")
        if not (m.codigo or "").upper().startswith(PREFIJO_GENERICO):
            errores["codigo"] = (f"El código de un genérico empieza con {PREFIJO_GENERICO} "
                                 "(por ejemplo, GEN-ACEITE-15W40).")
        if StockMaterial.query.filter_by(material_id=m.material_id).count():
            errores["es_generico"] = "Tiene stock: el stock es de las presentaciones, no del genérico."
        otras = sorted({p.unidad_medida.nombre_unidad for p in _presentaciones(m)
                        if p.unidad_medida_id != m.unidad_medida_id and p.unidad_medida})
        if otras and "unidad_medida_id" not in errores:
            errores["unidad_medida_id"] = (f"Sus presentaciones están en {', '.join(otras)}: "
                                           "la unidad del genérico tiene que ser la misma.")
    else:
        if operacion == "UPDATE" and "es_generico" in cambiados and _presentaciones(m):
            errores["es_generico"] = "Tiene presentaciones: no puede dejar de ser genérico."
        if m.material_generico_id is not None:
            if m.presentacion_cantidad is None or m.presentacion_cantidad <= 0:
                errores["presentacion_cantidad"] = ("Una presentación necesita el contenido por envase "
                                                    "(por ejemplo, 20 para un bidón de 20 L).")
    if errores:
        raise ErroresValidacion(errores)
    return None


NO_SI = [{"value": False, "label": "No"}, {"value": True, "label": "Sí"}]

OVERRIDES = {
    "materiales": {
        "model": Material,
        "label_singular": "material",
        "label_plural": "materiales",
        "genero": "m",
        "sidebar": True,
        "orden": 20,
        # Las presentaciones son pestaña de su genérico («Nueva presentación»
        # llega con el genérico elegido y su unidad).
        "padre": {"entidad": "materiales", "fk": "material_generico_id", "label": "Presentaciones",
                  "visible": lambda material: material.es_generico},
        "fields": {
            "codigo": {"label": "Código (número de parte)"},
            # Si no se envían, valen No (la columna tiene valor por defecto).
            "es_generico": {"required": False, "options": NO_SI},
            "controla_stock": {"required": False, "options": NO_SI},
            # Solo genéricos; la unidad de la presentación es la del genérico.
            "material_generico_id": {"fk_filtro": solo_genericos, "depende_de": "unidad_medida_id"},
        },
        "listado": [
            "codigo", "descripcion", "marca_id", "categoria_material_id",
            "tipo_material_id", "material_generico_id", "es_generico", "stock_total",
        ],
        "filtros": [
            "codigo", "descripcion", "codigo_erp", "marca_id", "categoria_material_id",
            "tipo_material_id", "material_generico_id", "es_generico", "controla_stock",
        ],
        "excluir": ["etiqueta"],  # es código + descripción, que ya se muestran
        "clave_natural": ["codigo"],
        "al_guardar": al_guardar_material,
    },
    "stock_material": {
        "model": StockMaterial,
        "label_singular": "stock",
        "label_plural": "stock por ubicación",
        "genero": "m",
        # Subentidad: pestaña del material. El sector es el de la ubicación.
        "padre": {"entidad": "materiales", "fk": "material_id"},
        "fields": {
            "fecha_actualizacion": {"solo_lectura": True},
            # El stock es de las presentaciones, nunca de un genérico.
            "material_id": {"fk_filtro": sin_genericos},
        },
        "clave_natural": ["material_id", "ubicacion_id"],
    },
    # Catálogos (vienen de SharePoint): categorías y, dentro de cada una, sus tipos.
    "categorias_material": {
        "model": CategoriaMaterial,
        "label_singular": "categoría de material",
        "label_plural": "categorías de material",
        "genero": "f",
        "sidebar": True,
        "grupo": "catalogos",
        "orden": 130,
        "clave_natural": ["nombre_categoria"],
    },
    "tipos_material": {
        "model": TipoMaterial,
        "label_singular": "tipo de material",
        "label_plural": "tipos de material",
        "genero": "m",
        "padre": {"entidad": "categorias_material", "fk": "categoria_material_id"},
        "clave_natural": ["nombre_tipo"],
    },
}
