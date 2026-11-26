# app/crud/web/views.py
"""
Vistas web CRUD generadas a partir de una EntitySpec.

Por cada entidad del registry se generan cinco pantallas:

    /<entidad>                          listado (búsqueda y filtros)
    /<entidad>/crear                    alta
    /<entidad>/<id>                     detalle (datos, historial, subentidades)
    /<entidad>/<id>/editar              edición
    /<entidad>/<id>/confirmar_eliminar  baja

Si la spec declara `edicion_en_linea`, además (fase 13, grilla con htmx):

    GET  /<entidad>/<id>/celda/<campo>  la celda en edición (<td>)
    POST /<entidad>/<id>/celda/<campo>  guarda; la fila entera (<tr>), o la fila con
                                        la celda abierta y el error (422)
    GET  /<entidad>/<id>/fila           la fila en lectura (Esc)

Si declara `alta_en_linea` (fase 13.3, alta rápida), la pestaña del padre
termina con una fila de alta:

    POST /<entidad>/alta_en_linea?<fk del padre>=<id>
                                        crea; la fila nueva y una fila de alta
                                        vacía, o la fila de alta con los errores (422)

Si la spec declara `acciones`: /<entidad>/<id>/accion/<accion> (POST; con
`campos`, además GET con el formulario de la acción).

Las reglas de edición según el registro (`editable_si`, `eliminable_si`, fase
13.2) las aplica el servicio; acá solo se reflejan: celdas congeladas en gris
(y 404 si se pide editarlas), campos congelados deshabilitados en el formulario
y el botón «Eliminar» oculto.

La navegación (a dónde vuelve cada pantalla, qué pestañas tiene el detalle)
se deduce de la spec: padre, hijos y nombre. No hay nombres de blueprint ni
URLs escritas a mano.

Las subentidades (ej: ubicaciones) funcionan en dos contextos:
  * desde el padre (?sector_id=3): el alta llega con el sector elegido y al
    guardar se vuelve a la pestaña del sector;
  * por su cuenta (/ubicaciones): listado completo, con el padre como columna
    y filtro, y alta eligiendo el padre en el formulario.

Una subentidad puede colgar de varios padres (ej: el BOM de un modelo aparece en
el modelo y en el material). El padre "activo" es el que viene en la URL
(?material_id=7); si no viene ninguno, se usa el principal (el primero declarado).
"""
from __future__ import annotations

from flask import abort, current_app, flash, redirect, render_template, request, url_for

from app.core.db import db

from app.crud.core import coercion, dependencias, fk, repository
from app.crud.core.coercion import ErroresValidacion
from app.crud.core.files import ArchivoInvalido, guardar
from app.crud.core.interpretes import buscar_por_texto
from app.crud.core.service import ErrorIntegridad, ServicioCRUD, permitido
from app.crud.entidades import servicio
from app.crud.meta.spec import EntitySpec, ParentSpec
from app.crud.web.textos import etiqueta_tabla, inicial

BLUEPRINT = "crud"
# Motivo que la auditoría registra para lo guardado desde la grilla. Es fijo: no
# está en el catálogo de motivos (ver propuesta_edicion_en_linea.md, decisión 1).
MOTIVO_EDICION_EN_LINEA = "Edición en línea"
MOTIVO_ALTA_EN_LINEA = "Alta en línea"
ACCIONES = ("listar", "crear", "detalle", "editar", "confirmar_eliminar")


def endpoint(entidad: str, accion: str) -> str:
    """Nombre del endpoint Flask de una acción, ej: ("sectores", "detalle") → "crud.sectores_detalle"."""
    return f"{BLUEPRINT}.{entidad}_{accion}"


def _valor_url(valor) -> str:
    """Un valor de filtro como va en la URL y en el <option>: Sí/No para los booleanos."""
    if isinstance(valor, bool):
        return "Sí" if valor else "No"
    return str(valor)


