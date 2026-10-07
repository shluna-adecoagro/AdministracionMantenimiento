from datetime import datetime
from app.core.db import db
from app.models.pedidos_models import Pedido, PedidoDetalle
from app.utils.simular_procesamiento_IA import simular_procesamiento_ia


def crear_pedido(data: dict) -> Pedido:
    # =========================
    # Validación mínima
    # =========================
    campos_obligatorios = ["origen", "fecha_pedido", "solicitante", "pedido_original"]

    for campo in campos_obligatorios:
        if campo not in data or not data[campo]:
            raise ValueError(f"Falta el campo obligatorio: {campo}")

    # =========================
    # Crear pedido (cabecera)
    # =========================
    pedido = Pedido(
        FechaPedido=datetime.fromisoformat(data["fecha_pedido"]).date(),
        Solicitante=data["solicitante"],
        Referencia=data.get("referencia"),
        Origen=data["origen"]
    )

    db.session.add(pedido)
    db.session.flush()  # obtenemos PedidoID sin commit

    # =========================
    # SIMULACIÓN de IA (mock)
    # =========================
    detalle_parseado = simular_procesamiento_ia(data["pedido_original"])

    # =========================
    # Crear detalles
    # =========================
    for item in detalle_parseado:
        detalle = PedidoDetalle(
            PedidoID=pedido.PedidoID,
            Cantidad=item["cantidad"],
            Descripcion=item["descripcion"],
            LineaOriginal=item.get("original")
        )
        db.session.add(detalle)

    db.session.commit()
    return pedido