# Plan de trabajo – TPI Tema 3: Sistema de Ventas e Inventario (CD → Locales)

Este documento divide el TP en 4 partes equivalentes. Cada integrante es dueño de un
**módulo vertical** completo (modelo + persistencia + lógica + pantallas + tests), de
**al menos un reporte no trivial** y de **un patrón de diseño**. Así cada uno tiene trabajo
visible y defendible en la presentación, y nadie queda solo con "lo aburrido".

> **Integrantes:** brache · pohlsi · turco · vinchi

---

## 1. Resumen de la consigna

**Obligatorio**

| # | Proceso de negocio |
|---|--------------------|
| P1 | Administrar sucursales/locales y Centro de Distribución (CD) |
| P2 | Administrar productos, categorías, precios, stock mínimo y proveedores |
| P3 | Consolidar necesidades de los locales en una **orden de reposición** al CD (origen y destino) |
| P4 | Empaquetar mercadería en **bultos**, asignando **remito** de despacho y **precinto** |
| P5 | Registrar el **despacho** de los bultos desde el CD |
| P6 | Registrar la **recepción** en el local, verificando que el precinto no esté violado |
| P7 | Registrar **ventas** (1..n productos), **cobros** con medios de pago, **comprobante** y **devoluciones** (impacto en stock y caja) |

**Validaciones**

| # | Validación |
|---|-----------|
| V1 | El stock **no** pasa a *Disponible* en el local hasta que remito y bulto estén *Verificado*; precinto roto ⇒ *Rechazado* y no habilita venta |
| V2 | Trazabilidad **inmutable** de estados del bulto: Preparado → Precintado → En tránsito → Recibido → Verificado / Rechazado |
| V3 | No vender más que el stock disponible y verificado |
| V4 | Evitar productos o proveedores duplicados (identificador único) |
| V5 | No aceptar devoluciones que no correspondan a una venta registrada o que incumplan reglas |

**Además:** mínimo **2 patrones de diseño** y **4 reportes no triviales**. El ciclo de vida
del bulto se evalúa críticamente.

---

## 2. Decisiones técnicas comunes (acordar en la primera reunión)

La consigna no fija tecnología. Propuesta por defecto (cámbienla si la cátedra pide otra):

- **Lenguaje:** Python 3.11+
- **Base de datos:** SQLite (archivo local, sin instalar nada)
- **Interfaz:** Tkinter (o la que use la cátedra)
- **Tests:** `unittest` / `pytest`
- **Reportes:** tablas en pantalla + gráfico con `matplotlib` (y/o exportar a PDF/CSV)

### Estructura de carpetas propuesta

```
src/
  persistencia/     # conexión, esquema SQL, repositorios        (brache)
  dominio/
    maestros/       # Sucursal, CentroDistribucion, Producto...  (brache)
    inventario/     # Stock, MovimientoStock, OrdenReposicion... (pohlsi)
    logistica/      # Bulto, Remito, Precinto, estados...        (turco)
    ventas/         # Venta, Cobro, Comprobante, Devolucion...   (vinchi)
  servicios/        # lógica de negocio y validaciones (cada uno el suyo)
  ui/               # ventana principal (brache) + pantallas de cada módulo
  reportes/         # cada uno sus reportes
tests/
docs/               # diagrama de clases, DER, diagrama de estados, capturas
main.py
```

### Contratos compartidos (definirlos ANTES de programar)

Para que nadie se bloquee, en la semana 1 se acuerdan estas interfaces aunque devuelvan datos falsos:

1. **Esquema de la BD** (lo arma brache con el aporte de todos).
2. **`StockService`** (lo publica pohlsi) – *todo* cambio de stock pasa por acá:
   - `stock_disponible(ubicacion_id, producto_id) -> int`
   - `ingresar_pendiente(ubicacion_id, producto_id, cant, ref)` (llega mercadería no verificada)
   - `confirmar_disponible(ubicacion_id, producto_id, cant, ref)` (bulto verificado)
   - `registrar_merma(ubicacion_id, producto_id, cant, ref)` (bulto rechazado)
   - `egresar(ubicacion_id, producto_id, cant, ref)` (venta / despacho; valida que alcance)
   - `reingresar(ubicacion_id, producto_id, cant, ref)` (devolución)
   - Cada llamada genera un `MovimientoStock` (sirve para reportes y trazabilidad).
3. **Repositorios base** (brache): `obtener_por_id`, `listar`, `guardar`, etc., que todos reutilizan.

---

## 3. División de tareas

### 👤 brache — Maestros + Infraestructura

**Procesos:** P1, P2 · **Validación:** V4 · **Patrones:** Singleton (conexión a BD) + Repository/DAO

