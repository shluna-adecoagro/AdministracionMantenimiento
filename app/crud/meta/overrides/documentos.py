"""
Documentos de proveedores y adjudicación (fase 10, PR 10.4).
Modelos en app/models/documentos_models.py; diseño en docs/diseno_tablas_operativas.md.

Reglas (se verifican al guardar, en la web, la API y la importación):

  * El proveedor se identifica por CUIT, código del ERP o razón social; mientras
    no se identifique queda el texto tal como vino, y el documento no se puede
    marcar «revisado» (tampoco sin fecha ni moneda).
  * Una línea de oferta nunca tiene un genérico (lo que se ofrece es una
    presentación); su unidad es la del material.
  * Una adjudicación vincula una línea de OFERTA con una línea de pedido:
      - no se adjudica a una línea anulada;
      - la oferta de una presentación de otro genérico no se puede convertir;
      - una línea de oferta sin material identificado no se adjudica a una
        línea de pedido que pide un genérico (no hay de dónde convertir);
      - lo adjudicado de una línea de oferta no supera lo ofertado.
  * Acciones del documento: «Vincular con pedidos» (crea las adjudicaciones en
    0 con las líneas de pedido abiertas del mismo material, o del genérico de la
    presentación) y «Adjudicar lo vinculado» (pone lo que falta comprar, sin
    superar lo ofertado; envases enteros si es una presentación).
"""
from __future__ import annotations

import math
import re

from app.core.db import db
from app.crud.core.coercion import ErroresValidacion
from app.crud.meta.overrides.pedidos import normalizar_oc
from app.models.documentos_models import (
    MONEDAS,
    TIPOS_DOCUMENTO,
    TIPOS_LINEA,
    Adjudicacion,
    DocumentoLinea,
    DocumentoProveedor,
)
from app.models.materiales_models import Material
from app.models.pedidos_models import PedidoLinea
from app.models.recursos_models import Proveedor

NO_SI = [{"value": False, "label": "No"}, {"value": True, "label": "Sí"}]


def _normalizar_texto(texto) -> str:
    from app.crud.introspect import normalizar_texto

    return re.sub(r"[.,]", "", normalizar_texto(texto))


def solo_digitos(texto) -> str:
    return re.sub(r"\D", "", str(texto or ""))


def identificar_proveedor(cuit=None, texto=None, codigo_erp=None):
    """Proveedor por CUIT, código del ERP o razón social (sin distinguir mayúsculas ni puntos)."""
    if cuit and solo_digitos(cuit):
        for p in Proveedor.query.filter(Proveedor.cuit.isnot(None)):
            if solo_digitos(p.cuit) == solo_digitos(cuit):
                return p
    if codigo_erp:
        p = Proveedor.query.filter_by(codigo_erp=str(codigo_erp).strip()).first()
        if p is not None:
            return p
    if texto:
        buscado = _normalizar_texto(texto)
        candidatos = [p for p in Proveedor.query if _normalizar_texto(p.razon_social) == buscado]
        if len(candidatos) == 1:
            return candidatos[0]
    return None


def sin_genericos():
    return Material.es_generico.is_(False)


def lineas_de_ofertas():
    return DocumentoLinea.documento.has(DocumentoProveedor.tipo == "oferta")


def _valor(datos, registro, campo):
    if campo in datos:
        return datos[campo]
    return getattr(registro, campo, None) if registro is not None else None


# ---------------------------------------------------------------------------
# Documento
# ---------------------------------------------------------------------------

def completar_documento(datos: dict, registro):
    if "nro_oc" in datos:
        datos["nro_oc"] = normalizar_oc(datos["nro_oc"])
    if _valor(datos, registro, "proveedor_id") is None:
        p = identificar_proveedor(_valor(datos, registro, "proveedor_cuit"),
                                  _valor(datos, registro, "proveedor_texto"))
        if p is not None:
            datos["proveedor_id"] = p.recurso_id
    return datos


def al_guardar_documento(doc, operacion: str, cambiados: set):
    if doc.revisado:
        faltan = [nombre for campo, nombre in (("proveedor_id", "el proveedor identificado"),
                                               ("fecha", "la fecha"), ("moneda", "la moneda"))
                  if getattr(doc, campo) is None]
        if faltan:
            raise ErroresValidacion({"revisado": "Para marcarlo revisado falta " + ", ".join(faltan) + "."})
    return None


# ---------------------------------------------------------------------------
# Adjudicación
# ---------------------------------------------------------------------------

def factor(linea_oferta, linea_pedido) -> float | None:
    """
    Cuánto vale 1 unidad de la línea de oferta en la unidad de la línea de pedido
    (None si no se puede convertir). Ver «Unidades: genérico y presentación».
    """
    return factor_material(linea_oferta.material, linea_pedido)


