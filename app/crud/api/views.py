# app/crud/api/views.py
"""
API REST generada a partir de cada EntitySpec.

Por cada entidad del registry:

    GET    /api/<entidad>          lista (array JSON)
    POST   /api/<entidad>          alta            → 201 + registro
    GET    /api/<entidad>/<id>     un registro
    PUT    /api/<entidad>/<id>     reemplazo total → 200 + registro
    PATCH  /api/<entidad>/<id>     cambio parcial  → 200 + registro
    DELETE /api/<entidad>/<id>     baja            → 200 {"status": "ok"}

Listado:
    ?q=texto&campo=<campo>     búsqueda (como en la web)
    ?<campo>=<valor>           filtro exacto por cualquier campo (ej: ?sector_id=3)
    ?limit=50&offset=100       paginación opcional; el total va en X-Total-Count

Errores (siempre JSON):
    400  {"status": "error", "message": ..., "errors": {campo: mensaje}}
    404  registro inexistente
    409  conflicto con la base (duplicado, registro en uso)

Usuario para la auditoría: encabezado X-Usuario (por defecto "api").

Usa el mismo servicio que la web: las reglas de guardado, la auditoría y el
borrado en cascada son idénticos.
"""
from __future__ import annotations

from datetime import date, datetime
from decimal import Decimal

from flask import Blueprint, jsonify, request
from sqlalchemy import inspect as sa_inspect
from werkzeug.exceptions import HTTPException

from app.crud.core import coercion, fk, repository
from app.crud.core.coercion import ErroresValidacion
from app.crud.core.service import ErrorIntegridad, ServicioCRUD
from app.crud.meta.spec import EntitySpec
from app.crud.schema import jsonschema
from app.crud.web.textos import etiqueta_tabla

BLUEPRINT = "api_crud"
LIMITE_MAXIMO = 1000
_PARAMETROS_RESERVADOS = {"q", "campo", "limit", "offset"}


# ---------------------------------------------------------------------------
# Respuestas
# ---------------------------------------------------------------------------

def _valor_json(valor):
    if isinstance(valor, datetime):
        return valor.isoformat()
    if isinstance(valor, date):
        return valor.isoformat()
    if isinstance(valor, Decimal):
        return float(valor)
    return valor


def serializar(spec: EntitySpec, registro) -> dict:
    """Registro → dict JSON: todas sus columnas, más `<fk>_label` con el texto de cada FK."""
    d = {
        attr.key: _valor_json(getattr(registro, attr.key))
        for attr in sa_inspect(spec.model).mapper.column_attrs
    }
    for campo, cfg in fk.campos_fk(spec.fields).items():
        obj = fk.destino(registro, campo, cfg)
        d[f"{campo}_label"] = fk.etiqueta(obj, cfg) if obj is not None else None
    return d


def error_json(status: int, mensaje: str, errores: dict | None = None):
    cuerpo = {"status": "error", "message": mensaje}
    if errores:
        cuerpo["errors"] = errores
    return jsonify(cuerpo), status


# ---------------------------------------------------------------------------
# Vistas de una entidad
# ---------------------------------------------------------------------------

