# app/crud/api/openapi.py
"""
Documentación de la API generada desde el registry.

    /api/openapi.json   OpenAPI 3.0 (estándar; lo usan herramientas como las
                        acciones de ChatGPT y la mayoría de los clientes)
    /api/swagger.json   OpenAPI 2.0 / Swagger (lo que importa un conector
                        personalizado de Power Apps / Power Automate)
    /api/docs           página para explorar y probar la API desde el navegador
"""
from __future__ import annotations

import copy
import json

from flask import Response, jsonify, request
from sqlalchemy import inspect as sa_inspect

from app.crud.meta.spec import EntitySpec
from app.crud.schema import jsonschema

TITULO = "Administración de Mantenimiento — API"
VERSION = "1.0.0"
SWAGGER_UI = "https://cdn.jsdelivr.net/npm/swagger-ui-dist@5.17.14"


# ---------------------------------------------------------------------------
# JSON Schema 2020-12 → esquema OpenAPI 3.0
# ---------------------------------------------------------------------------

def _a_openapi(esquema: dict) -> dict:
    """OpenAPI 3.0 no admite listas de tipos: ["string", "null"] → type + nullable."""
    e = copy.deepcopy(esquema)
    e.pop("$schema", None)
    tipo = e.get("type")
    if isinstance(tipo, list):
        no_nulos = [t for t in tipo if t != "null"]
        e["type"] = no_nulos[0]
        if "null" in tipo:
            e["nullable"] = True
    if "enum" in e:
        e["enum"] = [v for v in e["enum"] if v is not None]
    if "properties" in e:
        e["properties"] = {k: _a_openapi(v) for k, v in e["properties"].items()}
    return e


def _nombre(spec: EntitySpec) -> str:
    return spec.model.__name__


# ---------------------------------------------------------------------------
# OpenAPI 3.0
# ---------------------------------------------------------------------------

