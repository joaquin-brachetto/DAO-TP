# Sistema de Ventas e Inventario: Centro de Distribución → Locales

Trabajo Práctico Integrador de **Desarrollo de Aplicaciones con Objetos** (UTN FRC, 2026), tema 3.

Aplicación de escritorio en Python para un comercio con varios locales que se abastecen desde un Centro de
Distribución (CD). Integra compras, inventario, logística interna y ventas, y mantiene el stock actualizado en
cada ubicación.

## Qué hace el sistema

- **Maestros:** sucursales, Centro de Distribución, categorías, productos con su historial de precios,
  proveedores y stock mínimo de cada producto en cada ubicación.
- **Compras:** órdenes de compra a proveedores que, al recibirse, suman stock en el CD. El sistema puede
  sugerir qué comprar según los faltantes del CD.
- **Reposición:** cada local registra sus necesidades (a mano o de forma automática cuando un producto llega a
  su stock mínimo) y se consolidan en una orden de reposición con origen en el CD y destino en el local.
- **Logística:** la orden se empaqueta en bultos con precinto de seguridad y remito, se despacha y el local la
  recibe controlando cada precinto. Un bulto con el precinto íntegro y coincidente queda *Verificado* y su
  mercadería pasa a estar disponible; si el precinto llega roto o no coincide, queda *Rechazado* y la
  mercadería va a merma.
- **Ventas:** ventas de uno o más productos, cobro con uno o varios medios de pago, emisión de ticket o factura,
  caja por sucursal y devoluciones con su impacto en stock y caja.
- **Reportes:** seis reportes con filtros, totales y gráfico, que se pueden exportar a PDF y a CSV.

El stock de cada producto en cada ubicación se divide en **pendiente** (llegó pero no se verificó),
**disponible** (verificado, se puede vender) y **merma** (rechazado). Solo se vende el disponible, y cada
cambio de stock queda registrado en un movimiento que no se puede modificar ni borrar.

### Cobertura de la consigna

| Consigna | Dónde se resuelve |
|----------|-------------------|
| P1 – Sucursales y Centro de Distribución | Maestros → Sucursales y Centro de Distribución |
| P2 – Productos, categorías, precios, stock mínimo y proveedores | Maestros |
| P3 – Consolidar necesidades en una orden de reposición | Inventario → Necesidades y Órdenes de reposición |
| P4 – Bultos con remito y precinto | Logística → Armado de bultos y remitos |
| P5 – Despacho desde el CD | Logística → Despacho |
| P6 – Recepción con control de precinto | Logística → Recepción en sucursal |
| P7 – Ventas, cobros, comprobantes y devoluciones | Ventas |
| V1 – Sin stock disponible hasta verificar; precinto roto → rechazo | Stock en tres partes y recepción por bulto |
| V2 – Trazabilidad inmutable del bulto | Historial de estados que solo admite altas |
| V3 – No vender más que lo disponible y verificado | Validación al vender y restricción en la base |
| V4 – Sin productos ni proveedores duplicados | SKU, código de barras y CUIT únicos |
| V5 – Devoluciones solo de ventas registradas y dentro de las reglas | Plazo de 30 días y cantidades devueltas ≤ vendidas |
| Opcional – Órdenes de compra sugeridas por faltantes | Inventario → Compras a proveedores |

## Instalación y ejecución

Requisitos: **Python 3.11 o superior** con Tkinter (en Windows y macOS viene incluido; en Linux puede hacer
falta el paquete `python3-tk`).

Desde la carpeta del proyecto:

```bash
python -m pip install -r requirements.txt
python main.py
```

`requirements.txt` instala **pytest** (tests), **ReportLab** (exportar a PDF) y **Matplotlib** (gráficos del PDF).
El resto usa la biblioteca estándar: `sqlite3`, `tkinter` y `csv`.

La primera vez se crea la base de datos SQLite en `datos/ventas.db` con todas sus tablas. Para empezar de cero,
basta con cerrar el programa y borrar ese archivo.

## Datos de prueba

Se cargan desde el menú, **en este orden**, sobre una base vacía:

