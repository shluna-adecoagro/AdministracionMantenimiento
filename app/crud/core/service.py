# app/crud/core/service.py
"""
Escritura: alta, modificación y baja de registros, con auditoría.

Cada operación es UNA transacción: el cambio y su registro de auditoría se
guardan juntos o no se guarda nada. Los errores de la base (valor duplicado,
dato obligatorio, registro en uso) se traducen a mensajes legibles.

Lo usan la interfaz web y (desde la Fase 4) la API, así que las reglas de
guardado se escriben una sola vez.
"""
from __future__ import annotations

import re

from sqlalchemy import inspect as sa_inspect
from sqlalchemy.exc import IntegrityError

from app.audit.registrar import registrar_cambio
from app.core.db import db
from app.crud.core import dependencias, fk
from app.crud.core.coercion import ErroresValidacion
from app.crud.core.repository import valores


class ErrorIntegridad(Exception):
    """La base rechazó la operación. `campo` es None si no se pudo identificar."""

    def __init__(self, mensaje: str, campo: str | None = None):
        self.mensaje = mensaje
        self.campo = campo
        super().__init__(mensaje)


class RegistroEnUso(ErrorIntegridad):
    """No se puede borrar: otros registros lo usan. `bloqueantes` = [(tabla, cantidad)]."""

    def __init__(self, mensaje: str, bloqueantes: list[tuple[str, int]]):
        super().__init__(mensaje)
        self.bloqueantes = bloqueantes


def _etiqueta_por_defecto(tabla: str, cantidad: int) -> str:
    return f"{cantidad} registro{'s' if cantidad != 1 else ''} de {tabla.replace('_', ' ')}"


def _enumerar(partes: list[str]) -> str:
    return partes[0] if len(partes) == 1 else ", ".join(partes[:-1]) + " y " + partes[-1]


# Patrones de los mensajes de SQLite y MariaDB/MySQL.
_UNICO = (
    re.compile(r"UNIQUE constraint failed: (?:\w+\.)?(\w+)"),          # SQLite
    re.compile(r"Duplicate entry .* for key '(?:\w+\.)?(\w+)'"),        # MariaDB
)
_NULO = (
    re.compile(r"NOT NULL constraint failed: (?:\w+\.)?(\w+)"),
    re.compile(r"Column '(\w+)' cannot be null"),
)
_FK_EN_USO = ("FOREIGN KEY constraint failed", "Cannot delete or update a parent row")
_FK_INVALIDA = ("FOREIGN KEY constraint failed", "Cannot add or update a child row")


def _buscar(patrones, texto):
    for p in patrones:
        m = p.search(texto)
        if m:
            return m.group(1)
    return None


def traducir_integridad(error: IntegrityError, fields: dict, operacion: str) -> ErrorIntegridad:
    texto = str(error.orig)

    def label(campo):
        return fields.get(campo, {}).get("label", campo)

    campo = _buscar(_UNICO, texto)
    if campo:
        return ErrorIntegridad(f"Ya existe un registro con ese valor de «{label(campo)}».", campo)

    campo = _buscar(_NULO, texto)
    if campo:
        return ErrorIntegridad(f"{label(campo)} es obligatorio.", campo)

    if operacion == "DELETE" and any(s in texto for s in _FK_EN_USO):
        return ErrorIntegridad(
            "No se puede eliminar: hay otros registros que dependen de este. "
            "Eliminá o reasigná esos registros primero."
        )
    if any(s in texto for s in _FK_INVALIDA):
        return ErrorIntegridad("Alguno de los valores seleccionados ya no existe.")

    return ErrorIntegridad("La base de datos rechazó la operación por una restricción de integridad.")


