# app/models/preventivos_models.py
"""
Planes de mantenimiento preventivo.

    categorias_activo
     └── planes_preventivos ── incluye a ──► plan_preventivo (inferior)
          ├── plan_preventivo_tareas ──► tareas_preventivo (catálogo)
          └── planes_modelo ──► modelos
               └── plan_modelo_materiales ──► materiales (y la tarea que lo usa)

El plan define QUÉ se hace (tareas) y CADA CUÁNTO (período por uso, por tiempo o
los dos: lo que ocurra primero), para todos los activos de una categoría. El
plan del modelo agrega los materiales, que cambian según el modelo.

Un plan puede INCLUIR a otro (el completo de 1200 h incluye al parcial de
300 h): sus tareas y materiales son los del inferior más los propios, y cuando
coinciden se hace solo el superior. Las reglas están en
app/crud/meta/overrides/preventivos.py.
"""
import uuid
from datetime import datetime

from sqlalchemy import Integer, cast, func, select
from sqlalchemy.orm import column_property

from app.core.db import db
from app.crud.audit_mixin import AuditMixin
from app.crud.model_mixin import ModelMixin
from app.models.marcas_modelos_models import Modelo
from app.models.materiales_models import Material


class TareaPreventivo(db.Model, ModelMixin):
    """Catálogo de tareas que se usan en los planes (ej: «Cambio de aceite de motor»)."""

    __tablename__ = "tareas_preventivo"
    __label_field__ = "nombre_tarea"

    tarea_preventivo_id = db.Column(db.Integer, primary_key=True, autoincrement=True)
    nombre_tarea = db.Column(db.String(100), nullable=False, unique=True, info={"label": "Nombre"})
    descripcion = db.Column(db.String(300), nullable=True, info={"label": "Descripción"})
    horas_estimadas = db.Column(db.Float, nullable=True, info={"label": "Horas estimadas"})


class PlanPreventivo(db.Model, ModelMixin, AuditMixin):
    __tablename__ = "planes_preventivos"
    __label_field__ = "nombre_plan"

    plan_preventivo_id = db.Column(db.Integer, primary_key=True, autoincrement=True)
    uuid = db.Column(db.String(36), default=lambda: str(uuid.uuid4()), unique=True, nullable=False)

    nombre_plan = db.Column(db.String(100), nullable=False, unique=True, info={"label": "Nombre"})
    # Descripción del plan en el ERP (hoy EAM; con SAP PM se reemplaza por la de
    # SAP): equivalencia 1:1 para reconocer el plan en las OT importadas. La carga
    # el gestor (dueño: la app). Única cuando está cargada; vacío = NULL.
    nombre_erp = db.Column(db.String(150), nullable=True, unique=True,
                           info={"label": "Nombre en el ERP"})

    # FK → CategoriaActivo. Al borrar la categoría se borran sus planes.
    categoria_activo_id = db.Column(
        db.Integer, db.ForeignKey("categorias_activo.categoria_activo_id"), nullable=False,
        info={"label": "Categoría de activo"},
    )
    categoria_activo = db.relationship(
        "CategoriaActivo", lazy="joined",
        backref=db.backref("planes_preventivos", cascade="all, delete"),
    )

    # Período por uso: cada cuánto según un medidor (300 h, 10.000 km).
    periodo_uso = db.Column(db.Float, nullable=True, info={"label": "Período por uso"})
    unidad_uso_id = db.Column(
        db.Integer, db.ForeignKey("unidades_medida.unidad_medida_id"), nullable=True,
        info={"label": "Unidad (uso)"},
    )
    unidad_uso = db.relationship("UnidadMedida", foreign_keys=[unidad_uso_id])

    # Período por tiempo: cada cuánto según el calendario (6 meses, 1 año).
    periodo_tiempo = db.Column(db.Integer, nullable=True, info={"label": "Período por tiempo"})
    unidad_tiempo_id = db.Column(
        db.Integer, db.ForeignKey("unidades_medida.unidad_medida_id"), nullable=True,
        info={"label": "Unidad (tiempo)"},
    )
    unidad_tiempo = db.relationship("UnidadMedida", foreign_keys=[unidad_tiempo_id])

    # Plan que este incluye (el completo incluye al parcial). Un plan es
    # incluido por un solo superior. Sin backref: un plan incluido por otro no
    # se puede borrar.
    plan_inferior_id = db.Column(
        db.Integer, db.ForeignKey("planes_preventivos.plan_preventivo_id"), nullable=True,
        unique=True, info={"label": "Incluye al plan"},
    )
    plan_inferior = db.relationship(
        "PlanPreventivo", remote_side=[plan_preventivo_id], foreign_keys=[plan_inferior_id],
    )

    vigente = db.Column(db.Boolean, nullable=False, default=True)

    creado_en = db.Column(db.DateTime, default=datetime.utcnow)
    actualizado_en = db.Column(db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)