- [x] Infraestructura: conexión a SQLite (**Singleton**), script de creación del esquema, datos de prueba (seed).
- [x] Capa de persistencia genérica (**Repository/DAO**) que reutilizan los demás.
- [x] Ventana principal / menú de navegación y componentes de UI reutilizables (grilla, formulario, mensajes de error).
- [x] ABM de **Sucursales/Locales** y **Centro de Distribución** (P1).
- [x] ABM de **Categorías**.
- [x] ABM de **Productos**: código/SKU único, categoría, precio de venta, **costo**, stock mínimo por local (P2).
- [x] ABM de **Proveedores**: CUIT único, relación producto–proveedor (P2).
- [x] Validación **V4**: no duplicar productos (SKU/código de barras) ni proveedores (CUIT) – a nivel servicio *y* con `UNIQUE` en la BD.
- [x] **Reporte R1 – Existencias actuales y productos en/bajo stock mínimo** (por local, filtrable por categoría).
- [x] **Reporte R2 – Productos más vendidos y margen de ganancia/pérdida estimado** (precio venta − costo, por período).
- [ ] Integrar el diagrama de clases general y el DER en `docs/`.
- [x] Tests de sus servicios.

> Nota: brache tiene más carga al principio (infraestructura); por eso los reportes los hace en la segunda mitad.

---

### 👤 pohlsi — Inventario, Compras y Reposición

**Procesos:** P3 (+ ingreso de compras al CD) · **Validación:** base de V1 y V3 · **Patrón:** Observer

- [ ] Modelo **Stock por ubicación** (CD o local) con cantidades *pendiente de verificación*, *disponible* y *merma*.
- [ ] **`StockService`** + **`MovimientoStock`** (tipo, cantidad, fecha, referencia al documento origen). Es el corazón del sistema: publicar la interfaz la semana 1.
- [ ] **Compras / ingreso de mercadería del proveedor al CD** (la consigna pide integrar compras; sin esto el CD no tiene stock para reponer).
- [ ] **Necesidades de reposición** de cada local (manual o calculada: stock mínimo − disponible).
- [ ] **Orden de reposición** (P3): consolida necesidades de uno o varios locales, indica **origen (CD) y destino (local)**, con sus estados (Pendiente → En preparación → Despachada → Completada/Con faltantes).
- [ ] Patrón **Observer**: cuando el stock de un producto cae bajo el mínimo, se notifica a los suscriptores (alerta en pantalla y/o generación de necesidad de reposición).
  El mínimo **no** va en la tabla `stock`: lo administra maestros en `stock_minimo` y se consulta con
  `StockMinimoService.esta_en_minimo(producto_id, ubicacion_id, disponible)` (ver `docs/maestros.md`).
- [ ] *(Opcional, si sobra tiempo)* **Órdenes de compra sugeridas por faltantes** en el CD.
- [ ] **Reporte R3 – Movimientos y valorización del inventario** (entradas/salidas por período y stock valorizado a costo por ubicación).
- [ ] **Reporte R4 – Tiempo promedio de tránsito CD → locales** (despacho vs. recepción, por local y período).
- [ ] Diagrama de estados de la orden de reposición.
- [ ] Tests de `StockService` (no permitir stock negativo, movimientos correctos).

---

### 👤 turco — Logística: Bultos, Remitos y Precintos

**Procesos:** P4, P5, P6 · **Validaciones:** V1, V2 · **Patrón:** State

- [ ] Entidades **Bulto/Contenedor** (con su detalle de productos), **Remito** de despacho y **Precinto** (número único).
- [ ] Patrón **State** para el ciclo de vida del bulto: `Preparado → Precintado → EnTransito → Recibido → Verificado | Rechazado`. Cada estado sabe qué transiciones son válidas; cualquier otra lanza excepción. *(Es lo que la cátedra va a mirar con lupa).*
- [ ] **Historial de estados inmutable** (V2): tabla `historial_estado_bulto` donde solo se insertan filas (fecha/hora, estado anterior, estado nuevo, usuario, observación). Nunca `UPDATE` ni `DELETE`.
- [ ] **Empaquetado** (P4): a partir de una orden de reposición, armar bultos, asignar remito y precinto.
- [ ] **Despacho** (P5): registra salida del CD → bultos *En tránsito*; descuenta stock del CD e ingresa como *pendiente* en el local (vía `StockService`).
- [ ] **Recepción** (P6): el local recibe, registra el número de precinto recibido y su estado.
  - Precinto íntegro y coincide ⇒ *Verificado* ⇒ `confirmar_disponible` (recién ahí se puede vender – V1).
  - Precinto roto / no coincide ⇒ *Rechazado* ⇒ `registrar_merma` (rechazo logístico, no habilita venta).
