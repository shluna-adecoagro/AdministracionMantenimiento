# app/crud/intercambio/documentos_copilot.py
"""
Adaptador: documentos de proveedores leídos con Copilot (fase 10, PR 10.4).

Lee los bloques A (cabeceras) y B (líneas) que devuelve el prompt de
docs/prompt_copilot_documentos.md, guardados como dos archivos CSV separados por
punto y coma, y los carga con el mismo servicio que la web y la API (validación,
reglas y auditoría).

  * Cada documento se identifica por su `clave_documento` (clave de origen):
    repetir la importación actualiza en lugar de duplicar.
  * Los documentos ya REVISADOS no se tocan (se informan): las correcciones del
    gestor no se pisan.
  * El proveedor se identifica por CUIT o razón social; si no, queda el texto.
  * El material se identifica por `material_sugerido` (el código del maestro);
    si no está, la línea queda «a revisar» con el código del proveedor.
  * Todo entra con «revisado» = No y origen «PDF».
  * Todo o nada: si hay errores, se informan todos y no se guarda nada.
"""
from __future__ import annotations

import csv
import io
import re
from dataclasses import dataclass, field
from datetime import datetime

from app.core.db import db
from app.crud.core.coercion import ErroresValidacion
from app.crud.core.service import ErrorIntegridad
from app.crud.intercambio.csv_entidades import _leer_texto

COLUMNAS_CABECERA = (
    "clave_documento", "tipo", "numero", "proveedor_nombre", "proveedor_cuit", "fecha", "moneda",
    "tipo_cambio", "total_sin_iva", "descuento_global_pct", "iva", "total", "total_usd_informado",
    "plazo_entrega_dias", "validez_hasta", "nro_oc", "equipo_texto", "horas_medidor", "archivo",
    "observaciones", "suma_lineas", "diferencia", "revisar",
)
COLUMNAS_LINEAS = (
    "clave_documento", "nro_linea", "tipo_linea", "codigo_proveedor", "descripcion_proveedor", "cantidad",
    "udm", "precio_lista", "descuento_pct", "precio_unitario", "subtotal", "material_sugerido", "revisar",
)
_NUMEROS_CABECERA = ("tipo_cambio", "total_sin_iva", "descuento_global_pct", "iva", "total",
                     "total_usd_informado", "horas_medidor")
_NUMEROS_LINEA = ("cantidad", "precio_lista", "descuento_pct", "precio_unitario")


@dataclass
class ResultadoDocumentos:
    simulado: bool = False
    documentos_creados: int = 0
    documentos_actualizados: int = 0
    documentos_sin_cambios: int = 0
    lineas_creadas: int = 0
    lineas_actualizadas: int = 0
    lineas_borradas: int = 0
    revisados_salteados: list[str] = field(default_factory=list)
    avisos: list[str] = field(default_factory=list)
    errores: list[tuple[str, int, str, str]] = field(default_factory=list)  # (archivo, fila, campo, mensaje)

    @property
    def ok(self) -> bool:
        return not self.errores

    def resumen(self) -> str:
        lineas = ["Importación de documentos de proveedores (Copilot)"
                  + (" (SIMULACIÓN: no se guardó nada)" if self.simulado else "")]
        if self.errores:
            lineas.append(f"  ✘ {len(self.errores)} error/es. No se guardó nada:")
            for archivo, fila, campo, mensaje in self.errores:
                donde = f"{archivo}, fila {fila}" if fila else archivo
                lineas.append(f"    {donde} [{campo}]: {mensaje}")
            return "\n".join(lineas)
        lineas.append(f"  ✔ Documentos: {self.documentos_creados} creados, {self.documentos_actualizados} "
                      f"actualizados, {self.documentos_sin_cambios} sin cambios.")
        lineas.append(f"  ✔ Líneas: {self.lineas_creadas} creadas, {self.lineas_actualizadas} actualizadas, "
                      f"{self.lineas_borradas} borradas.")
        if self.revisados_salteados:
            lineas.append(f"  ℹ Ya revisados (no se tocaron): {', '.join(self.revisados_salteados)}")
        for aviso in self.avisos:
            lineas.append(f"  ⚠ {aviso}")
        return "\n".join(lineas)


def _filas(contenido: bytes) -> tuple[list[dict], list[str]]:
    texto = _leer_texto(contenido)
    lector = csv.DictReader(io.StringIO(texto), delimiter=";")
    return [{(k or "").strip(): (v or "").strip() for k, v in fila.items()} for fila in lector
            if any((v or "").strip() for v in fila.values())], [c.strip() for c in (lector.fieldnames or [])]


