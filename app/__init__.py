from flask import Flask, jsonify
from flask_cors import CORS
import os

from sqlalchemy.engine.url import make_url
from sqlalchemy import inspect, create_engine

from app.core.config import config
from app.core.db import db

# Blueprints
## API
from app.routes.api.auditoria_routes import audit_bp
from app.routes.api.sectores_routes import sectores_bp

## Web
from app.routes.web.sectores_web import sectores_web_bp
from app.routes.web.cuentas_web import cuentas_bp
from app.routes.web.index_web import index_web_bp
from app.routes.web.motivos_web import motivos_web
from app.routes.web.marcas_modelos_web import marcas_modelos_web_bp
from app.routes.web.recursos_web import recursos_web_bp
from app.routes.web.activos_web import activos_web_bp
from app.routes.web.lecturas_web import lecturas_web
from app.routes.web.insumos_web import insumos_web_bp
from app.routes.web.unidades_medida_web import unidades_medida_web_bp
from app.routes.web.bom_web import bom_web_bp


from app.utils.json_validator import JSONValidationError


def mysql_disponible(uri):
    """Verifica si MySQL/MariaDB está disponible."""
    try:
        engine = create_engine(uri)
        from sqlalchemy import text

        with engine.connect() as conn:
            conn.execute(text("SELECT 1"))
        return True
    except Exception:
        return False