class VistasEntidad:
    def __init__(self, spec: EntitySpec, registry: dict[str, EntitySpec]):
        self.spec = spec
        self.registry = registry
        self.fields = spec.fields
        self.servicio = servicio(spec)

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
        if self.spec.acciones:
            bp.add_url_rule(f"{base}/<int:id>/accion/<accion>", f"{n}_accion",
                            self.accion, methods=["GET", "POST"])
        if self.spec.edicion_en_linea:
            bp.add_url_rule(f"{base}/<int:id>/celda/<campo>", f"{n}_celda", self.celda,
                            methods=["GET", "POST"])
            bp.add_url_rule(f"{base}/<int:id>/fila", f"{n}_fila", self.fila)
        if self.spec.alta_en_linea:
            bp.add_url_rule(f"{base}/alta_en_linea", f"{n}_alta_en_linea", self.alta_en_linea,
                            methods=["POST"])

    # ------------------------------------------------------------------
    # Navegación
    # ------------------------------------------------------------------

    @property
    def endpoint_base(self):
        return f"{BLUEPRINT}.{self.spec.name}"

    def _padre_desde_url(self) -> tuple[ParentSpec | None, int | None]:
        """Padre recibido en la URL (?sector_id=3), o (None, None)."""
        for p in self.spec.padres:
            valor = request.args.get(p.fk, "")
            if valor.isdigit():
                return p, int(valor)
        return None, None

    def _padre_de(self, registro) -> tuple[ParentSpec | None, int | None]:
        """
        Padre activo para un registro (define a dónde vuelve cada pantalla):
          * el de la URL, si se llegó desde un padre (?sector_id=3);
          * si no, ninguno cuando la entidad tiene entrada propia en el menú
            (ej: un tipo de activo abierto desde Catálogos vuelve a su listado,
            no a la cuenta);
          * si no, el principal (ej: una ubicación vuelve a su sector).
        """
        p, padre_id = self._padre_desde_url()
        if p is not None:
            return p, getattr(registro, p.fk) or padre_id
        p = self.spec.padre
        if p is None or self.spec.sidebar:
            return None, None
        return p, getattr(registro, p.fk)

    def _url_volver(self, padre: ParentSpec | None, padre_id):
        """Pestaña de esta entidad en el detalle del padre, o el listado propio."""
        if padre and padre_id:
            return url_for(endpoint(padre.entidad, "detalle"), id=padre_id, seccion=self.spec.name)
        return url_for(endpoint(self.spec.name, "listar"))

    def _url_detalle(self, id, padre, padre_id):
        args = {padre.fk: padre_id} if padre and padre_id and request.args.get(padre.fk) else {}
        return url_for(endpoint(self.spec.name, "detalle"), id=id, **args)

    def _contexto(self, padre: ParentSpec | None = None, padre_id=None):
        """Variables comunes a todas las plantillas."""
        s = self.spec
        spec_padre = self.registry[padre.entidad] if padre else None
        # Si se llegó desde el padre, los enlaces (editar, eliminar) mantienen ese contexto.
        args_padre = {padre.fk: padre_id} if padre and padre_id and request.args.get(padre.fk) else {}
        return {
            "label_singular": s.label_singular,
            "label_plural": s.label_plural,
            "genero": s.genero,
            "pk": s.pk,
            "fields": self.fields,
            "endpoint_base": self.endpoint_base,
            # Las plantillas usan es_subentidad para navegar hacia el padre:
            # solo tiene sentido si hay un padre concreto.
            "es_subentidad": bool(padre and padre_id),
            "padre_id": padre_id,
            "fk_padre": padre.fk if padre else None,
            "args_padre": args_padre,
            "entidad_padre": spec_padre.label_singular if spec_padre else None,
            "entidad_padre_endpoint": endpoint(padre.entidad, "detalle") if padre else None,
        }

    def _motivo(self):
        return request.form.get("motivo_operacion") or None

    # ------------------------------------------------------------------
    # LISTAR
    # ------------------------------------------------------------------

    def _filtros_de_url(self, campos: list[str]) -> dict:
        """
        {campo: valor} de los filtros de la URL (?categoria_activo_id=2&sector_id=3),
        convertidos al tipo de la columna. Un valor vacío o inválido se ignora.
        """
        columnas = self.spec.model.__mapper__.columns
        resultado = {}
        for campo in campos:
            crudo = request.args.get(campo, "")
            if crudo == "" or campo not in columnas:
                continue
            try:
                valor = coercion.convertir(columnas[campo], crudo)
            except ValueError:
                continue
            if valor is not None:
                resultado[campo] = valor
        return resultado

    def listar(self):
        s = self.spec
        campo = request.args.get("campo") or "todos"
        q = request.args.get("q", "")
        padre, padre_id = self._padre_desde_url()

        # Filtros combinables: un select por cada FK, opción fija o Sí/No de los
        # `filtros`. Los enlaces viejos (?campo=<fk>&valor_fk=3) siguen andando.
        campos_select = repository.campos_de_filtro(self.fields, list(s.filtros))
        valores = self._filtros_de_url(campos_select)
        valor_fk = request.args.get("valor_fk")
        if campo in campos_select:
            if valor_fk not in (None, "") and campo not in valores:
                valores.update(self._filtros_de_url_valor(campo, valor_fk))
            campo = "todos"

        objetos = repository.consulta_listado(
            s.model, self.fields, list(s.filtros),
            q=q, campo=campo, valores=valores,
            filtro_padre=(padre.fk, padre_id) if padre else None,
        ).all()

        registros = [item_fila(s, r, s.listado) for r in objetos]

        opciones = fk.opciones_de(self.fields)
        for c in campos_select:
            if c not in opciones:  # opciones fijas y Sí/No
                opciones[c] = fk.con_texto([
                    {"value": _valor_url(o["value"]), "label": o["label"], "deps": None, "grupo": None}
                    for o in self.fields[c].options])

        return render_template(
            "crud/listado_entidad.html",
            **self._contexto(),
            nombre_entidad=inicial(s.label_plural),
            registros=registros,
            columns=list(s.listado),
            # La búsqueda de texto elige entre los campos que no tienen select.
            filtros={"campos": [c for c in s.filtros if c not in campos_select]},
            campos_select=campos_select,
            # Como texto, para comparar con el value de cada <option>.
            valores={c: _valor_url(v) for c, v in valores.items()},
            campo_actual=campo,
            fk_data=opciones,
            # Filtros que se eligen tipeando (campo con lista) en lugar de un select.
            con_lista={c for c in campos_select if fk.usa_lista(self.fields[c], opciones[c])},
            grilla=contexto_grilla(s, s.listado, {}),
            q=q,
        )

    def _filtros_de_url_valor(self, campo: str, crudo: str) -> dict:
        """Un filtro recibido con el formato viejo (?campo=<campo>&valor_fk=<valor>)."""
        columna = self.spec.model.__mapper__.columns.get(campo)
        try:
            valor = coercion.convertir(columna, crudo) if columna is not None else None
        except ValueError:
            return {}
        return {} if valor is None else {campo: valor}

    # ------------------------------------------------------------------
    # Formulario (alta y edición)
    # ------------------------------------------------------------------

    def _leer_formulario(self, parcial, por_defecto=None):
        """por_defecto: valores para los campos que el formulario no trae (ej: el padre de la URL)."""
        entrada = request.form.to_dict()
        for campo, valor in (por_defecto or {}).items():
            if not entrada.get(campo):
                entrada[campo] = valor
        datos, errores = {}, {}
        try:
            datos = coercion.datos_de_entrada(self.spec.model, self.fields, entrada, parcial=parcial)
        except ErroresValidacion as e:
            errores.update(e.errores)

        for campo, f in self.fields.items():
            if f.tipo != "file":
                continue
            archivo = request.files.get(campo)
            if archivo and archivo.filename:
                try:
                    datos[campo] = guardar(archivo, current_app.static_folder, self.spec.name,
                                           f.subcarpeta, f.extensiones)
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
            for campo, valor in repository.valores(registro).items()
        }

    def _con_lista(self, opciones: dict) -> set[str]:
        """Campos del formulario que se eligen tipeando (campo con lista) en lugar de un select."""
        return {c for c, ops in opciones.items() if fk.usa_lista(self.fields[c], ops)}

    def _render_form(self, tipo_operacion, modelo, padre, url_cancelar, errores=None, status=200,
                     congelados=None):
        """congelados: {campo: (texto del valor, porqué)} que se muestran deshabilitados (editable_si)."""
        padre, padre_id = padre
        s = self.spec
        if tipo_operacion == "INSERT":
            titulo = f"{'Nueva' if s.genero == 'f' else 'Nuevo'} {s.label_singular}"
        else:
            titulo = f"Editar {s.label_singular}"
        opciones = fk.opciones_de(self.fields)
        for c, f in self.fields.items():
            if f.tipo == "select":  # opciones fijas: también pueden ir con lista
                opciones[c] = fk.con_texto([
                    {"value": o["value"], "label": o["label"], "deps": None, "grupo": None}
                    for o in f.options])
        return render_template(
            "crud/form.html",
            **self._contexto(padre, padre_id),
            titulo_pagina=titulo,
            nombre_entidad=inicial(self.spec.label_singular),
            modelo=modelo,
            tipo_operacion=tipo_operacion,
            fk_data=opciones,
            con_lista=self._con_lista(opciones),
            sugerencias=fk.sugerencias_de(self.fields),
            campos_filtro=self._campos_filtro(),
            congelados=congelados or {},
            errores=errores or {},
            url_cancelar=url_cancelar,
        ), status

    def _campos_filtro(self) -> set[str]:
        """
        Campos calculados de los que depende otro (ej: el tipo de activo, del que
        depende la categoría): en el formulario son un filtro, sin name (no se envían).
        """
        return {padre for f in self.fields.values() for padre in f.depende_de
                if self.fields[padre].solo_lectura and self.fields[padre].tipo == "fk"}

    def _guardar(self, operacion, tipo_operacion, modelo_actual, padre, url_cancelar, por_defecto=None,
                 congelados=None):
        enviados = {**modelo_actual, **request.form.to_dict()}
        try:
            datos = self._leer_formulario(parcial=(tipo_operacion == "UPDATE"), por_defecto=por_defecto)
            return operacion(datos)
        except ErroresValidacion as e:
            errores = e.errores
        except ErrorIntegridad as e:
            errores = {e.campo or "_general": e.mensaje}
        return self._render_form(tipo_operacion, enviados, padre, url_cancelar, errores, 400, congelados)

    # ------------------------------------------------------------------
    # CREAR
    # ------------------------------------------------------------------

    def _valores_por_defecto(self) -> dict:
        """Valores por defecto de las columnas (ej: «Vigente» = Sí), para el formulario de alta."""
        columnas = self.spec.model.__table__.columns
        resultado = {}
        for campo in self.fields:
            col = columnas.get(campo)
            default = getattr(col, "default", None) if col is not None else None
            if default is None:
                continue
            if getattr(default, "is_scalar", False):
                resultado[campo] = default.arg
            elif getattr(default, "is_callable", False) and self.fields[campo].tipo == "fk":
                # Una FK con valor por defecto calculado (ej: el estado «Operativa»
                # de una ubicación). La función recibe el contexto de ejecución de
                # SQLAlchemy; fuera de un INSERT se la llama con None. Solo FK: las
                # fechas (date.today) se siguen cargando a mano.
                resultado[campo] = default.arg(None)
        return resultado

    def crear(self):
        padre, padre_id = self._padre_desde_url()
        modelo = {padre.fk: padre_id} if padre else {}
        formulario = {**self._valores_por_defecto(), **modelo}
        url_cancelar = self._url_volver(padre, padre_id)

        if request.method == "GET":
            return self._render_form("INSERT", formulario, (padre, padre_id), url_cancelar)

        def operacion(datos):
            nuevo = self.servicio.crear(datos, self._motivo())
            self._avisar(nuevo)
            # Si se vino desde el padre, volver a su pestaña; si no, al listado.
            return redirect(self._url_volver(padre, getattr(nuevo, padre.fk)) if padre
                            else self._url_volver(None, None))

        return self._guardar(operacion, "INSERT", modelo, (padre, padre_id), url_cancelar, por_defecto=modelo)

    # ------------------------------------------------------------------
    # EDITAR
    # ------------------------------------------------------------------

    def editar(self, id):
        registro = repository.obtener_o_404(self.spec.model, id)
        padre, padre_id = self._padre_de(registro)
        url_cancelar = self._url_detalle(id, padre, padre_id)
        congelados = self._congelados_formulario(registro)

        if request.method == "GET":
            return self._render_form("UPDATE", self._valores_formulario(registro), (padre, padre_id), url_cancelar,
                                     congelados=congelados)

        def operacion(datos):
            self.servicio.actualizar(registro, datos, self._motivo())
            self._avisar(registro)
            return redirect(self._url_volver(*self._padre_de(registro)))

        return self._guardar(operacion, "UPDATE", self._valores_formulario(registro), (padre, padre_id), url_cancelar,
                             congelados=congelados)

    def _congelados_formulario(self, registro) -> dict:
        """
        {campo: (texto del valor, porqué)} de los campos congelados en este registro.
        Se muestran deshabilitados (sin name: no se envían, y la edición es parcial).
        """
        resultado = {}
        for campo, porque in self.servicio.congelados(registro).items():
            f = self.fields[campo]
            valor = getattr(registro, campo)
            if f.tipo == "fk":
                obj = fk.destino(registro, campo, f)
                texto = fk.etiqueta(obj, f) if obj is not None else ""
            elif f.tipo == "select":
                texto = next((o["label"] for o in f.options if o["value"] == valor), valor)
            else:
                texto = coercion.valor_para_formulario(f, valor)
            resultado[campo] = ("" if texto is None else str(texto), porque)
        return resultado

    # ------------------------------------------------------------------
    # ELIMINAR
    # ------------------------------------------------------------------

    def confirmar_eliminar(self, id):
        registro = repository.obtener_o_404(self.spec.model, id)
        padre, padre_id = self._padre_de(registro)

        error = None
        if request.method == "POST":
            try:
                self.servicio.eliminar(registro, self._motivo())
                return redirect(self._url_volver(padre, padre_id))
            except ErrorIntegridad as e:
                error = e.mensaje
                registro = repository.obtener_o_404(self.spec.model, id)
        else:
            try:
                self.servicio.verificar_eliminable(registro)
            except ErrorIntegridad as e:
                error = e.mensaje

        return render_template(
            "crud/confirmar_eliminar.html",
            **self._contexto(padre, padre_id),
            titulo_pagina=f"Eliminar {self.spec.label_singular}",
            nombre_entidad=inicial(self.spec.label_singular),
            modelo=repository.valores(registro),
            fk_labels=fk.etiquetas(registro, self.fields),
            error=error,
            cascada=[etiqueta_tabla(t, n) for t, n in dependencias.resumen_cascada(registro)],
            url_cancelar=self._url_detalle(id, padre, padre_id),
        ), (409 if error and request.method == "POST" else 200)

    # ------------------------------------------------------------------
    # DETALLE
    # ------------------------------------------------------------------

    def detalle(self, id):
        s = self.spec
        registro = repository.obtener_o_404(s.model, id)
        padre, padre_id = self._padre_de(registro)
        modelo = fk.agregar_etiquetas(repository.valores(registro), registro, self.fields)

        historial, pagination = [], None
        if hasattr(registro, "obtener_historial"):
            historial, pagination = registro.obtener_historial(request.args.get("page", 1, type=int))

        secciones = [{"id": "datos", "label": "Datos"}]
        if hasattr(registro, "obtener_historial"):
            secciones.append({"id": "historial", "label": "Historial"})
        # Una pestaña por cada subentidad (hijos declarados con "padre")...
        for nombre_hijo in s.hijos:
            rel = self.registry[nombre_hijo].padre_de_tipo(s.name)
            if rel.visible is not None and not rel.visible(registro):
                continue  # ej: «Presentaciones» solo en los genéricos
            secciones.append({"id": nombre_hijo, "label": self._label_hijo(self.registry[nombre_hijo])})
        # ...y una por cada pestaña calculada (tabs_extra).
        for tab in s.tabs_extra:
            secciones.append({"id": tab.id, "label": tab.label})

        seccion = request.args.get("seccion", "datos")
        if seccion not in {sec["id"] for sec in secciones}:
            seccion = "datos"

        # Solo se consulta la pestaña que se muestra.
        sub = tabla = None
        if seccion in s.hijos:
            sub = self._subentidad(self.registry[seccion], registro, id)
        else:
            tab = next((t for t in s.tabs_extra if t.id == seccion), None)
            if tab:
                tabla = {"vacio": "No hay registros.", **tab.funcion(registro)}

        return render_template(
            "crud/detalle_entidad.html",
            **self._contexto(padre, padre_id),
            titulo_pagina=self._titulo_registro(registro),
            modelo=modelo,
            historial=historial,
            pagination=pagination,
            secciones=secciones,
            seccion_activa=seccion,
            sub=sub,
            tabla=tabla,
            acciones=self._acciones_de(registro, seccion),
            eliminable=self.servicio.no_eliminable(registro) is None,
            url_volver=self._url_volver(padre, padre_id),
        )

    def _label_hijo(self, hijo: EntitySpec) -> str:
        """Nombre de la pestaña de una subentidad en este padre (ej: «BOM» en el activo)."""
        return hijo.padre_de_tipo(self.spec.name).label or inicial(hijo.label_plural)

    # ------------------------------------------------------------------
    # ACCIONES (botones del detalle) y avisos
    # ------------------------------------------------------------------

    def _acciones_de(self, registro, seccion):
        return acciones_visibles(self.spec, registro, lambda a: a.seccion == seccion, request.args)

    def accion(self, id, accion):
        registro = repository.obtener_o_404(self.spec.model, id)
        a = next((x for x in self.spec.acciones if x.id == accion), None)
        if a is None or (a.visible is not None and not a.visible(registro)):
            return ("Acción no disponible.", 404)
        if request.method == "GET" and not a.campos:
            abort(405)
        # Desde la fila de una grilla se vuelve a la pestaña del padre; desde el
        # detalle, a la pestaña de la acción.
        args = {k: v for k, v in request.args.items() if k not in ("seccion", "desde")}
        if request.args.get("desde") == "fila":
            volver = self._url_volver(*self._padre_de(registro))
        else:
            volver = url_for(endpoint(self.spec.name, "detalle"), id=id, seccion=a.seccion, **args)
        if a.campos:
            return self._accion_con_formulario(registro, a, volver)
        try:
            self._flash_resultado(a.funcion(registro))
            db.session.commit()
        except (ErroresValidacion, ErrorIntegridad) as e:
            db.session.rollback()
            flash(getattr(e, "mensaje", None) or "; ".join(e.errores.values()), "error")
        return redirect(volver)

    def _accion_con_formulario(self, registro, a, volver):
        """GET: el formulario de la acción. POST: la ejecuta, o vuelve al formulario con los errores."""
        valores, errores = {}, {}
        if request.method == "POST":
            valores = request.form.to_dict()
            try:
                datos = {}
                for c, f in a.campos.items():
                    try:
                        valor = coercion.convertir_sin_columna(f, valores.get(c))
                    except ValueError as e:
                        errores[c] = f"{f.label} {e}."
                        continue
                    if valor is None and f.required:
                        errores[c] = f"{f.label} es obligatorio."
                    datos[c] = valor
                if errores:
                    raise ErroresValidacion(errores)
                fk.validar_existencia(a.campos, datos)
                ServicioCRUD(self.spec.model, a.campos).verificar_opciones(datos)
                self._flash_resultado(a.funcion(registro, datos))
                db.session.commit()
                return redirect(volver)
            except ErroresValidacion as e:
                db.session.rollback()
                errores = self._errores_de_accion(a, e.errores)
            except ErrorIntegridad as e:
                db.session.rollback()
                errores = {e.campo if e.campo in a.campos else "_general": e.mensaje}
            registro = repository.obtener_o_404(self.spec.model, getattr(registro, self.spec.pk))
        opciones = fk.opciones_de(a.campos)
        return render_template(
            "crud/accion.html",
            **self._contexto(*self._padre_de(registro)),
            titulo_pagina=f"{a.label} — {self._titulo_registro(registro)}",
            accion=a,
            registro_titulo=self._titulo_registro(registro),
            campos=a.campos,
            valores=valores,
            fk_data=opciones,
            con_lista={c for c, ops in opciones.items() if fk.usa_lista(a.campos[c], ops)},
            errores=errores,
            url_cancelar=volver,
        ), (400 if errores else 200)

    def _errores_de_accion(self, a, errores: dict) -> dict:
        """Los errores de campos del registro (no del formulario) van arriba, con su etiqueta."""
        resultado, generales = {}, []
        for campo, texto in errores.items():
            if campo in a.campos:
                resultado[campo] = texto
            else:
                generales.append(texto)
        if generales:
            resultado["_general"] = " ".join(generales)
        return resultado

    def _flash_resultado(self, resultado):
        """
        Lo que devuelve la función de una acción: un texto (ok), una tupla
        (categoría, texto) o una lista de ellos.
        """
        if not resultado:
            return
        for item in resultado if isinstance(resultado, list) else [resultado]:
            categoria, texto = item if isinstance(item, tuple) else ("ok", item)
            flash(texto, categoria)

    def _avisar(self, registro):
        for categoria, texto in getattr(registro, "avisos_guardado", []):
            flash(texto, categoria)

    def _titulo_registro(self, registro) -> str:
        """Nombre del registro para la pestaña del navegador (ej: «Tractor 1»)."""
        campo = getattr(self.spec.model, "__label_field__", None)
        nombre = getattr(registro, campo, None) if campo else None
        return str(nombre) if nombre not in (None, "") else inicial(self.spec.label_singular)

    def _subentidad(self, hijo: EntitySpec, registro, id):
        """Datos de la pestaña de una subentidad en el detalle del padre."""
        rel = hijo.padre_de_tipo(self.spec.name)
        # Las columnas del listado de la entidad, sin la del padre (es la misma en todas).
        columnas = [c for c in hijo.listado if c != rel.fk]
        objetos = (
            hijo.model.query.options(*fk.carga_anticipada(hijo.model, hijo.fields))
            .filter_by(**{rel.fk: id})
            .order_by(getattr(hijo.model, hijo.pk))
            .all()
        )
        return {
            "label": self._label_hijo(hijo),
            "label_singular": hijo.label_singular,
            "label_plural": hijo.label_plural,
            "template_listado": "crud/listado_subentidad.html",
            "items": [item_fila(hijo, o, columnas) for o in objetos],
            "grilla": contexto_grilla(hijo, columnas, {rel.fk: id}),
            "alta": (contexto_alta(hijo, columnas, {rel.fk: id})
                     if hijo.alta_en_linea and hijo.alta_en_linea_padre == self.spec.name else None),
            "entidad": hijo.name,
            # Las columnas del listado de la entidad (no todas: la tabla desbordaría).
            "fields": {c: hijo.fields[c] for c in hijo.listado},
            "pk": hijo.pk,
            "fk": rel.fk,
            "modelo_padre": repository.valores(registro),
            "padre_id": id,
            "endpoint_base": f"{BLUEPRINT}.{hijo.name}",
        }


    # ------------------------------------------------------------------
    # EDICIÓN EN LÍNEA (grilla)
    # ------------------------------------------------------------------

    def _grilla_de_url(self):
        """Contexto de la fila según desde dónde se llegó: la pestaña del padre o el listado."""
        padre, padre_id = self._padre_desde_url()
        if padre is not None:
            return contexto_grilla(self.spec, [c for c in self.spec.listado if c != padre.fk],
                                   {padre.fk: padre_id})
        return contexto_grilla(self.spec, self.spec.listado, {})

    def _campo_en_linea(self, registro, campo):
        """El campo, si se edita en la grilla y no está congelado en este registro; si no, 404."""
        if campo not in self.spec.edicion_en_linea or campo in self.servicio.congelados(registro):
            abort(404)
        return self.fields[campo]

    def _render_fila(self, registro, status=200, **extra):
        grilla = self._grilla_de_url()
        item = item_fila(self.spec, registro, grilla["columnas"])
        return render_template("crud/partials/_fila.html", grilla=grilla, item=item, **extra), status

    def fila(self, id):
        return self._render_fila(repository.obtener_o_404(self.spec.model, id))

    def _celda(self, registro, campo, texto=None, error=None):
        """Variables de crud/partials/_celda_edicion.html."""
        f = self.fields[campo]
        grilla = self._grilla_de_url()
        id_ = getattr(registro, self.spec.pk)
        control, opciones = control_celda(f)
        if texto is None:
            texto = texto_celda(registro, campo, f, control)
        return {
            "campo": campo, "columna": self.spec.columna_en_linea.get(campo, campo),
            "cfg": f, "valor": texto, "error": error,
            "control": control, "opciones": opciones,
            "id_lista": f"lista-{self.spec.name}-{campo}",
            "url": url_for(endpoint(self.spec.name, "celda"), id=id_, campo=campo, **grilla["args_fila"]),
            "url_cancelar": url_for(endpoint(self.spec.name, "fila"), id=id_, **grilla["args_fila"]),
        }

    def celda(self, id, campo):
        registro = repository.obtener_o_404(self.spec.model, id)
        f = self._campo_en_linea(registro, campo)
        if request.method == "GET":
            return render_template("crud/partials/_celda_edicion.html", celda=self._celda(registro, campo))

        texto = request.form.get(campo, "")
        try:
            datos = self._dato_de_celda(campo, f, texto)
            self.servicio.actualizar(registro, datos, MOTIVO_EDICION_EN_LINEA)
        except ErroresValidacion as e:
            error = self._mensaje_celda(campo, e.errores)
        except ErrorIntegridad as e:
            error = self._mensaje_celda(campo, {e.campo or "_general": e.mensaje})
        else:
            self._avisar(registro)
            return self._render_fila(registro, foco=self.spec.columna_en_linea.get(campo, campo))
        # Lo guardado se descartó (el servicio hace rollback): la fila se arma con lo
        # que hay en la base y la celda queda abierta con lo que se escribió.
        registro = repository.obtener_o_404(self.spec.model, id)
        return self._render_fila(registro, 422, celda=self._celda(registro, campo, texto, error))

    def alta_en_linea(self):
        """
        Alta rápida desde la última fila de la grilla (en la pestaña del padre). Cada
        celda pasa por su intérprete y el registro se crea con servicio.crear, como
        en el formulario (completar, al_guardar, auditoría y reglas valen igual).
        """
        padre, padre_id = self._padre_desde_url()
        if padre is None or padre.entidad != self.spec.alta_en_linea_padre:
            abort(404)
        spec_padre = self.registry[padre.entidad]
        registro_padre = repository.obtener_o_404(spec_padre.model, padre_id)
        columnas = [c for c in self.spec.listado if c != padre.fk]
        args = {padre.fk: padre_id}

        textos = {c.nombre: request.form.get(c.nombre, "") for c in self.spec.alta_en_linea}
        datos, errores = {padre.fk: padre_id}, {}
        for c in self.spec.alta_en_linea:
            try:
                datos.update(c.interprete.interpretar(textos[c.nombre], self.spec))
            except ErroresValidacion as e:
                errores.update(e.errores)
        nuevo = None
        if not errores:
            try:
                nuevo = self.servicio.crear(datos, MOTIVO_ALTA_EN_LINEA)
            except ErroresValidacion as e:
                errores = e.errores
            except ErrorIntegridad as e:
                errores = {e.campo or "_general": e.mensaje}
        if errores:
            alta = contexto_alta(self.spec, columnas, args, textos, errores)
            return render_template("crud/partials/_fila_alta.html", alta=alta), 422

        self._avisar(nuevo)
        grilla = contexto_grilla(self.spec, columnas, args)
        repetidos = {c.nombre: textos[c.nombre] for c in self.spec.alta_en_linea if c.repetir}
        alta = contexto_alta(self.spec, columnas, args, repetidos, foco=True)
        # Las acciones de la pestaña pueden cambiar (ej: «Enviar a Compras» aparece
        # con la primera línea en borrador): se reemplazan fuera de banda.
        botones = {
            "id": f"botones-{self.spec.name}",
            "acciones": acciones_visibles(spec_padre, registro_padre, lambda a: a.seccion == self.spec.name,
                                          {"seccion": self.spec.name}),
            "boton_url": url_for(endpoint(self.spec.name, "crear"), **args),
            "boton_texto": "Crear " + self.spec.label_singular,
        }
        return render_template("crud/partials/_alta_creada.html", grilla=grilla,
                               item=item_fila(self.spec, nuevo, columnas), alta=alta, botones=botones)

    def _dato_de_celda(self, campo, f, texto) -> dict:
        """
        {campo: valor} de lo escrito en la celda, por el mismo camino que el
        formulario (coercion + validar_existencia). Una FK con búsqueda llega como
        texto («RE504836 — Filtro de aceite», el código o el comienzo).
        """
        entrada = {campo: texto}
        if f.tipo == "fk" and texto.strip() and fk.usa_busqueda(f):
            entrada[campo] = str(buscar_por_texto(f, campo, texto))
        datos = coercion.datos_de_entrada(self.spec.model, {campo: f}, entrada, parcial=True)
        if f.excluir_en_linea and datos.get(campo) in f.excluir_en_linea:
            opcion = next(o["label"] for o in f.options if o["value"] == datos[campo])
            raise ErroresValidacion({campo: f"«{opcion}» no se elige en la grilla."})
        fk.validar_existencia(self.fields, datos)
        # Los campos de los que depende y que no se editan en la grilla se recalculan
        # (ej: la unidad de la línea, al cambiar el material): el servicio los
        # completa a partir del valor nuevo.
        if datos.get(campo) is not None:
            for padre in f.depende_de:
                if padre not in self.spec.edicion_en_linea and not self.fields[padre].solo_lectura:
                    datos[padre] = None
        return datos

    def _mensaje_celda(self, campo, errores: dict) -> str:
        """
        El error se muestra en la celda editada. Si una regla lo marcó en otro campo
        (ej: falta el motivo), va con la etiqueta de ese campo.
        """
        if campo in errores:
            return errores[campo]
        partes = []
        for otro, texto in errores.items():
            label = self.fields[otro].label if otro in self.fields else None
            partes.append(texto if not label or texto.startswith(label) else f"{label}: {texto}")
        return " ".join(partes)