def factor_material(ofertado, linea_pedido) -> float | None:
    """Ídem, para un material (el ofertado, o el recibido en una recepción)."""
    pedido = linea_pedido.material
    if pedido is None or not pedido.es_generico:
        return 1.0  # material concreto o sin identificar: tal cual
    if ofertado is None:
        return None  # pide un genérico y no se sabe qué se ofrece
    if ofertado.material_generico_id == pedido.material_id:
        return float(ofertado.presentacion_cantidad or 1)
    return None  # presentación de otro genérico (o un material sin relación)


def al_guardar_adjudicacion(a, operacion: str, cambiados: set):
    errores = {}
    lo, lp = a.documento_linea, a.pedido_linea
    if lp.estado == "anulado":
        errores["pedido_linea_id"] = "La línea de pedido está anulada."
    elif factor(lo, lp) is None:
        if lo.material is None:
            errores["documento_linea_id"] = (
                "La línea de la oferta no tiene el material identificado y la línea de pedido pide un "
                "genérico: no hay de dónde convertir. Identificá primero el material.")
        else:
            errores["documento_linea_id"] = (
                f"«{lo.material.etiqueta}» no es una presentación de «{lp.material.etiqueta}»: "
                "no se puede convertir la cantidad.")
    if a.cantidad_adjudicada is None or a.cantidad_adjudicada < 0:
        errores["cantidad_adjudicada"] = "La cantidad adjudicada no puede ser negativa."
    if errores:
        raise ErroresValidacion(errores)
    db.session.refresh(lo)
    if (lo.adjudicada or 0) > lo.cantidad + 1e-9:
        raise ErroresValidacion({"cantidad_adjudicada": (
            f"Se adjudica más de lo ofertado en la línea {lo.nro_linea} ({lo.adjudicada:g} de {lo.cantidad:g})."
        )})
    return None


def vincular_con_pedidos(doc) -> str:
    """Crea en 0 las adjudicaciones con las líneas de pedido abiertas del mismo material."""
    from app.crud.entidades import servicio

    s = servicio("adjudicaciones", confirmar=False)
    creadas, sin_material = 0, 0
    for lo in doc.lineas:
        if lo.tipo_linea != "material":
            continue
        if lo.material is None:
            sin_material += 1
            continue
        materiales = [lo.material_id] + ([lo.material.material_generico_id] if lo.material.material_generico_id else [])
        ya = {a.pedido_linea_id for a in lo.adjudicaciones}
        candidatas = (PedidoLinea.query
                      .filter(PedidoLinea.material_id.in_(materiales), PedidoLinea.estado != "anulado",
                              PedidoLinea.enviada_en.isnot(None))  # las en borrador no se cotizan
                      .order_by(PedidoLinea.pedido_linea_id).all())
        for lp in candidatas:
            if lp.pedido_linea_id in ya or (lp.pendiente_comprar or 0) <= 0:
                continue
            s.crear({"documento_linea_id": lo.documento_linea_id, "pedido_linea_id": lp.pedido_linea_id,
                     "cantidad_adjudicada": 0}, "Vinculación con pedidos")
            creadas += 1
    if creadas == 1:
        partes = ["Se vinculó 1 línea de pedido."]
    elif creadas:
        partes = [f"Se vincularon {creadas} líneas de pedido."]
    else:
        partes = ["No se encontraron líneas de pedido abiertas con esos materiales."]
    if sin_material:
        partes.append(f"{sin_material} línea{'s' if sin_material != 1 else ''} de la oferta sin el material "
                      "identificado no se vincularon.")
    return " ".join(partes)


def adjudicar_lo_vinculado(doc) -> str:
    """Pone en cada vínculo en 0 lo que falta comprar, sin superar lo ofertado."""
    from app.crud.entidades import servicio

    s = servicio("adjudicaciones", confirmar=False)
    adjudicadas = 0
    for lo in doc.lineas:
        for a in sorted(lo.adjudicaciones, key=lambda x: x.adjudicacion_id):
            if a.cantidad_adjudicada:
                continue
            db.session.refresh(lo)
            db.session.refresh(a.pedido_linea)
            f = factor(lo, a.pedido_linea)
            pendiente = a.pedido_linea.pendiente_comprar or 0
            disponible = lo.cantidad - (lo.adjudicada or 0)
            if f is None or pendiente <= 0 or disponible <= 0:
                continue
            cantidad = pendiente / f
            if lo.material is not None and lo.material.material_generico_id is not None:
                cantidad = math.ceil(cantidad - 1e-9)  # envases enteros
            cantidad = min(cantidad, disponible)
            s.actualizar(a, {"cantidad_adjudicada": cantidad}, "Adjudicación de lo vinculado")
            adjudicadas += 1
    if not adjudicadas:
        return "No había vínculos para adjudicar (o ya no queda nada pendiente de comprar)."
    if adjudicadas == 1:
        return "Se adjudicó 1 vínculo. Revisá la cantidad."
    return f"Se adjudicaron {adjudicadas} vínculos. Revisá las cantidades."