def _numero(texto: str):
    if texto == "":
        return None
    try:
        return float(texto)
    except ValueError:
        raise ValueError(f"«{texto}» no es un número (se espera punto decimal, sin separador de miles)") from None


def _fecha(texto: str):
    if texto == "":
        return None
    try:
        return datetime.strptime(texto, "%Y-%m-%d").date()
    except ValueError:
        raise ValueError(f"«{texto}» no es una fecha AAAA-MM-DD") from None


def _codigo(texto: str) -> str:
    return re.sub(r"[\s\-]", "", texto or "").upper()


def _material_por_codigo(codigo: str):
    from app.models.materiales_models import Material

    buscado = _codigo(codigo)
    if not buscado:
        return None
    for m in Material.query.filter(Material.es_generico.is_(False)):
        if _codigo(m.codigo) == buscado or (m.codigo_erp and _codigo(m.codigo_erp) == buscado):
            return m
    return None


def importar_documentos(cabeceras: bytes, lineas: bytes, *, nombre_cabeceras="documentos.csv",
                        nombre_lineas="documento_lineas.csv", simular=False,
                        usuario="importación") -> ResultadoDocumentos:
    from app.crud.entidades import servicio
    from app.crud.meta.overrides.documentos import TIPOS_DOCUMENTO
    from app.models.documentos_models import TIPOS_LINEA, DocumentoLinea, DocumentoProveedor

    r = ResultadoDocumentos(simulado=simular)
    filas_a, columnas_a = _filas(cabeceras)
    filas_b, columnas_b = _filas(lineas)
    for archivo, columnas, esperadas in ((nombre_cabeceras, columnas_a, COLUMNAS_CABECERA),
                                         (nombre_lineas, columnas_b, COLUMNAS_LINEAS)):
        faltan = [c for c in esperadas if c not in columnas]
        if faltan:
            r.errores.append((archivo, 1, "_columnas", f"faltan las columnas: {', '.join(faltan)}"))
    if r.errores:
        return r

    tipos = {o["value"] for o in TIPOS_DOCUMENTO}
    tipos_linea = {o["value"] for o in TIPOS_LINEA}
    s_doc = servicio("documentos_proveedor", confirmar=False)
    s_lin = servicio("documento_lineas", confirmar=False)
    motivo = f"Lectura de PDF con Copilot ({nombre_cabeceras})"

    lineas_por_doc: dict[str, list[tuple[int, dict]]] = {}
    for n, fila in enumerate(filas_b, start=2):
        lineas_por_doc.setdefault(fila["clave_documento"], []).append((n, fila))
    claves = {f["clave_documento"] for f in filas_a}
    for clave, filas in lineas_por_doc.items():
        if clave not in claves:
            r.errores.append((nombre_lineas, filas[0][0], "clave_documento",
                              f"«{clave}» no está en {nombre_cabeceras}"))

    try:
        for n, fila in enumerate(filas_a, start=2):
            clave = fila["clave_documento"]
            if not clave:
                r.errores.append((nombre_cabeceras, n, "clave_documento", "falta la clave del documento"))
                continue
            if fila["tipo"] not in tipos:
                r.errores.append((nombre_cabeceras, n, "tipo", f"«{fila['tipo']}» no es un tipo de documento "
                                  f"({', '.join(sorted(tipos))})"))
                continue
            existente = DocumentoProveedor.query.filter_by(clave_origen=clave).first()
            if existente is not None and existente.revisado:
                r.revisados_salteados.append(clave)
                continue
            try:
                datos = {
                    "tipo": fila["tipo"], "numero": fila["numero"] or None,
                    "proveedor_texto": fila["proveedor_nombre"] or None,
                    "proveedor_cuit": fila["proveedor_cuit"] or None,
                    "fecha": _fecha(fila["fecha"]), "moneda": (fila["moneda"] or "").upper() or None,
                    "validez_hasta": _fecha(fila["validez_hasta"]),
                    "plazo_entrega_dias": int(_numero(fila["plazo_entrega_dias"]))
                    if fila["plazo_entrega_dias"] else None,
                    "nro_oc": fila["nro_oc"] or None, "equipo_texto": fila["equipo_texto"] or None,
                    "observaciones": " ".join(x for x in (f"[{fila['archivo']}]" if fila["archivo"] else "",
                                                          fila["observaciones"]) if x) or None,
                    "motivo_revision": fila["revisar"] or None,
                    **{c: _numero(fila[c]) for c in _NUMEROS_CABECERA},
                }
            except ValueError as e:
                r.errores.append((nombre_cabeceras, n, "_valor", str(e)))
                continue
            if datos["moneda"] not in (None, "ARS", "USD"):
                r.errores.append((nombre_cabeceras, n, "moneda", f"«{datos['moneda']}» no es ARS ni USD"))
                continue

            try:
                if existente is None:
                    doc = s_doc.crear({**datos, "origen": "pdf", "clave_origen": clave}, motivo, usuario)
                    r.documentos_creados += 1
                else:
                    doc = existente
                    cambios = {c: v for c, v in datos.items() if getattr(doc, c) != v}
                    if cambios:
                        s_doc.actualizar(doc, cambios, motivo, usuario)
                        r.documentos_actualizados += 1
                    else:
                        r.documentos_sin_cambios += 1
            except (ErroresValidacion, ErrorIntegridad) as e:
                _error_servicio(r, nombre_cabeceras, n, e)
                continue

            # Líneas del documento.
            vistas = set()
            for nl, fl in lineas_por_doc.get(clave, []):
                try:
                    nro = int(_numero(fl["nro_linea"]) or 0)
                    if nro <= 0:
                        raise ValueError("falta el número de línea")
                    if fl["tipo_linea"] not in tipos_linea:
                        raise ValueError(f"tipo de línea «{fl['tipo_linea']}» inválido ({', '.join(sorted(tipos_linea))})")
                    valores = {c: _numero(fl[c]) for c in _NUMEROS_LINEA}
                    if valores["cantidad"] is None or valores["precio_unitario"] is None:
                        raise ValueError("faltan la cantidad o el precio unitario")
                except ValueError as e:
                    r.errores.append((nombre_lineas, nl, "_valor", str(e)))
                    continue
                vistas.add(nro)
                material = _material_por_codigo(fl["material_sugerido"])
                revisar = [fl["revisar"]] if fl["revisar"] else []
                if fl["material_sugerido"] and material is None:
                    revisar.append(f"el material sugerido «{fl['material_sugerido']}» no está en el maestro")
                datos_l = {
                    "tipo_linea": fl["tipo_linea"], "codigo_proveedor": fl["codigo_proveedor"] or None,
                    "descripcion_proveedor": fl["descripcion_proveedor"] or None,
                    "udm_texto": fl["udm"] or None,
                    "material_id": material.material_id if material else None,
                    "motivo_revision": "; ".join(revisar) or None, **valores,
                }
                linea = DocumentoLinea.query.filter_by(documento_id=doc.documento_id, nro_linea=nro).first()
                try:
                    if linea is None:
                        s_lin.crear({**datos_l, "documento_id": doc.documento_id, "nro_linea": nro,
                                     "origen": "pdf", "clave_origen": f"{clave}|{nro}"}, motivo, usuario)
                        r.lineas_creadas += 1
                    else:
                        cambios = {c: v for c, v in datos_l.items() if getattr(linea, c) != v}
                        if cambios:
                            s_lin.actualizar(linea, cambios, motivo, usuario)
                            r.lineas_actualizadas += 1
                except (ErroresValidacion, ErrorIntegridad) as e:
                    _error_servicio(r, nombre_lineas, nl, e)

            # Líneas que ya no vienen: se borran, salvo que tengan adjudicaciones.
            if existente is not None:
                for linea in list(doc.lineas):
                    if linea.nro_linea in vistas:
                        continue
                    if linea.adjudicaciones:
                        r.avisos.append(f"{clave}: la línea {linea.nro_linea} ya no viene en el archivo, pero "
                                        "tiene adjudicaciones; no se borró.")
                        continue
                    s_lin.eliminar(linea, motivo, usuario)
                    r.lineas_borradas += 1
    except ErrorIntegridad as e:
        r.errores.append((nombre_cabeceras, 0, "_base", e.mensaje))

    if r.errores or simular:
        db.session.rollback()
        if r.errores:
            r.documentos_creados = r.documentos_actualizados = r.documentos_sin_cambios = 0
            r.lineas_creadas = r.lineas_actualizadas = r.lineas_borradas = 0
        return r
    db.session.commit()
    return r


def _error_servicio(r, archivo, fila, e):
    if isinstance(e, ErroresValidacion):
        r.errores.extend((archivo, fila, c, m) for c, m in e.errores.items())
    else:
        r.errores.append((archivo, fila, e.campo or "_base", e.mensaje))
