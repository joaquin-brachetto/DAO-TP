# Modelo de dominio – Diagrama de clases

Diagramas de clases del sistema **tal como quedó implementado**. Los nombres de clases, atributos y
métodos son los mismos que en el código (`src/dominio/` y `src/servicios/`). Están escritos en
[Mermaid](https://mermaid.js.org/), así que GitHub los dibuja directamente.

El sistema se organiza en cuatro paquetes y una capa de persistencia común:

| Paquete | Carpeta | Clases principales | Procesos y validaciones de la consigna |
|---------|---------|--------------------|-----------------------------------------|
| Maestros | `dominio/maestros` | `Ubicacion`, `Sucursal`, `CentroDistribucion`, `Categoria`, `Producto`, `HistorialPrecio`, `Proveedor`, `ProductoProveedor`, `StockMinimo` | P1, P2, V4 |
| Inventario, compras y reposición | `dominio/inventario` | `Stock`, `MovimientoStock`, `OrdenCompra`, `NecesidadReposicion`, `OrdenReposicion` | P3, base de V1 y V3, compras sugeridas (opcional) |
| Logística | `dominio/logistica` | `Remito`, `Bulto`, `EstadoBulto` y sus estados, `Precinto`, `CambioEstadoBulto`, `Despacho`, `Recepcion`, `ControlBulto` | P4, P5, P6, V1, V2 |
| Ventas | `dominio/ventas` | `Venta`, `DetalleVenta`, `Cobro`, `MedioPago` y sus medios, `Comprobante` y sus tipos, `Devolucion`, `Caja`, `Cliente` | P7, V3, V5 |
| Persistencia | `persistencia` | `BaseDeDatos`, `RepositorioBase` | — |

**Convenciones de los diagramas**

- Las entidades son `@dataclass`; sus atributos son públicos (`+`). `id` vale `None` hasta que se guarda.
- Entre paquetes las entidades se relacionan **por id** (por ejemplo `Producto.categoria_id`): la
  relación se dibuja con el nombre del atributo que la implementa.
- La lógica que necesita la base de datos o coordina varias entidades está en las clases `...Service`
  de `src/servicios/`, que también se muestran.

---

## 1. Vista general

```mermaid
classDiagram
    direction LR

    class Ubicacion { <<abstract>> }
    class Sucursal
    class CentroDistribucion
    class Producto
    class Categoria
    class Proveedor
    class StockMinimo

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
    StockMinimo --> Producto
    StockMinimo --> Ubicacion

    Stock --> Producto
    Stock --> Ubicacion
    MovimientoStock --> Stock
    OrdenCompra --> Proveedor
    OrdenCompra --> CentroDistribucion : destino
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
→ `Bulto` + `Precinto` + `Remito` → `Despacho` → `Recepcion` → stock *disponible* → `Venta` → `Devolucion`.

Todos los cambios de stock de ese flujo pasan por **`StockService`** y quedan registrados como
`MovimientoStock`, con una `Referencia` al documento que los originó (orden de compra, remito, venta o
devolución).

---

## 2. Maestros

```mermaid
classDiagram
    class TipoUbicacion {
        <<enumeration>>
        SUCURSAL
        CD
    }
    class Ubicacion {
        <<abstract>>
        +id: int
        +codigo: str
        +nombre: str
        +direccion: str
        +telefono: str
        +activa: bool
        +tipo()* TipoUbicacion
        +es_centro_distribucion() bool
        +validar()
    }
    class Sucursal {
        +punto_venta: int
        +tipo() TipoUbicacion
        +validar()
    }
    class CentroDistribucion {
        +capacidad_m3: float
        +tipo() TipoUbicacion
        +validar()
    }
    class Categoria {
        +id: int
        +nombre: str
        +descripcion: str
        +validar()
    }
    class Producto {
        +id: int
        +sku: str
        +codigo_barras: str
        +nombre: str
        +descripcion: str
        +unidad_medida: str
        +categoria_id: int
        +costo_actual: Decimal
        +precio_venta_actual: Decimal
        +activo: bool
        +validar()
        +margen_unitario() Decimal
        +margen_porcentual() Decimal
    }
    class HistorialPrecio {
        +id: int
        +producto_id: int
        +costo: Decimal
        +precio_venta: Decimal
        +fecha_desde: datetime
        +fecha_hasta: datetime
        +esta_vigente() bool
    }
    class Proveedor {
        +id: int
        +cuit: str
        +razon_social: str
        +email: str
        +telefono: str
        +direccion: str
        +activo: bool
        +validar()
    }
    class ProductoProveedor {
        +producto_id: int
        +proveedor_id: int
        +codigo_en_proveedor: str
        +costo_pactado: Decimal
        +plazo_entrega_dias: int
        +validar()
    }
    class StockMinimo {
        +producto_id: int
        +ubicacion_id: int
        +cantidad_minima: int
        +validar()
        +esta_en_minimo(disponible) bool
        +faltante(disponible) int
    }

    Ubicacion <|-- Sucursal
    Ubicacion <|-- CentroDistribucion
    Ubicacion --> TipoUbicacion
    Producto "*" --> "1" Categoria : categoria_id
    Producto "1" -- "*" HistorialPrecio : producto_id
    Producto "1" -- "*" ProductoProveedor
    Proveedor "1" -- "*" ProductoProveedor
    Producto "1" -- "*" StockMinimo
    StockMinimo "*" --> "1" Ubicacion : ubicacion_id
```

```mermaid
classDiagram
    class UbicacionService {
        +listar(incluir_inactivas) list~Ubicacion~
        +listar_sucursales(incluir_inactivas) list~Sucursal~
        +obtener(ubicacion_id) Ubicacion
        +guardar(ubicacion) Ubicacion
        +dar_de_baja(ubicacion_id)
        +reactivar(ubicacion_id) Ubicacion
    }
    class CategoriaService {
        +listar() list~Categoria~
        +guardar(categoria) Categoria
        +eliminar(categoria_id)
    }
    class ProductoService {
        +listar(incluir_inactivos) list~Producto~
        +buscar(texto, incluir_inactivos) list~Producto~
        +obtener(producto_id) Producto
        +guardar(producto) Producto
        +dar_de_baja(producto_id)
        +reactivar(producto_id) Producto
        +historial_precios(producto_id) list~HistorialPrecio~
        +precio_vigente_en(producto_id, momento) HistorialPrecio
        +proveedores_de(producto_id) list~ProductoProveedor~
        +asignar_proveedor(relacion) ProductoProveedor
        +quitar_proveedor(producto_id, proveedor_id)
    }
    class ProveedorService {
        +listar(incluir_inactivos) list~Proveedor~
        +obtener(proveedor_id) Proveedor
        +guardar(proveedor) Proveedor
        +dar_de_baja(proveedor_id)
        +reactivar(proveedor_id) Proveedor
        +productos_de(proveedor_id) list~ProductoProveedor~
    }
    class StockMinimoService {
        +definir(minimo) StockMinimo
        +quitar(producto_id, ubicacion_id)
        +de_producto(producto_id) list~StockMinimo~
        +de_ubicacion(ubicacion_id) dict
        +minimo(producto_id, ubicacion_id) int
        +esta_en_minimo(producto_id, ubicacion_id, disponible) bool
    }
```

- **Herencia:** `Sucursal` y `CentroDistribucion` heredan de la clase abstracta `Ubicacion`, que obliga a
  definir `tipo()`. En la base van en **una sola tabla `ubicacion` con un campo `tipo`**, así el stock se
  maneja igual en el CD y en los locales. Solo puede haber un CD activo.
- **V4 (no duplicados):** `Producto.sku`, `Producto.codigo_barras` y `Proveedor.cuit` son únicos. Se valida
  en el servicio (con un mensaje claro) y además con `UNIQUE` en la base. El CUIT se valida con su dígito
  verificador.
- **Precios:** al cambiar el costo o el precio, `ProductoService` cierra el `HistorialPrecio` vigente y abre
  uno nuevo, así se sabe qué precio tenía un producto en cualquier fecha.
- **`StockMinimo`** es el nivel mínimo de cada producto **en cada ubicación** (P2). Un producto está *en stock
  mínimo* cuando su disponible llega al mínimo o queda por debajo; inventario lo consulta para el Observer.
- Las bajas son **lógicas** (`activo` / `activa`): un producto dado de baja sigue ocupando su SKU.

---

## 3. Inventario, compras y reposición

```mermaid
classDiagram
    class Referencia {
        <<inmutable>>
        +tipo_documento: str
        +documento_id: int
        +usuario: str
    }
    class Stock {
        +id: int
        +producto_id: int
        +ubicacion_id: int
        +cantidad_disponible: int
        +cantidad_pendiente: int
        +cantidad_merma: int
        +hay_disponible(cantidad) bool
    }
    class MovimientoStock {
        <<inmutable>>
        +id: int
        +stock_id: int
        +fecha_hora: datetime
        +tipo: TipoMovimiento
        +cantidad: int
        +costo_unitario: Decimal
        +tipo_documento: str
        +documento_id: int
        +usuario: str
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
        -observadores: list~ObservadorStock~
        +suscribir(observador)
        +desuscribir(observador)
        +stock_disponible(ubicacion_id, producto_id) int
        +stock_de(ubicacion_id, producto_id) Stock
        +listar_ubicacion(ubicacion_id) list~Stock~
        +ingresar_compra(ubicacion_id, producto_id, cantidad, ref, costo_unitario) Stock
        +ingresar_pendiente(ubicacion_id, producto_id, cantidad, ref) Stock
        +confirmar_disponible(ubicacion_id, producto_id, cantidad, ref) Stock
        +registrar_merma(ubicacion_id, producto_id, cantidad, ref) Stock
        +egresar(ubicacion_id, producto_id, cantidad, ref, tipo) Stock
        +reingresar(ubicacion_id, producto_id, cantidad, ref) Stock
        -_notificar(stock)
    }
    class ObservadorStock {
        <<abstract>>
        +stock_bajo_minimo(stock)*
    }
    class AlertaStockMinimo {
        +stock_bajo_minimo(stock)
        +alertas() list~AlertaStock~
        +descartar(producto_id, ubicacion_id)
        +limpiar()
    }
    class GeneradorNecesidades {
        +stock_bajo_minimo(stock)
    }

    Stock "1" -- "*" MovimientoStock : stock_id
    MovimientoStock --> TipoMovimiento
    StockService ..> Stock : gestiona
    StockService ..> MovimientoStock : registra
    StockService ..> Referencia : recibe
    StockService o-- "*" ObservadorStock : notifica
    ObservadorStock <|-- AlertaStockMinimo
    ObservadorStock <|-- GeneradorNecesidades
```

```mermaid
classDiagram
    class OrdenCompra {
        +id: int
        +numero: int
        +proveedor_id: int
        +destino_id: int
        +fecha_emision: date
        +estado: EstadoOrdenCompra
        +detalles: list~DetalleOrdenCompra~
        +total() Decimal
    }
    class DetalleOrdenCompra {
        +producto_id: int
        +cantidad: int
        +costo_unitario: Decimal
        +subtotal() Decimal
    }
    class EstadoOrdenCompra {
        <<enumeration>>
        PENDIENTE
        RECIBIDA
        ANULADA
    }
    class NecesidadReposicion {
        +id: int
        +ubicacion_id: int
        +fecha: date
        +origen: OrigenNecesidad
        +estado: EstadoNecesidad
        +orden_reposicion_id: int
        +detalles: list~DetalleNecesidad~
    }
    class DetalleNecesidad {
        +producto_id: int
        +cantidad_solicitada: int
    }
    class OrigenNecesidad {
        <<enumeration>>
        MANUAL
        AUTOMATICA
    }
    class EstadoNecesidad {
        <<enumeration>>
        PENDIENTE
        CONSOLIDADA
        ANULADA
    }
    class OrdenReposicion {
        +id: int
        +numero: int
        +fecha_emision: datetime
        +origen_id: int
        +destino_id: int
        +estado: EstadoOrdenReposicion
        +detalles: list~DetalleOrdenReposicion~
        +esta_completa() bool
    }
    class DetalleOrdenReposicion {
        +producto_id: int
        +cantidad_solicitada: int
        +cantidad_preparada: int
        +cantidad_recibida: int
        +faltante() int
    }
    class EstadoOrdenReposicion {
        <<enumeration>>
        PENDIENTE
        EN_PREPARACION
        DESPACHADA
        CERRADA_COMPLETA
        CERRADA_CON_FALTANTES
    }
    class ComprasService {
        +crear_orden(proveedor_id, destino_id, renglones, fecha) OrdenCompra
        +recibir_orden(orden_id, usuario) OrdenCompra
        +anular_orden(orden_id) OrdenCompra
        +sugerir_compras(cd_id) SugerenciaCompra
        +obtener(orden_id) OrdenCompra
        +listar(estado) list~OrdenCompra~
    }
    class ReposicionService {
        +crear_necesidad(sucursal_id, renglones, origen, fecha) NecesidadReposicion
        +anular_necesidad(necesidad_id) NecesidadReposicion
        +sugerir_necesidad(sucursal_id, producto_id) list
        +consolidar(necesidad_ids, fecha) OrdenReposicion
        +iniciar_preparacion(orden_id) OrdenReposicion
        +registrar_preparado(orden_id, producto_id, cantidad) OrdenReposicion
        +marcar_despachada(orden_id) OrdenReposicion
        +registrar_recibido(orden_id, producto_id, cantidad) OrdenReposicion
        +cerrar(orden_id) OrdenReposicion
    }

    OrdenCompra "1" *-- "1..*" DetalleOrdenCompra
    OrdenCompra --> EstadoOrdenCompra
    NecesidadReposicion "1" *-- "1..*" DetalleNecesidad
    NecesidadReposicion --> OrigenNecesidad
    NecesidadReposicion --> EstadoNecesidad
    OrdenReposicion "1" o-- "1..*" NecesidadReposicion : consolida
    OrdenReposicion "1" *-- "1..*" DetalleOrdenReposicion
    OrdenReposicion --> EstadoOrdenReposicion
    ComprasService ..> OrdenCompra
    ComprasService ..> StockService : ingresar_compra
    ReposicionService ..> NecesidadReposicion
    ReposicionService ..> OrdenReposicion
    GeneradorNecesidades ..> ReposicionService : crear_necesidad
```

Relaciones con otros paquetes: `Stock → Producto, Ubicacion`; `OrdenCompra → Proveedor, CentroDistribucion (destino)`;
`DetalleX → Producto`; `NecesidadReposicion → Sucursal`;
`OrdenReposicion → CentroDistribucion (origen), Sucursal (destino)`.

- **Stock con tres "baldes":** *pendiente* (llegó al local pero no se verificó), *disponible* (verificado, se
  puede vender) y *merma* (rechazado). Así se cumple **V1** de forma explícita: solo el disponible se vende.
- **V3:** `StockService.egresar` lanza `StockInsuficienteError` si no alcanza el disponible; además la base
  tiene `CHECK (cantidad_disponible >= 0)`.
- **Trazabilidad:** todo cambio de stock pasa por `StockService` y deja un `MovimientoStock`. Los movimientos
  no se pueden modificar ni borrar (triggers en la base) y alimentan los reportes de movimientos,
  valorización y tiempo de tránsito.
- **Patrón Observer:** `StockService` es el *sujeto*. Después de cada egreso consulta `StockMinimoService` y,
  si el producto quedó en su mínimo, notifica a todos los `ObservadorStock` suscriptos.
  `AlertaStockMinimo` muestra la alerta en pantalla y `GeneradorNecesidades` crea una
  `NecesidadReposicion` **automática** para el local (sin duplicar una que ya esté abierta).
- **P3 (consolidación):** `ReposicionService.consolidar` junta las necesidades pendientes de **un** local en
  **una** `OrdenReposicion` con origen (CD) y destino (local), sumando cantidades por producto.
- **Compras (opcional de la consigna):** `ComprasService.sugerir_compras` calcula, para cada producto del CD
  en su mínimo, *mínimo − disponible − lo ya pedido*, agrupado por el proveedor con menor costo pactado.

### Ciclo de vida de la orden de reposición

```mermaid
stateDiagram-v2
    [*] --> Pendiente : consolidar(necesidades)
    Pendiente --> EnPreparacion : iniciar_preparacion()
    EnPreparacion --> Despachada : marcar_despachada()
    Despachada --> CerradaCompleta : cerrar() [recibido = solicitado]
    Despachada --> CerradaConFaltantes : cerrar() [recibido < solicitado]
    CerradaCompleta --> [*]
    CerradaConFaltantes --> [*]

    EnPreparacion : En preparación
    Despachada : Despachada
    CerradaCompleta : Cerrada completa
    CerradaConFaltantes : Cerrada con faltantes
```

Las transiciones válidas están en la tabla `TRANSICIONES` de `reposicion_service.py`; cualquier otra lanza
`ValidacionError`. El avance lo informa logística al armar los bultos, despachar y recibir.

---

## 4. Logística

```mermaid
classDiagram
    class Remito {
        +id: int
        +numero: str
        +orden_reposicion_id: int
        +origen_id: int
        +destino_id: int
        +fecha_emision: datetime
        +estado: EstadoRemito
        +despacho_id: int
        +bultos: list~Bulto~
        +agregar_bulto(bulto)
        +cerrar_verificacion() EstadoRemito
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
        +id: int
        +codigo: str
        +remito_id: int
        +fecha_creacion: datetime
        +peso_kg: float
        +estado: EstadoBulto
        +motivo_rechazo: str
        +precinto: Precinto
        +detalles: list~DetalleBulto~
        +cambios_estado: list~CambioEstadoBulto~
        +agregar_producto(producto_id, cantidad)
        +precintar(precinto, usuario, fecha_hora)
        +despachar(usuario, fecha_hora)
        +recibir(usuario, fecha_hora)
        +verificar(usuario, observacion, fecha_hora)
        +rechazar(motivo, usuario, fecha_hora)
        +nombre_estado() str
        +es_estado_final() bool
        +total_unidades() int
        +historial() tuple
        -_cambiar_estado(nuevo, usuario, observacion, fecha_hora)
    }
    class DetalleBulto {
        +producto_id: int
        +cantidad: int
    }
    class Precinto {
        +numero: str
        +fecha_colocacion: datetime
        +usuario_colocacion: str
    }
    class CambioEstadoBulto {
        <<inmutable>>
        +fecha_hora: datetime
        +estado_anterior: str
        +estado_nuevo: str
        +usuario: str
        +observacion: str
    }

    class EstadoBulto {
        <<abstract>>
        +nombre()* str
        +es_final()* bool
        +agregar_producto(bulto, producto_id, cantidad)
        +precintar(bulto, precinto, usuario, fecha_hora)
        +despachar(bulto, usuario, fecha_hora)
        +recibir(bulto, usuario, fecha_hora)
        +verificar(bulto, usuario, observacion, fecha_hora)
        +rechazar(bulto, motivo, usuario, fecha_hora)
    }
    class Preparado {
        +agregar_producto(bulto, producto_id, cantidad)
        +precintar(bulto, precinto, usuario, fecha_hora)
    }
    class Precintado {
        +despachar(bulto, usuario, fecha_hora)
    }
    class EnTransito {
        +recibir(bulto, usuario, fecha_hora)
    }
    class Recibido {
        +verificar(bulto, usuario, observacion, fecha_hora)
        +rechazar(bulto, motivo, usuario, fecha_hora)
    }
    class Verificado
    class Rechazado

    class Despacho {
        +id: int
        +fecha_hora_salida: datetime
        +transportista: str
        +patente: str
        +usuario: str
        +observaciones: str
        +remito_ids: list~int~
    }
    class Recepcion {
        +id: int
        +remito_id: int
        +fecha_hora_llegada: datetime
        +recibido_por: str
        +observaciones: str
        +cerrada: bool
        +controles: list~ControlBulto~
    }
    class ControlBulto {
        +bulto_id: int
        +numero_precinto_leido: str
        +precinto_integro: bool
        +coincide_precinto: bool
        +resultado: ResultadoControl
        +observacion: str
        +fecha_hora_control: datetime
        +es_valido(precinto_esperado) bool
    }
    class ResultadoControl {
        <<enumeration>>
        VERIFICADO
        RECHAZADO
    }

    Remito "1" *-- "1..*" Bulto : bultos
    Remito --> EstadoRemito
    Bulto "1" *-- "1..*" DetalleBulto : detalles
    Bulto "1" *-- "0..1" Precinto
    Bulto "1" *-- "1..*" CambioEstadoBulto : cambios_estado
    Bulto --> EstadoBulto : estado actual

    EstadoBulto <|-- Preparado
    EstadoBulto <|-- Precintado
    EstadoBulto <|-- EnTransito
    EstadoBulto <|-- Recibido
    EstadoBulto <|-- Verificado
    EstadoBulto <|-- Rechazado

    Despacho "1" o-- "1..*" Remito : remito_ids
    Recepcion "1" --> "1" Remito : remito_id
    Recepcion "1" *-- "1..*" ControlBulto : controles
    ControlBulto --> Bulto : bulto_id
    ControlBulto --> ResultadoControl
```

```mermaid
classDiagram
    class LogisticaService {
        +armar_remito(orden_reposicion_id, bultos, numero_remito, usuario, fecha_hora) Remito
        +crear_remito(orden_reposicion_id, numero_remito, fecha_emision) Remito
        +armar_bulto(remito_id, renglones, codigo, peso_kg, numero_precinto, usuario, fecha_hora) Bulto
        +precintar_bulto(bulto_id, numero_precinto, usuario, fecha_hora) Bulto
        +registrar_despacho(remito_ids, transportista, patente, usuario, observaciones, fecha_hora) Despacho
        +recibir_remito(remito_id, recibido_por, observaciones, fecha_hora) Recepcion
        +registrar_control_bulto(recepcion_id, bulto_id, numero_precinto_leido, precinto_integro, observacion, usuario, fecha_hora) ControlBulto
        +cerrar_recepcion(recepcion_id, usuario, fecha_hora) Recepcion
        +procesar_recepcion_completa(remito_id, recibido_por, controles_por_bulto, observaciones, fecha_hora) Recepcion
        +historial_bulto(bulto_id) tuple
    }
    LogisticaService ..> Remito
    LogisticaService ..> Bulto
    LogisticaService ..> StockService : egresar, ingresar_pendiente, confirmar_disponible, registrar_merma
    LogisticaService ..> ReposicionService : avance de la orden
```

Relaciones con otros paquetes: `Remito → OrdenReposicion` (y de ahí origen y destino); `DetalleBulto → Producto`.

- **Patrón State:** `Bulto` delega cada acción en su `EstadoBulto` actual. La clase abstracta implementa todas
  las acciones lanzando `TransicionInvalidaError`; cada estado concreto redefine **solo** las que son válidas
  para él (por ejemplo, `Precintado` solo sabe `despachar`). `Verificado` y `Rechazado` son finales.
- **V2 (trazabilidad inmutable):** cada transición agrega un `CambioEstadoBulto` (`@dataclass(frozen=True)`).
  En la base, la tabla `cambio_estado_bulto` tiene triggers que impiden `UPDATE` y `DELETE`.
- **P4:** a partir de una orden de reposición se arman los bultos, cada uno con su precinto de número único,
  y se agrupan en un remito.
- **P5:** al despachar, el stock egresa del CD (`egresar` con `EGRESO_DESPACHO`) e ingresa como **pendiente** en
  el local (`ingresar_pendiente`). Todos los movimientos llevan la referencia `REMITO`.
- **P6 y V1:** en la recepción se registra un `ControlBulto` por bulto. Si el precinto leído coincide con el
  colocado y está íntegro, el bulto pasa a *Verificado*; si no, a *Rechazado* (rechazo logístico). Al cerrar la
  recepción el remito queda `VERIFICADO` o `VERIFICADO_CON_RECHAZOS`, y **recién ahí** se llama a
  `confirmar_disponible` por lo verificado y a `registrar_merma` por lo rechazado.

### Ciclo de vida del bulto

```mermaid
stateDiagram-v2
    [*] --> Preparado : armar_bulto()
    Preparado --> Preparado : agregar_producto()
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
| En tránsito | Egresa del CD e ingresa como **pendiente** en el local |
| Recibido | Sigue **pendiente**: no se puede vender |
| Verificado | Pasa de pendiente a **disponible** |
| Rechazado | Pasa de pendiente a **merma** (rechazo logístico) |

---

## 5. Ventas, cobros y devoluciones

```mermaid
classDiagram
    class Cliente {
        +id: int
        +documento: str
        +nombre: str
        +condicion_iva: CondicionIva
        +es_consumidor_final() bool
    }
    class CondicionIva {
        <<enumeration>>
        CONSUMIDOR_FINAL
        RESPONSABLE_INSCRIPTO
        MONOTRIBUTISTA
        EXENTO
    }
    class Venta {
        +id: int
        +ubicacion_id: int
        +numero: int
        +fecha_hora: datetime
        +vendedor: str
        +estado: EstadoVenta
        +cliente_id: int
        +detalles: list~DetalleVenta~
        +cobros: list~Cobro~
        +comprobante: Comprobante
        +total() Decimal
        +total_cobrado() Decimal
    }
    class DetalleVenta {
        +id: int
        +producto_id: int
        +cantidad: int
        +precio_unitario: Decimal
        +costo_unitario: Decimal
        +cantidad_devuelta: int
        +recargo_asignado: Decimal
        +monto_reintegrado: Decimal
        +subtotal() Decimal
        +cantidad_devolvible() int
    }
    class Cobro {
        +medio_pago: str
        +monto: Decimal
        +recargo: Decimal
        +nro_autorizacion: str
        +fecha_hora: datetime
    }
    class MedioPago {
        <<abstract>>
        +tipo: str
        +calcular_recargo(monto)* Decimal
        +validar(datos)* bool
        +permite_reintegro() bool
    }
    class Efectivo
    class TarjetaDebito
    class TarjetaCredito {
        +cuotas: int
        +recargo_por_cuota: Decimal
    }
    class Transferencia

    class Comprobante {
        +punto_venta: int
        +numero: int
        +fecha_emision: datetime
        +total: Decimal
        +tipo() str
    }
    class Ticket
    class FacturaA
    class FacturaB
    class NotaCredito
    class ComprobanteFactory {
        +tipo_para_venta(cliente) str
        +crear_para_venta(cliente, punto_venta, numero, fecha_emision, total) Comprobante
        +crear_nota_credito(punto_venta, numero, fecha_emision, total) NotaCredito
    }

    class Devolucion {
        +id: int
        +venta_id: int
        +fecha_hora: datetime
        +motivo: str
        +detalles: list~DetalleDevolucion~
        +total_reintegrar: Decimal
        +comprobante: NotaCredito
    }
    class DetalleDevolucion {
        +detalle_venta_id: int
        +cantidad: int
        +reingresa_stock: bool
        +monto_reintegrado: Decimal
    }
    class Caja {
        +id: int
        +ubicacion_id: int
        +fecha_apertura: datetime
        +fecha_cierre: datetime
        +saldo_inicial: Decimal
        +saldo_actual(ingresos, egresos) Decimal
    }
    class MovimientoCaja {
        +tipo: str
        +monto: Decimal
        +concepto: str
        +medio_pago: str
        +fecha_hora: datetime
    }

    Venta "*" --> "0..1" Cliente : cliente_id
    Cliente --> CondicionIva
    Venta "1" *-- "1..*" DetalleVenta : detalles
    Venta "1" *-- "1..*" Cobro : cobros
    Venta "1" --> "1" Comprobante
    Cobro ..> MedioPago : se calcula con
    MedioPago <|-- Efectivo
    MedioPago <|-- TarjetaDebito
    MedioPago <|-- TarjetaCredito
    MedioPago <|-- Transferencia

    Comprobante <|-- Ticket
    Comprobante <|-- FacturaA
    Comprobante <|-- FacturaB
    Comprobante <|-- NotaCredito
    ComprobanteFactory ..> Comprobante : crea

    Devolucion "*" --> "1" Venta : venta_id
    Devolucion "1" *-- "1..*" DetalleDevolucion
    DetalleDevolucion --> DetalleVenta : detalle_venta_id
    Devolucion --> NotaCredito
    Caja "1" *-- "*" MovimientoCaja
```

```mermaid
classDiagram
    class VentasService {
        +registrar_cliente(cliente) Cliente
        +abrir_caja(ubicacion_id, saldo_inicial) Caja
        +cerrar_caja(ubicacion_id) Decimal
        +saldo_caja_abierta(ubicacion_id) Decimal
        +validar_disponibilidad(ubicacion_id, producto_id, cantidad)
        +registrar_venta(ubicacion_id, items, pagos, cliente_id, vendedor, fecha_hora) int
        +registrar_devolucion(venta_id, detalles, motivo, fecha_hora) int
    }
    class PagoSolicitado {
        +medio_pago: str
        +monto: Decimal
        +datos: dict
        +cuotas: int
    }
    VentasService ..> PagoSolicitado : recibe
    VentasService ..> MedioPago : crear_medio_pago()
    VentasService ..> ComprobanteFactory
    VentasService ..> StockService : stock_disponible, egresar, reingresar
```

Relaciones con otros paquetes: `Venta → Sucursal`; `DetalleVenta → Producto`; `Caja → Sucursal`.

- **P7:** una venta tiene uno o más renglones, uno o más cobros (pago mixto) y un comprobante con numeración
  correlativa por local. Cada cobro y cada reintegro queda como `MovimientoCaja` de la caja abierta del local.
- **V3:** antes de confirmar se consulta `StockService.stock_disponible` (solo stock **verificado**) y al
  confirmar se llama a `egresar`. Todo ocurre en una transacción: si algo falla, no queda ni la venta, ni los
  cobros, ni el movimiento de stock.
- `DetalleVenta` guarda **el precio y el costo del momento de la venta**, así el reporte de margen no cambia
  si después se actualiza el producto.
- **Patrón Strategy:** cada `MedioPago` calcula su recargo y valida sus datos a su manera (por ejemplo,
  `TarjetaCredito` suma un recargo por cuota); la venta no pregunta "¿es tarjeta?". `crear_medio_pago()` elige
  la estrategia según el medio indicado.
- **Patrón Factory:** `ComprobanteFactory` decide Ticket, Factura A o Factura B según la condición frente al IVA
  del cliente, y crea la Nota de crédito de las devoluciones.
- **V5 (devoluciones):** una `Devolucion` siempre apunta a una `Venta` registrada; por cada renglón,
  `cantidad ≤ DetalleVenta.cantidad_devolvible()`, el renglón debe pertenecer a esa venta y la devolución debe
  estar dentro del plazo (30 días). Si `reingresa_stock` es verdadero se llama a `StockService.reingresar`.
  Genera una `NotaCredito` y un egreso en la `Caja`.

---

## 6. Persistencia

```mermaid
classDiagram
    class BaseDeDatos {
        <<singleton>>
        -_instancia: BaseDeDatos$
        +ruta: str
        +inicializar_esquema(carpeta)
        +transaccion()
        +ejecutar(sql, parametros) Cursor
        +consultar(sql, parametros) list
        +consultar_uno(sql, parametros) Row
        +cerrar()
        +reiniciar()$
    }
    class RepositorioBase~T~ {
        +tabla: str
        +entidad: type
        +campo_activo: str
        +guardar(entidad) T
        +obtener(id) T
        +obtener_por_id(id) T
        +listar(incluir_inactivos) list~T~
        +buscar_por(filtros) list~T~
        +buscar_uno_por(filtros) T
        +existe(excluir_id, filtros) bool
        +eliminar(id)
        #_a_entidad(fila) T
        #_a_fila(entidad) dict
    }
    class ProductoRepositorio
    class StockRepositorio
    class BultoRepositorio
    class ClienteRepositorio

    RepositorioBase <|-- ProductoRepositorio
    RepositorioBase <|-- StockRepositorio
    RepositorioBase <|-- BultoRepositorio
    RepositorioBase <|-- ClienteRepositorio
    RepositorioBase ..> BaseDeDatos : usa
```

- **Patrón Singleton:** `BaseDeDatos` redefine `__new__` para que toda la aplicación comparta **una única**
  conexión a SQLite. `transaccion()` permite anidar operaciones: confirma al salir de la más externa y, si
  algo falla adentro, deshace todo.
- **Patrón Repository:** `RepositorioBase[T]` resuelve el guardado y la lectura de cualquier entidad a partir
  de su tabla y su clase. Cada paquete tiene sus repositorios (en `repositorio_maestros.py`,
  `repositorio_inventario.py`, `repositorio_logistica.py` y `repositorio_ventas.py`); en el diagrama se muestra
  uno de cada paquete como ejemplo. Cuando un atributo no coincide con una columna (por ejemplo, un enum o una
  lista de detalles), el repositorio redefine `_a_entidad` y `_a_fila`.

---

## 7. Patrones de diseño aplicados

| Patrón | Dónde | Para qué |
|--------|-------|----------|
| **Singleton** | `BaseDeDatos` (`persistencia/conexion.py`) | Una sola conexión compartida y transacciones anidadas |
| **Repository** | `RepositorioBase` y sus subclases (`persistencia/`) | Separar el dominio del SQL |
| **Observer** | `StockService` → `ObservadorStock` (`servicios/stock_service.py`, `observadores_stock.py`, `generador_necesidades.py`) | Avisar y generar necesidades cuando un producto llega a su stock mínimo |
| **State** | `Bulto` → `EstadoBulto` (`dominio/logistica/modelos.py`) | Ciclo de vida del bulto con transiciones válidas |
| **Strategy** | `MedioPago` y sus medios (`dominio/ventas/modelos.py`) | Recargo y validación propios de cada medio de pago |
| **Factory** | `ComprobanteFactory` (`dominio/ventas/modelos.py`) | Elegir y crear el tipo de comprobante |
