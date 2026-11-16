# app/crud/framework.py
"""
Vistas web CRUD generadas a partir de un metamodelo (dict de ENTIDADES).

Desde la Fase 2 esta clase solo hace lo que es propio de la web: leer el
request, elegir la plantilla y armar su contexto. Convertir datos, consultar,
guardar y auditar lo hace app/crud/core/. En la Fase 3 esta clase se reemplaza
por vistas generadas desde el registry tipado.
"""
from flask import current_app, redirect, render_template, request, url_for

from app.crud.core import coercion, dependencias, fk, repository
from app.crud.core.coercion import ErroresValidacion
from app.crud.core.files import ArchivoInvalido, guardar
from app.crud.core.service import ErrorIntegridad, RegistroEnUso, ServicioCRUD
from app.crud.metamodelos import ENTIDADES


def etiqueta_tabla(tabla, cantidad):
    """("ubicaciones", 2) → "2 ubicaciones"; usa los textos del metamodelo si existen."""
    for cfg in ENTIDADES.values():
        if cfg["model"].__tablename__ == tabla:
            texto = cfg.get("label_plural" if cantidad != 1 else "label_singular", tabla)
            return f"{cantidad} {texto}"
    nombre = tabla.replace("_", " ")
    return f"{cantidad} registro{'s' if cantidad != 1 else ''} de {nombre}"


