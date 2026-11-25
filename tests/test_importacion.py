"""Importación y exportación CSV (app/crud/intercambio/csv_entidades.py)."""
import pytest

from app.crud.intercambio.csv_entidades import exportar, importar
from app.crud.entidades import REGISTRY
from app.models.sectores_models import Sector
from app.models.ubicaciones_models import Ubicacion

SECTORES = REGISTRY["sectores"]
UBICACIONES = REGISTRY["ubicaciones"]


def csv(texto, codificacion="utf-8-sig"):
    return texto.strip().encode(codificacion)


# Como lo exporta Excel en castellano: separador ";", BOM y columnas extra de SharePoint.
SECTORES_CSV = csv("""
ID;Nombre del Sector;Centro de Costo;Estado;Modificado
1;Taller;CC-100;Activo;17/11/2026
2;Depósito;CC-200;Inactivo;17/11/2026
""")


# ---------------------------------------------------------------------------
# Alta, actualización y reimportación
# ---------------------------------------------------------------------------

def test_importa_y_reconoce_columnas_por_etiqueta(app, auditoria):
    r = importar(SECTORES, SECTORES_CSV, "sectores.csv")
    assert r.ok, r.resumen()
    assert (r.creados, r.actualizados, r.sin_cambios) == (2, 0, 0)
    assert r.columnas_ignoradas == ["ID", "Modificado"]

    deposito = Sector.query.filter_by(nombre_sector="Depósito").one()
    assert deposito.estado.nombre_estado_sector == "Inactivo"  # FK por nombre

    log = auditoria("sectores")[0]
    assert (log.TipoDeCambio, log.Usuario) == ("INSERT", "importación")
    assert log.motivo_operacion == "Importación de sectores.csv"


def test_reimportar_lo_mismo_no_cambia_nada(app, auditoria):
    importar(SECTORES, SECTORES_CSV)
    r = importar(SECTORES, SECTORES_CSV)
    assert (r.creados, r.actualizados, r.sin_cambios) == (0, 0, 2)
    assert Sector.query.count() == 2
    assert len(auditoria("sectores")) == 2  # el historial no se ensucia


def test_reimportar_con_cambios_actualiza(app, auditoria):
    importar(SECTORES, SECTORES_CSV)
    r = importar(SECTORES, csv("""
Nombre del Sector;Centro de Costo;Estado
Taller;CC-999;activo
"""))
    assert (r.creados, r.actualizados) == (0, 1)
    assert Sector.query.filter_by(nombre_sector="Taller").one().centro_costo == "CC-999"
    log = auditoria("sectores")[-1]
    assert log.TipoDeCambio == "UPDATE"
    assert (log.EstadoAnterior["centro_costo"], log.EstadoActual["centro_costo"]) == ("CC-100", "CC-999")
    assert r.solo_en_la_base == 1  # Depósito no estaba en el archivo (no se toca)


def test_columnas_por_nombre_de_campo_y_fk_por_id(app, estado_sector_activo):
    r = importar(SECTORES, csv(f"""
nombre_sector,centro_costo,estado_sector_id
Taller,CC-100,{estado_sector_activo.estado_sector_id}
"""))
    assert r.ok, r.resumen()
    assert Sector.query.one().estado_sector_id == estado_sector_activo.estado_sector_id


def test_archivo_en_codificacion_de_windows(app):
    r = importar(SECTORES, csv("Nombre del Sector;Centro de Costo;Estado\nDepósito;CC-1;Activo", "cp1252"))
    assert r.ok, r.resumen()
    assert Sector.query.one().nombre_sector == "Depósito"


def test_simulacion_no_guarda(app, auditoria):
    r = importar(SECTORES, SECTORES_CSV, simular=True)
    assert r.ok and r.simulado
    assert r.creados == 2
    assert Sector.query.count() == 0
    assert auditoria("sectores") == []
    assert "SIMULACIÓN" in r.resumen()


# ---------------------------------------------------------------------------
# Errores: se informan todos y no se guarda nada
# ---------------------------------------------------------------------------

def test_errores_por_fila_y_todo_o_nada(app):
    r = importar(SECTORES, csv("""
Nombre del Sector;Centro de Costo;Estado
Taller;CC-100;Activo
Depósito;;Activo
Pañol;CC-300;Clausurado
"""))
    assert not r.ok
    assert (3, "centro_costo", "Centro de Costo es obligatorio.") in r.errores
    assert (4, "estado_sector_id", "Estado: no existe «Clausurado».") in r.errores
    assert Sector.query.count() == 0  # tampoco la fila 2, que era válida
    assert "No se guardó nada" in r.resumen()


def test_falta_columna_obligatoria(app):
    r = importar(SECTORES, csv("Nombre del Sector;Estado\nTaller;Activo"))
    assert [(f, c) for f, c, _ in r.errores] == [(1, "centro_costo")]


def test_fila_repetida_en_el_archivo(app):
    r = importar(SECTORES, csv("""
Nombre del Sector;Centro de Costo;Estado
Taller;CC-1;Activo
taller;CC-2;Activo
Taller;CC-3;Activo
"""))
    assert (4, "_clave", "repite el registro de la fila 2") in r.errores


def test_archivo_vacio(app):
    assert not importar(SECTORES, b"").ok


def test_entidad_sin_clave_natural(app):
    from dataclasses import replace

    r = importar(replace(SECTORES, clave_natural=()), SECTORES_CSV)
    assert "clave_natural" in r.errores[0][2]


# ---------------------------------------------------------------------------
# Ubicaciones: clave combinada nombre + sector
# ---------------------------------------------------------------------------