ACCIONES_DOCUMENTO = [
    {
        "id": "vincular_pedidos",
        "label": "Vincular con pedidos",
        "funcion": vincular_con_pedidos,
        "seccion": "documento_lineas",
        "confirmar": ("¿Vincular cada línea con las líneas de pedido abiertas del mismo material? "
                      "Quedan cotizadas (adjudicada 0)."),
        "visible": lambda doc: doc.tipo == "oferta",
    },
    {
        "id": "adjudicar_vinculado",
        "label": "Adjudicar lo vinculado",
        "funcion": adjudicar_lo_vinculado,
        "seccion": "documento_lineas",
        "confirmar": ("¿Adjudicar en cada vínculo lo que falta comprar (sin superar lo ofertado)? "
                      "Después se pueden corregir las cantidades."),
        "visible": lambda doc: doc.tipo == "oferta",
    },
]


# ---------------------------------------------------------------------------
# Entidades
# ---------------------------------------------------------------------------

OVERRIDES = {
    "documentos_proveedor": {
        "model": DocumentoProveedor,
        "label_singular": "documento de proveedor",
        "label_plural": "documentos de proveedores",
        "genero": "m",
        "sidebar": True,
        "grupo": "operativos",
        "orden": 20,
        "padre": {"entidad": "proveedores", "fk": "proveedor_id", "label": "Documentos"},
        "fields": {
            "tipo": {"tipo": "select", "options": TIPOS_DOCUMENTO, "required": False},
            "moneda": {"tipo": "select", "options": MONEDAS},
            "moneda_inferida": {"required": False, "options": NO_SI},
            "revisado": {"required": False, "options": NO_SI},
        },
        "excluir": ["nombre"],
        "listado": ["tipo", "numero", "fecha", "proveedor_id", "proveedor_texto", "moneda", "total_sin_iva",
                    "total_lineas", "total_adjudicado", "nro_oc", "revisado"],
        "filtros": ["tipo", "numero", "proveedor_id", "proveedor_texto", "moneda", "nro_oc", "revisado",
                    "observaciones"],
        "completar": completar_documento,
        "al_guardar": al_guardar_documento,
        "acciones": ACCIONES_DOCUMENTO,
    },
    "documento_lineas": {
        "model": DocumentoLinea,
        "label_singular": "línea de documento",
        "label_plural": "líneas de documentos",
        "genero": "f",
        "padre": [
            {"entidad": "documentos_proveedor", "fk": "documento_id", "label": "Líneas"},
            {"entidad": "materiales", "fk": "material_id", "label": "Ofertas y documentos"},
        ],
        "fields": {
            "nro_linea": {"numeracion": "{n}", "numeracion_por": "documento_id"},
            "tipo_linea": {"tipo": "select", "options": TIPOS_LINEA, "required": False},
            "material_id": {"fk_filtro": sin_genericos},
        },
        "excluir": ["nombre"],
        "listado": ["documento_id", "nro_linea", "tipo_linea", "material_id", "descripcion_proveedor", "cantidad",
                    "se_cuenta_en", "precio_unitario", "subtotal", "adjudicada", "a_revisar"],
        "filtros": ["material_id", "codigo_proveedor", "descripcion_proveedor", "tipo_linea"],
        "clave_natural": ["documento_id", "nro_linea"],
    },
    "adjudicaciones": {
        "model": Adjudicacion,
        "label_singular": "adjudicación",
        "label_plural": "adjudicaciones",
        "genero": "f",
        "padre": [
            {"entidad": "documento_lineas", "fk": "documento_linea_id", "label": "Adjudicaciones"},
            {"entidad": "pedido_lineas", "fk": "pedido_linea_id", "label": "Ofertas y adjudicaciones"},
        ],
        "fields": {
            "documento_linea_id": {"fk_filtro": lineas_de_ofertas},
            "cantidad_adjudicada": {"required": False},
        },
        "listado": ["documento_linea_id", "pedido_linea_id", "cantidad_ofertada", "cantidad_adjudicada",
                    "adjudicada_en_pedido"],
        "clave_natural": ["documento_linea_id", "pedido_linea_id"],
        "al_guardar": al_guardar_adjudicacion,
    },
}
