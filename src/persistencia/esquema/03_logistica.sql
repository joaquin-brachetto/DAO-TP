-- =============================================================================
-- 03 · LOGÍSTICA (turco)
-- Remitos, bultos/contenedores, detalle de bultos, precintos de seguridad,
-- historial inmutable de cambios de estado del bulto (V2), despachos desde CD,
-- recepciones en sucursal y controles de precinto por bulto (P4, P5, P6, V1, V2).
-- Convenciones: ver README.md, sección "Convenciones de la base de datos".
-- =============================================================================

-- Despacho de uno o varios remitos desde el Centro de Distribución (P5).
CREATE TABLE IF NOT EXISTS despacho (
    id                 INTEGER   PRIMARY KEY AUTOINCREMENT,
    fecha_hora_salida  TIMESTAMP NOT NULL,
    transportista      TEXT      NOT NULL,
    patente            TEXT      NOT NULL,
    usuario            TEXT      NOT NULL DEFAULT 'sistema',
    observaciones      TEXT      NOT NULL DEFAULT ''
);

CREATE INDEX IF NOT EXISTS ix_despacho_fecha ON despacho (fecha_hora_salida);

-- Remito de despacho asociado a una OrdenReposicion (CD -> sucursal).
CREATE TABLE IF NOT EXISTS remito (
    id                   INTEGER   PRIMARY KEY AUTOINCREMENT,
    numero               TEXT      NOT NULL UNIQUE COLLATE NOCASE,
    orden_reposicion_id  INTEGER   NOT NULL REFERENCES orden_reposicion (id),
    origen_id            INTEGER   NOT NULL REFERENCES ubicacion (id),
    destino_id           INTEGER   NOT NULL REFERENCES ubicacion (id),
    fecha_emision        TIMESTAMP NOT NULL,
    estado               TEXT      NOT NULL DEFAULT 'EMITIDO' CHECK (estado IN (
                             'EMITIDO', 'EN_TRANSITO', 'RECIBIDO',
                             'VERIFICADO', 'VERIFICADO_CON_RECHAZOS')),
    despacho_id          INTEGER   REFERENCES despacho (id),
    CHECK (origen_id <> destino_id)
);

CREATE INDEX IF NOT EXISTS ix_remito_orden ON remito (orden_reposicion_id);
CREATE INDEX IF NOT EXISTS ix_remito_destino_estado ON remito (destino_id, estado);

-- Relación 1..* entre Despacho y Remito (según docs/modelo_dominio.md).
CREATE TABLE IF NOT EXISTS despacho_remito (
    id           INTEGER PRIMARY KEY AUTOINCREMENT,
    despacho_id  INTEGER NOT NULL REFERENCES despacho (id),
    remito_id    INTEGER NOT NULL UNIQUE REFERENCES remito (id)
);

CREATE INDEX IF NOT EXISTS ix_despacho_remito_despacho ON despacho_remito (despacho_id);

-- Bulto / contenedor físico armado en el CD para un remito (P4, Patrón State).
CREATE TABLE IF NOT EXISTS bulto (
    id              INTEGER   PRIMARY KEY AUTOINCREMENT,
    codigo          TEXT      NOT NULL UNIQUE COLLATE NOCASE,
    remito_id       INTEGER   NOT NULL REFERENCES remito (id),
    fecha_creacion  TIMESTAMP NOT NULL,
    peso_kg         REAL      CHECK (peso_kg IS NULL OR peso_kg > 0),
    estado          TEXT      NOT NULL DEFAULT 'PREPARADO' CHECK (estado IN (
                        'PREPARADO', 'PRECINTADO', 'EN_TRANSITO',
                        'RECIBIDO', 'VERIFICADO', 'RECHAZADO')),
    motivo_rechazo  TEXT
);

CREATE INDEX IF NOT EXISTS ix_bulto_remito ON bulto (remito_id);
CREATE INDEX IF NOT EXISTS ix_bulto_estado ON bulto (estado);

-- Contenido de productos dentro de cada bulto.
CREATE TABLE IF NOT EXISTS detalle_bulto (
    id           INTEGER PRIMARY KEY AUTOINCREMENT,
    bulto_id     INTEGER NOT NULL REFERENCES bulto (id),
    producto_id  INTEGER NOT NULL REFERENCES producto (id),
    cantidad     INTEGER NOT NULL CHECK (cantidad > 0),
    UNIQUE (bulto_id, producto_id)
);

