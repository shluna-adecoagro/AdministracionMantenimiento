# Informe modo sombra: metamodelos manuales vs. inferidos

Entidades analizadas: **17**

## Resumen

| Entidad | 🔴 ERROR | 🟠 REVISAR | 🟡 OVERRIDE | 🟢 MEJORA | ⚪ INFO |
|---|---|---|---|---|---|
| activos | 0 | 1 | 6 | 0 | 1 |
| medidores | 1 | 1 | 2 | 2 | 1 |
| lecturas_medidor | 0 | 1 | 4 | 0 | 0 |
| insumos | 0 | 2 | 5 | 1 | 1 |
| stock_insumo | 0 | 2 | 0 | 0 | 0 |
| unidades_medida | 1 | 0 | 2 | 0 | 0 |
| marcas | 1 | 0 | 1 | 0 | 0 |
| modelos | 1 | 1 | 1 | 0 | 0 |
| recursos | 3 | 0 | 2 | 1 | 0 |
| empleados | 3 | 0 | 0 | 1 | 0 |
| proveedores | 2 | 0 | 0 | 1 | 0 |
| contactos_proveedor | 2 | 0 | 2 | 1 | 0 |
| bom_modelo | 1 | 3 | 2 | 3 | 0 |
| bom_activo | 1 | 5 | 3 | 3 | 0 |
| cuentas | 0 | 0 | 0 | 0 | 0 |
| sectores | 0 | 0 | 0 | 0 | 0 |
| ubicaciones | 0 | 0 | 0 | 0 | 0 |
| **TOTAL** | **16** | **16** | **30** | **13** | **3** |

## Detalle por entidad

### activos  (`Activo`)

**🟠 REVISAR**

- `subentidad:bom_activo`: 'bom_activo' cuelga de 'activos' pero tiene es_subentidad=False

**🟡 OVERRIDE**

- `campo:tipo_activo_id`: label: 'Tipo de activo' (inferido: 'Tipo activo')
- `campo:categoria_activo_id`: label: 'Categoría' (inferido: 'Categoria activo')
- `campo:nro_serie_chasis`: label: 'Nro. serie chasis' (inferido: 'Nro serie chasis')
- `campo:nro_motor`: label: 'Nro. motor' (inferido: 'Nro motor')
- `campo:sector_id`: label: 'Sector asignado' (inferido: 'Sector')
- `campo:usuario_asignado`: tipo: metamodelo='datalist' vs inferido='text'

**⚪ INFO**

- `subentidad:medidores`: campos_listado usa 'nombre_unidad', que no es un field de 'medidores' (¿se resuelve por relación?)

Override sugerido (hace que lo inferido iguale al metamodelo actual):

```python
override(Activo,
    campos={
        'tipo_activo_id': {'label': 'Tipo de activo'},
        'categoria_activo_id': {'label': 'Categoría'},
        'nro_serie_chasis': {'label': 'Nro. serie chasis'},
        'nro_motor': {'label': 'Nro. motor'},
        'sector_id': {'label': 'Sector asignado'},
        'usuario_asignado': {'tipo': 'datalist'},
    })
```

### medidores  (`Medidor`)

**🔴 ERROR**

- `campo:unidad_medida_id`: la columna es NOT NULL pero el formulario no la exige (falla recién en la base)

**🟠 REVISAR**

- `entidad`: el modelo tiene AuditMixin pero el metamodelo no define 'auditoria'

**🟡 OVERRIDE**

- `campo:nombre_medidor`: label: 'Nombre' (inferido: 'Nombre medidor')
- `campo:unidad_medida_id`: label: 'Unidad de medida' (inferido: 'Unidad medida')

**🟢 MEJORA**

- `campo:unidad_medida_id`: relacion inferible: 'unidad_medida'
- `campo:unidad_medida_id`: fk_label inferible: 'nombre_unidad'

**⚪ INFO**

- `campo:activo_id`: FK al padre (la inyecta el framework)

Override sugerido (hace que lo inferido iguale al metamodelo actual):