def generar_openapi(registry: dict[str, EntitySpec], url_base: str) -> dict:
    esquemas = {
        "Error": {
            "type": "object",
            "properties": {
                "status": {"type": "string", "example": "error"},
                "message": {"type": "string"},
                "errors": {
                    "type": "object",
                    "additionalProperties": {"type": "string"},
                    "description": "Mensaje por campo",
                },
            },
        },
        "Ok": {"type": "object", "properties": {"status": {"type": "string", "example": "ok"}}},
    }

    def ref(nombre):
        return {"$ref": f"#/components/schemas/{nombre}"}

    def respuesta_json(descripcion, esquema):
        return {"description": descripcion, "content": {"application/json": {"schema": esquema}}}

    errores = {
        "400": respuesta_json("Datos inválidos", ref("Error")),
        "404": respuesta_json("No existe el registro", ref("Error")),
        "409": respuesta_json("Conflicto (duplicado o registro en uso)", ref("Error")),
    }
    usuario = {
        "name": "X-Usuario", "in": "header", "required": False,
        "description": "Usuario que se registra en la auditoría (por defecto «api»)",
        "schema": {"type": "string"},
    }

    paths, tags = {}, []
    for spec in registry.values():
        n, nombre = spec.name, _nombre(spec)
        tags.append({"name": n, "description": spec.label_plural.capitalize()})

        esquemas[nombre] = _a_openapi(jsonschema.esquema_registro(spec))
        for modo, sufijo in (("crear", "Crear"), ("reemplazar", "Reemplazar"), ("modificar", "Modificar")):
            esquemas[f"{nombre}{sufijo}"] = _a_openapi(jsonschema.esquema_entrada(spec, modo))

        filtros = []
        for campo in jsonschema.campos_api(spec):
            esquema = _a_openapi(jsonschema.esquema_campo(spec, campo))
            esquema.pop("title", None)
            filtros.append({
                "name": campo, "in": "query", "required": False,
                "description": f"Filtra por {spec.fields[campo].label} (igualdad exacta)",
                "schema": esquema,
            })

        listado_params = [
            {"name": "q", "in": "query", "required": False, "schema": {"type": "string"},
             "description": "Texto a buscar (contiene, sin distinguir mayúsculas)"},
            {"name": "campo", "in": "query", "required": False,
             "schema": {"type": "string", "enum": ["todos", *spec.filtros]},
             "description": "Campo donde buscar `q` (por defecto, todos)"},
            {"name": "limit", "in": "query", "required": False,
             "schema": {"type": "integer", "minimum": 0, "maximum": 1000}},
            {"name": "offset", "in": "query", "required": False,
             "schema": {"type": "integer", "minimum": 0}},
            *filtros,
        ]
        id_param = {"name": "id", "in": "path", "required": True, "schema": {"type": "integer"},
                    "description": f"ID ({spec.pk})"}

        def cuerpo(sufijo):
            return {"required": True,
                    "content": {"application/json": {"schema": ref(f"{nombre}{sufijo}")}}}

        lista = respuesta_json(f"Lista de {spec.label_plural}", {"type": "array", "items": ref(nombre)})
        lista["headers"] = {"X-Total-Count": {"description": "Total de registros (sin paginar)",
                                              "schema": {"type": "integer"}}}

        paths[f"/{n}"] = {
            "get": {
                "tags": [n], "operationId": f"listar_{n}",
                "summary": f"Listar {spec.label_plural}",
                "parameters": listado_params,
                "responses": {"200": lista, "400": errores["400"]},
            },
            "post": {
                "tags": [n], "operationId": f"crear_{n}",
                "summary": f"Crear {spec.label_singular}",
                "parameters": [usuario],
                "requestBody": cuerpo("Crear"),
                "responses": {"201": respuesta_json("Creado", ref(nombre)),
                              "400": errores["400"], "409": errores["409"]},
            },
        }
        paths[f"/{n}/{{id}}"] = {
            "get": {
                "tags": [n], "operationId": f"obtener_{n}",
                "summary": f"Obtener {spec.label_singular}",
                "parameters": [id_param],
                "responses": {"200": respuesta_json("Registro", ref(nombre)), "404": errores["404"]},
            },
            "put": {
                "tags": [n], "operationId": f"reemplazar_{n}",
                "summary": f"Reemplazar {spec.label_singular} (todos los campos)",
                "parameters": [id_param, usuario],
                "requestBody": cuerpo("Reemplazar"),
                "responses": {"200": respuesta_json("Actualizado", ref(nombre)), **errores},
            },
            "patch": {
                "tags": [n], "operationId": f"modificar_{n}",
                "summary": f"Modificar {spec.label_singular} (solo los campos enviados)",
                "parameters": [id_param, usuario],
                "requestBody": cuerpo("Modificar"),
                "responses": {"200": respuesta_json("Actualizado", ref(nombre)), **errores},
            },
            "delete": {
                "tags": [n], "operationId": f"eliminar_{n}",
                "summary": f"Eliminar {spec.label_singular}",
                "description": _descripcion_borrado(spec, registry),
                "parameters": [
                    id_param, usuario,
                    {"name": "motivo", "in": "query", "required": False, "schema": {"type": "string"},
                     "description": "Motivo que queda en la auditoría"},
                ],
                "responses": {"200": respuesta_json("Eliminado", ref("Ok")),
                              "404": errores["404"], "409": errores["409"]},
            },
        }

    return {
        "openapi": "3.0.3",
        "info": {
            "title": TITULO,
            "version": VERSION,
            "description": (
                "API generada automáticamente desde los modelos. Cada entidad tiene "
                "listado, alta, consulta, reemplazo (PUT), modificación parcial (PATCH) y baja. "
                "Todos los cambios quedan en la auditoría."
            ),
        },
        "servers": [{"url": url_base}],
        "tags": tags,
        "paths": paths,
        "components": {"schemas": esquemas},
    }