def test_ubicaciones_con_clave_combinada(app):
    importar(SECTORES, SECTORES_CSV)
    datos = csv("""
Nombre de la ubicación;Sector
Galpón 1;Taller
Galpón 1;Depósito
Estantería;
""")
    r = importar(UBICACIONES, datos)
    assert r.ok, r.resumen()
    assert r.creados == 3
    assert Ubicacion.query.filter_by(nombre_ubicacion="Galpón 1").count() == 2

    r = importar(UBICACIONES, datos)
    assert (r.creados, r.sin_cambios) == (0, 3)


def test_ubicacion_con_sector_inexistente(app):
    r = importar(UBICACIONES, csv("Nombre de la ubicación;Sector\nGalpón 1;Inexistente"))
    assert r.errores == [(2, "sector_id", "Sector: no existe «Inexistente».")]


def test_ubicacion_repetida_en_un_sector_se_rechaza_en_la_web(client, ubicacion, sector):
    r = client.post(f"/ubicaciones/crear?sector_id={sector.sector_id}", data={
        "nombre_ubicacion": "Galpón 1", "sector_id": str(sector.sector_id),
    })
    assert r.status_code == 400
    assert "Ya existe" in r.get_data(as_text=True)


# ---------------------------------------------------------------------------
# Alias de columnas (ej: "name" en SharePoint)
# ---------------------------------------------------------------------------

def test_alias_de_columna_declarado_en_el_override(app):
    from app.crud.meta.registry import construir_registry

    reg = construir_registry({"sectores": {
        "model": Sector,
        "clave_natural": ["nombre_sector"],
        "fields": {"nombre_sector": {"alias": ["name"]}, "estado_sector_id": {"alias": ["status"]}},
    }})
    r = importar(reg["sectores"], csv("name;Centro de Costo;status\nTaller;CC-1;Activo"))
    assert r.ok, r.resumen()
    assert Sector.query.one().nombre_sector == "Taller"


# ---------------------------------------------------------------------------
# Exportación
# ---------------------------------------------------------------------------

def test_exportar(app, sector):
    contenido = exportar(SECTORES)
    assert contenido.startswith("﻿".encode("utf-8"))  # BOM para Excel
    lineas = contenido.decode("utf-8-sig").splitlines()
    assert lineas == ["Nombre del Sector;Centro de Costo;Estado", "Taller;CC-100;Activo"]


def test_exportar_e_importar_da_lo_mismo(app, sector, ubicacion):
    for spec in (SECTORES, UBICACIONES):
        r = importar(spec, exportar(spec))
        assert r.ok, r.resumen()
        assert (r.creados, r.actualizados) == (0, 0)


# ---------------------------------------------------------------------------
# Comandos de consola
# ---------------------------------------------------------------------------

@pytest.fixture
def cli(app):
    return app.test_cli_runner()


def test_comando_importar(cli, tmp_path):
    archivo = tmp_path / "sectores.csv"
    archivo.write_bytes(SECTORES_CSV)

    r = cli.invoke(args=["importar", "sectores", str(archivo), "--simular"])
    assert r.exit_code == 0, r.output
    assert "SIMULACIÓN" in r.output
    assert Sector.query.count() == 0

    r = cli.invoke(args=["importar", "sectores", str(archivo)])
    assert r.exit_code == 0, r.output
    assert "Creados: 2" in r.output
    assert Sector.query.count() == 2


def test_comando_importar_con_errores_sale_con_codigo_1(cli, tmp_path):
    archivo = tmp_path / "sectores.csv"
    archivo.write_bytes(csv("Nombre del Sector;Centro de Costo;Estado\nTaller;CC;Nada"))
    r = cli.invoke(args=["importar", "sectores", str(archivo)])
    assert r.exit_code == 1
    assert "Fila 2" in r.output


def test_comando_entidad_inexistente(cli, tmp_path):
    archivo = tmp_path / "x.csv"
    archivo.write_bytes(b"a\n1")
    r = cli.invoke(args=["importar", "sectorez", str(archivo)])
    assert r.exit_code == 2
    assert "Disponibles" in r.output


def test_comando_exportar(cli, sector, tmp_path):
    archivo = tmp_path / "salida.csv"
    r = cli.invoke(args=["exportar", "sectores", str(archivo)])
    assert r.exit_code == 0, r.output
    assert "Taller" in archivo.read_text(encoding="utf-8-sig")


def test_exportar_y_reimportar_conserva_los_decimales(app, db, categorias_activo):
    """Los decimales salen con coma: «1,234» vuelve como 1,234 (no como 1234)."""
    from app.models.preventivos_models import PlanPreventivo
    from app.models.unidadmedida_models import TipoUnidad, UnidadMedida

    tiempo = TipoUnidad.query.filter_by(nombre_tipo="Tiempo").one().tipo_unidad_id
    h = UnidadMedida(nombre_unidad="Horas", abreviatura="h", tipo_medidor="Horómetro", tipo_unidad_id=tiempo)
    db.session.add(h)
    db.session.flush()
    db.session.add(PlanPreventivo(nombre_plan="P", periodo_uso=1.234, unidad_uso_id=h.unidad_medida_id,
                                  categoria_activo_id=categorias_activo["Tractor"].categoria_activo_id))
    db.session.commit()
    planes = REGISTRY["planes_preventivos"]
    contenido = exportar(planes)
    assert "1,234" in contenido.decode("utf-8-sig")
    PlanPreventivo.query.one().periodo_uso = 5
    db.session.commit()
    assert importar(planes, contenido).ok
    assert PlanPreventivo.query.one().periodo_uso == 1.234