# ---------------------------------------------------------------------------
# Filas y celdas de la grilla (las usan el listado, la pestaña del padre y las
# rutas de celda: una fila se arma igual en los tres lugares)
# ---------------------------------------------------------------------------

def contexto_grilla(spec: EntitySpec, columnas, args_fila: dict) -> dict:
    """
    Lo que crud/partials/_fila.html necesita además del registro. `args_fila`: el
    padre desde el que se llegó ({"pedido_id": 3}), para los enlaces y las celdas.
    """
    return {
        "columnas": list(columnas),
        "campos": spec.fields,
        "pk": spec.pk,
        "entidad": spec.name,
        "endpoint_base": f"{BLUEPRINT}.{spec.name}",
        "args_fila": args_fila,
        # {columna: campo que se edita en ella} (casi siempre, el mismo).
        "editables": {spec.columna_en_linea.get(c, c): c for c in spec.edicion_en_linea},
        "con_eliminar": spec.eliminable_si is not None,
    }


def contexto_alta(spec: EntitySpec, columnas, args_fila: dict, textos: dict | None = None,
                  errores: dict | None = None, foco: bool = False) -> dict:
    """
    Lo que crud/partials/_fila_alta.html necesita: una celda por cada columna de la
    grilla (las de alta con su colspan), con lo escrito y su error.

    textos   lo escrito en cada celda (después de un error, o lo que se repite).
    errores  {campo: mensaje} del intérprete o del servicio: cada uno va en la
             celda que produce ese campo; los que no son de ninguna, junto al botón.
    foco     True: el foco va a la primera celda con error o, si no hay, a la primera.
    """
    textos, errores = textos or {}, dict(errores or {})
    por_campo = {}
    for c in spec.alta_en_linea:
        for campo in (c.nombre, *c.interprete.campos):
            por_campo.setdefault(campo, c.nombre)
    mensajes: dict[str, list[str]] = {}
    for campo, texto in errores.items():
        destino = por_campo.get(campo)
        if destino is None:  # de un campo que no es de ninguna celda: junto al botón, con su etiqueta
            label = spec.fields[campo].label if campo in spec.fields else None
            texto = texto if not label or texto.startswith(label) else f"{label}: {texto}"
            destino = "_general"
        mensajes.setdefault(destino, []).append(texto)

    celdas_por_columna = {c.columnas[0]: c for c in spec.alta_en_linea}
    cubiertas = {col for c in spec.alta_en_linea for col in c.columnas[1:]}
    layout = []
    for col in columnas:
        if col in cubiertas:
            continue
        c = celdas_por_columna.get(col)
        if c is None:
            layout.append(None)
            continue
        control = c.interprete.control(spec)
        layout.append({
            "nombre": c.nombre, "label": c.label, "colspan": len(c.columnas), "control": control,
            "opciones": c.interprete.opciones(spec) if control in ("lista", "select") else [],
            "id_lista": f"lista-alta-{spec.name}-{c.nombre}",
            "valor": textos.get(c.nombre, ""),
            "error": " ".join(mensajes.get(c.nombre, [])) or None,
        })
    con_error = [x["nombre"] for x in layout if x and x["error"]]
    primera = next(x["nombre"] for x in layout if x)
    return {
        "entidad": spec.name,
        "id": f"alta-{spec.name}",
        "form_id": f"form-alta-{spec.name}",
        "url": url_for(endpoint(spec.name, "alta_en_linea"), **args_fila),
        "layout": layout,
        "error": " ".join(mensajes.get("_general", [])) or None,
        "foco": (con_error[0] if con_error else primera) if (foco or errores) else None,
    }


