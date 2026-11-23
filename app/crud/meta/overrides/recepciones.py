"""
Recepciones: la conformidad de lo que llegó (fase 10, PR 10.5).
Modelo en app/models/recepciones_models.py; diseño en docs/diseno_tablas_operativas.md.

Reglas (se verifican al guardar, en la web, la API y la importación):

  * Material recibido: si se deja vacío, la presentación adjudicada (si hay una
    sola) o el material de la línea (si es concreto). Nunca un genérico.
  * Cantidad: si se deja vacía, lo pendiente de recibir del destino, convertido a
    la unidad del material (envases enteros, si es una presentación).
  * Se convierte a la unidad de la línea igual que la adjudicación: una
    presentación de otro genérico no se puede recibir para esa línea.
  * Recibir más de lo comprado se acepta, con un aviso (la conformidad es
    registrar lo que llegó).
"""
from __future__ import annotations

import math

from app.core.db import db
from app.crud.core.coercion import ErroresValidacion
from app.crud.meta.overrides.documentos import factor_material
from app.models.documentos_models import Adjudicacion, DocumentoLinea, DocumentoProveedor
from app.models.materiales_models import Material
from app.models.pedidos_models import PedidoLineaDestino
from app.models.recepciones_models import Recepcion


def sin_genericos():
    return Material.es_generico.is_(False)


def lineas_de_remitos():
    return DocumentoLinea.documento.has(DocumentoProveedor.tipo == "remito")


def _es_presentacion(material) -> bool:
    return material is not None and material.material_generico_id is not None


def completar_recepcion(datos: dict, registro):
    if registro is not None:
        return datos  # en una modificación no se completa nada
    destino = db.session.get(PedidoLineaDestino, datos.get("pedido_linea_destino_id") or 0)
    if destino is None:
        return datos  # la FK inexistente la informa la validación
    linea = destino.pedido_linea

    if datos.get("material_id") is None:
        adjudicados = {a.documento_linea.material_id for a in
                       Adjudicacion.query.filter(Adjudicacion.pedido_linea_id == linea.pedido_linea_id,
                                                 Adjudicacion.cantidad_adjudicada > 0)
                       if a.documento_linea.material_id is not None}
        if len(adjudicados) == 1:
            datos["material_id"] = adjudicados.pop()
        elif linea.material is not None and not linea.material.es_generico:
            datos["material_id"] = linea.material_id
        else:
            raise ErroresValidacion({"material_id": (
                "Indicá qué material llegó: la línea pide un genérico (o no tiene material) y no hay una "
                "única presentación adjudicada.")})

    if datos.get("cantidad") is None:
        material = db.session.get(Material, datos["material_id"])
        f = factor_material(material, linea)
        pendiente = destino.pendiente_recibir
        if f is None:
            return datos  # el error de conversión lo informa al_guardar
        if pendiente <= 1e-9:
            raise ErroresValidacion({"cantidad": "No queda nada pendiente de recibir en este destino: "
                                                 "indicá la cantidad que llegó."})
        cantidad = pendiente / f
        if _es_presentacion(material):
            cantidad = math.ceil(cantidad - 1e-9)  # envases enteros
        datos["cantidad"] = cantidad
    return datos


def al_guardar_recepcion(r, operacion: str, cambiados: set):
    linea = r.destino.pedido_linea
    errores = {}
    if factor_material(r.material, linea) is None:
        errores["material_id"] = (f"«{r.material.etiqueta}» no es una presentación de "
                                  f"«{linea.material.etiqueta}»: no se puede convertir la cantidad.")
    if r.cantidad is None or r.cantidad <= 0:
        errores["cantidad"] = "La cantidad recibida tiene que ser mayor que cero."
    if errores:
        raise ErroresValidacion(errores)

    db.session.refresh(linea)
    destino = r.destino
    if destino.pendiente_recibir < -1e-9:
        return ("aviso", f"Se recibió más de lo comprado en este destino ({destino.recibida:g} de "
                         f"{destino.comprada:g} {linea.se_cuenta_en or ''}).".replace(" )", ")"))
    return None


def tab_recepciones_de_la_linea(linea) -> dict:
    filas = []
    for d in sorted(linea.destinos, key=lambda x: x.pedido_linea_destino_id):
        for r in sorted(d.recepciones, key=lambda x: (x.fecha, x.recepcion_id)):
            filas.append([r.fecha.isoformat(), d.nombre.split(" → ")[-1], r.material.etiqueta,
                          f"{r.cantidad:g} {r.se_cuenta_en or ''}".strip(), f"{r.recibida_en_linea:g}",
                          r.recibido_por.nombre_completo if r.recibido_por else "—", r.observaciones or "—"])
    return {
        "columnas": ["Fecha", "Destino", "Material recibido", "Cantidad", "En la unidad de la línea",
                     "Recibido por", "Observaciones"],
        "filas": filas,
        "vacio": "Todavía no se recibió nada.",
        "nota": "Las recepciones se cargan en cada destino (pestaña «Destinos» → «Recepciones»).",
    }


OVERRIDES = {
    "recepciones": {
        "model": Recepcion,
        "label_singular": "recepción",
        "label_plural": "recepciones",
        "genero": "f",
        "padre": [
            {"entidad": "pedido_linea_destinos", "fk": "pedido_linea_destino_id", "label": "Recepciones"},
            {"entidad": "documento_lineas", "fk": "documento_linea_id", "label": "Recepciones",
             "visible": lambda linea: linea.documento.tipo == "remito"},
        ],
        "fields": {
            # Si se dejan vacíos, se completan (ver completar_recepcion).
            "material_id": {"fk_filtro": sin_genericos, "required": False},
            "cantidad": {"required": False},
            "documento_linea_id": {"fk_filtro": lineas_de_remitos},
        },
        "listado": ["fecha", "pedido_linea_destino_id", "material_id", "cantidad", "se_cuenta_en",
                    "recibida_en_linea", "recibido_por_id"],
        "clave_natural": ["pedido_linea_destino_id", "fecha", "material_id"],
        "completar": completar_recepcion,
        "al_guardar": al_guardar_recepcion,
    },
}