def create_app(env="development"):

    app = Flask(
        __name__,
        instance_relative_config=True,
        template_folder="templates",
        static_folder="static",
    )

    # ============================
    # Configuración inicial
    # ============================
    app.config.from_object(config[env])

    # Detectar motor y aplicar fallback si es necesario
    # URI original desde config.py
    original_uri = config[env].SQLALCHEMY_DATABASE_URI
    url = make_url(original_uri)
    db_is_mysql = url.get_backend_name() in ["mysql", "mariadb"]

    print("\n==============================")
    print("  🔍 Verificando motor de base de datos")
    print("==============================")

    if db_is_mysql:
        print(f"➡ Intentando conectar a MySQL/MariaDB: {original_uri}")

        if mysql_disponible(original_uri):
            print("✔ Conexión MySQL/MariaDB verificada.")
            final_uri = original_uri
        else:
            print("⚠ MySQL/MariaDB no disponible. Activando fallback a SQLite.")
            fallback_path = os.path.join(app.instance_path, "fallback.db")
            final_uri = "sqlite:///" + fallback_path
            print(f"➡ Usando SQLite en: {fallback_path}")
    else:
        print("ℹ Usando SQLite directamente.")
        final_uri = original_uri

    # Aplicar la URI final
    app.config["SQLALCHEMY_DATABASE_URI"] = final_uri

    # Inicializar DB
    db.init_app(app)
    CORS(app)

    # ============================
    # Registrar API REST
    # ============================
    app.register_blueprint(sectores_bp, url_prefix="/api/sectores")
    app.register_blueprint(audit_bp, url_prefix="/api/auditoria")

    # ============================
    # Registrar frontend
    # ============================
    app.register_blueprint(index_web_bp)
    app.register_blueprint(sectores_web_bp)
    app.register_blueprint(motivos_web)
    app.register_blueprint(cuentas_bp)
    app.register_blueprint(marcas_modelos_web_bp)
    app.register_blueprint(recursos_web_bp)
    app.register_blueprint(activos_web_bp)
    app.register_blueprint(lecturas_web)
    app.register_blueprint(insumos_web_bp)
    app.register_blueprint(unidades_medida_web_bp)
    app.register_blueprint(bom_web_bp)

    # ============================
    # Manejo de errores JSON
    # ============================
    @app.errorhandler(JSONValidationError)
    def manejar_error_json(e):
        return (
            jsonify({"status": "error", "message": "JSON inválido", "details": str(e)}),
            400,
        )

    # ============================
    # Comando: flask reset-db
    # ============================
    @app.cli.command("reset-db")
    def reset_db():
        """Elimina todas las tablas o archivo SQLite, recrea y seed-ea."""
        from app.utils.seed import seed_data

        uri = app.config["SQLALCHEMY_DATABASE_URI"]
        url = make_url(uri)
        db_is_sqlite = url.get_backend_name() == "sqlite"
        db_path = url.database if db_is_sqlite else None

        print("Base de datos:", uri)

        db.session.remove()

        with app.app_context():
            if db_is_sqlite and db_path and os.path.exists(db_path):
                os.remove(db_path)
                print("✔ Archivo SQLite eliminado.")
            else:
                print("✔ Eliminando tablas existentes...")
                db.drop_all()

            db.create_all()
            print("✔ Tablas creadas.")

            seed_data()
            print("✔ Datos iniciales cargados.")

        print("✔ Reset completo.")

    # ============================
    # Comando: flask create-db
    # ============================
    @app.cli.command("create-db")
    def create_db():
        """Crea las tablas si no existen."""
        from app.utils.seed import seed_data

        with app.app_context():
            db.create_all()
            print("✔ Tablas creadas.")

        print("✔ Base de datos lista.")

    # ============================
    # Comando: flask drop-db
    # ============================
    @app.cli.command("drop-db")
    def drop_db():
        """Elimina todas las tablas o archivo SQLite."""
        uri = app.config["SQLALCHEMY_DATABASE_URI"]
        url = make_url(uri)
        db_is_sqlite = url.get_backend_name() == "sqlite"
        db_path = url.database if db_is_sqlite else None

        print("Base de datos:", uri)

        db.session.remove()

        with app.app_context():
            if db_is_sqlite and db_path and os.path.exists(db_path):
                os.remove(db_path)
                print("✔ Archivo SQLite eliminado.")
            else:
                db.drop_all()
                print("✔ Tablas eliminadas.")

    # ============================
    # Comando: flask seed
    # ============================
    @app.cli.command("seed")
    def seed():
        """Ejecuta el seed sin recrear la base."""
        from app.utils.seed import seed_data

        with app.app_context():
            seed_data()
            print("✔ Datos iniciales cargados.")

    # ============================
    # Comando: flask inspect-db
    # ============================
    @app.cli.command("inspect-db")
    def inspect_db():
        """Muestra tablas, columnas, tipos, PK y FK."""
        with app.app_context():
            inspector = inspect(db.engine)

            print("\n📌 INSPECCIÓN DE BASE DE DATOS")
            print("====================================\n")

            for table_name in inspector.get_table_names():
                print(f"🟦 Tabla: {table_name}")

                columns = inspector.get_columns(table_name)
                for col in columns:
                    col_name = col["name"]
                    col_type = col["type"]
                    nullable = col["nullable"]
                    default = col.get("default")
                    print(
                        f"   • {col_name} ({col_type})  "
                        f"{'NULL' if nullable else 'NOT NULL'}  "
                        f"{f'default={default}' if default else ''}"
                    )

                pk = inspector.get_pk_constraint(table_name)
                if pk and pk.get("constrained_columns"):
                    print(f"   🔑 PK: {pk['constrained_columns']}")

                fks = inspector.get_foreign_keys(table_name)
                if fks:
                    print("   🔗 FKs:")
                    for fk in fks:
                        print(
                            f"      → {fk['constrained_columns']} "
                            f"→ {fk['referred_table']}.{fk['referred_columns']}"
                        )

                print("")

            print("✔ Inspección completada.\n")

    # ============================
    # Crear DB automáticamente si no existe
    # ============================
    app.db_initialized = False

    @app.before_request
    def ensure_database():
        from app.utils.seed import seed_data

        if app.db_initialized:
            return

        uri = app.config["SQLALCHEMY_DATABASE_URI"]
        url = make_url(uri)
        db_is_sqlite = url.get_backend_name() == "sqlite"
        db_path = url.database if db_is_sqlite else None

        print("\n==============================")
        print("  🔍 Verificando base de datos")
        print("==============================")

        with app.app_context():
            inspector = inspect(db.engine)
            tablas = inspector.get_table_names()

            if not tablas:
                if db_is_sqlite:
                    print(f"⚠ No se encontró la base en: {db_path}")
                else:
                    print("⚠ No se encontraron tablas en MySQL/MariaDB.")

                print("➡ Creando nueva base de datos...")

                db.create_all()
                print("✔ Tablas creadas correctamente.")

                seed_data()
                print("✔ Datos iniciales cargados.")

                print("✔ Base de datos creada automáticamente.\n")
            else:
                if db_is_sqlite:
                    print(f"✔ Base encontrada: {db_path}")
                else:
                    print(f"✔ Base MySQL/MariaDB con {len(tablas)} tablas.")
                print("✔ No es necesario crear nada.\n")

        app.db_initialized = True

    # ============================
    # Comando: flask sync-db (con auditoría global + por registro)
    # ============================
    @app.cli.command("sync-db")
    def sync_db():
        """
        Sincroniza la base SQLite fallback con MySQL/MariaDB cuando MySQL vuelve a estar disponible.
        Registra auditoría global (inicio/fin) y auditoría por cada INSERT y UPDATE.
        Estrategia: Last Write Wins (LWW) usando updated_at.
        """

        from sqlalchemy import create_engine, text
        from app.crud.metamodelos import ENTIDADES
        from app.audit.registrar import registrar_cambio

        uri_mysql = config["development"].SQLALCHEMY_DATABASE_URI
        url = make_url(uri_mysql)
        es_mysql = url.get_backend_name() in ["mysql", "mariadb"]

        if not es_mysql:
            print(
                "⚠ La configuración actual no usa MySQL/MariaDB. No hay nada que sincronizar."
            )
            return

        # Verificar disponibilidad de MySQL
        try:
            engine_mysql = create_engine(uri_mysql)
            with engine_mysql.connect() as conn:
                conn.execute(text("SELECT 1"))
            print("✔ MySQL/MariaDB disponible.")
        except Exception as e:
            print("❌ MySQL/MariaDB sigue caído. No se puede sincronizar.")
            print(e)
            return

        # Ubicación del fallback SQLite
        fallback_path = os.path.join(app.instance_path, "fallback.db")
        uri_sqlite = f"sqlite:///{fallback_path}"

        if not os.path.exists(fallback_path):
            print("ℹ No existe fallback.db. No hay nada que sincronizar.")
            return

        engine_sqlite = create_engine(uri_sqlite)

        print("\n======================================")
        print("🔄 INICIANDO SINCRONIZACIÓN DE BASES")
        print("======================================\n")

        # Auditoría de inicio
        registrar_cambio(
            tabla="sistema",
            registro_uuid="sync-db",
            tipo="sync_start",
            estado_anterior=None,
            estado_actual={"mensaje": "Inicio de sincronización fallback → MySQL"},
            motivo_operacion="Sincronización iniciada",
            usuario="sistema",
        )

        total_inserts = 0
        total_updates = 0

        with app.app_context():
            for entidad, cfg in ENTIDADES.items():
                modelo = cfg["model"]
                tabla = modelo.__tablename__
                pk = cfg["pk"]

                print(f"🟦 Sincronizando tabla: {tabla}")

                # Leer datos desde SQLite
                with engine_sqlite.connect() as conn_sqlite:
                    registros_sqlite = (
                        conn_sqlite.execute(text(f"SELECT * FROM {tabla}"))
                        .mappings()
                        .all()
                    )

                # Leer datos desde MySQL
                with engine_mysql.connect() as conn_mysql:
                    registros_mysql = (
                        conn_mysql.execute(text(f"SELECT * FROM {tabla}"))
                        .mappings()
                        .all()
                    )

                dict_sqlite = {r[pk]: dict(r) for r in registros_sqlite}
                dict_mysql = {r[pk]: dict(r) for r in registros_mysql}

                # INSERT / UPDATE con auditoría
                with engine_mysql.begin() as trans:
                    for id_registro, reg_sqlite in dict_sqlite.items():

                        if id_registro not in dict_mysql:
                            # INSERT
                            columnas = ", ".join(reg_sqlite.keys())
                            valores = ", ".join([f":{c}" for c in reg_sqlite.keys()])
                            trans.execute(
                                text(
                                    f"INSERT INTO {tabla} ({columnas}) VALUES ({valores})"
                                ),
                                reg_sqlite,
                            )

                            total_inserts += 1

                            # Auditoría
                            registrar_cambio(
                                tabla=tabla,
                                registro_uuid=id_registro,
                                tipo="sync_insert",
                                estado_anterior=None,
                                estado_actual=reg_sqlite,
                                motivo_operacion="Sincronización fallback → MySQL",
                                usuario="sistema",
                            )

                            print(f"   ➕ INSERT → id={id_registro}")

                        else:
                            # UPDATE si SQLite es más nuevo
                            reg_mysql = dict_mysql[id_registro]

                            if (
                                "updated_at" in reg_sqlite
                                and reg_sqlite["updated_at"] > reg_mysql["updated_at"]
                            ):
                                set_clause = ", ".join(
                                    [f"{c} = :{c}" for c in reg_sqlite.keys()]
                                )
                                trans.execute(
                                    text(
                                        f"UPDATE {tabla} SET {set_clause} WHERE {pk} = :{pk}"
                                    ),
                                    reg_sqlite,
                                )

                                total_updates += 1

                                # Auditoría
                                registrar_cambio(
                                    tabla=tabla,
                                    registro_uuid=id_registro,
                                    tipo="sync_update",
                                    estado_anterior=reg_mysql,
                                    estado_actual=reg_sqlite,
                                    motivo_operacion="Sincronización fallback → MySQL",
                                    usuario="sistema",
                                )

                                print(f"   🔄 UPDATE → id={id_registro}")

                print(f"✔ Tabla {tabla} sincronizada.\n")

        # Auditoría de fin
        registrar_cambio(
            tabla="sistema",
            registro_uuid="sync-db",
            tipo="sync_end",
            estado_anterior={"inserts": total_inserts, "updates": total_updates},
            estado_actual={"mensaje": "Fin de sincronización fallback → MySQL"},
            motivo_operacion="Sincronización finalizada",
            usuario="sistema",
        )

        print("======================================")
        print("✔ SINCRONIZACIÓN COMPLETA")
        print(f"   ➕ Inserts: {total_inserts}")
        print(f"   🔄 Updates: {total_updates}")
        print("======================================\n")

    # ============================
    # Banner de inicio del servidor
    # ============================
    app.banner_shown = False

    @app.before_request
    def show_banner():
        if app.banner_shown:
            return

        env_name = env
        uri = app.config["SQLALCHEMY_DATABASE_URI"]
        url = make_url(uri)
        db_is_sqlite = url.get_backend_name() == "sqlite"
        db_path = url.database if db_is_sqlite else uri

        print("\n========================================")
        print("   🚀 AdministracionMantenimiento")
        print(f"   🗂  Entorno: {env_name}")
        print(f"   🗄  Base: {db_path}")
        print("========================================\n")

        app.banner_shown = True

    show_banner()

    # ============================
    # Sidebar dinámico
    # ============================
    from app.crud.metamodelos import ENTIDADES

    @app.context_processor
    def inject_sidebar_entities():
        items = []

        for name, cfg in ENTIDADES.items():
            if cfg.get("mostrar_en_sidebar", False):
                items.append(
                    {
                        "name": name,
                        "label": cfg.get("label_plural", name).capitalize(),
                        "url": f"/{name}",
                        "orden": cfg.get("orden", 999),
                    }
                )

        items = sorted(items, key=lambda x: x["orden"])

        return {"sidebar_items": items}

    return app