def item_fila(spec: EntitySpec, registro, columnas) -> dict:
    """
    Valores de una fila: las columnas pedidas, la PK y la etiqueta (y color) de
    cada FK. Además, lo que depende del registro: los campos congelados (con el
    porqué), si se puede eliminar y las acciones de la fila.
    """
    item = {c: getattr(registro, c, None) for c in columnas}
    item[spec.pk] = getattr(registro, spec.pk)
    item["_congelados"] = {}
    for campo, regla in spec.editable_si.items():
        if campo in spec.edicion_en_linea:
            porque = permitido(regla(registro))
            if porque is not None:
                item["_congelados"][campo] = porque
    item["_eliminable"] = spec.eliminable_si is None or permitido(spec.eliminable_si(registro)) is None
    item["_acciones"] = [a for a in spec.acciones
                         if a.en_fila and (a.visible is None or a.visible(registro))]
    for c in columnas:
        f = spec.fields.get(c)
        if f is None or f.tipo != "fk":
            continue
        obj = fk.destino(registro, c, f)
        item[f"{c}_label"] = fk.etiqueta(obj, f) if obj is not None else None
        if obj is not None and f.es_estado:
            item[f"{c}_color"] = getattr(obj, "color_badge", None)
    return item


def control_celda(f) -> tuple[str, list]:
    """
    (control, opciones) de la celda en edición: "busqueda" (FK con muchos registros:
    <input list>), "select" (FK con pocos u opciones fijas), "datalist" (texto con
    sugerencias), "number", "date" o "text".
    """
    if f.tipo == "fk":
        opciones = fk.opciones(f)
        if fk.usa_busqueda(f):
            return "busqueda", [o["label"] for o in opciones]
        return "select", opciones
    if f.tipo == "select":
        return "select", [o for o in f.options if o["value"] not in f.excluir_en_linea]
    if f.tipo == "datalist":
        return "datalist", fk.sugerencias_de({f.name: f}).get(f.name, [])
    if f.tipo in ("number", "date"):
        return f.tipo, []
    return "text", []


