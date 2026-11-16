#!/usr/bin/env python
"""
Corre el modo sombra: compara app/crud/metamodelos (manuales) contra lo inferido
desde los modelos SQLAlchemy y escribe un informe Markdown.

Uso (desde la raíz del proyecto, con el entorno activado):

    python tools/crud_shadow.py                      # escribe informe_sombra.md
    python tools/crud_shadow.py --salida otro.md
    python tools/crud_shadow.py --estricto           # exit 1 si hay hallazgos ERROR (para CI)

No necesita base de datos ni .env: solo importa los modelos y configura los mappers.
"""
import argparse
import importlib
import pkgutil
import sys
from pathlib import Path

RAIZ = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(RAIZ))


def _importar_todos_los_modelos():
    """Importa app.models.* para que el registry de SQLAlchemy conozca todas las clases."""
    import app.models as paquete

    for m in pkgutil.iter_modules(paquete.__path__):
        try:
            importlib.import_module(f"app.models.{m.name}")
        except Exception as e:  # un modelo roto no debe frenar el informe
            print(f"[aviso] no pude importar app.models.{m.name}: {e}", file=sys.stderr)


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawTextHelpFormatter)
    ap.add_argument("--salida", default="informe_sombra.md")
    ap.add_argument("--estricto", action="store_true")
    args = ap.parse_args()

    from app.crud.metamodelos import ENTIDADES
    _importar_todos_los_modelos()

    from app.core.db import db
    from app.crud.introspect import fk_apunta_a, inferir_entidad
    from app.crud.shadow_diff import generar_informe

    modelos = [m.class_ for m in db.Model.registry.mappers]
    texto, resultados = generar_informe(ENTIDADES, modelos, inferir_entidad, fk_apunta_a)

    Path(args.salida).write_text(texto, encoding="utf-8")

    errores = sum(1 for hs in resultados.values() for h in hs if h.nivel == "ERROR")
    print(f"Informe escrito en {args.salida}")
    print(f"Entidades: {len(resultados)} | hallazgos ERROR: {errores}")

    if args.estricto and errores:
        sys.exit(1)


if __name__ == "__main__":
    main()