# Ciclo: cuántas veces entra el período del inferior en el del plan (1200 / 300 = 4).
# (Alias de la tabla, no aliased(): este no obliga a configurar los mappers al importar.)
_inferior = PlanPreventivo.__table__.alias("plan_inferior")
PlanPreventivo.ciclo = column_property(
    select(cast(func.round(func.coalesce(
        PlanPreventivo.periodo_uso / _inferior.c.periodo_uso,
        PlanPreventivo.periodo_tiempo * 1.0 / _inferior.c.periodo_tiempo,
    )), Integer))
    .where(_inferior.c.plan_preventivo_id == PlanPreventivo.plan_inferior_id)
    .correlate_except(_inferior)
    .scalar_subquery(),
    info={"label": "Ciclo"},
)


class PlanPreventivoTarea(db.Model, ModelMixin, AuditMixin):
    """Tarea de un plan, en el orden en que se hace (solo las propias; las del plan incluido se heredan)."""

    __tablename__ = "plan_preventivo_tareas"
    __label_field__ = None
    __table_args__ = (db.UniqueConstraint("plan_preventivo_id", "tarea_preventivo_id"),)

    plan_preventivo_tarea_id = db.Column(db.Integer, primary_key=True, autoincrement=True)
    uuid = db.Column(db.String(36), default=lambda: str(uuid.uuid4()), unique=True, nullable=False)

    # Al borrar el plan se borran sus tareas.
    plan_preventivo_id = db.Column(
        db.Integer, db.ForeignKey("planes_preventivos.plan_preventivo_id"), nullable=False,
        info={"label": "Plan"},
    )
    plan_preventivo = db.relationship(
        "PlanPreventivo", lazy="joined", backref=db.backref("tareas", cascade="all, delete"),
    )

    # Sin backref: una tarea usada en un plan no se puede borrar.
    tarea_preventivo_id = db.Column(
        db.Integer, db.ForeignKey("tareas_preventivo.tarea_preventivo_id"), nullable=False,
        info={"label": "Tarea"},
    )
    tarea = db.relationship("TareaPreventivo", lazy="joined")

    paso = db.Column(db.Integer, nullable=False)

    creado_en = db.Column(db.DateTime, default=datetime.utcnow)
    actualizado_en = db.Column(db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)