```python
override(Medidor,
    campos={
        'nombre_medidor': {'label': 'Nombre'},
        'unidad_medida_id': {'label': 'Unidad de medida'},
    })
```

### lecturas_medidor  (`LecturaMedidor`)

**🟠 REVISAR**

- `entidad`: el modelo tiene AuditMixin pero el metamodelo no define 'auditoria'

**🟡 OVERRIDE**

- `campo:medidor_id`: oculto=True (no inferible)
- `campo:fecha_lectura`: label: 'Fecha' (inferido: 'Fecha lectura')
- `campo:origen`: tipo: metamodelo='select' vs inferido='text'
- `campo:origen`: options propias

Override sugerido (hace que lo inferido iguale al metamodelo actual):

```python
override(LecturaMedidor,
    campos={
        'medidor_id': {'oculto': True},
        'fecha_lectura': {'label': 'Fecha'},
        'origen': {'tipo': 'select', 'options': [{'value': 'manual', 'label': 'Manual'}, {'value': 'iot', 'label': 'IoT'}, {'value': 'importacion', 'label': 'Importación'}]},
    })
```

### insumos  (`Insumo`)

**🟠 REVISAR**

- `subentidad:bom_modelo`: 'bom_modelo' cuelga de 'insumos' pero tiene es_subentidad=False
- `subentidad:bom_activo`: 'bom_activo' cuelga de 'insumos' pero tiene es_subentidad=False

**🟡 OVERRIDE**

- `campo:categoria_insumo_id`: label: 'Categoría' (inferido: 'Categoria insumo')
- `campo:tipo_insumo_id`: label: 'Tipo' (inferido: 'Tipo insumo')
- `campo:presentacion_cantidad`: label: 'Cantidad por presentación' (inferido: 'Presentacion cantidad')
- `campo:unidad_medida_id`: label: 'Unidad de medida' (inferido: 'Unidad medida')
- `campo:cantidad_minima`: label: 'Stock mínimo' (inferido: 'Cantidad minima')

**🟢 MEJORA**

- `campo:unidad_medida_id`: relacion inferible: 'unidad_medida'

**⚪ INFO**

- `campo:stock_total`: campo virtual (no existe como columna)

Override sugerido (hace que lo inferido iguale al metamodelo actual):

```python
override(Insumo,
    campos={
        'categoria_insumo_id': {'label': 'Categoría'},
        'tipo_insumo_id': {'label': 'Tipo'},
        'presentacion_cantidad': {'label': 'Cantidad por presentación'},
        'unidad_medida_id': {'label': 'Unidad de medida'},
        'cantidad_minima': {'label': 'Stock mínimo'},
    })
```

### stock_insumo  (`StockInsumo`)

**🟠 REVISAR**

- `campo:sector_id`: el metamodelo exige más que el esquema (¿regla de negocio o desfase?)
- `campo:fecha_actualizacion`: el modelo tiene 'fecha_actualizacion' (date) que el metamodelo no expone

Override sugerido (hace que lo inferido iguale al metamodelo actual):

```python
override(StockInsumo,
    campos={
        'sector_id': {'required': True},
        'fecha_actualizacion': {'excluir': True},
    })
```

### unidades_medida  (`UnidadMedida`)

**🔴 ERROR**

- `campo:tipo_unidad_id`: la columna es NOT NULL pero el formulario no la exige (falla recién en la base)

**🟡 OVERRIDE**

- `campo:nombre_unidad`: label: 'Nombre' (inferido: 'Nombre unidad')
- `campo:tipo_unidad_id`: label: 'Tipo' (inferido: 'Tipo unidad')

Override sugerido (hace que lo inferido iguale al metamodelo actual):

```python
override(UnidadMedida,
    campos={
        'nombre_unidad': {'label': 'Nombre'},
        'tipo_unidad_id': {'label': 'Tipo'},
    })
```

### marcas  (`Marca`)

**🔴 ERROR**

- `campo:nombre_marca`: la columna es NOT NULL pero el formulario no la exige (falla recién en la base)

**🟡 OVERRIDE**

- `campo:nombre_marca`: label: 'Nombre de la marca' (inferido: 'Nombre marca')