class ServicioCRUD:
    """
    Operaciones de escritura de una entidad.

    model      clase SQLAlchemy
    fields     campos del metamodelo (para etiquetas de FK y mensajes)
    auditoria  {"enabled": bool, "ignore_fields": [...]}
    etiqueta_tabla  función (tabla, cantidad) → texto, para los mensajes
                    (ej: ("activos", 2) → "2 activos")
    confirmar  True: cada operación se confirma (commit) sola. False: se deja
               pendiente para que quien llama confirme o descarte un lote
               completo (ej: una importación "todo o nada").
    """

    def __init__(self, model, fields: dict, auditoria: dict | None = None,
                 etiqueta_tabla=None, confirmar: bool = True):
        self.model = model
        self.fields = fields
        self.auditoria = auditoria or {"enabled": False}
        self.pk = model.__mapper__.primary_key[0].name
        self.etiqueta_tabla = etiqueta_tabla or _etiqueta_por_defecto
        self.confirmar = confirmar

    # ------------------------------------------------------------------
    def completar_dependencias(self, datos: dict, registro=None) -> dict:
        """
        Selects dependientes (ej: modelo_id depende de marca_id): verifica que el
        modelo sea de la marca elegida y, si no se eligió marca, la completa con
        la del modelo. Devuelve los datos con lo completado; lanza
        ErroresValidacion si no coinciden.

        Con `registro` (edición), los campos que no vienen en `datos` conservan
        su valor actual.
        """
        from app.core.db import db

        def valor(campo):
            if campo in datos:
                return datos[campo]
            return getattr(registro, campo) if registro is not None else None

        resultado, errores = dict(datos), {}
        for campo, cfg in self.fields.items():
            padre = cfg.get("depende_de")
            if not padre or valor(campo) is None:
                continue
            if campo not in datos and padre not in datos:
                continue  # no cambió ninguno de los dos
            hijo = db.session.get(cfg["fk_model"], valor(campo))
            if hijo is None:
                continue  # la FK inexistente la informa validar_existencia
            correcto = getattr(hijo, cfg["depende_fk"])
            elegido = valor(padre)
            if elegido is None:
                resultado[padre] = correcto
            elif correcto != elegido:
                cfg_padre = self.fields[padre]
                obj_padre = db.session.get(cfg_padre["fk_model"], elegido)
                nombre_padre = fk.etiqueta(obj_padre, cfg_padre) if obj_padre is not None else elegido
                errores[campo] = (
                    f"{cfg.get('label', campo)}: «{fk.etiqueta(hijo, cfg)}» no pertenece a "
                    f"«{nombre_padre}» ({cfg_padre.get('label', padre).lower()})."
                )
        if errores:
            raise ErroresValidacion(errores)
        return resultado

    # ------------------------------------------------------------------
    def crear(self, datos: dict, motivo: str | None = None, usuario: str = "sistema"):
        datos = self.completar_dependencias(datos)
        registro = self.model(**datos)
        db.session.add(registro)
        self._confirmar("INSERT", registro, None, motivo, usuario)
        return registro

    def actualizar(self, registro, datos: dict, motivo: str | None = None, usuario: str = "sistema"):
        datos = self.completar_dependencias(datos, registro)
        anterior = self._estado(registro)
        for campo, valor in datos.items():
            setattr(registro, campo, valor)
        self._confirmar("UPDATE", registro, anterior, motivo, usuario)
        return registro

    def eliminar(self, registro, motivo: str | None = None, usuario: str = "sistema"):
        """
        Borra el registro y, si el modelo lo declara, sus hijos en cascada
        (cada uno queda en la auditoría). Si otros registros lo usan, no borra
        nada y lanza RegistroEnUso.
        """
        self.verificar_eliminable(registro)
        anterior = self._estado(registro)

        hijos = dependencias.en_cascada(registro)
        if hijos:
            pk = getattr(registro, self.pk)
            motivo_hijos = f"Eliminación en cascada de {self.model.__tablename__} #{pk}"
            if motivo:
                motivo_hijos += f": {motivo}"
            for hijo in hijos:
                self._auditar_hijo(hijo, motivo_hijos, usuario)

        db.session.delete(registro)
        self._confirmar("DELETE", registro, anterior, motivo, usuario)

    def verificar_eliminable(self, registro):
        bloqueos = dependencias.bloqueantes(registro)
        if bloqueos:
            partes = [self.etiqueta_tabla(tabla, n) for tabla, n in bloqueos]
            raise RegistroEnUso(
                f"No se puede eliminar porque lo usan {_enumerar(partes)}. "
                "Eliminá o reasigná esos registros primero.",
                bloqueos,
            )

    def _auditar_hijo(self, hijo, motivo, usuario):
        if not (hasattr(hijo, "obtener_historial") and hasattr(hijo, "uuid")):
            return
        registrar_cambio(
            tabla=hijo.__tablename__,
            registro_uuid=hijo.uuid,
            tipo="DELETE",
            estado_anterior=valores(hijo, calculados=False),
            estado_actual=None,
            motivo_operacion=motivo,
            usuario=usuario,
            registro_id=sa_inspect(hijo).identity[0],
        )

    # ------------------------------------------------------------------
    def _estado(self, registro):
        return fk.para_auditoria(registro, self.fields) if self.auditoria.get("enabled") else None

    def _confirmar(self, tipo, registro, anterior, motivo, usuario):
        try:
            # flush: la base valida ANTES de escribir la auditoría.
            db.session.flush()
            if tipo != "DELETE":
                db.session.refresh(registro)

            if self.auditoria.get("enabled"):
                registrar_cambio(
                    tabla=self.model.__tablename__,
                    registro_uuid=registro.uuid,
                    tipo=tipo,
                    estado_anterior=anterior,
                    estado_actual=None if tipo == "DELETE" else self._estado(registro),
                    motivo_operacion=motivo,
                    usuario=usuario,
                    registro_id=getattr(registro, self.pk),
                    ignore_fields=self.auditoria.get("ignore_fields", []),
                )
            if self.confirmar:
                db.session.commit()
        except IntegrityError as e:
            db.session.rollback()
            raise traducir_integridad(e, self.fields, tipo) from e
