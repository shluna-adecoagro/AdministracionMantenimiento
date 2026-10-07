from app.models.sectores_models import Sector, EstadoSector
from app.models.auditoria_models import AuditLog
from app.core.db import db
from app.audit.registrar import registrar_cambio

def obtener_estados_sector():
    return EstadoSector.query.all()

def obtener_sectores_filtrados(campo, q, valor_fk):
    query = Sector.query

    if campo == "estado_sector_id" and valor_fk:
        query = query.filter(Sector.estado_sector_id == valor_fk)

    if q:
        if campo == "todos":
            query = query.filter(
                (Sector.nombre_sector.ilike(f"%{q}%")) |
                (Sector.centro_costo.ilike(f"%{q}%"))
            )
        else:
            query = query.filter(getattr(Sector, campo).ilike(f"%{q}%"))

    return query.all()

def crear_sector(form):
    motivo = form.get("motivo_operacion")

    nuevo = Sector(
        nombre_sector=form["nombre_sector"],
        centro_costo=form["centro_costo"],
        estado_sector_id=form["estado_sector_id"]
    )

    db.session.add(nuevo)
    db.session.flush()
    db.session.refresh(nuevo)

    estado_actual = nuevo.to_dict()
    estado_actual["estado_sector_nombre"] = nuevo.estado.nombre_estado_sector
    estado_actual.pop("estado", None)
    estado_actual.pop("estado_sector", None)

    registrar_cambio(
        "sectores",
        nuevo.sector_id,
        "INSERT",
        None,
        estado_actual,
        motivo
    )

    db.session.commit()

def obtener_sector(id):
    return Sector.query.get_or_404(id)

def actualizar_sector(id, form):
    motivo = form.get("motivo_operacion")

    sector = obtener_sector(id)

    estado_anterior = sector.to_dict()
    estado_anterior["estado_sector_nombre"] = sector.estado.nombre_estado_sector
    estado_anterior.pop("estado", None)
    estado_anterior.pop("estado_sector", None)

    sector.nombre_sector = form["nombre_sector"]
    sector.centro_costo = form["centro_costo"]
    sector.estado_sector_id = form["estado_sector_id"]

    db.session.flush()
    db.session.refresh(sector)

    estado_actual = sector.to_dict()
    estado_actual["estado_sector_nombre"] = sector.estado.nombre_estado_sector
    estado_actual.pop("estado", None)
    estado_actual.pop("estado_sector", None)

    registrar_cambio(
        "sectores",
        id,
        "UPDATE",
        estado_anterior,
        estado_actual,
        motivo
    )

    db.session.commit()


def eliminar_sector(id, form):
    motivo = form.get("motivo_operacion")

    sector = obtener_sector(id)

    estado_anterior = sector.to_dict()
    estado_anterior["estado_sector_nombre"] = sector.estado.nombre_estado_sector
    estado_anterior.pop("estado", None)
    estado_anterior.pop("estado_sector", None)

    db.session.delete(sector)

    registrar_cambio(
        "sectores",
        id,
        "DELETE",
        estado_anterior,
        None,
        motivo
    )

    db.session.commit()

def obtener_historial_sector(id, page):
    query = (
        AuditLog.query
        .filter_by(TablaAfectada="sectores", RegistroID=str(id))
        .order_by(AuditLog.Version.desc())
    )
    paginado = query.paginate(page=page, per_page=10, error_out=False)
    return paginado.items, paginado

def obtener_config_sector(estados):
    return {
        "fields": {
            "nombre_sector": {"label": "Nombre del Sector", "tipo": "text", "required": True},
            "centro_costo": {"label": "Centro de Costo", "tipo": "text", "required": True},
            "estado_sector_id": {
                "label": "Estado",
                "tipo": "select",
                "options": [
                    {"value": e.estado_sector_id, "label": e.nombre_estado_sector}
                    for e in estados
                ]
            }
        }
    }