1. **Archivo → Cargar datos de prueba.** Un CD, tres sucursales, cinco categorías, cuatro proveedores,
   23 productos con historial de precios, el stock mínimo de cada producto en cada ubicación y tres clientes
   (consumidor final, responsable inscripto y monotributista).
2. **Inventario → Cargar stock de prueba.** Una orden de compra recibida por proveedor, una carga inicial
   verificada en cada sucursal y una orden de compra pendiente. El *Café molido 250 g* queda justo en su mínimo
   en la Sucursal Centro: al venderle una unidad aparece la alerta de stock mínimo y se genera una necesidad de
   reposición automática.
3. **Logística → Cargar datos de prueba de logística.** Tres remitos despachados:
   - Sucursal Centro: dos bultos verificados; la orden cierra completa.
   - Sucursal Nueva Córdoba: un bulto verificado y dos rechazados (uno con el precinto roto y otro con un
     precinto que no coincide); la orden cierra con faltantes.
   - Sucursal Cerro de las Rosas: un remito todavía en tránsito, listo para recibirlo desde la pantalla.

   Además deja una orden de reposición pendiente, lista para armar sus bultos.

Cada paso exige el anterior. Las ventas no se cargan: se registran desde el menú Ventas.

## Menús

| Menú | Opción | Qué permite |
|------|--------|-------------|
| **Archivo** | Cargar datos de prueba · Salir | |
| **Maestros** | Sucursales y Centro de Distribución | Alta, modificación, baja y reactivación |
| | Categorías | Alta, modificación y eliminación (si no tiene productos) |
| | Productos y precios | Alta, modificación, baja y reactivación; historial de precios, proveedores del producto y stock mínimo por ubicación |
| | Proveedores | Alta, modificación, baja, reactivación y productos que provee |
| **Inventario** | Stock por ubicación | Disponible, pendiente y merma de cada producto, movimientos de un producto y alertas de stock mínimo |
| | Compras a proveedores | Crear, recibir y anular órdenes de compra; sugerir una orden según los faltantes del CD |
| | Necesidades de reposición | Registrar necesidades, sugerirlas según el stock mínimo y consolidarlas en una orden |
| | Órdenes de reposición | Estado y avance de cada orden (solicitado, preparado, recibido); iniciar la preparación y cerrarla |
| **Logística** | Armado de bultos y remitos | Empaquetar una orden de reposición en bultos, precintarlos y emitir el remito |
| | Despacho | Registrar la salida de uno o más remitos del CD (transportista y patente) |
| | Recepción en sucursal | Recibir un remito y controlar el precinto de cada bulto |
| | Trazabilidad de bultos | Buscar un bulto y ver su historial de estados |
| **Ventas** | Nueva venta | Venta con uno o más productos, pago mixto y comprobante |
| | Devoluciones | Devolución total o parcial de una venta, con reingreso a stock opcional y reintegro en caja |
| | Caja | Apertura, saldo y cierre de la caja de cada sucursal |
| **Reportes** | Los seis reportes | Ver la sección siguiente |

La barra inferior de la ventana principal avisa cuando una venta o un despacho deja un producto en su stock
mínimo.

## Reportes

Todos tienen filtros, un resumen con totales y un gráfico, y se exportan con los botones **Exportar PDF** y
**Exportar CSV**. El PDF incluye los filtros, el resumen, el gráfico y las tablas que se ven en pantalla.

| Reporte | Qué muestra | Filtros |
|---------|-------------|---------|
| **R1 – Existencias y stock mínimo** | Stock disponible de cada producto en cada ubicación frente a su mínimo, faltante y valorizado al costo. Primero los que están en su mínimo. | Ubicación, categoría, solo en stock mínimo |
| **R2 – Productos más vendidos y margen** | Ranking por unidades vendidas con ingresos, costo, margen y margen %. Usa el precio y el costo del momento de la venta, descuenta devoluciones y marca los productos vendidos a pérdida. | Período, sucursal, categoría |
| **R3 – Movimientos y valorización del inventario** | Entradas, salidas y movimientos internos por tipo; stock de cada ubicación valorizado al costo; detalle de cada movimiento con su documento de origen. | Período, ubicación, categoría, tipo de movimiento |
| **R4 – Tiempo promedio de tránsito CD → locales** | Tiempo entre el despacho en el CD y la verificación en el local: promedio, mínimo y máximo por sucursal, remitos en tránsito y remitos con rechazos. | Período, sucursal |
| **R5 – Bultos rechazados y mermas** | Bultos rechazados por precinto roto o que no coincide, tasa de rechazo por sucursal y mermas valorizadas por producto. | Período, sucursal, categoría, tipo de anomalía |
| **R6 – Ventas e ingresos** | Cantidad de ventas y total cobrado por sucursal y medio de pago. | Período, sucursal |