Override sugerido (hace que lo inferido iguale al metamodelo actual):

```python
override(Marca,
    campos={
        'nombre_marca': {'label': 'Nombre de la marca'},
    })
```

### modelos  (`Modelo`)

**🔴 ERROR**

- `campo:marca_id`: la columna es NOT NULL pero el formulario no la exige (falla recién en la base)

**🟠 REVISAR**

- `subentidad:bom_modelo`: 'bom_modelo' cuelga de 'modelos' pero tiene es_subentidad=False

**🟡 OVERRIDE**

- `campo:nombre_modelo`: label: 'Nombre del modelo' (inferido: 'Nombre modelo')

Override sugerido (hace que lo inferido iguale al metamodelo actual):

```python
override(Modelo,
    campos={
        'nombre_modelo': {'label': 'Nombre del modelo'},
    })
```

### recursos  (`Recurso`)

**🔴 ERROR**

- `campo:tipo_recurso`: tipo 'string' fuera del vocabulario ['datalist', 'date', 'file', 'fk', 'number', 'select', 'text', 'textarea']
- `campo:tipo_recurso`: la columna es NOT NULL pero el formulario no la exige (falla recién en la base)
- `campo:estado_recurso_id`: la columna es NOT NULL pero el formulario no la exige (falla recién en la base)

**🟡 OVERRIDE**

- `campo:tipo_recurso`: tipo: metamodelo='string' vs inferido='text'
- `campo:tipo_recurso`: label: 'Tipo' (inferido: 'Tipo recurso')

**🟢 MEJORA**

- `campo:estado_recurso_id`: relacion inferible: 'estado'

Override sugerido (hace que lo inferido iguale al metamodelo actual):

```python
override(Recurso,
    campos={
        'tipo_recurso': {'label': 'Tipo'},
    })
```

### empleados  (`Empleado`)

**🔴 ERROR**

- `campo:nombre`: la columna es NOT NULL pero el formulario no la exige (falla recién en la base)
- `campo:apellido`: la columna es NOT NULL pero el formulario no la exige (falla recién en la base)
- `campo:estado_recurso_id`: la columna es NOT NULL pero el formulario no la exige (falla recién en la base)

**🟢 MEJORA**

- `campo:estado_recurso_id`: relacion inferible: 'estado'

### proveedores  (`Proveedor`)

**🔴 ERROR**

- `campo:razon_social`: la columna es NOT NULL pero el formulario no la exige (falla recién en la base)
- `campo:estado_recurso_id`: la columna es NOT NULL pero el formulario no la exige (falla recién en la base)

**🟢 MEJORA**

- `campo:estado_recurso_id`: relacion inferible: 'estado'

### contactos_proveedor  (`ContactoProveedor`)

**🔴 ERROR**

- `campo:proveedor_id`: la columna es NOT NULL pero el formulario no la exige (falla recién en la base)
- `campo:nombre_contacto`: la columna es NOT NULL pero el formulario no la exige (falla recién en la base)

**🟡 OVERRIDE**

- `campo:nombre_contacto`: label: 'Nombre' (inferido: 'Nombre contacto')
- `campo:tipo_contacto`: label: 'Tipo de contacto' (inferido: 'Tipo contacto')

**🟢 MEJORA**

- `campo:proveedor_id`: relacion inferible: 'proveedor'

Override sugerido (hace que lo inferido iguale al metamodelo actual):

```python
override(ContactoProveedor,
    campos={
        'nombre_contacto': {'label': 'Nombre'},
        'tipo_contacto': {'label': 'Tipo de contacto'},
    })
```

### bom_modelo  (`BOMModelo`)

**🔴 ERROR**

- `entidad`: clave desconocida 'audit' (¿quisiste 'auditoria'?): probablemente el framework la ignora (verificar)

**🟠 REVISAR**

- `campo:insumo_id`: sin fk_label y el destino no define __label_field__: probablemente el select use el fallback de ModelMixin.label (primera columna con length, p. ej. uuid)
- `campo:es_equivalencia`: el metamodelo exige más que el esquema (¿regla de negocio o desfase?)
- `entidad`: el modelo tiene AuditMixin pero el metamodelo no define 'auditoria'