CREATE INDEX IF NOT EXISTS ix_detalle_bulto_bulto ON detalle_bulto (bulto_id);

-- Precinto de seguridad con numeración única asignado al cerrar un bulto (P4).
CREATE TABLE IF NOT EXISTS precinto (
    id                  INTEGER   PRIMARY KEY AUTOINCREMENT,
    numero              TEXT      NOT NULL UNIQUE COLLATE NOCASE,
    bulto_id            INTEGER   NOT NULL UNIQUE REFERENCES bulto (id),
    fecha_colocacion    TIMESTAMP NOT NULL,
    usuario_colocacion  TEXT      NOT NULL DEFAULT 'sistema'
);

-- Historial inmutable de cambios de estado del bulto (V2).
-- Solo admite INSERT: los triggers bloquean cualquier UPDATE o DELETE.
CREATE TABLE IF NOT EXISTS cambio_estado_bulto (
    id               INTEGER   PRIMARY KEY AUTOINCREMENT,
    bulto_id         INTEGER   NOT NULL REFERENCES bulto (id),
    fecha_hora       TIMESTAMP NOT NULL,
    estado_anterior  TEXT      CHECK (estado_anterior IS NULL OR estado_anterior IN (
                         'PREPARADO', 'PRECINTADO', 'EN_TRANSITO',
                         'RECIBIDO', 'VERIFICADO', 'RECHAZADO')),
    estado_nuevo     TEXT      NOT NULL CHECK (estado_nuevo IN (
                         'PREPARADO', 'PRECINTADO', 'EN_TRANSITO',
                         'RECIBIDO', 'VERIFICADO', 'RECHAZADO')),
    usuario          TEXT      NOT NULL DEFAULT 'sistema',
    observacion      TEXT      NOT NULL DEFAULT ''
);

CREATE INDEX IF NOT EXISTS ix_cambio_estado_bulto_bulto ON cambio_estado_bulto (bulto_id, fecha_hora, id);

CREATE TRIGGER IF NOT EXISTS cambio_estado_bulto_no_update
BEFORE UPDATE ON cambio_estado_bulto
BEGIN
    SELECT RAISE(ABORT, 'El historial de estados del bulto es inmutable: no se puede modificar.');
END;

CREATE TRIGGER IF NOT EXISTS cambio_estado_bulto_no_delete
BEFORE DELETE ON cambio_estado_bulto
BEGIN
    SELECT RAISE(ABORT, 'El historial de estados del bulto es inmutable: no se puede borrar.');
END;

-- Recepción de un remito en la sucursal destino (P6).
CREATE TABLE IF NOT EXISTS recepcion (
    id                  INTEGER   PRIMARY KEY AUTOINCREMENT,
    remito_id           INTEGER   NOT NULL UNIQUE REFERENCES remito (id),
    fecha_hora_llegada  TIMESTAMP NOT NULL,
    recibido_por        TEXT      NOT NULL,
    observaciones       TEXT      NOT NULL DEFAULT '' ,
    cerrada             BOOLEAN   NOT NULL DEFAULT 0 CHECK (cerrada IN (0, 1))
);

-- Control individual de precinto e integridad física de cada bulto recibido (P6, V1).
CREATE TABLE IF NOT EXISTS control_bulto (
    id                     INTEGER   PRIMARY KEY AUTOINCREMENT,
    recepcion_id           INTEGER   NOT NULL REFERENCES recepcion (id),
    bulto_id               INTEGER   NOT NULL UNIQUE REFERENCES bulto (id),
    numero_precinto_leido  TEXT      NOT NULL,
    precinto_integro       BOOLEAN   NOT NULL CHECK (precinto_integro IN (0, 1)),
    coincide_precinto      BOOLEAN   NOT NULL CHECK (coincide_precinto IN (0, 1)),
    resultado              TEXT      NOT NULL CHECK (resultado IN ('VERIFICADO', 'RECHAZADO')),
    observacion            TEXT      NOT NULL DEFAULT '',
    fecha_hora_control     TIMESTAMP NOT NULL
);

CREATE INDEX IF NOT EXISTS ix_control_bulto_recepcion ON control_bulto (recepcion_id);