## Estructura del proyecto

```
main.py                   Punto de entrada
requirements.txt
pytest.ini                Configuración de pytest
src/
  config.py               Ruta de la base de datos y título de la aplicación
  excepciones.py          Errores de negocio (ValidacionError, EntidadDuplicadaError, ...)
  datos_prueba*.py        Datos de prueba de maestros, inventario y logística
  dominio/                Clases del dominio, una carpeta por paquete
    maestros/  inventario/  logistica/  ventas/
  persistencia/
    conexion.py           BaseDeDatos: conexión a SQLite y transacciones
    repositorio_base.py   RepositorioBase: guardar, obtener, listar, buscar y eliminar
    repositorio_*.py      Repositorios de cada paquete
    esquema/              Scripts SQL de creación de tablas, uno por paquete
  servicios/              Reglas de negocio y validaciones
  reportes/               Consultas de los seis reportes y exportación a PDF y CSV
  ui/
    ventana_principal.py  Ventana principal y menú
    componentes.py        Grilla, formulario y mensajes reutilizables
    graficos.py           Gráfico de barras sobre Canvas
    pantallas/            Pantallas de cada menú
tests/                    Tests con pytest
docs/
  modelo_dominio.md       Diagramas de clases y de estados
```

El código está separado en capas: las **pantallas** muestran datos y llaman a los **servicios**; los servicios
aplican las reglas de negocio sobre las clases del **dominio** y guardan con los **repositorios**, que son los
únicos que ejecutan SQL.

Los diagramas de clases de cada paquete y los diagramas de estados del bulto y de la orden de reposición están
en [`docs/modelo_dominio.md`](docs/modelo_dominio.md).

## Patrones de diseño

| Patrón | Dónde | Para qué |
|--------|-------|----------|
| **Singleton** | `BaseDeDatos` (`persistencia/conexion.py`) | Una única conexión a la base, compartida por toda la aplicación |
| **Repository** | `RepositorioBase` y sus subclases (`persistencia/`) | Separar las clases del dominio del SQL |
| **Observer** | `SujetoStock` / `StockService` → `ObservadorStock` (`servicios/observadores_stock.py`) | Cuando un producto llega a su stock mínimo, mostrar la alerta y generar la necesidad de reposición |
| **State** | `Bulto` → `EstadoBulto` y sus seis estados (`dominio/logistica/modelos.py`) | Ciclo de vida del bulto: cada estado define qué transiciones son válidas |
| **Strategy** | `MedioPago` → efectivo, débito, crédito y transferencia (`dominio/ventas/modelos.py`) | Cada medio de pago valida sus datos y calcula su recargo |
| **Strategy** | `ExportadorReporte` → `ExportadorPDF`, `ExportadorCSV` (`reportes/exportacion.py`) | Exportar cualquier reporte al formato elegido |
| **Factory** | `ComprobanteFactory` (`dominio/ventas/modelos.py`) | Crear el comprobante que corresponde (ticket, factura A o B, nota de crédito) |
| **Iterator** | `OrdenReposicion` → `IteradorDetalles`, `IteradorFaltantes` (`dominio/inventario/modelos.py`) | Recorrer los renglones de una orden, todos o solo los que tienen faltante |

## Tests

Los tests usan **pytest** y una base SQLite en memoria, así que no modifican `datos/ventas.db`.

```bash
python -m pytest              # todos los tests
python -m pytest -v           # con el nombre de cada test
python -m pytest -k ventas    # solo los que tienen "ventas" en el nombre
python -m pytest tests/test_stock_service.py
```

Cubren las reglas de negocio de cada paquete (incluidas las validaciones V1 a V5), las transiciones válidas e
inválidas del bulto, los patrones, los reportes y la exportación.
