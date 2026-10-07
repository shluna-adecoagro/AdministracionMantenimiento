from app.models.auditoria_models import AuditLog

class AuditMixin:

    def obtener_historial(self, page):
        tabla = self.__tablename__
        uuid_value = str(self.uuid)

        query = (
            AuditLog.query
            .filter_by(TablaAfectada=tabla, RegistroUUID=uuid_value)
            .order_by(AuditLog.Version.desc())
        )

        paginado = query.paginate(page=page, per_page=10, error_out=False)
        return paginado.items, paginado
