class ModelMixin:
    """
    Mixin genérico para modelos del framework CRUD.
    Provee:
    - pk: propiedad para obtener la clave primaria
    - label: representación legible del registro (para FKs y mensajes)

    Para pasar un registro a dict se usa app.crud.core.repository.valores().
    """

    @property
    def pk(self):
        """
        Devuelve el valor de la clave primaria del modelo.
        Se basa en el atributo definido en __mapper__.primary_key.
        """
        pk_column = self.__mapper__.primary_key[0].name
        return getattr(self, pk_column)

    @property
    def label(self):
        """
        Devuelve una representación legible del registro.
        Si el modelo define __label_field__, se usa ese campo.
        Si no, se usa el primer campo de texto disponible.
        """
        campo = getattr(self, "__label_field__", None)
        if campo:
            return getattr(self, campo)

        # fallback: buscar el primer string column
        for col in self.__table__.columns:
            if hasattr(col.type, "length"):  # String, Text, etc.
                return getattr(self, col.name)

        # último recurso
        return str(self.pk)
