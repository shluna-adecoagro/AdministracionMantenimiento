# app/models/marcas_modelos_models.py

import uuid
from app.core.db import db
from app.crud.model_mixin import ModelMixin
from app.crud.audit_mixin import AuditMixin

class Marca(db.Model, ModelMixin, AuditMixin):
    __tablename__ = "marcas"
    __label_field__ = "nombre_marca"

    marca_id = db.Column(db.Integer, primary_key=True)
    uuid = db.Column(db.String(36), default=lambda: str(uuid.uuid4()), unique=True, nullable=False)

    nombre_marca = db.Column(db.String(100), nullable=False, unique=True)

    # Relación 1 → N
    modelos = db.relationship("Modelo", back_populates="marca", cascade="all, delete-orphan")

class Modelo(db.Model, ModelMixin, AuditMixin):
    __tablename__ = "modelos"
    __label_field__ = "nombre_modelo"

    modelo_id = db.Column(db.Integer, primary_key=True)
    uuid = db.Column(db.String(36), default=lambda: str(uuid.uuid4()), unique=True, nullable=False)

    nombre_modelo = db.Column(db.String(100), nullable=False)

    # FK → Marca
    marca_id = db.Column(db.Integer, db.ForeignKey("marcas.marca_id"), nullable=False)

    # Relación inversa
    marca = db.relationship("Marca", back_populates="modelos")
