# Módulo de Maestros – brache

Implementa el paquete **Maestros** de `modelo_dominio.md`, los procesos P1 y P2 y la validación V4.
Además provee la base que usan todos los módulos (conexión, repositorio genérico, menú y componentes de UI; ver el README).

## Qué hay y dónde

| Capa | Archivo | Contenido |
|------|---------|-----------|
| Dominio | `src/dominio/maestros/modelos.py` | `Ubicacion` (abstracta), `Sucursal`, `CentroDistribucion`, `Categoria`, `Producto`, `HistorialPrecio`, `Proveedor`, `ProductoProveedor` y funciones de CUIT |
| Persistencia | `src/persistencia/repositorio_maestros.py` | Un repositorio por entidad (heredan de `RepositorioBase`) |
| Esquema | `src/persistencia/esquema/01_maestros.sql` | Tablas, `UNIQUE` y `CHECK` |
| Servicios | `src/servicios/maestros_service.py` | `UbicacionService`, `CategoriaService`, `ProductoService`, `ProveedorService` |
| Pantallas | `src/ui/pantallas/maestros.py` | Menú **Maestros**: Sucursales y CD, Categorías, Productos y precios, Proveedores |
| Tests | `tests/test_maestros.py` | Reglas de negocio de los cuatro servicios |

## Reglas de negocio

**Ubicaciones (P1)**
- Código único (se guarda en mayúsculas).
- Cada sucursal necesita un **punto de venta** propio, entero y mayor a cero: ventas lo usa para numerar comprobantes.
- Hay **un solo Centro de Distribución activo**, como describe la consigna.
- Una sucursal no puede convertirse en CD ni al revés.
- Las bajas son lógicas (`activa = 0`) y se pueden revertir.

**Categorías (P2)**
- Nombre único sin importar mayúsculas.
- No se puede eliminar una categoría que tenga productos, aunque estén dados de baja.

**Productos y precios (P2)**
- **V4:** el SKU (sin importar mayúsculas) y el código de barras no se repiten. Un producto dado de baja sigue ocupando su SKU.
- El costo y el precio de venta no pueden ser negativos. Se guardan como `Decimal` con dos decimales.
- Cada alta y cada cambio de costo o precio agrega un registro en `historial_precio` y cierra el anterior.
  `ProductoService.precio_vigente_en(producto_id, momento)` devuelve el costo y el precio de una fecha dada.
- `Producto.margen_unitario()` y `margen_porcentual()` sirven para el reporte R2.
- Proveedores de cada producto: código del proveedor, costo pactado y plazo de entrega. Solo se pueden asignar proveedores activos.

**Proveedores (P2)**
- **V4:** el CUIT no se repite. Se acepta con o sin guiones, se guarda con los 11 dígitos y se valida el dígito verificador.
- Formato de email básico. Las bajas son lógicas.

## Para los demás módulos

- Las sucursales y el CD están en la tabla `ubicacion` (`tipo` = `'SUCURSAL'` o `'CD'`). Para obtenerlas como objetos:
  `UbicacionService().listar_sucursales()` o `UbicacionRepositorio().listar_centros()`.
- Para leer productos: `ProductoService().obtener(id)`, `.listar()` o `.buscar(texto)`.
- Los proveedores de un producto (útil para órdenes de compra): `ProductoService().proveedores_de(producto_id)`.

## Pendiente

- **Stock mínimo por local:** el modelo lo ubica en `Stock` (inventario, de pohlsi), pero administrarlo es parte de P2.
  Hay que acordar si va en la tabla de stock o en una tabla propia de maestros.
- Datos de prueba (seed), reportes R1 y R2.