class CRUDResource:
    def __init__(self, name, config, blueprint):
        self.name = name
        self.config = config
        self.model = config["model"]
        self.pk = config.get("pk") or self.model.__mapper__.primary_key[0].name
        self.fields = config["fields"]
        self.listado_cfg = config["listado"]
        self.filtros = config["filtros"]
        self.audit = config.get("auditoria", {"enabled": False, "ignore_fields": []})
        self.bp = blueprint
        self.servicio = ServicioCRUD(self.model, self.fields, self.audit, etiqueta_tabla)

        self.es_subentidad = config.get("es_subentidad", False)
        self.fk_padre = config.get("fk_padre")
        self.entidad_padre = config.get("entidad_padre")

        self.registrar_rutas()

    # ------------------------------------------------------------------
    # Rutas
    # ------------------------------------------------------------------

    def registrar_rutas(self):
        base = f"/{self.name}"
        n = self.name
        self.bp.add_url_rule(base, f"{n}_listar", self.listar)
        self.bp.add_url_rule(f"{base}/crear", f"{n}_crear", self.crear, methods=["GET", "POST"])
        self.bp.add_url_rule(f"{base}/<int:id>/editar", f"{n}_editar", self.editar, methods=["GET", "POST"])
        self.bp.add_url_rule(
            f"{base}/<int:id>/confirmar_eliminar", f"{n}_confirmar_eliminar",
            self.confirmar_eliminar, methods=["GET", "POST"],
        )
        self.bp.add_url_rule(f"{base}/<int:id>", f"{n}_detalle", self.detalle)

    # ------------------------------------------------------------------
    # Contexto común
    # ------------------------------------------------------------------

    @property
    def endpoint_base(self):
        # El blueprint donde realmente se registraron las rutas.
        return f"{self.bp.name}.{self.name}"

    @property
    def endpoint_padre(self):
        if not self.es_subentidad:
            return None
        bp_padre = ENTIDADES[self.entidad_padre]["bp_name"]
        return f"{bp_padre}.{self.entidad_padre}_detalle"

    def _labels(self):
        return {
            "label_singular": self.config.get("label_singular", self.name),
            "label_plural": self.config.get("label_plural", self.name),
            "genero": self.config.get("genero", "m"),
        }

    def _volver(self, padre_id):
        """Destino después de guardar: el detalle del padre o el listado."""
        if self.es_subentidad and padre_id:
            return redirect(url_for(self.endpoint_padre, id=padre_id))
        return redirect(url_for(f"{self.endpoint_base}_listar"))

    def _motivo(self):
        return request.form.get("motivo_operacion") or None

    # ------------------------------------------------------------------
    # Formulario
    # ------------------------------------------------------------------

    def _leer_formulario(self, parcial):
        """Datos del formulario convertidos y validados, incluidos los archivos."""
        datos, errores = {}, {}
        try:
            datos = coercion.datos_de_entrada(self.model, self.fields, request.form, parcial=parcial)
        except ErroresValidacion as e:
            errores.update(e.errores)

        for campo, cfg in self.fields.items():
            if cfg.get("tipo") != "file" or cfg.get("virtual"):
                continue
            archivo = request.files.get(campo)
            if archivo and archivo.filename:
                try:
                    datos[campo] = guardar(
                        archivo, current_app.static_folder, self.name, cfg.get("subcarpeta")
                    )
                except ArchivoInvalido as e:
                    errores[campo] = f"{cfg.get('label', campo)}: {e}."
            elif cfg.get("required") and not parcial:
                errores[campo] = f"{cfg.get('label', campo)} es obligatorio."

        if errores:
            raise ErroresValidacion(errores)
        return datos

    def _valores_formulario(self, registro):
        d = registro.to_dict()
        return {
            campo: coercion.valor_para_formulario(self.fields.get(campo, {}), valor)
            for campo, valor in d.items()
        }

    def _render_form(self, tipo_operacion, modelo, padre_id, errores=None, status=200):
        return render_template(
            "crud/form.html",
            **self._labels(),
            nombre_entidad=self._labels()["label_singular"].capitalize(),
            endpoint_base=self.endpoint_base,
            modelo=modelo,
            tipo_operacion=tipo_operacion,
            fields=self.fields,
            pk=self.pk,
            es_subentidad=self.es_subentidad,
            padre_id=padre_id,
            entidad_padre_endpoint=self.endpoint_padre,
            entidad_padre=self.entidad_padre,
            fk_data=fk.opciones_de(self.fields),
            errores=errores or {},
        ), status

    def _guardar(self, operacion, tipo_operacion, modelo_actual, padre_id):
        """Ejecuta `operacion(datos)`; ante un error vuelve a mostrar el formulario."""
        valores_enviados = {**modelo_actual, **request.form.to_dict()}
        try:
            datos = self._leer_formulario(parcial=(tipo_operacion == "UPDATE"))
            return operacion(datos)
        except ErroresValidacion as e:
            return self._render_form(tipo_operacion, valores_enviados, padre_id, e.errores, 400)
        except ErrorIntegridad as e:
            errores = {e.campo or "_general": e.mensaje}
            return self._render_form(tipo_operacion, valores_enviados, padre_id, errores, 400)

    # ------------------------------------------------------------------
    # LISTAR
    # ------------------------------------------------------------------

    def listar(self):
        campo = request.args.get("campo") or "todos"
        q = request.args.get("q", "")
        valor_fk = request.args.get("valor_fk")
        padre_id = self._padre_desde_url()

        query = repository.consulta_listado(
            self.model, self.fields, self.filtros["campos"],
            q=q, campo=campo, valor_fk=valor_fk,
            filtro_padre=(self.fk_padre, padre_id) if self.es_subentidad else None,
        )
        objetos = query.all()

        columnas = self.listado_cfg["columns"]
        fk_labels = [fk.etiquetas(r, self.fields) for r in objetos]
        registros = []
        for r, labels in zip(objetos, fk_labels):
            d = r.to_dict()
            fila = {c: labels[c] if c in labels else d.get(c) for c in columnas}
            fila[self.pk] = d.get(self.pk)
            registros.append(fila)

        template = self.config.get(
            "template_listado",
            "crud/listado_subentidad.html" if self.es_subentidad else "crud/listado_entidad.html",
        )
        labels = self._labels()
        return render_template(
            template,
            pk=self.pk,
            **labels,
            nombre_entidad=labels["label_plural"].capitalize(),
            endpoint_base=self.endpoint_base,
            registros=registros,
            columns=columnas,
            fields=self.fields,
            filtros=self.filtros,
            campo_actual=campo,
            valor_fk=valor_fk,
            fk_data=fk.opciones_de(self.fields),
            fk_labels=fk_labels,
            q=q,
            es_subentidad=self.es_subentidad,
            padre_id=padre_id,
            fk_padre=self.fk_padre,
            entidad_padre_endpoint=self.endpoint_padre,
        )

    # ------------------------------------------------------------------
    # CREAR
    # ------------------------------------------------------------------

    def _padre_desde_url(self):
        """ID del padre recibido en la URL (?sector_id=3), o None si no es válido."""
        if not self.es_subentidad:
            return None
        valor = request.args.get(self.fk_padre, "")
        return int(valor) if valor.isdigit() else None

    def crear(self):
        padre_id = self._padre_desde_url()

        if request.method == "GET":
            modelo = {self.fk_padre: padre_id} if padre_id else {}
            return self._render_form("INSERT", modelo, padre_id)

        def operacion(datos):
            if self.es_subentidad and padre_id and datos.get(self.fk_padre) is None:
                datos[self.fk_padre] = padre_id
            nuevo = self.servicio.crear(datos, self._motivo())
            return self._volver(getattr(nuevo, self.fk_padre) if self.es_subentidad else None)

        modelo = {self.fk_padre: padre_id} if padre_id else {}
        return self._guardar(operacion, "INSERT", modelo, padre_id)

    # ------------------------------------------------------------------
    # EDITAR
    # ------------------------------------------------------------------

    def editar(self, id):
        registro = repository.obtener_o_404(self.model, id)
        padre_id = getattr(registro, self.fk_padre) if self.es_subentidad else None

        if request.method == "GET":
            return self._render_form("UPDATE", self._valores_formulario(registro), padre_id)

        def operacion(datos):
            self.servicio.actualizar(registro, datos, self._motivo())
            return self._volver(getattr(registro, self.fk_padre) if self.es_subentidad else None)

        return self._guardar(operacion, "UPDATE", self._valores_formulario(registro), padre_id)

    # ------------------------------------------------------------------
    # ELIMINAR
    # ------------------------------------------------------------------

    def confirmar_eliminar(self, id):
        registro = repository.obtener_o_404(self.model, id)
        padre_id = getattr(registro, self.fk_padre) if self.es_subentidad else None

        error = None
        if request.method == "POST":
            try:
                self.servicio.eliminar(registro, self._motivo())
                return self._volver(padre_id)
            except ErrorIntegridad as e:
                error = e.mensaje
                registro = repository.obtener_o_404(self.model, id)
        else:
            # Avisar ANTES de confirmar si no se puede borrar.
            try:
                self.servicio.verificar_eliminable(registro)
            except RegistroEnUso as e:
                error = e.mensaje

        cascada = [etiqueta_tabla(t, n) for t, n in dependencias.resumen_cascada(registro)]

        return render_template(
            "crud/confirmar_eliminar.html",
            **self._labels(),
            nombre_entidad=self._labels()["label_singular"].capitalize(),
            endpoint_base=self.endpoint_base,
            modelo=registro.to_dict(),
            fields=self.fields,
            fk_labels=fk.etiquetas(registro, self.fields),
            pk=self.pk,
            es_subentidad=self.es_subentidad,
            padre_id=padre_id,
            fk_padre=self.fk_padre,
            entidad_padre_endpoint=self.endpoint_padre,
            error=error,
            cascada=cascada,
        ), (409 if error and request.method == "POST" else 200)

    # ------------------------------------------------------------------
    # DETALLE
    # ------------------------------------------------------------------

    def detalle(self, id):
        registro = repository.obtener_o_404(self.model, id)
        modelo = fk.agregar_etiquetas(registro.to_dict(), registro, self.fields)
        padre_id = getattr(registro, self.fk_padre) if self.es_subentidad else None

        # Historial de auditoría
        if self.es_subentidad or not hasattr(registro, "obtener_historial"):
            historial, pagination = [], None
        else:
            historial, pagination = registro.obtener_historial(request.args.get("page", 1, type=int))

        # Subentidades (pestañas)
        subentidades = []
        filtro_valor = padre_id if self.es_subentidad else id
        for sub in self.config.get("subentidades", []):
            sub_cfg = ENTIDADES[sub["entidad"]]
            objetos = sub_cfg["model"].query.filter_by(**{sub["fk"]: filtro_valor}).all()
            subentidades.append({
                "label": sub_cfg.get("label_plural", sub["label"]).capitalize(),
                "label_singular": sub_cfg.get("label_singular", sub["entidad"]),
                "label_plural": sub_cfg.get("label_plural", sub["label"]),
                "template_listado": sub["template_listado"],
                "items": [fk.agregar_etiquetas(o.to_dict(), o, sub_cfg["fields"]) for o in objetos],
                "entidad": sub["entidad"],
                "fields": sub_cfg["fields"],
                "pk": sub_cfg.get("pk") or sub_cfg["model"].__mapper__.primary_key[0].name,
                "fk": sub["fk"],
                "modelo_padre": registro.to_dict(),
                "padre_id": filtro_valor,
                "endpoint_base": f"{sub_cfg['bp_name']}.{sub['entidad']}",
            })

        secciones = [{"id": "datos", "label": "Datos"}, {"id": "historial", "label": "Historial"}]
        secciones_dict = {s["id"]: {**s, "sub": None} for s in secciones}
        for sub in subentidades:
            secciones.append({"id": sub["entidad"], "label": sub["label"]})
            secciones_dict[sub["entidad"]] = {"id": sub["entidad"], "label": sub["label"], "sub": sub}

        template = self.config.get(
            "template_detalle",
            "crud/detalle_subentidad.html" if self.es_subentidad else "crud/detalle_entidad.html",
        )
        return render_template(
            template,
            modelo=modelo,
            fields=self.fields,
            pk=self.pk,
            **self._labels(),
            historial=historial,
            pagination=pagination,
            es_subentidad=self.es_subentidad,
            padre_id=padre_id,
            fk_padre=self.fk_padre,
            subentidades=subentidades,
            endpoint_base=self.endpoint_base,
            entidad_padre=self.entidad_padre,
            entidad_padre_endpoint=self.endpoint_padre,
            secciones=secciones,
            secciones_dict=secciones_dict,
            seccion_activa=request.args.get("seccion", "datos"),
        )
