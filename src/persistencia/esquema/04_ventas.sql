-- =============================================================================
-- 04 · VENTAS, COBROS Y DEVOLUCIONES (vinchi)
-- P7: venta, detalle, pagos mixtos, comprobantes, devoluciones y caja.
-- V3/V5: restricciones de cantidades y trazabilidad entre venta y devolución.
-- =============================================================================

CREATE TABLE IF NOT EXISTS cliente (
	id             INTEGER PRIMARY KEY AUTOINCREMENT,
	documento      TEXT NOT NULL UNIQUE,
	nombre         TEXT NOT NULL,
	condicion_iva  TEXT NOT NULL CHECK (condicion_iva IN (
		'CONSUMIDOR_FINAL', 'RESPONSABLE_INSCRIPTO', 'MONOTRIBUTISTA', 'EXENTO'
	))
);

CREATE TABLE IF NOT EXISTS venta (
	id            INTEGER PRIMARY KEY AUTOINCREMENT,
	ubicacion_id  INTEGER NOT NULL REFERENCES ubicacion (id),
	cliente_id    INTEGER REFERENCES cliente (id),
	numero        INTEGER NOT NULL CHECK (numero > 0),
	fecha_hora    TIMESTAMP NOT NULL,
	vendedor      TEXT NOT NULL,
	estado        TEXT NOT NULL CHECK (estado IN ('CONFIRMADA', 'ANULADA')),
	total         DECIMAL(12, 2) NOT NULL CHECK (total >= 0),
	UNIQUE (ubicacion_id, numero)
);

CREATE INDEX IF NOT EXISTS ix_venta_fecha_ubicacion ON venta (fecha_hora, ubicacion_id);

CREATE TABLE IF NOT EXISTS detalle_venta (
	id                 INTEGER PRIMARY KEY AUTOINCREMENT,
	venta_id           INTEGER NOT NULL REFERENCES venta (id),
	producto_id        INTEGER NOT NULL REFERENCES producto (id),
	cantidad           INTEGER NOT NULL CHECK (cantidad > 0),
	precio_unitario    DECIMAL(12, 2) NOT NULL CHECK (precio_unitario >= 0),
	costo_unitario     DECIMAL(12, 2) NOT NULL CHECK (costo_unitario >= 0),
	cantidad_devuelta  INTEGER NOT NULL DEFAULT 0 CHECK (cantidad_devuelta >= 0 AND cantidad_devuelta <= cantidad),
	recargo_asignado   DECIMAL(12, 2) NOT NULL DEFAULT 0 CHECK (recargo_asignado >= 0),
	monto_reintegrado  DECIMAL(12, 2) NOT NULL DEFAULT 0 CHECK (monto_reintegrado >= 0)
);

CREATE INDEX IF NOT EXISTS ix_detalle_venta_venta ON detalle_venta (venta_id);

CREATE TABLE IF NOT EXISTS cobro (
	id               INTEGER PRIMARY KEY AUTOINCREMENT,
	venta_id         INTEGER NOT NULL REFERENCES venta (id),
	fecha_hora       TIMESTAMP NOT NULL,
	medio_pago       TEXT NOT NULL CHECK (medio_pago IN ('EFECTIVO', 'DEBITO', 'CREDITO', 'TRANSFERENCIA')),
	monto            DECIMAL(12, 2) NOT NULL CHECK (monto > 0),
	recargo          DECIMAL(12, 2) NOT NULL DEFAULT 0 CHECK (recargo >= 0),
	cuotas           INTEGER NOT NULL DEFAULT 1 CHECK (cuotas BETWEEN 1 AND 12),
	nro_autorizacion TEXT NOT NULL DEFAULT ''
);

CREATE TABLE IF NOT EXISTS caja (
	id              INTEGER PRIMARY KEY AUTOINCREMENT,
	ubicacion_id    INTEGER NOT NULL REFERENCES ubicacion (id),
	fecha_apertura  TIMESTAMP NOT NULL,
	fecha_cierre    TIMESTAMP,
	saldo_inicial   DECIMAL(12, 2) NOT NULL CHECK (saldo_inicial >= 0),
	CHECK (fecha_cierre IS NULL OR fecha_cierre >= fecha_apertura)
);

CREATE UNIQUE INDEX IF NOT EXISTS ux_caja_abierta_ubicacion
	ON caja (ubicacion_id) WHERE fecha_cierre IS NULL;

CREATE TABLE IF NOT EXISTS devolucion (
	id               INTEGER PRIMARY KEY AUTOINCREMENT,
	venta_id         INTEGER NOT NULL REFERENCES venta (id),
	fecha_hora       TIMESTAMP NOT NULL,
	motivo           TEXT NOT NULL,
	total_reintegrar DECIMAL(12, 2) NOT NULL CHECK (total_reintegrar >= 0)
);

CREATE TABLE IF NOT EXISTS detalle_devolucion (
	id                INTEGER PRIMARY KEY AUTOINCREMENT,
	devolucion_id     INTEGER NOT NULL REFERENCES devolucion (id),
	detalle_venta_id  INTEGER NOT NULL REFERENCES detalle_venta (id),
	cantidad          INTEGER NOT NULL CHECK (cantidad > 0),
	reingresa_stock   BOOLEAN NOT NULL CHECK (reingresa_stock IN (0, 1)),
	monto_reintegrado DECIMAL(12, 2) NOT NULL CHECK (monto_reintegrado >= 0)
);

CREATE TABLE IF NOT EXISTS comprobante (
	id             INTEGER PRIMARY KEY AUTOINCREMENT,
	punto_venta    INTEGER NOT NULL CHECK (punto_venta > 0),
	numero         INTEGER NOT NULL CHECK (numero > 0),
	tipo           TEXT NOT NULL CHECK (tipo IN ('TICKET', 'FACTURA_A', 'FACTURA_B', 'NOTA_CREDITO')),
	fecha_emision  TIMESTAMP NOT NULL,
	total          DECIMAL(12, 2) NOT NULL CHECK (total >= 0),
	venta_id       INTEGER UNIQUE REFERENCES venta (id),
	devolucion_id  INTEGER UNIQUE REFERENCES devolucion (id),
	CHECK ((venta_id IS NOT NULL AND devolucion_id IS NULL) OR
		   (venta_id IS NULL AND devolucion_id IS NOT NULL)),
	UNIQUE (punto_venta, tipo, numero)
);

CREATE TABLE IF NOT EXISTS movimiento_caja (
	id           INTEGER PRIMARY KEY AUTOINCREMENT,
	caja_id      INTEGER NOT NULL REFERENCES caja (id),
	fecha_hora   TIMESTAMP NOT NULL,
	tipo         TEXT NOT NULL CHECK (tipo IN ('INGRESO', 'EGRESO')),
	monto        DECIMAL(12, 2) NOT NULL CHECK (monto > 0),
	medio_pago   TEXT NOT NULL,
	concepto     TEXT NOT NULL,
	cobro_id     INTEGER REFERENCES cobro (id),
	devolucion_id INTEGER REFERENCES devolucion (id),
	CHECK ((tipo = 'INGRESO' AND cobro_id IS NOT NULL AND devolucion_id IS NULL) OR
		   (tipo = 'EGRESO' AND devolucion_id IS NOT NULL AND cobro_id IS NULL))
);

CREATE INDEX IF NOT EXISTS ix_movimiento_caja_caja_fecha ON movimiento_caja (caja_id, fecha_hora);
