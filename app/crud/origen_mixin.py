# app/crud/origen_mixin.py
"""
Origen de los registros importados (histórico, reportes del ERP, PDF).

Toda tabla que recibe datos de otra fuente lleva:

  * origen        de dónde vino el registro: app (cargado en la app), histórico
                  (Excel), reporte (del ERP) o PDF (leído con IA y revisado).
  * clave_origen  cómo se lo identifica en esa fuente (ej: archivo + hoja del
                  Excel, o sistema + número del ERP). Única cuando está cargada.

Con eso la importación es idempotente: repetirla actualiza en lugar de duplicar.
Las dos columnas son de solo importación (se ven, pero no se editan en la web ni
en la API) y, si el override no declara otra, `clave_origen` es la clave natural.
Lo cargado en la app queda con origen «app» y sin clave de origen.
"""
from app.core.db import db

OPCIONES_ORIGEN = (
    {"value": "app", "label": "App"},
    {"value": "historico", "label": "Histórico"},
    {"value": "reporte", "label": "Reporte del ERP"},
    {"value": "pdf", "label": "PDF"},
)


class OrigenMixin:
    origen = db.Column(db.String(20), nullable=False, default="app", info={"label": "Origen"})
    clave_origen = db.Column(db.String(200), nullable=True, unique=True, info={"label": "Clave de origen"})
