from flask import request, render_template, redirect, url_for
from app.core.db import db
from app.audit.registrar import registrar_cambio
from app.crud.metamodelos import ENTIDADES
import os
import uuid


class CRUDResource:
    def __init__(self, name, config, blueprint):
        self.name = name
        self.config = config
        self.model = config["model"]
        # pk puede venir del metamodelo o inferirse desde el mapper
        self.pk = config.get("pk") or self.model.__mapper__.primary_key[0].name
        self.fields = config["fields"]
        self.listado_cfg = config["listado"]
        self.filtros = config["filtros"]
        self.audit = config.get("auditoria", {"enabled": False, "ignore_fields": []})
        self.bp = blueprint

        self.registrar_rutas()

    # ------------------------------
    # RUTAS
    # ------------------------------

    def registrar_rutas(self):
        base = f"/{self.name}"

        self.bp.add_url_rule(base, f"{self.name}_listar", self.listar)
        self.bp.add_url_rule(
            f"{base}/crear",
            f"{self.name}_crear",
            self.crear,
            methods=["GET", "POST"],
        )
        self.bp.add_url_rule(
            f"{base}/<int:id>/editar",
            f"{self.name}_editar",
            self.editar,
            methods=["GET", "POST"],
        )
        self.bp.add_url_rule(
            f"{base}/<int:id>/confirmar_eliminar",
            f"{self.name}_confirmar_eliminar",
            self.confirmar_eliminar,
            methods=["GET", "POST"],
        )
        self.bp.add_url_rule(f"{base}/<int:id>", f"{self.name}_detalle", self.detalle)

    # ------------------------------
    # HELPERS
    # ------------------------------

    def _infer_relacion_fk(self, campo_fk, cfg):
        # Si el metamodelo ya la define, usarla
        if "relacion" in cfg:
            return cfg["relacion"]

        # Intentar inferirla desde el mapper de SQLAlchemy
        for rel in self.model.__mapper__.relationships:
            for col in rel.local_columns:
                if col.name == campo_fk:
                    return rel.key

        # Fallback: None
        return None

    def _fk_label(self, obj, cfg):
        # Si el metamodelo define fk_label, usarlo
        if "fk_label" in cfg:
            return getattr(obj, cfg["fk_label"])
        # Si el modelo tiene .label (ModelMixin), usarlo
        if hasattr(obj, "label"):
            return obj.label
        # Fallback: str(obj.pk) si existe, o str(obj)
        if hasattr(obj, "pk"):
            return str(obj.pk)
        return str(obj)

    def _expandir_fk(self, data_dict, registro_obj):
        """
        Agrega al dict los nombres de FK (ej: estado = 'Activo')
        para que el historial compare textos en lugar de IDs.
        """
        for campo, cfg in self.fields.items():
            if cfg["tipo"] == "fk":
                relacion = self._infer_relacion_fk(campo, cfg)
                obj = getattr(registro_obj, relacion) if relacion else None
                if obj:
                    nombre_campo = campo.replace("_id", "")
                    data_dict[nombre_campo] = self._fk_label(obj, cfg)

                    if cfg.get("es_estado"):
                        data_dict[nombre_campo + "_color"] = getattr(
                            obj, "color_badge", None
                        )

        return data_dict

    # ------------------------------
    # LISTAR
    # ------------------------------

    def listar(self):
        campo = request.args.get("campo")
        q = request.args.get("q", "")
        valor_fk = request.args.get("valor_fk")

        # ============================================================
        # LABELS DE ENTIDAD
        # ============================================================
        label_singular = self.config.get("label_singular", self.name)
        label_plural = self.config.get("label_plural", self.name)
        genero = self.config.get("genero", "m")

        # ============================================================
        # SUBENTIDAD
        # ============================================================
        es_subentidad = self.config.get("es_subentidad", False)
        padre_id = None
        fk_padre = None
        entidad_padre_endpoint = None

        if es_subentidad:
            fk_padre = self.config["fk_padre"]
            padre_id = request.args.get(fk_padre)

            entidad_padre = self.config["entidad_padre"]
            bp_padre = ENTIDADES[entidad_padre]["bp_name"]

            entidad_padre_endpoint = f"{bp_padre}.{entidad_padre}_detalle"

        # ============================================================
        # NORMALIZACIÓN DEL CAMPO DE BÚSQUEDA
        # ============================================================
        if campo is None and q == "" and valor_fk is None:
            campo = "todos"
        else:
            campo = campo or "todos"

        query = self.model.query

        # ============================================================
        # CONSTRUIR fk_data (con metadata para filtrado dinámico)
        # ============================================================
        fk_data = {}

        for campo_fk, cfg in self.fields.items():
            if cfg["tipo"] == "fk":

                # Detectar el campo padre del modelo FK (si existe)
                # Ej: Ubicacion.sector_id, Modelo.marca_id
                fk_model = cfg["fk_model"]
                fk_pk = fk_model.__mapper__.primary_key[0].name

                # Intentamos detectar automáticamente el campo padre
                posibles_padres = [
                    c.name
                    for c in fk_model.__table__.columns
                    if c.name.endswith("_id") and c.name != fk_pk
                ]

                fk_extra_field = posibles_padres[0] if posibles_padres else None

                fk_data[campo_fk] = []

                for obj in fk_model.query.all():
                    value = getattr(obj, "pk", getattr(obj, fk_pk))
                    label = self._fk_label(obj, cfg)
                    extra = getattr(obj, fk_extra_field) if fk_extra_field else None

                    fk_data[campo_fk].append(
                        {
                            "value": value,
                            "label": label,
                            "extra_value": extra,  # valor del padre (ej: marca_id = 4)
                            "extra_field": fk_extra_field,  # nombre del campo padre (ej: "marca_id")
                        }
                    )

        # ============================================================
        # FILTROS
        # ============================================================

        # Filtro por texto
        if q:
            if campo == "todos":
                filtros = [
                    getattr(self.model, f).ilike(f"%{q}%")
                    for f in self.filtros["campos"]
                ]
                query = query.filter(db.or_(*filtros))
            else:
                query = query.filter(getattr(self.model, campo).ilike(f"%{q}%"))

        # Filtro por FK
        if valor_fk and campo in fk_data:
            query = query.filter(getattr(self.model, campo) == valor_fk)

        # Filtro obligatorio si es subentidad
        if es_subentidad and padre_id:
            query = query.filter(getattr(self.model, fk_padre) == padre_id)

        registros = query.all()

        # ============================================================
        # LABELS FK POR REGISTRO
        # ============================================================
        fk_labels_por_registro = []

        for r in registros:
            labels = {}
            for campo_fk, cfg in self.fields.items():
                if cfg["tipo"] == "fk":
                    relacion = self._infer_relacion_fk(campo_fk, cfg)
                    obj = getattr(r, relacion) if relacion else None
                    if not obj:
                        labels[campo_fk] = None
                    else:
                        if cfg.get("es_estado"):
                            labels[campo_fk] = {
                                "label": self._fk_label(obj, cfg),
                                "color": getattr(obj, "color_badge", None),
                            }
                        else:
                            labels[campo_fk] = self._fk_label(obj, cfg)
            fk_labels_por_registro.append(dict(labels))

        # ============================================================
        # Convertir registros a dicts para el listado
        # ============================================================
        registros_modelo = query.all()
        registros = []
        for i, r in enumerate(registros_modelo):
            d = r.to_dict()

            d_filtrado = {}

            for col in self.listado_cfg["columns"]:
                # Si la columna es FK → usar el label
                if col in fk_labels_por_registro[i]:
                    d_filtrado[col] = fk_labels_por_registro[i][col]
                else:
                    d_filtrado[col] = d.get(col)

            # Siempre incluir el PK
            d_filtrado[self.pk] = d.get(self.pk)

            registros.append(d_filtrado)

        # ============================================================
        # PLANTILLA SEGÚN TIPO
        # ============================================================
        template_listado = self.config.get(
            "template_listado",
            (
                "crud/listado_subentidad.html"
                if es_subentidad
                else "crud/listado_entidad.html"
            ),
        )

        # ============================================================
        # RENDER FINAL
        # ============================================================
        return render_template(
            template_listado,
            pk=self.pk,
            label_singular=label_singular,
            label_plural=label_plural,
            genero=genero,
            nombre_entidad=label_plural.capitalize(),
            endpoint_base=f"{self.config['bp_name']}.{self.name}",
            registros=registros,  # ← AHORA SON DICTS
            columns=self.listado_cfg["columns"],
            fields=self.fields,
            filtros=self.filtros,
            campo_actual=campo,
            valor_fk=valor_fk,
            fk_data=fk_data,
            fk_labels=fk_labels_por_registro,
            q=q,
            es_subentidad=es_subentidad,
            padre_id=padre_id,
            fk_padre=fk_padre,
            entidad_padre_endpoint=entidad_padre_endpoint,
        )

    # ------------------------------
    # CREAR
    # ------------------------------

    def crear(self):
        from app.audit.registrar import registrar_cambio
        import uuid
        import os
        from werkzeug.utils import secure_filename

        # ============================================================
        # LABELS DE ENTIDAD
        # ============================================================
        label_singular = self.config.get("label_singular", self.name)
        label_plural = self.config.get("label_plural", self.name)
        genero = self.config.get("genero", "m")

        # ============================================================
        # SIEMPRE construir fk_data (GET y POST)
        # ============================================================
        fk_data = {}

        for campo_fk, cfg in self.fields.items():
            if cfg["tipo"] == "fk":

                fk_model = cfg["fk_model"]
                fk_pk = fk_model.__mapper__.primary_key[0].name

                posibles_padres = [
                    c.name
                    for c in fk_model.__table__.columns
                    if c.name.endswith("_id") and c.name != fk_pk
                ]

                fk_extra_field = posibles_padres[0] if posibles_padres else None

                fk_data[campo_fk] = []

                for obj in fk_model.query.all():
                    value = getattr(obj, "pk", getattr(obj, fk_pk))
                    label = self._fk_label(obj, cfg)
                    extra = getattr(obj, fk_extra_field) if fk_extra_field else None

                    fk_data[campo_fk].append(
                        {
                            "value": value,
                            "label": label,
                            "extra_value": extra,  # valor del padre (ej: marca_id = 4)
                            "extra_field": fk_extra_field,  # nombre del campo padre (ej: "marca_id")
                        }
                    )

        # ============================================================
        # POST → procesar formulario
        # ============================================================
        if request.method == "POST":

            datos = {}
            for campo, cfg in self.fields.items():
                if cfg.get("virtual"):
                    continue
                if cfg["tipo"] != "file":
                    datos[campo] = request.form.get(campo)

            # Manejo de archivos
            for campo, cfg in self.fields.items():
                if cfg.get("virtual"):
                    continue
                if cfg["tipo"] == "file":
                    archivo = request.files.get(campo)
                    if archivo and archivo.filename:
                        extension = os.path.splitext(archivo.filename)[1]
                        filename = f"{uuid.uuid4()}{extension}"

                        subcarpeta = cfg.get("subcarpeta", "")
                        if subcarpeta:
                            upload_folder = (
                                f"app/static/uploads/{self.name}/{subcarpeta}"
                            )
                            public_path = (
                                f"/static/uploads/{self.name}/{subcarpeta}/{filename}"
                            )
                        else:
                            upload_folder = f"app/static/uploads/{self.name}"
                            public_path = f"/static/uploads/{self.name}/{filename}"

                        os.makedirs(upload_folder, exist_ok=True)
                        archivo.save(os.path.join(upload_folder, filename))
                        datos[campo] = public_path

            # Subentidad → completar FK del padre
            if self.config.get("es_subentidad"):
                fk_padre = self.config["fk_padre"]
                padre_id = request.args.get(fk_padre)
                if padre_id:
                    datos[fk_padre] = padre_id

            motivo = request.form.get("motivo_operacion")

            nuevo = self.model(**datos)
            db.session.add(nuevo)
            db.session.flush()
            db.session.refresh(nuevo)

            if self.audit["enabled"]:
                registrar_cambio(
                    tabla=self.name,
                    registro_uuid=nuevo.uuid,
                    tipo="INSERT",
                    estado_anterior=None,
                    estado_actual=self._expandir_fk(nuevo.to_dict(), nuevo),
                    motivo_operacion=motivo,
                    registro_id=getattr(nuevo, self.pk),
                    ignore_fields=self.audit.get("ignore_fields", []),
                )

            db.session.commit()

            # ============================================================
            # REDIRECCIÓN DESPUÉS DE CREAR
            # ============================================================

            bp_name = self.config.get("bp_name", self.bp.name)

            if self.config.get("es_subentidad"):
                fk_padre = self.config["fk_padre"]
                return redirect(
                    url_for(
                        f"{ENTIDADES[self.config['entidad_padre']]['bp_name']}."
                        f"{self.config['entidad_padre']}_detalle",
                        id=datos[fk_padre],
                    )
                )
            else:
                return redirect(url_for(f"{bp_name}.{self.name}_listar"))

        # ============================================================
        # GET → mostrar formulario
        # ============================================================
        es_subentidad = self.config.get("es_subentidad", False)
        entidad_padre_endpoint = None
        padre_id = (
            request.args.get(self.config.get("fk_padre")) if es_subentidad else None
        )

        if es_subentidad:
            entidad_padre = self.config["entidad_padre"]
            entidad_padre_endpoint = (
                f"{ENTIDADES[entidad_padre]['bp_name']}.{entidad_padre}_detalle"
            )

        return render_template(
            "crud/form.html",
            label_singular=label_singular,
            label_plural=label_plural,
            genero=genero,
            nombre_entidad=label_singular.capitalize(),
            endpoint_base=f"{self.bp.name}.{self.name}",
            modelo={},
            tipo_operacion="INSERT",
            fields=self.fields,
            pk=self.pk,
            es_subentidad=es_subentidad,
            padre_id=padre_id,
            entidad_padre_endpoint=entidad_padre_endpoint,
            entidad_padre=self.config.get("entidad_padre"),
            fk_data=fk_data,  # ⭐ AHORA SÍ EXISTE EN GET Y POST
        )

    # ------------------------------
    # EDITAR
    # ------------------------------

    def editar(self, id):
        from app.audit.registrar import registrar_cambio
        import uuid
        import os

        label_singular = self.config.get("label_singular", self.name)
        label_plural = self.config.get("label_plural", self.name)
        genero = self.config.get("genero", "m")

        registro = self.model.query.get_or_404(id)

        if request.method == "POST":
            motivo = request.form.get("motivo_operacion")
            estado_anterior = self._expandir_fk(registro.to_dict(), registro)

            # 1. Actualizar campos normales
            for campo in self.fields.keys():
                if self.fields[campo]["tipo"] != "file":
                    setattr(registro, campo, request.form.get(campo))

            # 2. Manejo de archivos
            for campo, cfg in self.fields.items():
                if cfg["tipo"] == "file":
                    archivo = request.files.get(campo)

                    if archivo and archivo.filename:
                        extension = os.path.splitext(archivo.filename)[1]
                        filename = f"{uuid.uuid4()}{extension}"

                        subcarpeta = cfg.get("subcarpeta", "")
                        if subcarpeta:
                            upload_folder = (
                                f"app/static/uploads/{self.name}/{subcarpeta}"
                            )
                            public_path = (
                                f"/static/uploads/{self.name}/{subcarpeta}/{filename}"
                            )
                        else:
                            upload_folder = f"app/static/uploads/{self.name}"
                            public_path = f"/static/uploads/{self.name}/{filename}"

                        os.makedirs(upload_folder, exist_ok=True)
                        archivo.save(os.path.join(upload_folder, filename))

                        setattr(registro, campo, public_path)

            db.session.flush()
            db.session.refresh(registro)

            if self.audit["enabled"]:
                registrar_cambio(
                    tabla=self.name,
                    registro_uuid=registro.uuid,
                    tipo="UPDATE",
                    estado_anterior=estado_anterior,
                    estado_actual=self._expandir_fk(registro.to_dict(), registro),
                    motivo_operacion=motivo,
                    registro_id=id,
                    ignore_fields=self.audit.get("ignore_fields", []),
                )

            db.session.commit()

            # ============================================================
            # REDIRECCIÓN DESPUÉS DE EDITAR
            # ============================================================

            bp_name = self.config.get("bp_name", self.bp.name)

            if self.config.get("es_subentidad"):
                fk_padre = self.config["fk_padre"]
                padre_id = getattr(registro, fk_padre)

                return redirect(
                    url_for(
                        f"{ENTIDADES[self.config['entidad_padre']]['bp_name']}."
                        f"{self.config['entidad_padre']}_detalle",
                        id=padre_id,
                    )
                )
            else:
                return redirect(url_for(f"{bp_name}.{self.name}_listar"))

        # ============================================================
        # CONSTRUIR fk_data (igual que en listar)
        # ============================================================
        fk_data = {}

        for campo_fk, cfg in self.fields.items():
            if cfg["tipo"] == "fk":

                fk_model = cfg["fk_model"]
                fk_pk = fk_model.__mapper__.primary_key[0].name

                posibles_padres = [
                    c.name
                    for c in fk_model.__table__.columns
                    if c.name.endswith("_id") and c.name != fk_pk
                ]

                fk_extra_field = posibles_padres[0] if posibles_padres else None

                fk_data[campo_fk] = []

                for obj in fk_model.query.all():
                    value = getattr(obj, "pk", getattr(obj, fk_pk))
                    label = self._fk_label(obj, cfg)
                    extra = getattr(obj, fk_extra_field) if fk_extra_field else None

                    fk_data[campo_fk].append(
                        {
                            "value": value,
                            "label": label,
                            "extra_value": extra,  # valor del padre (ej: marca_id = 4)
                            "extra_field": fk_extra_field,  # nombre del campo padre (ej: "marca_id")
                        }
                    )

        es_subentidad = self.config.get("es_subentidad", False)
        entidad_padre_endpoint = None
        padre_id = (
            getattr(registro, self.config.get("fk_padre")) if es_subentidad else None
        )

        if es_subentidad:
            entidad_padre = self.config["entidad_padre"]
            entidad_padre_endpoint = (
                f"{ENTIDADES[entidad_padre]['bp_name']}.{entidad_padre}_detalle"
            )

        return render_template(
            "crud/form.html",
            label_singular=label_singular,
            label_plural=label_plural,
            genero=genero,
            nombre_entidad=label_singular.capitalize(),
            endpoint_base=f"{self.bp.name}.{self.name}",
            modelo=registro.to_dict(),
            tipo_operacion="UPDATE",
            fields=self.fields,
            pk=self.pk,
            es_subentidad=es_subentidad,
            padre_id=padre_id,
            entidad_padre_endpoint=entidad_padre_endpoint,
            fk_data=fk_data,
        )

    # ------------------------------
    # ELIMINAR
    # ------------------------------

    def confirmar_eliminar(self, id):
        from app.audit.registrar import registrar_cambio

        # ============================================================
        # LABELS DE ENTIDAD (nuevo)
        # ============================================================
        label_singular = self.config.get("label_singular", self.name)
        label_plural = self.config.get("label_plural", self.name)
        genero = self.config.get("genero", "m")

        registro = self.model.query.get_or_404(id)

        # ============================================================
        # Obtener padre_id ANTES del POST (para GET y POST)
        # ============================================================
        padre_id = None
        fk_padre = None
        entidad_padre_endpoint = None

        if self.config.get("es_subentidad"):
            fk_padre = self.config["fk_padre"]
            padre_id = getattr(registro, fk_padre)
            bp_padre = ENTIDADES[self.config["entidad_padre"]]["bp_name"]
            entidad_padre_endpoint = (
                f"{bp_padre}.{self.config['entidad_padre']}_detalle"
            )

        if request.method == "POST":
            motivo = request.form.get("motivo_operacion")
            estado_anterior = self._expandir_fk(registro.to_dict(), registro)

            db.session.delete(registro)

            if self.audit["enabled"]:
                registrar_cambio(
                    tabla=self.name,
                    registro_uuid=registro.uuid,
                    tipo="DELETE",
                    estado_anterior=estado_anterior,
                    estado_actual=None,
                    motivo_operacion=motivo,
                    registro_id=id,
                    ignore_fields=self.audit.get("ignore_fields", []),
                )

            db.session.commit()

            # Navegación contextual
            if self.config.get("es_subentidad"):
                return redirect(url_for(entidad_padre_endpoint, id=padre_id))
            else:
                bp_name = self.config.get("bp_name", self.bp.name)
                return redirect(url_for(f"{bp_name}.{self.name}_listar"))

        # ============================================================
        # Preparar FK labels (tu código original)
        # ============================================================
        fk_labels = {}
        for campo, cfg in self.fields.items():
            if cfg["tipo"] == "fk":
                relacion = self._infer_relacion_fk(campo, cfg)
                obj = getattr(registro, relacion) if relacion else None
                if not obj:
                    fk_labels[campo] = None
                else:
                    if cfg.get("es_estado"):
                        fk_labels[campo] = {
                            "label": self._fk_label(obj, cfg),
                            "color": getattr(obj, "color_badge", None),
                        }
                    else:
                        fk_labels[campo] = self._fk_label(obj, cfg)

        return render_template(
            "crud/confirmar_eliminar.html",
            # ========================================================
            # NUEVO: labels correctos
            # ========================================================
            label_singular=label_singular,
            label_plural=label_plural,
            genero=genero,
            nombre_entidad=label_singular.capitalize(),
            endpoint_base=f"{self.bp.name}.{self.name}",
            modelo=registro.to_dict(),
            fields=self.fields,
            fk_labels=fk_labels,
            pk=self.pk,
            # Variables necesarias para subentidades
            es_subentidad=self.config.get("es_subentidad", False),
            padre_id=padre_id,
            fk_padre=fk_padre,
            entidad_padre_endpoint=entidad_padre_endpoint,
        )

    # ------------------------------
    # DETALLE
    # ------------------------------

    def detalle(self, id):
        registro = self.model.query.get_or_404(id)

        # ============================================================
        # LABELS DE ENTIDAD
        # ============================================================
        label_singular = self.config.get("label_singular", self.name)
        label_plural = self.config.get("label_plural", self.name)
        genero = self.config.get("genero", "m")

        # ============================================================
        # 1. Convertir a dict y expandir FK labels
        # ============================================================
        modelo = registro.to_dict()

        for campo, cfg in self.fields.items():
            if cfg["tipo"] == "fk":
                relacion = self._infer_relacion_fk(campo, cfg)
                obj = getattr(registro, relacion) if relacion else None

                if obj:
                    modelo[f"{campo}_label"] = self._fk_label(obj, cfg)
                    if cfg.get("es_estado"):
                        modelo[f"{campo}_color"] = getattr(obj, "color_badge", None)
                else:
                    modelo[f"{campo}_label"] = None

        # ============================================================
        # 2. HISTORIAL
        # ============================================================
        if self.config.get("es_subentidad"):
            historial = []
            pagination = None
        else:
            page = request.args.get("page", 1, type=int)
            historial, pagination = registro.obtener_historial(page)

        # ============================================================
        # 3. PLANTILLA SEGÚN TIPO
        # ============================================================
        template = self.config.get(
            "template_detalle",
            (
                "crud/detalle_subentidad.html"
                if self.config.get("es_subentidad")
                else "crud/detalle_entidad.html"
            ),
        )

        # ============================================================
        # 4. SI ES SUBENTIDAD → obtener ID del padre
        # ============================================================
        padre_id = None
        if self.config.get("es_subentidad"):
            fk_padre = self.config["fk_padre"]
            padre_id = getattr(registro, fk_padre)

        # ============================================================
        # 5. CARGAR SUBENTIDADES (para entidades y subentidades)
        # ============================================================
        subentidades = []

        for sub in self.config.get("subentidades", []):
            sub_cfg = ENTIDADES[sub["entidad"]]
            ModelSub = sub_cfg["model"]
            fk = sub["fk"]

            filtro_valor = id if not self.config.get("es_subentidad") else padre_id

            objetos = ModelSub.query.filter_by(**{fk: filtro_valor}).all()

            items = []
            for obj in objetos:
                d = obj.to_dict()

                for campo, cfg in sub_cfg["fields"].items():
                    if cfg["tipo"] == "fk":
                        relacion = self._infer_relacion_fk(campo, cfg)
                        fk_obj = getattr(obj, relacion) if relacion else None

                        if fk_obj:
                            d[f"{campo}_label"] = self._fk_label(fk_obj, cfg)
                            if cfg.get("es_estado"):
                                d[f"{campo}_color"] = getattr(
                                    fk_obj, "color_badge", None
                                )
                        else:
                            d[f"{campo}_label"] = None

                items.append(d)

            subentidades.append(
                {
                    "label": sub_cfg.get("label_plural", sub["label"]).capitalize(),
                    "label_singular": sub_cfg.get("label_singular", sub["entidad"]),
                    "label_plural": sub_cfg.get("label_plural", sub["label"]),
                    "template_listado": sub["template_listado"],
                    "items": items,
                    "entidad": sub["entidad"],
                    "fields": sub_cfg["fields"],
                    "pk": sub_cfg.get("pk")
                    or sub_cfg["model"].__mapper__.primary_key[0].name,
                    "fk": fk,
                    "modelo_padre": registro.to_dict(),
                    "padre_id": filtro_valor,
                    "endpoint_base": f"{sub_cfg['bp_name']}.{sub['entidad']}",
                }
            )

        # ============================================================
        # 6. Construir SECCIONES (tabs)
        # ============================================================
        secciones = []
        secciones_dict = {}

        secciones.append({"id": "datos", "label": "Datos"})
        secciones_dict["datos"] = {"id": "datos", "label": "Datos", "sub": None}

        secciones.append({"id": "historial", "label": "Historial"})
        secciones_dict["historial"] = {
            "id": "historial",
            "label": "Historial",
            "sub": None,
        }

        for sub in subentidades:
            sec_id = sub["entidad"]
            sec_label = sub["label"]

            secciones.append({"id": sec_id, "label": sec_label})
            secciones_dict[sec_id] = {"id": sec_id, "label": sec_label, "sub": sub}

        seccion_activa = request.args.get("seccion", "datos")

        # ============================================================
        # 7. Render final
        # ============================================================
        return render_template(
            template,
            modelo=modelo,
            fields=self.fields,
            pk=self.pk,
            label_singular=label_singular,
            label_plural=label_plural,
            genero=genero,
            historial=historial,
            pagination=pagination,
            es_subentidad=self.config.get("es_subentidad", False),
            padre_id=padre_id,
            subentidades=subentidades,
            endpoint_base=f"{self.bp.name}.{self.name}",
            entidad_padre=self.config.get("entidad_padre"),
            entidad_padre_endpoint=(
                f"{self.bp.name}.{self.config['entidad_padre']}_detalle"
                if self.config.get("es_subentidad")
                else None
            ),
            secciones=secciones,
            secciones_dict=secciones_dict,
            seccion_activa=seccion_activa,
        )
