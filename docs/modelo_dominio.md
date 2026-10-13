# Modelo de dominio – Diagrama de clases

Primera versión del modelo de dominio para discutir en grupo. Los diagramas están en
[Mermaid](https://mermaid.js.org/), así que GitHub los dibuja solos y se pueden editar como texto.

El modelo se divide en 4 paquetes, uno por integrante:

| Paquete | Responsable | Clases principales |
|---------|-------------|--------------------|
| Maestros | brache | `Ubicacion`, `Sucursal`, `CentroDistribucion`, `Categoria`, `Producto`, `HistorialPrecio`, `Proveedor`, `ProductoProveedor` |
| Inventario y reposición | pohlsi | `Stock`, `MovimientoStock`, `OrdenCompra`, `NecesidadReposicion`, `OrdenReposicion` |
| Logística | turco | `Remito`, `Bulto`, `Precinto`, `EstadoBulto` (State), `CambioEstadoBulto`, `Despacho`, `Recepcion`, `ControlBulto` |
| Ventas | vinchi | `Venta`, `DetalleVenta`, `Cobro`, `MedioPago` (Strategy), `Comprobante`, `Devolucion`, `Caja`, `MovimientoCaja`, `Cliente` |

---

## 1. Vista general

Solo las clases y cómo se conectan los paquetes (los atributos están en las secciones siguientes).

```mermaid
classDiagram
    direction LR

    class Ubicacion { <<abstract>> }
    class Sucursal
    class CentroDistribucion
    class Producto
    class Categoria
    class Proveedor

    class Stock
    class MovimientoStock
    class OrdenCompra
    class NecesidadReposicion
    class OrdenReposicion

    class Remito
    class Bulto
    class Precinto
    class Despacho
    class Recepcion

    class Venta
    class Cobro
    class Comprobante
    class Devolucion
    class Caja

    Ubicacion <|-- Sucursal
    Ubicacion <|-- CentroDistribucion
    Producto --> Categoria
    Producto "*" -- "*" Proveedor

    Stock --> Producto
    Stock --> Ubicacion
    MovimientoStock --> Stock
    OrdenCompra --> Proveedor
    OrdenCompra --> CentroDistribucion
    NecesidadReposicion --> Sucursal
    OrdenReposicion o-- NecesidadReposicion
    OrdenReposicion --> CentroDistribucion : origen
    OrdenReposicion --> Sucursal : destino

    Remito --> OrdenReposicion
    Remito *-- Bulto
    Bulto *-- Precinto
    Despacho o-- Remito
    Recepcion --> Remito

    Venta --> Sucursal
    Venta *-- Cobro
    Venta --> Comprobante
    Devolucion --> Venta
    Caja --> Sucursal
```

**Flujo de punta a punta:**
`OrdenCompra` (proveedor → CD) → `NecesidadReposicion` (cada local) → `OrdenReposicion` (CD → local)
→ `Bulto` + `Precinto` + `Remito` → `Despacho` → `Recepcion` → stock *Disponible* → `Venta` → `Devolucion`.

---

## 2. Maestros (brache)

```mermaid
classDiagram
    class Ubicacion {
        <<abstract>>
        -id: int
        -codigo: str
        -nombre: str
        -direccion: str
        -telefono: str
        -activa: bool
        +esCentroDistribucion() bool
    }
    class Sucursal {
        -puntoVenta: int
    }
    class CentroDistribucion {
        -capacidadM3: float
    }
    class Categoria {
        -id: int
        -nombre: str
        -descripcion: str
    }
    class Producto {
        -id: int
        -sku: str
        -codigoBarras: str
        -nombre: str
        -descripcion: str
        -unidadMedida: str
        -costoActual: decimal
        -precioVentaActual: decimal
        -activo: bool
        +actualizarPrecio(costo, precioVenta)
        +margenUnitario() decimal
    }
    class HistorialPrecio {
        -fechaDesde: datetime
        -fechaHasta: datetime
        -costo: decimal
        -precioVenta: decimal
    }
    class Proveedor {
        -id: int
        -cuit: str
        -razonSocial: str
        -email: str
        -telefono: str
        -direccion: str
        -activo: bool
    }
    class ProductoProveedor {
        -codigoEnProveedor: str
        -costoPactado: decimal
        -plazoEntregaDias: int
    }

    Ubicacion <|-- Sucursal
    Ubicacion <|-- CentroDistribucion
    Producto "*" --> "1" Categoria
    Producto "1" *-- "*" HistorialPrecio : historialPrecios
    Producto "1" -- "*" ProductoProveedor
    Proveedor "1" -- "*" ProductoProveedor
```

- **V4 (no duplicados):** `Producto.sku`, `Producto.codigoBarras` y `Proveedor.cuit` son únicos.
- `Sucursal` y `CentroDistribucion` heredan de `Ubicacion`. En la base de datos van en **una sola
  tabla `ubicacion` con un campo `tipo`**, así el stock se maneja igual en el CD y en los locales.
- `HistorialPrecio` cubre "administrar precios" y permite saber qué precio y costo tenía un producto en una fecha dada.
- El **stock mínimo** no está en `Producto` porque depende de cada local: está en `Stock` (paquete de inventario).

---

## 3. Inventario, compras y reposición (pohlsi)

```mermaid
classDiagram
    class Stock {
        -producto: Producto
        -ubicacion: Ubicacion
        -cantidadDisponible: int
        -cantidadPendiente: int
        -cantidadMerma: int
        -stockMinimo: int
        +hayDisponible(cantidad) bool
        +estaBajoMinimo() bool
    }
    class MovimientoStock {
        -id: int
        -fechaHora: datetime
        -tipo: TipoMovimiento
        -cantidad: int
        -costoUnitario: decimal
        -tipoDocumento: str
        -idDocumento: int
        -usuario: str
    }
    class TipoMovimiento {
        <<enumeration>>
        INGRESO_COMPRA
        EGRESO_DESPACHO
        INGRESO_PENDIENTE
        CONFIRMACION_VERIFICADO
        MERMA_RECHAZO
        EGRESO_VENTA
        REINGRESO_DEVOLUCION
        AJUSTE
    }
    class StockService {
        +stockDisponible(ubicacion, producto) int
        +ingresarPendiente(ubicacion, producto, cant, ref)
        +confirmarDisponible(ubicacion, producto, cant, ref)
        +registrarMerma(ubicacion, producto, cant, ref)
        +egresar(ubicacion, producto, cant, ref)
        +reingresar(ubicacion, producto, cant, ref)
        +suscribir(observador)
    }
    class ObservadorStock {
        <<interface>>
        +stockBajoMinimo(stock)
    }
    class AlertaStockMinimo {
        +stockBajoMinimo(stock)
    }
    class GeneradorNecesidades {
        +stockBajoMinimo(stock)
    }

    class OrdenCompra {
        -numero: int
        -fechaEmision: date
        -estado: EstadoOrdenCompra
        +recibir()
        +total() decimal
    }
    class DetalleOrdenCompra {
        -cantidad: int
        -costoUnitario: decimal
    }
    class NecesidadReposicion {
        -id: int
        -fecha: date
        -origen: str
        -estado: EstadoNecesidad
    }
    class DetalleNecesidad {
        -cantidadSolicitada: int
    }
    class OrdenReposicion {
        -numero: int
        -fechaEmision: datetime
        -estado: EstadoOrdenReposicion
        +consolidar(necesidades)
        +estaCompleta() bool
    }
    class DetalleOrdenReposicion {
        -cantidadSolicitada: int
        -cantidadPreparada: int
        -cantidadRecibida: int
    }
    class EstadoOrdenReposicion {
        <<enumeration>>
        PENDIENTE
        EN_PREPARACION
        DESPACHADA
        CERRADA_COMPLETA
        CERRADA_CON_FALTANTES
    }

    Stock "1" *-- "*" MovimientoStock : movimientos
    MovimientoStock --> TipoMovimiento
    StockService ..> Stock : gestiona
    StockService o-- "*" ObservadorStock : observadores
    ObservadorStock <|.. AlertaStockMinimo
    ObservadorStock <|.. GeneradorNecesidades
    GeneradorNecesidades ..> NecesidadReposicion : crea

    OrdenCompra "1" *-- "1..*" DetalleOrdenCompra
    NecesidadReposicion "1" *-- "1..*" DetalleNecesidad
    OrdenReposicion "1" o-- "1..*" NecesidadReposicion : consolida
    OrdenReposicion "1" *-- "1..*" DetalleOrdenReposicion
    OrdenReposicion --> EstadoOrdenReposicion
```

Relaciones con otros paquetes (no dibujadas para no ensuciar): `Stock → Producto, Ubicacion`;
`OrdenCompra → Proveedor, CentroDistribucion`; `DetalleX → Producto`;
`NecesidadReposicion → Sucursal`; `OrdenReposicion → CentroDistribucion (origen), Sucursal (destino)`.

- **Stock con tres "baldes":** *pendiente* (llegó o está en camino pero no se verificó), *disponible*
  (verificado, se puede vender) y *merma* (rechazado). Así se cumple **V1** de forma explícita.
- **Todo cambio de stock pasa por `StockService`** y deja un `MovimientoStock`. Los movimientos nunca
  se editan: alimentan los reportes de movimientos y valorización.
- **Patrón Observer:** `StockService` notifica a los `ObservadorStock` cuando un producto queda bajo el
  mínimo. `GeneradorNecesidades` crea automáticamente una `NecesidadReposicion` (el campo `origen`
  dice si fue manual o automática).
- **Consolidación (P3):** varias `NecesidadReposicion` de un mismo local se juntan en **una**
  `OrdenReposicion` con origen (CD) y destino (local), sumando cantidades por producto.

---

## 4. Logística (turco)

```mermaid
classDiagram
    class Remito {
        -numero: str
        -fechaEmision: datetime
        -estado: EstadoRemito
        +agregarBulto(bulto)
        +cerrarVerificacion()
    }
    class EstadoRemito {
        <<enumeration>>
        EMITIDO
        EN_TRANSITO
        RECIBIDO
        VERIFICADO
        VERIFICADO_CON_RECHAZOS
    }
    class Bulto {
        -codigo: str
        -fechaCreacion: datetime
        -pesoKg: float
        -estado: EstadoBulto
        +agregarProducto(producto, cantidad)
        +precintar(precinto)
        +despachar()
        +recibir()
        +verificar()
        +rechazar(motivo)
        ~cambiarEstado(nuevoEstado, usuario, observacion)
        +historial() list~CambioEstadoBulto~
    }
    class DetalleBulto {
        -cantidad: int
    }
    class Precinto {
        -numero: str
        -fechaColocacion: datetime
    }
    class CambioEstadoBulto {
        <<inmutable>>
        -fechaHora: datetime
        -estadoAnterior: str
        -estadoNuevo: str
        -usuario: str
        -observacion: str
    }

    class EstadoBulto {
        <<abstract>>
        +precintar(bulto, precinto)
        +despachar(bulto)
        +recibir(bulto)
        +verificar(bulto)
        +rechazar(bulto, motivo)
        +nombre() str
        +esFinal() bool
    }
    class Preparado
    class Precintado
    class EnTransito
    class Recibido
    class Verificado
    class Rechazado

    class Despacho {
        -id: int
        -fechaHoraSalida: datetime
        -transportista: str
        -patente: str
        +registrar()
    }
    class Recepcion {
        -id: int
        -fechaHoraLlegada: datetime
        -recibidoPor: str
        -observaciones: str
        +registrarControl(bulto, precintoLeido, integro)
        +cerrar()
    }
    class ControlBulto {
        -numeroPrecintoLeido: str
        -precintoIntegro: bool
        -observacion: str
        +esValido() bool
    }

    Remito "1" *-- "1..*" Bulto : bultos
    Remito --> EstadoRemito
    Bulto "1" *-- "1..*" DetalleBulto : contenido
    Bulto "1" -- "0..1" Precinto
    Bulto "1" *-- "1..*" CambioEstadoBulto : historial
    Bulto --> EstadoBulto : estado actual

    EstadoBulto <|-- Preparado
    EstadoBulto <|-- Precintado
    EstadoBulto <|-- EnTransito
    EstadoBulto <|-- Recibido
    EstadoBulto <|-- Verificado
    EstadoBulto <|-- Rechazado

    Despacho "1" o-- "1..*" Remito : remitos
    Recepcion "1" --> "1" Remito
    Recepcion "1" *-- "1..*" ControlBulto : controles
    ControlBulto --> Bulto
```

Relaciones con otros paquetes: `Remito → OrdenReposicion` (y de ahí origen/destino); `DetalleBulto → Producto`.

- **Patrón State:** `Bulto` delega cada acción en su `EstadoBulto` actual. Cada estado concreto
  implementa solo las transiciones válidas y en las demás lanza `TransicionInvalidaError`
  (por ejemplo, no se puede despachar un bulto sin precintar).
- **V2 (trazabilidad inmutable):** cada transición agrega un `CambioEstadoBulto` y nunca se modifica ni se borra
  (en Python, `@dataclass(frozen=True)`; en la base, solo `INSERT`).
- **Recepción (P6):** por cada bulto se registra un `ControlBulto`. Si el precinto leído coincide con el
  colocado y está íntegro, el bulto pasa a *Verificado*; si no, a *Rechazado*.
- **V1:** al cerrar la `Recepcion`, el remito pasa a `VERIFICADO` o `VERIFICADO_CON_RECHAZOS`. **Recién ahí**
  se llama a `StockService.confirmarDisponible` por los bultos verificados y a `registrarMerma` por los rechazados.

### Ciclo de vida del bulto

```mermaid
stateDiagram-v2
    [*] --> Preparado : se arma con productos de la orden
    Preparado --> Precintado : precintar(precinto)
    Precintado --> EnTransito : despachar()
    EnTransito --> Recibido : recibir()
    Recibido --> Verificado : verificar() [precinto íntegro y coincide]
    Recibido --> Rechazado : rechazar() [precinto roto o no coincide]
    Verificado --> [*]
    Rechazado --> [*]
```

| Estado | Efecto en stock |
|--------|-----------------|
| Preparado / Precintado | Sigue en el CD (disponible del CD) |
| En tránsito | Egresa del CD (`egresar`) e ingresa como **pendiente** en el local (`ingresarPendiente`) |
| Recibido | Sigue **pendiente**: no se puede vender |
| Verificado | Pasa de pendiente a **disponible** (`confirmarDisponible`) |
| Rechazado | Pasa de pendiente a **merma** (`registrarMerma`): rechazo logístico |

---

## 5. Ventas, cobros y devoluciones (vinchi)

```mermaid
classDiagram
    class Cliente {
        -id: int
        -documento: str
        -nombre: str
        -condicionIva: CondicionIva
        +esConsumidorFinal() bool
    }
    class Venta {
        -numero: int
        -fechaHora: datetime
        -vendedor: str
        -estado: EstadoVenta
        +agregarItem(producto, cantidad)
        +total() decimal
        +totalCobrado() decimal
        +confirmar()
    }
    class DetalleVenta {
        -cantidad: int
        -precioUnitario: decimal
        -costoUnitario: decimal
        -cantidadDevuelta: int
        +subtotal() decimal
        +cantidadDevolvible() int
    }
    class Cobro {
        -fechaHora: datetime
        -monto: decimal
        -recargo: decimal
        -nroAutorizacion: str
    }
    class MedioPago {
        <<interface>>
        +nombre() str
        +calcularRecargo(monto) decimal
        +validar(datos) bool
        +permiteReintegro() bool
    }
    class Efectivo
    class TarjetaDebito
    class TarjetaCredito {
        -cuotas: int
        -recargoPorCuota: float
    }
    class Transferencia

    class Comprobante {
        <<abstract>>
        -puntoVenta: int
        -numero: int
        -fechaEmision: datetime
        -total: decimal
        +tipo() str
    }
    class Ticket
    class FacturaA
    class FacturaB
    class NotaCredito
    class ComprobanteFactory {
        +crearParaVenta(venta) Comprobante
        +crearNotaCredito(devolucion) NotaCredito
    }

    class Devolucion {
        -numero: int
        -fechaHora: datetime
        -motivo: str
        +validar()
        +totalAReintegrar() decimal
    }
    class DetalleDevolucion {
        -cantidad: int
        -reingresaStock: bool
    }
    class Caja {
        -fechaApertura: datetime
        -fechaCierre: datetime
        -saldoInicial: decimal
        +saldoActual() decimal
        +registrarIngreso(monto, medio, ref)
        +registrarEgreso(monto, medio, ref)
    }
    class MovimientoCaja {
        -fechaHora: datetime
        -tipo: str
        -monto: decimal
        -concepto: str
    }

    Venta "*" --> "0..1" Cliente
    Venta "1" *-- "1..*" DetalleVenta : items
    Venta "1" *-- "1..*" Cobro : cobros
    Venta "1" --> "1" Comprobante
    Cobro --> MedioPago
    MedioPago <|.. Efectivo
    MedioPago <|.. TarjetaDebito
    MedioPago <|.. TarjetaCredito
    MedioPago <|.. Transferencia

    Comprobante <|-- Ticket
    Comprobante <|-- FacturaA
    Comprobante <|-- FacturaB
    Comprobante <|-- NotaCredito
    ComprobanteFactory ..> Comprobante : crea

    Devolucion "*" --> "1" Venta
    Devolucion "1" *-- "1..*" DetalleDevolucion
    DetalleDevolucion --> DetalleVenta
    Devolucion --> NotaCredito
    Caja "1" *-- "*" MovimientoCaja
    MovimientoCaja ..> Cobro : por cobro
    MovimientoCaja ..> Devolucion : por reintegro
```

Relaciones con otros paquetes: `Venta → Sucursal`; `DetalleVenta → Producto`; `Caja → Sucursal`.

- **V3:** al agregar un ítem y al confirmar la venta se consulta `StockService.stockDisponible` (solo
  stock **verificado**). Al confirmar, se llama a `egresar`.
- `DetalleVenta.costoUnitario` **guarda el costo al momento de la venta**, así el reporte de margen
  no cambia si después se actualiza el costo del producto.
- **Patrón Strategy:** cada `MedioPago` calcula su recargo y valida sus datos a su manera; la venta no
  pregunta "¿es tarjeta?". Una venta puede tener varios `Cobro` (pago mixto).
- **Patrón Factory:** `ComprobanteFactory` decide Ticket / Factura A / Factura B según el cliente.
- **V5 (devoluciones):** una `Devolucion` siempre apunta a una `Venta` existente; por cada ítem,
  `cantidad ≤ DetalleVenta.cantidadDevolvible()` y debe estar dentro del plazo (por ejemplo, 30 días).
  Si `reingresaStock` es verdadero, se llama a `StockService.reingresar`. Genera una `NotaCredito` y un egreso en `Caja`.

---

## 6. Dónde se cumple cada validación de la consigna

| Validación | Dónde se resuelve en el modelo |
|-----------|-------------------------------|
| V1 – Stock disponible solo tras verificar | `Stock.cantidadPendiente` vs. `cantidadDisponible`; `Recepcion.cerrar()` → `confirmarDisponible` / `registrarMerma` |
| V2 – Trazabilidad inmutable del bulto | `CambioEstadoBulto` (inmutable, solo se agrega) + patrón State |
| V3 – No vender más que el stock verificado | `Venta.agregarItem/confirmar` → `StockService.stockDisponible` |
| V4 – Sin productos ni proveedores duplicados | `Producto.sku`, `Producto.codigoBarras`, `Proveedor.cuit` únicos |
| V5 – Devoluciones válidas | `Devolucion → Venta` obligatoria + `DetalleVenta.cantidadDevolvible()` + plazo |

## 7. Patrones de diseño

| Patrón | Dónde | Responsable |
|--------|-------|-------------|
| **State** | `Bulto` / `EstadoBulto` y sus 6 estados | turco |
| **Strategy** | `MedioPago` y sus implementaciones | vinchi |
| **Observer** | `StockService` / `ObservadorStock` | pohlsi |
| **Factory Method** | `ComprobanteFactory` | vinchi |
| **Singleton** + **Repository** | Conexión a la BD y repositorios (capa de persistencia, no se ve en el dominio) | brache |

---

## 8. Decisiones abiertas para charlar en grupo

1. **¿Una orden de reposición por local o una para varios locales?** El modelo propone una por destino
   (la consigna dice "indicando origen y destino"). Si es para varios, el destino pasa a `DetalleOrdenReposicion`.
2. **Remito con bultos verificados y rechazados mezclados:** se propone que lo verificado se habilite y lo rechazado
   vaya a merma (`VERIFICADO_CON_RECHAZOS`). La alternativa estricta es rechazar el remito entero.
3. **Bulto rechazado:** ¿la mercadería se pierde (merma) o vuelve al CD? Se propone merma, porque el reporte pide "mermas por rotura de precinto".
4. **Plazo y condiciones de devolución:** definir el número de días y si un producto dañado reingresa al stock.
5. **Usuarios:** por ahora `usuario` es un texto. Si la cátedra pide login, se agrega una clase `Usuario` con rol.
6. **Opcionales:** `Cliente` ya está, así que "clientes frecuentes" sería fácil de sumar. Las órdenes de compra
   sugeridas salen casi gratis del Observer.
