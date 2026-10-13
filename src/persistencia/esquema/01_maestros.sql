-- =============================================================================
-- 01 · MAESTROS (brache)
-- Ubicaciones (sucursales y Centro de Distribución), categorías, productos,
-- historial de precios, proveedores y su relación con los productos.
-- Convenciones: ver README.md, sección "Convenciones de la base de datos".
-- =============================================================================

-- Sucursales y Centro de Distribución en una sola tabla (herencia en una tabla).
-- Así el stock, las órdenes y los remitos referencian siempre a `ubicacion`.
CREATE TABLE IF NOT EXISTS ubicacion (
    id            INTEGER PRIMARY KEY AUTOINCREMENT,
    tipo          TEXT    NOT NULL CHECK (tipo IN ('SUCURSAL', 'CD')),
    codigo        TEXT    NOT NULL UNIQUE,
    nombre        TEXT    NOT NULL,
    direccion     TEXT,
    telefono      TEXT,
    punto_venta   INTEGER UNIQUE,                 -- solo sucursales (numeración de comprobantes)
    capacidad_m3  REAL,                           -- solo Centro de Distribución
    activa        BOOLEAN NOT NULL DEFAULT 1 CHECK (activa IN (0, 1)),
    CHECK (tipo = 'SUCURSAL' OR punto_venta IS NULL),
    CHECK (tipo = 'CD' OR capacidad_m3 IS NULL)
);

CREATE TABLE IF NOT EXISTS categoria (
    id           INTEGER PRIMARY KEY AUTOINCREMENT,
    nombre       TEXT    NOT NULL UNIQUE COLLATE NOCASE,
    descripcion  TEXT
);

-- V4: no puede haber dos productos con el mismo SKU ni con el mismo código de barras.
CREATE TABLE IF NOT EXISTS producto (
    id                   INTEGER PRIMARY KEY AUTOINCREMENT,
    sku                  TEXT    NOT NULL UNIQUE COLLATE NOCASE,
    codigo_barras        TEXT    UNIQUE,          -- opcional, pero si se carga no se repite
    nombre               TEXT    NOT NULL,
    descripcion          TEXT,
    unidad_medida        TEXT    NOT NULL DEFAULT 'UN',
    categoria_id         INTEGER NOT NULL REFERENCES categoria (id),
    costo_actual         DECIMAL(12, 2) NOT NULL CHECK (costo_actual >= 0),
    precio_venta_actual  DECIMAL(12, 2) NOT NULL CHECK (precio_venta_actual >= 0),
    activo               BOOLEAN NOT NULL DEFAULT 1 CHECK (activo IN (0, 1))
);

CREATE INDEX IF NOT EXISTS ix_producto_categoria ON producto (categoria_id);

-- Un registro por cada cambio de costo / precio. El vigente tiene fecha_hasta NULL.
CREATE TABLE IF NOT EXISTS historial_precio (
    id            INTEGER PRIMARY KEY AUTOINCREMENT,
    producto_id   INTEGER   NOT NULL REFERENCES producto (id),
    fecha_desde   TIMESTAMP NOT NULL,
    fecha_hasta   TIMESTAMP,
    costo         DECIMAL(12, 2) NOT NULL CHECK (costo >= 0),
    precio_venta  DECIMAL(12, 2) NOT NULL CHECK (precio_venta >= 0),
    CHECK (fecha_hasta IS NULL OR fecha_hasta >= fecha_desde)
);

CREATE INDEX IF NOT EXISTS ix_historial_precio_producto ON historial_precio (producto_id, fecha_desde);

-- V4: no puede haber dos proveedores con el mismo CUIT (se guardan los 11 dígitos, sin guiones).
CREATE TABLE IF NOT EXISTS proveedor (
    id            INTEGER PRIMARY KEY AUTOINCREMENT,
    cuit          TEXT    NOT NULL UNIQUE CHECK (length(cuit) = 11 AND cuit NOT GLOB '*[^0-9]*'),
    razon_social  TEXT    NOT NULL,
    email         TEXT,
    telefono      TEXT,
    direccion     TEXT,
    activo        BOOLEAN NOT NULL DEFAULT 1 CHECK (activo IN (0, 1))
);

-- Qué proveedores venden cada producto, con su código y costo pactado.
CREATE TABLE IF NOT EXISTS producto_proveedor (
    producto_id          INTEGER NOT NULL REFERENCES producto (id),
    proveedor_id         INTEGER NOT NULL REFERENCES proveedor (id),
    codigo_en_proveedor  TEXT,
    costo_pactado        DECIMAL(12, 2) CHECK (costo_pactado >= 0),
    plazo_entrega_dias   INTEGER CHECK (plazo_entrega_dias >= 0),
    PRIMARY KEY (producto_id, proveedor_id)
);
