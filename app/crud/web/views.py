# app/crud/web/views.py
"""
Vistas web CRUD generadas a partir de una EntitySpec.

Por cada entidad del registry se generan cinco pantallas:

    /<entidad>                          listado (búsqueda y filtros)
    /<entidad>/crear                    alta
    /<entidad>/<id>                     detalle (datos, historial, subentidades)
    /<entidad>/<id>/editar              edición
    /<entidad>/<id>/confirmar_eliminar  baja

La navegación (a dónde vuelve cada pantalla, qué pestañas tiene el detalle)
se deduce de la spec: padre, hijos y nombre. No hay nombres de blueprint ni
URLs escritas a mano.

Las subentidades (ej: ubicaciones) funcionan en dos contextos:
  * desde el padre (?sector_id=3): el alta llega con el sector elegido y al
    guardar se vuelve a la pestaña del sector;
  * por su cuenta (/ubicaciones): listado completo, con el padre como columna
    y filtro, y alta eligiendo el padre en el formulario.
"""
from __future__ import annotations

from flask import current_app, redirect, render_template, request, url_for

from app.crud.core import coercion, dependencias, fk, repository
from app.crud.core.coercion import ErroresValidacion
from app.crud.core.files import ArchivoInvalido, guardar
from app.crud.core.service import ErrorIntegridad, RegistroEnUso, ServicioCRUD
from app.crud.meta.spec import EntitySpec
from app.crud.web.textos import etiqueta_tabla

BLUEPRINT = "crud"
ACCIONES = ("listar", "crear", "detalle", "editar", "confirmar_eliminar")


def endpoint(entidad: str, accion: str) -> str:
    """Nombre del endpoint Flask de una acción, ej: ("sectores", "detalle") → "crud.sectores_detalle"."""
    return f"{BLUEPRINT}.{entidad}_{accion}"