- [ ] El **Remito** también pasa a *Verificado* cuando todos sus bultos fueron procesados.
- [ ] **Reporte R5 – Bultos rechazados y mermas por rotura de precinto** (por local, período, valorizado).
- [ ] Diagrama de estados del bulto en `docs/`.
- [ ] Tests de todas las transiciones válidas e inválidas.

---

### 👤 vinchi — Ventas, Cobros, Comprobantes y Devoluciones

**Proceso:** P7 · **Validaciones:** V3, V5 · **Patrones:** Strategy (+ Factory opcional)

- [ ] **Venta** con uno o más renglones (producto, cantidad, precio unitario al momento de la venta, subtotal).
- [ ] Validación **V3**: no permitir vender más que el stock **disponible y verificado** del local (`StockService.stock_disponible`). Al confirmar, `egresar`.
- [ ] **Medios de pago** (efectivo, débito, crédito, transferencia…) y **cobro** (posibilidad de pago mixto).
- [ ] Patrón **Strategy** para los medios de pago (cada medio calcula recargo/descuento, valida datos y registra el cobro a su manera).
- [ ] **Comprobante** (ticket/factura A/B con numeración correlativa por local). Opcional: **Factory** para crear el tipo de comprobante.
- [ ] **Caja**: registro de ingresos (cobros) y egresos (reintegros por devolución).
- [ ] **Devoluciones** (V5): solo sobre una venta registrada, por cantidad ≤ vendida − ya devuelta, dentro de un plazo (ej. 30 días). Reingresa stock (`reingresar`) y registra el reintegro en caja.
- [ ] **Reporte R6 – Ventas e ingresos por período, local y medio de pago** (con totales y gráfico).
- [ ] Tests de venta sin stock, devolución inválida, cálculo de totales.

---

## 4. Resumen de cobertura

| Requisito | Responsable |
|-----------|-------------|
| P1, P2, V4 | brache |
| P3 (+ compras) | pohlsi |
| P4, P5, P6, V1, V2 | turco (usa `StockService` de pohlsi) |
| P7, V3, V5 | vinchi (usa `StockService` de pohlsi) |
| Patrón Singleton + Repository | brache |
| Patrón Observer | pohlsi |
| Patrón State | turco |
| Patrón Strategy (+ Factory) | vinchi |
| Reportes R1, R2 | brache |
| Reportes R3, R4 | pohlsi |
| Reporte R5 | turco |
| Reporte R6 | vinchi |

→ **6 reportes** y **4–5 patrones** (piden 4 y 2): si alguno no llega o la cátedra no lo
considera "no trivial", igual se cumple el mínimo.

### Dependencias entre módulos

```
          brache (infra + maestros)
             │
             ▼
          pohlsi (StockService, reposición)
            ╱ ╲
           ▼   ▼
       turco   vinchi
 (logística)   (ventas)
```

brache y pohlsi tienen que publicar su base **primero**; turco y vinchi pueden empezar en paralelo con
*stubs* (implementaciones falsas) de `StockService` y de los repositorios.

---

## 5. Planificación por etapas

| Etapa | Qué se hace | Quién |
|-------|-------------|-------|
| **0. Modelado (todos juntos)** | Leer la consigna, diagrama de clases del dominio completo, DER, diagrama de estados del bulto, acordar contratos de la sección 2 | Todos |
| **1. Base** | Esquema + conexión + repositorios + menú (brache). Interfaz de `StockService` (pohlsi). turco y vinchi modelan sus entidades con stubs | Todos |
| **2. Procesos** | Cada uno implementa su proceso de punta a punta con su pantalla | Cada uno |
| **3. Integración** | Flujo completo: compra → reposición → bulto → despacho → recepción → venta → devolución | Todos |
| **4. Reportes y patrones** | Terminar reportes, revisar que los patrones estén bien aplicados | Cada uno |
| **5. Cierre** | Datos de prueba realistas, tests, documentación, ensayo de presentación | Todos |

---

## 6. Forma de trabajo en el repositorio

1. **Nunca** commitear directo a `main`.
2. Cada tarea en su rama: `feature/<modulo>-<tarea>` (ej. `feature/logistica-estado-bulto`).
3. Abrir un **Pull Request** a `main` y que lo revise **al menos otro integrante** antes de mergear.
4. Antes de abrir el PR: traer los últimos cambios de `main` (`git pull origin main`) y verificar que los tests pasen.
5. Cambios al **esquema de BD** o a los **contratos compartidos** se avisan en el grupo, porque afectan a todos.
6. Se puede crear un *Issue* por cada checkbox de este documento y asignarlo, para ver el avance en GitHub.
