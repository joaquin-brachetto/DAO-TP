# Módulo de Maestros – brache

Implementa el paquete **Maestros** de `modelo_dominio.md`, los procesos P1 y P2, la validación V4,
los reportes R1 y R2 y los datos de prueba.
Además provee la base que usan todos los módulos (conexión, repositorio genérico, menú y componentes de UI; ver el README).

## Qué hay y dónde

| Capa | Archivo | Contenido |
|------|---------|-----------|
| Dominio | `src/dominio/maestros/modelos.py` | `Ubicacion` (abstracta), `Sucursal`, `CentroDistribucion`, `Categoria`, `Producto`, `HistorialPrecio`, `Proveedor`, `ProductoProveedor`, `StockMinimo` y funciones de CUIT |
| Persistencia | `src/persistencia/repositorio_maestros.py` | Un repositorio por entidad (heredan de `RepositorioBase`) |
| Esquema | `src/persistencia/esquema/01_maestros.sql` | Tablas, `UNIQUE` y `CHECK` |
| Servicios | `src/servicios/maestros_service.py` | `UbicacionService`, `CategoriaService`, `ProductoService`, `StockMinimoService`, `ProveedorService` |
| Pantallas | `src/ui/pantallas/maestros.py` | Menú **Maestros**: Sucursales y CD, Categorías, Productos y precios (con historial, proveedores y stock mínimo), Proveedores |
| Reportes | `src/reportes/existencias_reporte.py`, `src/reportes/productos_reporte.py` | R1 y R2 |
| Pantallas de reportes | `src/ui/pantallas/reportes_maestros.py`, `src/ui/graficos.py` | Menú **Reportes**: tabla, totales y gráfico de barras |
| Datos de prueba | `src/datos_prueba.py` | `python -m src.datos_prueba` o menú Archivo → Cargar datos de prueba |
| Tests | `tests/test_maestros.py`, `tests/test_reportes_maestros.py`, `tests/test_datos_prueba.py` | Servicios, reportes y seed |

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

**Stock mínimo por ubicación (P2)**
- Tabla propia de maestros, `stock_minimo`: un mínimo por producto y ubicación (sucursal o CD). Sin registro, no hay mínimo.
- Se define desde Productos → "Stock mínimo…". Solo para productos y ubicaciones activos; el mínimo es un entero ≥ 0.
- Un producto está **en stock mínimo** cuando su disponible **llega** al mínimo o queda por debajo (`disponible <= mínimo`, con mínimo > 0).

**Proveedores (P2)**
- **V4:** el CUIT no se repite. Se acepta con o sin guiones, se guarda con los 11 dígitos y se valida el dígito verificador.
- Formato de email básico. Las bajas son lógicas.

## Para los demás módulos

- Las sucursales y el CD están en la tabla `ubicacion` (`tipo` = `'SUCURSAL'` o `'CD'`). Para obtenerlas como objetos:
  `UbicacionService().listar_sucursales()` o `UbicacionRepositorio().listar_centros()`.
- Para leer productos: `ProductoService().obtener(id)`, `.listar()` o `.buscar(texto)`.
- Los proveedores de un producto (útil para órdenes de compra): `ProductoService().proveedores_de(producto_id)`.
- **Observer de inventario (pohlsi):** el mínimo no se guarda en `stock`. Después de cada egreso, el `StockService`
  lo consulta así y, si corresponde, notifica a sus observadores:

  ```python
  minimos = StockMinimoService(self.db)
  if minimos.esta_en_minimo(producto_id, ubicacion_id, disponible):
      self._notificar(...)            # ObservadorStock.stock_bajo_minimo(...)
  faltan = minimos.minimo(producto_id, ubicacion_id) - disponible   # para la NecesidadReposicion
  ```

## Reportes

**R1 – Existencias actuales y productos en stock mínimo.** Una fila por producto activo y ubicación activa, con
disponible, mínimo, faltante, valorizado al costo actual y estado. Primero aparecen los que están en stock mínimo.
Se filtra por ubicación, categoría y "solo en stock mínimo". El gráfico muestra los 10 más cerca de su mínimo
(barra = disponible, línea = mínimo). El disponible lo da `StockService.stock_disponible` de inventario: la pantalla
toma el `stock_service` de la ventana principal y, mientras no esté integrado, avisa que falta.

**R2 – Productos más vendidos y margen estimado.** Ranking por unidades vendidas en un período (y opcionalmente por
sucursal y categoría), con ingresos, costo, margen y margen %. Usa el precio y el costo guardados en cada renglón de
venta, descuenta las devoluciones y no cuenta los recargos de las cuotas como margen. Los productos vendidos a
pérdida se marcan en rojo con "⚠ pérdida".

## Datos de prueba

`python -m src.datos_prueba` carga 1 CD, 3 sucursales, 5 categorías, 4 proveedores, 23 productos (uno a pérdida,
para ver R2), su historial de precios, sus proveedores, el stock mínimo en cada ubicación y 3 clientes (consumidor
final, responsable inscripto y monotributista). Todo pasa por los servicios, con las mismas validaciones que la
interfaz. Solo funciona sobre una base sin productos. El stock y las ventas no se cargan: dependen de inventario.