class VistasEntidad:
    def __init__(self, spec: EntitySpec, registry: dict[str, EntitySpec]):
        self.spec = spec
        self.registry = registry
        self.fields = spec.fields
        self.padre = registry[spec.padre.entidad] if spec.padre else None
        self.servicio = ServicioCRUD(
            spec.model,
            spec.fields,
            {"enabled": spec.auditoria, "ignore_fields": list(spec.auditoria_ignorar)},
            etiqueta_tabla,
        )

    # ------------------------------------------------------------------
    # Registro de rutas
    # ------------------------------------------------------------------

    def registrar(self, bp):
        n = self.spec.name
        base = f"/{n}"
        bp.add_url_rule(base, f"{n}_listar", self.listar)
        bp.add_url_rule(f"{base}/crear", f"{n}_crear", self.crear, methods=["GET", "POST"])
        bp.add_url_rule(f"{base}/<int:id>", f"{n}_detalle", self.detalle)
        bp.add_url_rule(f"{base}/<int:id>/editar", f"{n}_editar", self.editar, methods=["GET", "POST"])
        bp.add_url_rule(
            f"{base}/<int:id>/confirmar_eliminar", f"{n}_confirmar_eliminar",
            self.confirmar_eliminar, methods=["GET", "POST"],
        )

    # ------------------------------------------------------------------
    # Navegación
    # ------------------------------------------------------------------

    @property
    def endpoint_base(self):
        return f"{BLUEPRINT}.{self.spec.name}"

    @property
    def endpoint_padre(self):
        return endpoint(self.padre.name, "detalle") if self.padre else None

    def _padre_de(self, registro):
        return getattr(registro, self.spec.padre.fk) if self.spec.padre else None

    def _padre_desde_url(self):
        """ID del padre recibido en la URL (?sector_id=3), o None si no es válido."""
        if not self.spec.padre:
            return None
        valor = request.args.get(self.spec.padre.fk, "")
        return int(valor) if valor.isdigit() else None

    def _url_volver(self, padre_id):
        """Pestaña de esta entidad en el detalle del padre, o el listado propio."""
        if padre_id:
            return url_for(self.endpoint_padre, id=padre_id, seccion=self.spec.name)
        return url_for(endpoint(self.spec.name, "listar"))

    def _contexto(self, padre_id=None):
        """Variables comunes a todas las plantillas."""
        s = self.spec
        return {
            "label_singular": s.label_singular,
            "label_plural": s.label_plural,
            "genero": s.genero,
            "pk": s.pk,
            "fields": self.fields,
            "endpoint_base": self.endpoint_base,
            # Las plantillas usan es_subentidad para navegar hacia el padre:
            # solo tiene sentido si hay un padre concreto.
            "es_subentidad": bool(self.padre and padre_id),
            "padre_id": padre_id,
            "fk_padre": s.padre.fk if s.padre else None,
            "entidad_padre": self.padre.label_singular if self.padre else None,
            "entidad_padre_endpoint": self.endpoint_padre,
        }

    def _motivo(self):
        return request.form.get("motivo_operacion") or None

    # ------------------------------------------------------------------
    # LISTAR
    # ------------------------------------------------------------------

    def listar(self):
        s = self.spec
        campo = request.args.get("campo") or "todos"
        q = request.args.get("q", "")
        valor_fk = request.args.get("valor_fk")
        padre_id = self._padre_desde_url()

        objetos = repository.consulta_listado(
            s.model, self.fields, list(s.filtros),
            q=q, campo=campo, valor_fk=valor_fk,
            filtro_padre=(s.padre.fk, padre_id) if s.padre else None,
        ).all()

        fk_labels = [fk.etiquetas(r, self.fields) for r in objetos]
        registros = []
        for r, labels in zip(objetos, fk_labels):
            d = r.to_dict()
            fila = {c: labels[c] if c in labels else d.get(c) for c in s.listado}
            fila[s.pk] = d.get(s.pk)
            registros.append(fila)

        return render_template(
            "crud/listado_entidad.html",
            **self._contexto(),
            nombre_entidad=s.label_plural.capitalize(),
            registros=registros,
            columns=list(s.listado),
            filtros={"campos": list(s.filtros)},
            campo_actual=campo,
            valor_fk=valor_fk,
            fk_data=fk.opciones_de(self.fields),
            fk_labels=fk_labels,
            q=q,
        )

    # ------------------------------------------------------------------
    # Formulario (alta y edición)
    # ------------------------------------------------------------------

    def _leer_formulario(self, parcial):
        datos, errores = {}, {}
        try:
            datos = coercion.datos_de_entrada(self.spec.model, self.fields, request.form, parcial=parcial)
        except ErroresValidacion as e:
            errores.update(e.errores)

        for campo, f in self.fields.items():
            if f.tipo != "file":
                continue
            archivo = request.files.get(campo)
            if archivo and archivo.filename:
                try:
                    datos[campo] = guardar(archivo, current_app.static_folder, self.spec.name, f.subcarpeta)
                except ArchivoInvalido as e:
                    errores[campo] = f"{f.label}: {e}."
            elif f.required and not parcial:
                errores[campo] = f"{f.label} es obligatorio."

        try:
            fk.validar_existencia(self.fields, datos)
        except ErroresValidacion as e:
            errores.update(e.errores)

        if errores:
            raise ErroresValidacion(errores)
        return datos

    def _valores_formulario(self, registro):
        return {
            campo: coercion.valor_para_formulario(self.fields.get(campo, {}), valor)
            for campo, valor in registro.to_dict().items()
        }

    def _render_form(self, tipo_operacion, modelo, padre_id, url_cancelar, errores=None, status=200):
        return render_template(
            "crud/form.html",
            **self._contexto(padre_id),
            nombre_entidad=self.spec.label_singular.capitalize(),
            modelo=modelo,
            tipo_operacion=tipo_operacion,
            fk_data=fk.opciones_de(self.fields),
            errores=errores or {},
            url_cancelar=url_cancelar,
        ), status

    def _guardar(self, operacion, tipo_operacion, modelo_actual, padre_id, url_cancelar):
        enviados = {**modelo_actual, **request.form.to_dict()}
        try:
            datos = self._leer_formulario(parcial=(tipo_operacion == "UPDATE"))
            return operacion(datos)
        except ErroresValidacion as e:
            errores = e.errores
        except ErrorIntegridad as e:
            errores = {e.campo or "_general": e.mensaje}
        return self._render_form(tipo_operacion, enviados, padre_id, url_cancelar, errores, 400)

    # ------------------------------------------------------------------
    # CREAR
    # ------------------------------------------------------------------

    def crear(self):
        padre_id = self._padre_desde_url()
        modelo = {self.spec.padre.fk: padre_id} if padre_id else {}
        url_cancelar = self._url_volver(padre_id)

        if request.method == "GET":
            return self._render_form("INSERT", modelo, padre_id, url_cancelar)

        def operacion(datos):
            if padre_id and datos.get(self.spec.padre.fk) is None:
                datos[self.spec.padre.fk] = padre_id
            nuevo = self.servicio.crear(datos, self._motivo())
            # Si se vino desde el padre, volver a su pestaña; si no, al listado.
            return redirect(self._url_volver(self._padre_de(nuevo) if padre_id else None))

        return self._guardar(operacion, "INSERT", modelo, padre_id, url_cancelar)

    # ------------------------------------------------------------------
    # EDITAR
    # ------------------------------------------------------------------

    def editar(self, id):
        registro = repository.obtener_o_404(self.spec.model, id)
        padre_id = self._padre_de(registro)
        url_cancelar = url_for(endpoint(self.spec.name, "detalle"), id=id)

        if request.method == "GET":
            return self._render_form("UPDATE", self._valores_formulario(registro), padre_id, url_cancelar)

        def operacion(datos):
            self.servicio.actualizar(registro, datos, self._motivo())
            return redirect(self._url_volver(self._padre_de(registro)))

        return self._guardar(operacion, "UPDATE", self._valores_formulario(registro), padre_id, url_cancelar)

    # ------------------------------------------------------------------
    # ELIMINAR
    # ------------------------------------------------------------------

    def confirmar_eliminar(self, id):
        registro = repository.obtener_o_404(self.spec.model, id)
        padre_id = self._padre_de(registro)

        error = None
        if request.method == "POST":
            try:
                self.servicio.eliminar(registro, self._motivo())
                return redirect(self._url_volver(padre_id))
            except ErrorIntegridad as e:
                error = e.mensaje
                registro = repository.obtener_o_404(self.spec.model, id)
        else:
            try:
                self.servicio.verificar_eliminable(registro)
            except RegistroEnUso as e:
                error = e.mensaje

        return render_template(
            "crud/confirmar_eliminar.html",
            **self._contexto(padre_id),
            nombre_entidad=self.spec.label_singular.capitalize(),
            modelo=registro.to_dict(),
            fk_labels=fk.etiquetas(registro, self.fields),
            error=error,
            cascada=[etiqueta_tabla(t, n) for t, n in dependencias.resumen_cascada(registro)],
            url_cancelar=url_for(endpoint(self.spec.name, "detalle"), id=id),
        ), (409 if error and request.method == "POST" else 200)

    # ------------------------------------------------------------------
    # DETALLE
    # ------------------------------------------------------------------

    def detalle(self, id):
        s = self.spec
        registro = repository.obtener_o_404(s.model, id)
        padre_id = self._padre_de(registro)
        modelo = fk.agregar_etiquetas(registro.to_dict(), registro, self.fields)

        historial, pagination = [], None
        if hasattr(registro, "obtener_historial"):
            historial, pagination = registro.obtener_historial(request.args.get("page", 1, type=int))

        # Una pestaña por cada subentidad (hijos declarados con "padre").
        subentidades = []
        for nombre_hijo in s.hijos:
            hijo = self.registry[nombre_hijo]
            objetos = hijo.model.query.filter_by(**{hijo.padre.fk: id}).all()
            subentidades.append({
                "label": hijo.label_plural.capitalize(),
                "label_singular": hijo.label_singular,
                "label_plural": hijo.label_plural,
                "template_listado": "crud/listado_subentidad.html",
                "items": [fk.agregar_etiquetas(o.to_dict(), o, hijo.fields) for o in objetos],
                "entidad": hijo.name,
                "fields": hijo.fields,
                "pk": hijo.pk,
                "fk": hijo.padre.fk,
                "modelo_padre": registro.to_dict(),
                "padre_id": id,
                "endpoint_base": f"{BLUEPRINT}.{hijo.name}",
            })

        secciones = [{"id": "datos", "label": "Datos"}]
        if hasattr(registro, "obtener_historial"):
            secciones.append({"id": "historial", "label": "Historial"})
        secciones_dict = {sec["id"]: {**sec, "sub": None} for sec in secciones}
        for sub in subentidades:
            secciones.append({"id": sub["entidad"], "label": sub["label"]})
            secciones_dict[sub["entidad"]] = {"id": sub["entidad"], "label": sub["label"], "sub": sub}

        seccion = request.args.get("seccion", "datos")
        if seccion not in secciones_dict:
            seccion = "datos"

        return render_template(
            "crud/detalle_entidad.html",
            **self._contexto(padre_id),
            modelo=modelo,
            historial=historial,
            pagination=pagination,
            subentidades=subentidades,
            secciones=secciones,
            secciones_dict=secciones_dict,
            seccion_activa=seccion,
            url_volver=self._url_volver(padre_id),
        )


def registrar_web(app, registry: dict[str, EntitySpec]):
    """Genera y registra las pantallas de todas las entidades del registry."""
    from flask import Blueprint

    bp = Blueprint(BLUEPRINT, __name__)
    for spec in registry.values():
        VistasEntidad(spec, registry).registrar(bp)
    app.register_blueprint(bp)
    return bp
