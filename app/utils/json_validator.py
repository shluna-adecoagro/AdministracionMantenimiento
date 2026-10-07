from jsonschema import validate, ValidationError
from app.schemas import sectores_schema, auditoria_schema

class JSONValidationError(Exception):
    pass

def validar_con_schema(data, schema):
    try:
        validate(instance=data, schema=schema)
    except ValidationError as e:
        raise JSONValidationError(e.message)

def validar_sector(data):
    validar_con_schema(data, sectores_schema)

def validar_auditoria(data):
    validar_con_schema(data, auditoria_schema)