def texto_celda(registro, campo, f, control) -> str:
    """Valor actual como va en el control (en una búsqueda, la etiqueta del registro)."""
    if control == "busqueda":
        obj = fk.destino(registro, campo, f)
        return fk.etiqueta(obj, f) if obj is not None else ""
    valor = coercion.valor_para_formulario(f, getattr(registro, campo))
    return "" if valor is None else str(valor)


def acciones_visibles(spec: EntitySpec, registro, condicion, args) -> list[dict]:
    """Botones de las acciones de un registro que cumplen `condicion` (y su `visible`)."""
    id_ = getattr(registro, spec.pk)
    return [
        {"label": a.label, "confirmar": a.confirmar, "con_formulario": bool(a.campos),
         "url": url_for(endpoint(spec.name, "accion"), id=id_, accion=a.id, **args)}
        for a in spec.acciones
        if condicion(a) and (a.visible is None or a.visible(registro))
    ]


def registrar_web(app, registry: dict[str, EntitySpec]):
    """Genera y registra las pantallas de todas las entidades del registry."""
    from flask import Blueprint

    bp = Blueprint(BLUEPRINT, __name__)
    for spec in registry.values():
        VistasEntidad(spec, registry).registrar(bp)
    app.register_blueprint(bp)
    return bp
