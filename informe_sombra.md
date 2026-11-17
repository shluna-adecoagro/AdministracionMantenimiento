# Informe modo sombra: metamodelos manuales vs. inferidos

Entidades analizadas: **18**

## Resumen

| Entidad | 🔴 ERROR | 🟠 REVISAR | 🟡 OVERRIDE | 🟢 MEJORA | ⚪ INFO |
|---|---|---|---|---|---|
| activos | 0 | 0 | 1 | 0 | 0 |
| medidores | 0 | 0 | 0 | 0 | 0 |
| lecturas_medidor | 0 | 1 | 2 | 0 | 0 |
| bom_modelo | 0 | 0 | 0 | 0 | 0 |
| bom_activo | 0 | 0 | 0 | 0 | 0 |
| cuentas | 0 | 0 | 0 | 0 | 0 |
| insumos | 0 | 2 | 0 | 0 | 0 |
| stock_insumo | 0 | 0 | 0 | 0 | 0 |
| categorias_insumo | 0 | 0 | 0 | 0 | 0 |
| tipos_insumo | 0 | 0 | 0 | 0 | 0 |
| marcas | 0 | 0 | 0 | 0 | 0 |
| modelos | 0 | 0 | 0 | 0 | 0 |
| unidades_medida | 0 | 0 | 0 | 0 | 0 |
| empleados | 0 | 0 | 0 | 0 | 0 |
| proveedores | 0 | 0 | 0 | 0 | 0 |
| contactos_proveedor | 0 | 0 | 0 | 0 | 0 |
| sectores | 0 | 0 | 0 | 0 | 0 |
| ubicaciones | 0 | 0 | 0 | 0 | 0 |
| **TOTAL** | **0** | **3** | **3** | **0** | **0** |

## Detalle por entidad

### activos  (`Activo`)

**🟡 OVERRIDE**

- `campo:usuario_asignado`: tipo: metamodelo='datalist' vs inferido='text'

Override sugerido (hace que lo inferido iguale al metamodelo actual):

```python
override(Activo,
    campos={
        'usuario_asignado': {'tipo': 'datalist'},
    })
```

### medidores

✅ Sin diferencias.

### lecturas_medidor  (`LecturaMedidor`)

**🟠 REVISAR**

- `campo:origen`: el metamodelo exige más que el esquema (¿regla de negocio o desfase?)

**🟡 OVERRIDE**

- `campo:origen`: tipo: metamodelo='select' vs inferido='text'
- `campo:origen`: options propias

Override sugerido (hace que lo inferido iguale al metamodelo actual):

```python
override(LecturaMedidor,
    campos={
        'origen': {'tipo': 'select', 'required': True, 'options': [{'value': 'manual', 'label': 'Manual'}, {'value': 'iot', 'label': 'IoT'}, {'value': 'importacion', 'label': 'Importación'}]},
    })
```

### bom_modelo

✅ Sin diferencias.

### bom_activo

✅ Sin diferencias.

### cuentas

✅ Sin diferencias.

### insumos  (`Insumo`)

**🟠 REVISAR**

- `subentidad:bom_modelo`: entidad_padre de 'bom_modelo' es 'modelos': el esquema admite un solo padre y 'insumos' también la lista
- `subentidad:bom_activo`: entidad_padre de 'bom_activo' es 'activos': el esquema admite un solo padre y 'insumos' también la lista

### stock_insumo

✅ Sin diferencias.

### categorias_insumo

✅ Sin diferencias.

### tipos_insumo

✅ Sin diferencias.

### marcas

✅ Sin diferencias.

### modelos

✅ Sin diferencias.

### unidades_medida

✅ Sin diferencias.

### empleados

✅ Sin diferencias.

### proveedores

✅ Sin diferencias.

### contactos_proveedor

✅ Sin diferencias.

### sectores

✅ Sin diferencias.

### ubicaciones

✅ Sin diferencias.

## Modelos sin metamodelo

Pueden ser catálogos (solo se usan como destino de FK) o modelos que se manejan solo por API:

`AuditLog`, `CategoriaActivo`, `EstadoActivo`, `EstadoCuenta`, `EstadoRecurso`, `EstadoSector`, `MotivoOperacion`, `Pedido`, `PedidoDetalle`, `Recurso`, `TipoActivo`, `TipoUnidad`

## Blueprints compartidos (`bp_name`)

- `crud`: activos, medidores, lecturas_medidor, bom_modelo, bom_activo, cuentas, insumos, stock_insumo, categorias_insumo, tipos_insumo, marcas, modelos, unidades_medida, empleados, proveedores, contactos_proveedor, sectores, ubicaciones