class VistasAPI:
    def __init__(self, spec: EntitySpec):
        self.spec = spec
        self.servicio = ServicioCRUD(
            spec.model,
            spec.fields,
            {"enabled": spec.auditoria, "ignore_fields": list(spec.auditoria_ignorar)},
            etiqueta_tabla,
        )

    def registrar(self, bp):
        n = self.spec.name
        bp.add_url_rule(f"/{n}", f"{n}_coleccion", self.coleccion,
                        methods=["GET", "POST"], strict_slashes=False)
        bp.add_url_rule(f"/{n}/<int:id>", f"{n}_registro", self.registro,
                        methods=["GET", "PUT", "PATCH", "DELETE"], strict_slashes=False)

    # ------------------------------------------------------------------
    def coleccion(self):
        return self._listar() if request.method == "GET" else self._crear()

    def registro(self, id):
        registro = repository.obtener_o_404(self.spec.model, id)
        if request.method == "GET":
            return jsonify(serializar(self.spec, registro))
        if request.method == "DELETE":
            return self._eliminar(registro)
        modo = "reemplazar" if request.method == "PUT" else "modificar"
        return self._guardar(modo, registro)

    # ------------------------------------------------------------------
    def _usuario(self):
        return request.headers.get("X-Usuario") or "api"

    def _cuerpo(self):
        datos = request.get_json(silent=True)
        if datos is None:
            raise ErroresValidacion({"_general": "El cuerpo de la petición debe ser JSON (Content-Type: application/json)."})
        return datos

    def _entero(self, nombre, default):
        valor = request.args.get(nombre)
        if valor is None:
            return default
        if not valor.isdigit():
            raise ErroresValidacion({nombre: f"«{nombre}» debe ser un número entero no negativo."})
        return int(valor)

    # ------------------------------------------------------------------
    def _listar(self):
        s = self.spec
        try:
            query = repository.consulta_listado(
                s.model, s.fields, list(s.filtros),
                q=request.args.get("q", ""),
                campo=request.args.get("campo") or "todos",
            )
            # Filtros exactos por campo (?sector_id=3&centro_costo=CC-1)
            columnas = sa_inspect(s.model).columns
            errores = {}
            for campo, valor in request.args.items():
                if campo in _PARAMETROS_RESERVADOS or campo not in s.fields:
                    continue
                try:
                    convertido = coercion.convertir(columnas[campo], valor)
                except ValueError as e:
                    errores[campo] = f"{s.fields[campo].label} {e}."
                    continue
                columna = getattr(s.model, campo)
                query = query.filter(columna.is_(None) if convertido is None else columna == convertido)
            if errores:
                raise ErroresValidacion(errores)

            total = query.count()
            query = query.order_by(getattr(s.model, s.pk))
            limite = self._entero("limit", None)
            if limite is not None:
                query = query.limit(min(limite, LIMITE_MAXIMO))
            query = query.offset(self._entero("offset", 0))
        except ErroresValidacion as e:
            return error_json(400, "Parámetros inválidos", e.errores)

        respuesta = jsonify([serializar(s, r) for r in query.all()])
        respuesta.headers["X-Total-Count"] = str(total)
        return respuesta

    def _crear(self):
        try:
            datos = self._datos("crear")
            nuevo = self.servicio.crear(datos, usuario=self._usuario())
        except ErroresValidacion as e:
            return error_json(400, "Datos inválidos", e.errores)
        except ErrorIntegridad as e:
            return error_json(409, e.mensaje, {e.campo: e.mensaje} if e.campo else None)
        return jsonify(serializar(self.spec, nuevo)), 201

    def _guardar(self, modo, registro):
        try:
            datos = self._datos(modo)
            self.servicio.actualizar(registro, datos, usuario=self._usuario())
        except ErroresValidacion as e:
            return error_json(400, "Datos inválidos", e.errores)
        except ErrorIntegridad as e:
            return error_json(409, e.mensaje, {e.campo: e.mensaje} if e.campo else None)
        return jsonify(serializar(self.spec, registro)), 200

    def _eliminar(self, registro):
        motivo = request.args.get("motivo")
        try:
            self.servicio.eliminar(registro, motivo, usuario=self._usuario())
        except ErrorIntegridad as e:
            return error_json(409, e.mensaje)
        return jsonify({"status": "ok"}), 200

    def _datos(self, modo):
        """Valida contra el JSON Schema y convierte a tipos Python."""
        cuerpo = self._cuerpo()
        jsonschema.validar(self.spec, cuerpo, modo)
        campos = {c: self.spec.fields[c] for c in jsonschema.campos_api(self.spec)}
        datos = coercion.datos_de_entrada(
            self.spec.model, campos, cuerpo, parcial=(modo == "modificar")
        )
        fk.validar_existencia(self.spec.fields, datos)
        return datos


# ---------------------------------------------------------------------------
# Registro en la app
# ---------------------------------------------------------------------------

def registrar_api(app, registry: dict[str, EntitySpec], prefijo: str = "/api"):
    # Respuestas JSON con tildes legibles ("Número") en vez de "N\u00famero".
    app.json.ensure_ascii = False

    bp = Blueprint(BLUEPRINT, __name__, url_prefix=prefijo)
    for spec in registry.values():
        VistasAPI(spec).registrar(bp)

    # Errores HTTP como JSON en toda la API. Se registra en la app (no en el
    # blueprint) porque un 404 de URL inexistente o un 405 ocurren antes de que
    # Flask sepa qué blueprint atiende la ruta.
    mensajes = {404: "No existe el recurso solicitado.", 405: "Método no permitido."}

    def _error_http(e):
        if request.path == prefijo or request.path.startswith(prefijo + "/"):
            return error_json(e.code, mensajes.get(e.code, e.description))
        return e

    app.register_error_handler(HTTPException, _error_http)

    from app.crud.api.openapi import registrar_documentacion

    registrar_documentacion(bp, registry, prefijo)
    app.register_blueprint(bp)
    return bp
