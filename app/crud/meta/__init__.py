# app/crud/meta/__init__.py
"""
Metamodelo del framework CRUD.

- spec.py       EntitySpec / FieldSpec: la descripción tipada de cada entidad.
- registry.py   Construye las specs: inferido del modelo + overrides, y las valida.
- overrides/    Un archivo por módulo con lo que NO se puede inferir del modelo.
"""
