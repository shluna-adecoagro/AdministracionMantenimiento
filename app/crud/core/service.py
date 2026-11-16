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

from sqlalchemy.exc import IntegrityError

from app.audit.registrar import registrar_cambio
from app.core.db import db
from app.crud.core import fk


class ErrorIntegridad(Exception):
    """La base rechazó la operación. `campo` es None si no se pudo identificar."""

    def __init__(self, mensaje: str, campo: str | None = None):
        self.mensaje = mensaje
        self.campo = campo
        super().__init__(mensaje)


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
    """

    def __init__(self, model, fields: dict, auditoria: dict | None = None):
        self.model = model
        self.fields = fields
        self.auditoria = auditoria or {"enabled": False}
        self.pk = model.__mapper__.primary_key[0].name

    # ------------------------------------------------------------------
    def crear(self, datos: dict, motivo: str | None = None, usuario: str = "sistema"):
        registro = self.model(**datos)
        db.session.add(registro)
        self._confirmar("INSERT", registro, None, motivo, usuario)
        return registro

    def actualizar(self, registro, datos: dict, motivo: str | None = None, usuario: str = "sistema"):
        anterior = self._estado(registro)
        for campo, valor in datos.items():
            setattr(registro, campo, valor)
        self._confirmar("UPDATE", registro, anterior, motivo, usuario)
        return registro

    def eliminar(self, registro, motivo: str | None = None, usuario: str = "sistema"):
        anterior = self._estado(registro)
        db.session.delete(registro)
        self._confirmar("DELETE", registro, anterior, motivo, usuario)

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
            db.session.commit()
        except IntegrityError as e:
            db.session.rollback()
            raise traducir_integridad(e, self.fields, tipo) from e
