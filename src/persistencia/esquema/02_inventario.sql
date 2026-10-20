-- =============================================================================
-- 02 · INVENTARIO, COMPRAS Y REPOSICIÓN (pohlsi)
-- Stock por ubicación, movimientos de stock, órdenes de compra, necesidades de
-- reposición y órdenes de reposición (CD -> sucursal).
-- Convenciones: ver README.md, sección "Convenciones de la base de datos".
-- El stock mínimo NO va en `stock`: está en la tabla `stock_minimo` de maestros
-- (se lee con StockMinimoService.esta_en_minimo / minimo).
-- =============================================================================

-- Stock de cada producto en cada ubicación (CD o sucursal), en tres "baldes":
--   pendiente  = llegó o va en camino, pero todavía no se verificó (NO se puede vender)
--   disponible = verificado: es lo único que se puede vender (V1 y V3)
--   merma      = rechazado (por ejemplo, precinto roto)
-- Los CHECK impiden que cualquier cantidad quede negativa, aunque falle una validación.
CREATE TABLE IF NOT EXISTS stock (
    id                   INTEGER PRIMARY KEY AUTOINCREMENT,
    producto_id          INTEGER NOT NULL REFERENCES producto (id),
    ubicacion_id         INTEGER NOT NULL REFERENCES ubicacion (id),
    cantidad_disponible  INTEGER NOT NULL DEFAULT 0 CHECK (cantidad_disponible >= 0),
    cantidad_pendiente   INTEGER NOT NULL DEFAULT 0 CHECK (cantidad_pendiente >= 0),
    cantidad_merma       INTEGER NOT NULL DEFAULT 0 CHECK (cantidad_merma >= 0),
    UNIQUE (producto_id, ubicacion_id)
);

CREATE INDEX IF NOT EXISTS ix_stock_ubicacion ON stock (ubicacion_id);

-- Libro de movimientos de stock. Es inmutable: solo se hace INSERT.
-- `cantidad` siempre es positiva; el sentido (entra / sale) lo da el `tipo`.
-- `tipo_documento` + `documento_id` indican el documento que originó el movimiento
-- (VENTA, DEVOLUCION, ORDEN_COMPRA, REMITO...). No es una FK porque apunta a tablas distintas.
CREATE TABLE IF NOT EXISTS movimiento_stock (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    stock_id        INTEGER   NOT NULL REFERENCES stock (id),
    fecha_hora      TIMESTAMP NOT NULL,
    tipo            TEXT      NOT NULL CHECK (tipo IN (
                        'INGRESO_COMPRA', 'EGRESO_DESPACHO', 'INGRESO_PENDIENTE',
                        'CONFIRMACION_VERIFICADO', 'MERMA_RECHAZO', 'EGRESO_VENTA',
                        'REINGRESO_DEVOLUCION', 'AJUSTE')),
    cantidad        INTEGER   NOT NULL CHECK (cantidad > 0),
    costo_unitario  DECIMAL(12, 2) NOT NULL CHECK (costo_unitario >= 0),
    tipo_documento  TEXT      NOT NULL,
    documento_id    INTEGER,
    usuario         TEXT      NOT NULL DEFAULT 'sistema'
);

CREATE INDEX IF NOT EXISTS ix_movimiento_stock_stock ON movimiento_stock (stock_id, fecha_hora);
CREATE INDEX IF NOT EXISTS ix_movimiento_stock_fecha ON movimiento_stock (fecha_hora);

-- Los movimientos no se editan ni se borran (igual que el historial del bulto).
CREATE TRIGGER IF NOT EXISTS movimiento_stock_no_update
BEFORE UPDATE ON movimiento_stock
BEGIN
    SELECT RAISE(ABORT, 'Los movimientos de stock son inmutables: no se pueden modificar.');
END;

CREATE TRIGGER IF NOT EXISTS movimiento_stock_no_delete
BEFORE DELETE ON movimiento_stock
BEGIN
    SELECT RAISE(ABORT, 'Los movimientos de stock son inmutables: no se pueden borrar.');
END;

-- ---------------------------------------------------------------------------
-- Compras: ingreso de mercadería del proveedor al Centro de Distribución.
-- ---------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS orden_compra (
    id             INTEGER PRIMARY KEY AUTOINCREMENT,
    numero         INTEGER NOT NULL UNIQUE,
    proveedor_id   INTEGER NOT NULL REFERENCES proveedor (id),
    destino_id     INTEGER NOT NULL REFERENCES ubicacion (id),   -- siempre un CD (lo valida el servicio)
    fecha_emision  DATE    NOT NULL,
    estado         TEXT    NOT NULL DEFAULT 'PENDIENTE' CHECK (estado IN ('PENDIENTE', 'RECIBIDA', 'ANULADA'))
);

