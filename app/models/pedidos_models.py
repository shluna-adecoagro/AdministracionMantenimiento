from datetime import datetime
from app.core.db import db

class Pedido(db.Model):
    __tablename__ = "pedidos"

    # =========================
    # Clave primaria
    # =========================
    PedidoID = db.Column(db.Integer, primary_key=True)

    # =========================
    # Datos generales del pedido
    # =========================
    NumeroPedido = db.Column(db.String(50), unique=True, nullable=True)
    FechaPedido = db.Column(db.Date, nullable=False)
    Solicitante = db.Column(db.String(150), nullable=False)
    Referencia = db.Column(db.String(255), nullable=True)

    # Origen del pedido: Chat, Forms, Mail, WhatsApp, etc.
    Origen = db.Column(db.String(50), nullable=False)

    # =========================
    # Auditoría
    # =========================
    FechaCreacion = db.Column(db.DateTime, default=datetime.utcnow, nullable=False)

    # =========================
    # Relaciones
    # =========================
    Detalles = db.relationship(
        "PedidoDetalle",
        backref="Pedido",
        cascade="all, delete-orphan",
        lazy=True
    )

    def __repr__(self):
        return f"<Pedido {self.PedidoID} - {self.Solicitante}>"


class PedidoDetalle(db.Model):
    __tablename__ = "pedido_detalle"

    DetalleID = db.Column(db.Integer, primary_key=True)
    PedidoID = db.Column(db.Integer, db.ForeignKey("pedidos.PedidoID"), nullable=False)
    Cantidad = db.Column(db.Float, nullable=False)
    Descripcion = db.Column(db.String(500), nullable=False)
    LineaOriginal = db.Column(db.String(500))