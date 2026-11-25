# app/seed.py

from app.core.db import db
import uuid

# MODELOS
from app.models.sectores_models import EstadoSector
from app.models.ubicaciones_models import EstadoUbicacion
from app.models.motivos_models import MotivoOperacion
from app.models.cuentas_models import EstadoCuenta
from app.models.recursos_models import EstadoRecurso

from app.models.activos_models import EstadoActivo

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
    # ESTADOS DE UBICACIÓN
    # ============================================================
    # La migración que los agregó (5c7c85247e05) ya los inserta en una base
    # existente; esto los carga en una base creada sin migraciones (tests).
    if EstadoUbicacion.query.count() == 0:
        db.session.add_all(
            [
                EstadoUbicacion(nombre_estado_ubicacion=nombre, color_badge=color)
                for nombre, color in (
                    ("Operativa", "#16a34a"),
                    ("En mantenimiento", "#eab308"),
                    ("Inactiva", "#dc2626"),
                )
            ]
        )
        print("✔ Estados de ubicación precargados.")

    # ============================================================
    # MOTIVOS DE OPERACIÓN
    # ============================================================
    # Se decide por tipo de operación y no por tabla vacía: la migración de
    # pedidos (2923dcc41468) ya inserta los de ANULACION, y con un chequeo de
    # "tabla vacía" el resto nunca se cargaba tras un reset-db. Cada tipo se
    # carga solo si todavía no tiene ningún motivo (respeta lo editado a mano).
    motivos_por_tipo = {
        "INSERT": ["Alta inicial", "Creación por reorganización", "División de sector"],
        "UPDATE": [
            "Corrección de datos",
            "Cambio de estado",
            "Actualización administrativa",
            "Ajuste operativo",
        ],
        "DELETE": [
            "Depuración de registros",
            "Eliminación por reorganización",
            "Registro duplicado",
            "Error de carga",
        ],
        # Anulación de líneas de pedido (fase 10).
        "ANULACION": ["Ya no hace falta", "Pedido duplicado", "Se resolvió de otra forma"],
    }
    for tipo, nombres in motivos_por_tipo.items():
        if MotivoOperacion.query.filter_by(tipo_operacion=tipo).count() == 0:
            db.session.add_all(
                [MotivoOperacion(nombre_motivo=n, tipo_operacion=tipo) for n in nombres]
            )
            print(f"✔ Motivos de operación {tipo} precargados.")

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

    # Tipos y categorías de activo: no se precargan. Cada tipo necesita su
    # cuenta de imputación, así que los carga el usuario (Catálogos → Tipos de activo).

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