CREATE INDEX IF NOT EXISTS ix_orden_compra_proveedor ON orden_compra (proveedor_id);

CREATE TABLE IF NOT EXISTS detalle_orden_compra (
    id               INTEGER PRIMARY KEY AUTOINCREMENT,
    orden_compra_id  INTEGER NOT NULL REFERENCES orden_compra (id),
    producto_id      INTEGER NOT NULL REFERENCES producto (id),
    cantidad         INTEGER NOT NULL CHECK (cantidad > 0),
    costo_unitario   DECIMAL(12, 2) NOT NULL CHECK (costo_unitario >= 0),
    UNIQUE (orden_compra_id, producto_id)
);

-- ---------------------------------------------------------------------------
-- Reposición (P3): las necesidades de las sucursales se consolidan en una orden.
-- ---------------------------------------------------------------------------

-- Orden de reposición: origen = CD, destino = sucursal. Turco arma los bultos a partir de ella.
CREATE TABLE IF NOT EXISTS orden_reposicion (
    id             INTEGER PRIMARY KEY AUTOINCREMENT,
    numero         INTEGER   NOT NULL UNIQUE,
    fecha_emision  TIMESTAMP NOT NULL,
    origen_id      INTEGER   NOT NULL REFERENCES ubicacion (id),   -- CD
    destino_id     INTEGER   NOT NULL REFERENCES ubicacion (id),   -- sucursal
    estado         TEXT      NOT NULL DEFAULT 'PENDIENTE' CHECK (estado IN (
                       'PENDIENTE', 'EN_PREPARACION', 'DESPACHADA',
                       'CERRADA_COMPLETA', 'CERRADA_CON_FALTANTES')),
    CHECK (origen_id <> destino_id)
);

CREATE INDEX IF NOT EXISTS ix_orden_reposicion_destino ON orden_reposicion (destino_id, estado);

CREATE TABLE IF NOT EXISTS detalle_orden_reposicion (
    id                   INTEGER PRIMARY KEY AUTOINCREMENT,
    orden_reposicion_id  INTEGER NOT NULL REFERENCES orden_reposicion (id),
    producto_id          INTEGER NOT NULL REFERENCES producto (id),
    cantidad_solicitada  INTEGER NOT NULL CHECK (cantidad_solicitada > 0),
    cantidad_preparada   INTEGER NOT NULL DEFAULT 0 CHECK (cantidad_preparada >= 0),
    cantidad_recibida    INTEGER NOT NULL DEFAULT 0 CHECK (cantidad_recibida >= 0),
    UNIQUE (orden_reposicion_id, producto_id)
);

-- Necesidad de reposición de una sucursal: manual, o automática cuando el Observer
-- detecta stock bajo el mínimo. Al consolidarse queda asociada a su orden.
CREATE TABLE IF NOT EXISTS necesidad_reposicion (
    id                   INTEGER PRIMARY KEY AUTOINCREMENT,
    ubicacion_id         INTEGER NOT NULL REFERENCES ubicacion (id),   -- sucursal que la necesita
    fecha                DATE    NOT NULL,
    origen               TEXT    NOT NULL CHECK (origen IN ('MANUAL', 'AUTOMATICA')),
    estado               TEXT    NOT NULL DEFAULT 'PENDIENTE' CHECK (estado IN ('PENDIENTE', 'CONSOLIDADA', 'ANULADA')),
    orden_reposicion_id  INTEGER REFERENCES orden_reposicion (id),
    CHECK ((estado = 'CONSOLIDADA') = (orden_reposicion_id IS NOT NULL))
);

CREATE INDEX IF NOT EXISTS ix_necesidad_reposicion_ubicacion ON necesidad_reposicion (ubicacion_id, estado);

CREATE TABLE IF NOT EXISTS detalle_necesidad (
    id                      INTEGER PRIMARY KEY AUTOINCREMENT,
    necesidad_reposicion_id INTEGER NOT NULL REFERENCES necesidad_reposicion (id),
    producto_id             INTEGER NOT NULL REFERENCES producto (id),
    cantidad_solicitada     INTEGER NOT NULL CHECK (cantidad_solicitada > 0),
    UNIQUE (necesidad_reposicion_id, producto_id)
);
