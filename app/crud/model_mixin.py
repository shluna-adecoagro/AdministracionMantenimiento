class ModelMixin:
    """
    Mixin genérico para modelos del framework CRUD.
    Provee:
    - pk: propiedad para obtener la clave primaria
    - label: representación legible del registro
    - to_dict: serialización genérica
    - as_fk_option: opción para selects de FK
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
        if hasattr(self, "__label_field__"):
            return getattr(self, self.__label_field__)

        # fallback: buscar el primer string column
        for col in self.__table__.columns:
            if hasattr(col.type, "length"):  # String, Text, etc.
                return getattr(self, col.name)

        # último recurso
        return str(self.pk)

    def to_dict(self):
        """
        Serialización genérica del modelo.
        Convierte todos los campos simples a dict.
        """
        data = {}
        for col in self.__table__.columns:
            data[col.name] = getattr(self, col.name)
        return data

    def as_fk_option(self, label_field=None):
        """
        Devuelve un dict para usar en selects de FK.
        """
        return {
            "value": self.pk,
            "label": getattr(self, label_field) if label_field else self.label
        }