class PlanModelo(db.Model, ModelMixin, AuditMixin):
    """Un plan preventivo aplicado a un modelo: ahí se cargan los materiales de ese modelo."""

    __tablename__ = "planes_modelo"
    __label_field__ = "nombre"
    __table_args__ = (db.UniqueConstraint("plan_preventivo_id", "modelo_id"),)

    plan_modelo_id = db.Column(db.Integer, primary_key=True, autoincrement=True)
    uuid = db.Column(db.String(36), default=lambda: str(uuid.uuid4()), unique=True, nullable=False)

    # Al borrar el plan o el modelo se borran sus planes del modelo.
    plan_preventivo_id = db.Column(
        db.Integer, db.ForeignKey("planes_preventivos.plan_preventivo_id"), nullable=False,
        info={"label": "Plan"},
    )
    plan_preventivo = db.relationship(
        "PlanPreventivo", lazy="joined", backref=db.backref("planes_modelo", cascade="all, delete"),
    )
    modelo_id = db.Column(
        db.Integer, db.ForeignKey("modelos.modelo_id"), nullable=False, info={"label": "Modelo"},
    )
    modelo = db.relationship(
        "Modelo", lazy="joined", backref=db.backref("planes_modelo", cascade="all, delete"),
    )

    vigente = db.Column(db.Boolean, nullable=False, default=True)

    creado_en = db.Column(db.DateTime, default=datetime.utcnow)
    actualizado_en = db.Column(db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    # Calculados: la categoría (del plan) y la marca (del modelo). En el
    # formulario filtran los planes y los modelos.
    categoria_activo_id = column_property(
        select(PlanPreventivo.categoria_activo_id)
        .where(PlanPreventivo.plan_preventivo_id == plan_preventivo_id)
        .correlate_except(PlanPreventivo)
        .scalar_subquery(),
        info={"label": "Categoría de activo"},
    )
    marca_id = column_property(
        select(Modelo.marca_id)
        .where(Modelo.modelo_id == modelo_id)
        .correlate_except(Modelo)
        .scalar_subquery(),
        info={"label": "Marca"},
    )
    # Cómo se muestra (ej: «Parcial palas — 644K»); también sirve para importar
    # los materiales por nombre.
    nombre = column_property(
        select(PlanPreventivo.nombre_plan + " — " + Modelo.nombre_modelo)
        .where(PlanPreventivo.plan_preventivo_id == plan_preventivo_id,
               Modelo.modelo_id == modelo_id)
        .correlate_except(PlanPreventivo, Modelo)
        .scalar_subquery(),
        info={"label": "Nombre"},
    )


class PlanModeloMaterial(db.Model, ModelMixin, AuditMixin):
    """Material que lleva un plan en un modelo (solo los propios; los del plan incluido se heredan)."""

    __tablename__ = "plan_modelo_materiales"
    __label_field__ = None
    __table_args__ = (db.UniqueConstraint("plan_modelo_id", "material_id"),)

    plan_modelo_material_id = db.Column(db.Integer, primary_key=True, autoincrement=True)
    uuid = db.Column(db.String(36), default=lambda: str(uuid.uuid4()), unique=True, nullable=False)

    # Al borrar el plan del modelo se borran sus materiales.
    plan_modelo_id = db.Column(
        db.Integer, db.ForeignKey("planes_modelo.plan_modelo_id"), nullable=False,
        info={"label": "Plan del modelo"},
    )
    plan_modelo = db.relationship(
        "PlanModelo", lazy="joined", backref=db.backref("materiales", cascade="all, delete"),
    )

    # Sin backref: un material usado en un plan no se puede borrar.
    material_id = db.Column(
        db.Integer, db.ForeignKey("materiales.material_id"), nullable=False, info={"label": "Material"},
    )
    material = db.relationship("Material", lazy="joined")

    # Tarea en la que se usa (opcional): tiene que estar en el plan, propia o heredada.
    tarea_preventivo_id = db.Column(
        db.Integer, db.ForeignKey("tareas_preventivo.tarea_preventivo_id"), nullable=True,
        info={"label": "Tarea"},
    )
    tarea = db.relationship("TareaPreventivo")

    cantidad = db.Column(db.Float, nullable=False)

    creado_en = db.Column(db.DateTime, default=datetime.utcnow)
    actualizado_en = db.Column(db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    # La cantidad va en la unidad del material (ej: litros).
    unidad_medida_id = column_property(
        select(Material.unidad_medida_id)
        .where(Material.material_id == material_id)
        .correlate_except(Material)
        .scalar_subquery(),
        info={"label": "Unidad"},
    )
