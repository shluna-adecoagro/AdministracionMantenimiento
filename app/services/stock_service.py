from app.core.db import db
from app.models.insumos_models import StockInsumo, Insumo
from app.models.ubicaciones_models import Ubicacion
from datetime import datetime


class StockService:

    # ============================================================
    # 1) STOCK TOTAL DE UN INSUMO
    # ============================================================
    @staticmethod
    def obtener_stock_total(insumo_id: int) -> float:
        registros = StockInsumo.query.filter_by(insumo_id=insumo_id).all()
        return sum(r.cantidad for r in registros)

    # ============================================================
    # 2) STOCK POR UBICACIÓN (DETALLE)
    # ============================================================
    @staticmethod
    def obtener_stock_por_ubicacion(insumo_id: int):
        registros = StockInsumo.query.filter_by(insumo_id=insumo_id).all()
        return [
            {
                "ubicacion_id": r.ubicacion_id,
                "ubicacion": r.ubicacion.nombre_ubicacion,
                "cantidad": r.cantidad,
                "fecha_actualizacion": r.fecha_actualizacion.isoformat()
            }
            for r in registros
        ]

    # ============================================================
    # 3) OBTENER STOCK EN UNA UBICACIÓN ESPECÍFICA
    # ============================================================
    @staticmethod
    def obtener_stock_en_ubicacion(insumo_id: int, ubicacion_id: int) -> float:
        registro = StockInsumo.query.filter_by(
            insumo_id=insumo_id,
            ubicacion_id=ubicacion_id
        ).first()
        return registro.cantidad if registro else 0

    # ============================================================
    # 4) AGREGAR STOCK (entrada)
    # ============================================================
    @staticmethod
    def agregar_stock(insumo_id: int, ubicacion_id: int, cantidad: float):
        registro = StockInsumo.query.filter_by(
            insumo_id=insumo_id,
            ubicacion_id=ubicacion_id
        ).first()

        if registro:
            registro.cantidad += cantidad
            registro.fecha_actualizacion = datetime.utcnow()
        else:
            registro = StockInsumo(
                insumo_id=insumo_id,
                ubicacion_id=ubicacion_id,
                cantidad=cantidad,
                fecha_actualizacion=datetime.utcnow()
            )
            db.session.add(registro)

        db.session.commit()
        return registro

    # ============================================================
    # 5) DESCONTAR STOCK (salida)
    # ============================================================
    @staticmethod
    def descontar_stock(insumo_id: int, ubicacion_id: int, cantidad: float):
        registro = StockInsumo.query.filter_by(
            insumo_id=insumo_id,
            ubicacion_id=ubicacion_id
        ).first()

        if not registro:
            raise ValueError("No existe stock en esa ubicación.")

        if registro.cantidad < cantidad:
            raise ValueError("Stock insuficiente para realizar la salida.")

        registro.cantidad -= cantidad
        registro.fecha_actualizacion = datetime.utcnow()

        db.session.commit()
        return registro

    # ============================================================
    # 6) TRANSFERIR STOCK ENTRE UBICACIONES
    # ============================================================
    @staticmethod
    def transferir_stock(insumo_id: int, origen_id: int, destino_id: int, cantidad: float):
        # Descontar del origen
        StockService.descontar_stock(insumo_id, origen_id, cantidad)

        # Agregar al destino
        StockService.agregar_stock(insumo_id, destino_id, cantidad)

        return {
            "insumo_id": insumo_id,
            "origen_id": origen_id,
            "destino_id": destino_id,
            "cantidad_transferida": cantidad,
            "fecha": datetime.utcnow().isoformat()
        }

    # ============================================================
    # 7) VALIDAR STOCK MÍNIMO
    # ============================================================
    @staticmethod
    def stock_por_debajo_del_minimo(insumo_id: int) -> bool:
        insumo = Insumo.query.get(insumo_id)
        if not insumo or insumo.cantidad_minima is None:
            return False

        total = StockService.obtener_stock_total(insumo_id)
        return total < insumo.cantidad_minima

    # ============================================================
    # 8) ALERTA DE STOCK MÍNIMO (opcional)
    # ============================================================
    @staticmethod
    def obtener_alertas_stock_minimo():
        alertas = []
        insumos = Insumo.query.all()

        for insumo in insumos:
            if insumo.cantidad_minima is None:
                continue

            total = StockService.obtener_stock_total(insumo.insumo_id)

            if total < insumo.cantidad_minima:
                alertas.append({
                    "insumo_id": insumo.insumo_id,
                    "codigo": insumo.codigo,
                    "descripcion": insumo.descripcion,
                    "stock_total": total,
                    "stock_minimo": insumo.cantidad_minima
                })

        return alertas
