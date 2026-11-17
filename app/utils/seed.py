# app/seed.py

from app.core.db import db
import uuid

# MODELOS
from app.models.sectores_models import EstadoSector
from app.models.motivos_models import MotivoOperacion
from app.models.cuentas_models import EstadoCuenta
from app.models.recursos_models import EstadoRecurso

from app.models.activos_models import (
    TipoActivo,
    CategoriaActivo,
    EstadoActivo,
)

from app.models.materiales_models import CategoriaMaterial, TipoMaterial
from app.models.unidadmedida_models import TipoUnidad


def seed_data():
    """
    Carga datos iniciales en la base de datos.
    Se ejecuta solo si las tablas están vacías.
    """

    # ============================================================
    # ESTADOS DE SECTOR
    # ============================================================
    if EstadoSector.query.count() == 0:
        db.session.add_all(
            [
                EstadoSector(
                    uuid=str(uuid.uuid4()),
                    nombre_estado_sector="Activo",
                    color_badge="#16a34a",
                ),
                EstadoSector(
                    uuid=str(uuid.uuid4()),
                    nombre_estado_sector="Inactivo",
                    color_badge="#dc2626",
                ),
            ]
        )
        print("✔ Estados de sector precargados.")

    # ============================================================
    # MOTIVOS DE OPERACIÓN
    # ============================================================
    if MotivoOperacion.query.count() == 0:
        motivos = [
            ("Alta inicial", "INSERT"),
            ("Creación por reorganización", "INSERT"),
            ("División de sector", "INSERT"),
            ("Corrección de datos", "UPDATE"),
            ("Cambio de estado", "UPDATE"),
            ("Actualización administrativa", "UPDATE"),
            ("Ajuste operativo", "UPDATE"),
            ("Depuración de registros", "DELETE"),
            ("Eliminación por reorganización", "DELETE"),
            ("Registro duplicado", "DELETE"),
            ("Error de carga", "DELETE"),
        ]

        db.session.add_all(
            [MotivoOperacion(nombre_motivo=m, tipo_operacion=t) for m, t in motivos]
        )
        print("✔ Motivos de operación precargados.")

    # ============================================================
    # ESTADOS DE CUENTA
    # ============================================================
    if EstadoCuenta.query.count() == 0:
        estados_cuenta = [
            (1, "Activa", "#16a34a"),
            (2, "Suspendida", "#facc15"),
            (3, "Inactiva", "#dc2626"),
        ]

        db.session.add_all(
            [
                EstadoCuenta(
                    uuid=str(uuid.uuid4()),
                    estado_cuenta_id=id_,
                    nombre_estado_cuenta=nombre,
                    color_badge=color,
                )
                for id_, nombre, color in estados_cuenta
            ]
        )
        print("✔ Estados de cuenta precargados.")

    # ============================================================
    # ESTADOS DE RECURSO
    # ============================================================
    if EstadoRecurso.query.count() == 0:
        estados_recurso = [
            (1, "Activo", "#16a34a"),
            (2, "Suspendido", "#facc15"),
            (3, "Inactivo", "#dc2626"),
        ]

        db.session.add_all(
            [
                EstadoRecurso(
                    uuid=str(uuid.uuid4()),
                    estado_recurso_id=id_,
                    nombre_estado_recurso=nombre,
                    color_badge=color,
                )
                for id_, nombre, color in estados_recurso
            ]
        )
        print("✔ Estados de recurso precargados.")

    # ============================================================
    # ESTADOS DE ACTIVO
    # ============================================================
    if EstadoActivo.query.count() == 0:
        estados = [
            ("Activo", "#22c55e"),
            ("En reparación", "#eab308"),
            ("Baja", "#ef4444"),
        ]

        db.session.add_all(
            [
                EstadoActivo(nombre_estado=nombre, color_badge=color)
                for nombre, color in estados
            ]
        )
        print("✔ Estados de activo precargados.")

    # ============================================================
    # TIPOS DE ACTIVO
    # ============================================================
    tipo_objs = {}
    if TipoActivo.query.count() == 0:
        tipos = ["Maquinaria", "Vehículo", "Instalación"]

        for nombre in tipos:
            obj = TipoActivo(nombre_tipo=nombre)
            db.session.add(obj)
            tipo_objs[nombre] = obj

        print("✔ Tipos de activo precargados.")
    else:
        # Si ya existen, igual necesitamos el dict
        for obj in TipoActivo.query.all():
            tipo_objs[obj.nombre_tipo] = obj

    # ============================================================
    # CATEGORÍAS DE ACTIVO
    # ============================================================
    if CategoriaActivo.query.count() == 0:
        categorias = [
            ("Tractor", "Maquinaria"),
            ("Pala cargadora", "Maquinaria"),
            ("Retroexcavadora", "Maquinaria"),
            ("Motoguadaña", "Maquinaria"),
            ("Pickup", "Vehículo"),
            ("Moto", "Vehículo"),
            ("Galpón", "Instalación"),
            ("Taller", "Instalación"),
            ("Depósito", "Instalación"),
        ]

        db.session.add_all(
            [
                CategoriaActivo(
                    nombre_categoria=nombre_categoria,
                    tipo_activo_id=tipo_objs[tipo_nombre].tipo_activo_id,
                )
                for nombre_categoria, tipo_nombre in categorias
            ]
        )

        print("✔ Categorías de activo precargadas.")

    # ============================================================
    # CATEGORÍAS DE MATERIAL
    # ============================================================
    if CategoriaMaterial.query.count() == 0:
        categorias_materials = [
            "Lubricantes",
            "Filtros",
            "Rodamientos",
            "Refrigerantes",
            "Tornillería",
            "Eléctricos",
            "Neumáticos",
            "Herramientas",
            "Consumibles",
            "EPP",
        ]

        db.session.add_all(
            [CategoriaMaterial(nombre_categoria=c) for c in categorias_materials]
        )

        print("✔ Categorías de material precargadas.")

    # ============================================================
    # TIPOS DE MATERIAL
    # ============================================================
    if TipoMaterial.query.count() == 0:
        tipos_por_categoria = {
            "Filtros": [
                "Filtro de aire",
                "Filtro de aceite",
                "Filtro hidráulico",
                "Filtro de combustible",
            ],
            "Lubricantes": ["Aceite 15W40", "Aceite hidráulico ISO 46", "Grasa EP2"],
            "Rodamientos": ["6204", "6205", "6307", "Rodamiento cónico"],
            "Refrigerantes": ["Refrigerante orgánico", "Refrigerante sintético"],
            "Consumibles": ["Cinta aisladora", "Precintos", "Silicona"],
            "Herramientas": ["Llave fija", "Llave francesa", "Destornillador"],
            "EPP": ["Guantes", "Lentes", "Protectores auditivos"],
        }

        for categoria, tipos in tipos_por_categoria.items():
            cat = CategoriaMaterial.query.filter_by(nombre_categoria=categoria).first()
            if not cat:
                continue

            for t in tipos:
                db.session.add(
                    TipoMaterial(
                        nombre_tipo=t, categoria_material_id=cat.categoria_material_id
                    )
                )

        print("✔ Tipos de material precargados.")

    # ============================================================
    # TIPOS DE UNIDAD DE MEDIDA
    # ============================================================
    if TipoUnidad.query.count() == 0:
        tipos_unidad = [
            "Volumen",
            "Masa",
            "Longitud",
            "Tiempo",
            "Cantidad",
        ]

        db.session.add_all([TipoUnidad(nombre_tipo=nombre) for nombre in tipos_unidad])

        print("✔ Tipos de unidad de medida precargados.")

    # ============================================================
    # COMMIT FINAL
    # ============================================================
    db.session.commit()
    print("✔ Seed completado correctamente.")
