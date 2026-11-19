"""El entorno conda (environment.yml) tiene todo lo que piden los requirements*.txt."""
import re
from pathlib import Path

RAIZ = Path(__file__).resolve().parents[1]


def _requirements(nombre):
    paquetes = set()
    for linea in (RAIZ / nombre).read_text().splitlines():
        linea = linea.split("#")[0].strip()
        if not linea:
            continue
        if linea.startswith("-r "):
            paquetes |= _requirements(linea[3:].strip())
            continue
        paquetes.add(re.split(r"[<>=!~\[ ;]", linea, maxsplit=1)[0].lower())
    return paquetes


def _conda():
    paquetes = set()
    for linea in (RAIZ / "environment.yml").read_text().splitlines():
        m = re.match(r"\s+-\s+([A-Za-z0-9_.\-]+)", linea)
        if m:
            paquetes.add(re.split(r"[<>=!]", m.group(1))[0].lower())
    return paquetes


def test_environment_yml_tiene_todos_los_requirements():
    faltan = _requirements("requirements-dev.txt") - _conda()
    assert not faltan, f"Agregar a environment.yml: {sorted(faltan)}"


def test_environment_yml_es_portable():
    texto = (RAIZ / "environment.yml").read_text()
    assert "prefix:" not in texto  # ruta de una máquina en particular