def _descripcion_borrado(spec: EntitySpec, registry) -> str:
    textos = []
    for h in spec.hijos:
        textos.append(f"Borra en cascada sus {registry[h].label_plural} si el modelo lo declara.")
    textos.append("Devuelve 409 si otros registros lo usan.")
    return " ".join(textos)


# ---------------------------------------------------------------------------
# OpenAPI 3.0 → 2.0 (Swagger), para Power Apps
# ---------------------------------------------------------------------------

def _esquema_v2(e: dict) -> dict:
    e = copy.deepcopy(e)
    if e.pop("nullable", False):
        e["x-nullable"] = True
    if "properties" in e:
        e["properties"] = {k: _esquema_v2(v) for k, v in e["properties"].items()}
    if "items" in e:
        e["items"] = _esquema_v2(e["items"])
    return e


def a_swagger2(doc: dict) -> dict:
    url = doc["servers"][0]["url"]
    esquema_url, _, resto = url.partition("://")
    host, _, base = resto.partition("/")

    paths = {}
    for ruta, operaciones in doc["paths"].items():
        paths[ruta] = {}
        for metodo, op in operaciones.items():
            nueva = {k: v for k, v in op.items() if k not in ("parameters", "requestBody", "responses")}
            parametros = []
            for p in op.get("parameters", []):
                plano = {k: v for k, v in p.items() if k != "schema"}
                plano.update(_esquema_v2(p["schema"]))
                parametros.append(plano)
            if "requestBody" in op:
                esquema = op["requestBody"]["content"]["application/json"]["schema"]
                parametros.append({"name": "body", "in": "body", "required": True, "schema": esquema})
            if parametros:
                nueva["parameters"] = parametros

            respuestas = {}
            for codigo, r in op["responses"].items():
                nueva_r = {"description": r["description"]}
                if "content" in r:
                    nueva_r["schema"] = _esquema_v2(r["content"]["application/json"]["schema"])
                if "headers" in r:
                    nueva_r["headers"] = {
                        h: {"description": v["description"], **v["schema"]}
                        for h, v in r["headers"].items()
                    }
                respuestas[codigo] = nueva_r
            nueva["responses"] = respuestas
            paths[ruta][metodo] = nueva

    resultado = {
        "swagger": "2.0",
        "info": doc["info"],
        "host": host,
        "basePath": "/" + base if base else "/",
        "schemes": [esquema_url],
        "consumes": ["application/json"],
        "produces": ["application/json"],
        "tags": doc["tags"],
        "paths": paths,
        "definitions": {k: _esquema_v2(v) for k, v in doc["components"]["schemas"].items()},
    }
    texto = json.dumps(resultado).replace("#/components/schemas/", "#/definitions/")
    return json.loads(texto)


# ---------------------------------------------------------------------------
# Rutas
# ---------------------------------------------------------------------------

_PAGINA_DOCS = """<!doctype html>
<html lang="es">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>API — Administración de Mantenimiento</title>
  <link rel="stylesheet" href="{ui}/swagger-ui.css">
</head>
<body>
  <div id="swagger-ui"></div>
  <script src="{ui}/swagger-ui-bundle.js"></script>
  <script>
    SwaggerUIBundle({{ url: "{spec}", dom_id: "#swagger-ui" }});
  </script>
</body>
</html>"""


def registrar_documentacion(bp, registry, prefijo: str):
    def url_base():
        return request.host_url.rstrip("/") + prefijo

    @bp.get("/openapi.json")
    def openapi_json():
        return jsonify(generar_openapi(registry, url_base()))

    @bp.get("/swagger.json")
    def swagger_json():
        return jsonify(a_swagger2(generar_openapi(registry, url_base())))

    @bp.get("/docs")
    def docs():
        html = _PAGINA_DOCS.format(ui=SWAGGER_UI, spec=f"{prefijo}/openapi.json")
        return Response(html, mimetype="text/html")
