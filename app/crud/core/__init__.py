# app/crud/core/__init__.py
"""
Núcleo del framework CRUD, independiente de Flask y de las plantillas.

- coercion.py    texto de entrada → tipos Python, con validación
- fk.py          opciones y etiquetas de claves foráneas
- repository.py  consultas de lectura (búsqueda, filtros, carga anticipada)
- service.py     alta / modificación / baja en una transacción, con auditoría
- files.py       almacenamiento de archivos subidos
"""