**🟡 OVERRIDE**

- `campo:nota_equivalencia`: label: 'Nota de equivalencia' (inferido: 'Nota equivalencia')
- `campo:origen_equivalencia`: label: 'Origen de equivalencia' (inferido: 'Origen equivalencia')

**🟢 MEJORA**

- `campo:insumo_id`: relacion inferible: 'insumo'
- `campo:modelo_id`: relacion inferible: 'modelo'
- `campo:modelo_id`: fk_label inferible: 'nombre_modelo'

Override sugerido (hace que lo inferido iguale al metamodelo actual):

```python
override(BOMModelo,
    campos={
        'es_equivalencia': {'required': True},
        'nota_equivalencia': {'label': 'Nota de equivalencia'},
        'origen_equivalencia': {'label': 'Origen de equivalencia'},
    })
```

### bom_activo  (`BOMActivo`)

**🔴 ERROR**

- `entidad`: clave desconocida 'audit' (¿quisiste 'auditoria'?): probablemente el framework la ignora (verificar)

**🟠 REVISAR**

- `campo:activo_id`: sin fk_label y el destino no define __label_field__: probablemente el select use el fallback de ModelMixin.label (primera columna con length, p. ej. uuid)
- `campo:insumo_id`: sin fk_label y el destino no define __label_field__: probablemente el select use el fallback de ModelMixin.label (primera columna con length, p. ej. uuid)
- `campo:es_equivalencia`: el metamodelo exige más que el esquema (¿regla de negocio o desfase?)
- `campo:reemplaza_insumo_modelo_id`: sin fk_label y el destino no define __label_field__: probablemente el select use el fallback de ModelMixin.label (primera columna con length, p. ej. uuid)
- `entidad`: el modelo tiene AuditMixin pero el metamodelo no define 'auditoria'

**🟡 OVERRIDE**

- `campo:nota_equivalencia`: label: 'Nota de equivalencia' (inferido: 'Nota equivalencia')
- `campo:origen_equivalencia`: label: 'Origen de equivalencia' (inferido: 'Origen equivalencia')
- `campo:reemplaza_insumo_modelo_id`: label: 'Reemplaza insumo del modelo' (inferido: 'Reemplaza insumo modelo')

**🟢 MEJORA**

- `campo:activo_id`: relacion inferible: 'activo'
- `campo:insumo_id`: relacion inferible: 'insumo'
- `campo:reemplaza_insumo_modelo_id`: relacion inferible: 'reemplaza_insumo_modelo'

Override sugerido (hace que lo inferido iguale al metamodelo actual):

```python
override(BOMActivo,
    campos={
        'es_equivalencia': {'required': True},
        'nota_equivalencia': {'label': 'Nota de equivalencia'},
        'origen_equivalencia': {'label': 'Origen de equivalencia'},
        'reemplaza_insumo_modelo_id': {'label': 'Reemplaza insumo del modelo'},
    })
```

### cuentas

✅ Sin diferencias.

### sectores

✅ Sin diferencias.

### ubicaciones

✅ Sin diferencias.

## Modelos sin metamodelo

Pueden ser catálogos (solo se usan como destino de FK) o modelos que se manejan solo por API:

`AuditLog`, `CategoriaActivo`, `CategoriaInsumo`, `EstadoActivo`, `EstadoCuenta`, `EstadoRecurso`, `EstadoSector`, `MotivoOperacion`, `Pedido`, `PedidoDetalle`, `TipoActivo`, `TipoInsumo`, `TipoUnidad`

## Blueprints compartidos (`bp_name`)

- `activos`: activos, medidores, bom_modelo, bom_activo
- `cuentas`: cuentas
- `insumos`: insumos, stock_insumo
- `lecturas`: lecturas_medidor
- `marcas_modelos`: marcas, modelos
- `recursos_web`: recursos, empleados, proveedores, contactos_proveedor
- `sectores_web`: sectores, ubicaciones
- `unidades_medida_web`: unidades_medida
