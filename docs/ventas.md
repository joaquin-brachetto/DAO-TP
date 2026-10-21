# Módulo de Ventas – vinchi

Alcance: implementación del paquete **Ventas** de `modelo_dominio.md` y del proceso P7. Este módulo no crea ni modifica la lógica de maestros, inventario o logística, que pertenecen a brache, pohlsi y turco.

## Trazabilidad con la consigna

| Elemento implementado | Qué representa | Cumplimiento |
|---|---|---|
| `Cliente` y `CondicionIva` | Comprador opcional, documento fiscal y condición frente al IVA | P7: permite asociar el cliente y emitir el comprobante apropiado |
| `Venta` | Operación de una sucursal con número, fecha, vendedor, estado, renglones y cobros | P7: registra una venta de uno o más productos |
| `DetalleVenta` | Producto, cantidad, precio y costo unitarios congelados al vender | P7; el costo histórico preserva el margen ante cambios posteriores de precio |
| `MedioPago`, `Efectivo`, `TarjetaDebito`, `TarjetaCredito`, `Transferencia` | Estrategias independientes de validación y cálculo de recargo | Patrón Strategy de vinchi; habilita cobro mixto |
| `Cobro` | Parte base, recargo, medio, autorización/referencia y fecha | P7: registra uno o varios medios; no almacena números ni claves de tarjeta |
| `Comprobante`, `Ticket`, `FacturaA`, `FacturaB`, `NotaCredito` | Documento con punto de venta, tipo, total y número correlativo | P7: comprobantes de venta y nota de crédito para la devolución |
| `ComprobanteFactory` | Selecciona Ticket, Factura A o Factura B según el cliente | Patrón Factory opcional documentado en el modelo |
| `Caja` y `MovimientoCaja` | Apertura/cierre por sucursal, saldo inicial, ingresos y reintegros | P7: cada cobro impacta como ingreso y cada devolución como egreso |
| `Devolucion` y `DetalleDevolucion` | Motivo, fecha, renglones, cantidades y decisión de reingreso | V5: requiere venta confirmada, plazo vigente y cantidad aún no devuelta |
| `ReporteVentas` | Ingresos cobrados agrupados por local y medio, con rango inclusivo de fechas | R6: ventas e ingresos por período, local y medio de pago; incluye conteo de ventas y se grafica en la pantalla |

## Validaciones aplicadas

- **V3:** se consulta `StockService.stock_disponible(ubicacion_id, producto_id)` al agregar el renglón y nuevamente dentro de la transacción de confirmación. Cada egreso se hace con `StockService.egresar`; un producto inexistente/inactivo o stock insuficiente bloquea la operación.
- **V5:** la devolución debe apuntar a una venta `CONFIRMADA`; cada renglón debe pertenecer a esa venta; el plazo predeterminado es de 30 días; la suma devuelta nunca puede superar la cantidad vendida. La cantidad se verifica otra vez dentro de la transacción para rechazar una devolución concurrente desactualizada.
- Los cobros base deben sumar exactamente el importe de los renglones. Los recargos se calculan por estrategia, se distribuyen entre renglones para devolver importes parciales con redondeo a centavos y quedan incluidos en el comprobante y en caja.
- La numeración de venta es correlativa por sucursal; la de comprobante, por punto de venta y tipo. Una caja abierta única por sucursal y las restricciones `UNIQUE`/`CHECK` refuerzan las reglas en SQLite.
- El precio y el costo del producto se copian al detalle de venta para conservar los valores históricos.

## Integración con Inventario

`VentasService` recibe un `StockService` por constructor. Usa exclusivamente el contrato compartido para consultar stock, egresar ventas y reingresar devoluciones. `VentanaPrincipal` crea el servicio compartido de inventario y pasa la misma instancia de `BaseDeDatos` a `VentasService`, de modo que los cambios de venta y stock participan de la transacción exterior. No se incluye un inventario alternativo ni un stub productivo.

La pantalla puede recibir `ventas_service` desde su ventana padre; así las acciones de venta y devolución operan sobre el mismo servicio y base compartidos.

## Pantallas y pruebas

El menú **Ventas** abre las pestañas de Venta, Devolución, Caja y Reporte R6. El comprobante aparece con número y tipo al consultar la venta en la base; la pantalla confirma su identificador. El reporte permite filtrar fechas y sucursal, presenta ingresos por medio de pago y grafica los totales.

Los tests de `tests/test_ventas.py` usan una base SQLite en memoria; hay casos unitarios con un doble y pruebas de integración con el `StockService` real, incluyendo rollback conjunto si falla el egreso. Cubren ventas, stock insuficiente, pagos mixtos, Strategy, Factura A/B, correlatividad, caja, devoluciones parciales, límites V5 y R6.