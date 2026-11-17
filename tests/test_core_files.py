"""Almacenamiento de archivos subidos (app/crud/core/files.py)."""
import io

import pytest
from werkzeug.datastructures import FileStorage

from app.crud.core.files import ArchivoInvalido, guardar


def archivo(nombre):
    return FileStorage(stream=io.BytesIO(b"contenido"), filename=nombre)


def test_guarda_con_nombre_aleatorio(tmp_path):
    ruta = guardar(archivo("Foto Camión.JPG"), str(tmp_path), "activos", "fotos")
    assert ruta.startswith("/static/uploads/activos/fotos/")
    assert ruta.endswith(".jpg")
    guardado = tmp_path / ruta.removeprefix("/static/")
    assert guardado.read_bytes() == b"contenido"


@pytest.mark.parametrize("nombre", ["script.py", "pagina.html", "sin_extension"])
def test_rechaza_extensiones_no_permitidas(tmp_path, nombre):
    with pytest.raises(ArchivoInvalido):
        guardar(archivo(nombre), str(tmp_path), "activos")


def test_rechaza_rutas_fuera_de_uploads(tmp_path):
    with pytest.raises(ValueError):
        guardar(archivo("a.jpg"), str(tmp_path), "../../etc")
