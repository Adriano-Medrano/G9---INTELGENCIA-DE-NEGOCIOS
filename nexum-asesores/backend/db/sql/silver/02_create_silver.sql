-- ╔══════════════════════════════════════════════════════════════╗
-- ║  RENIEC — Schema SILVER                                     ║
-- ║  Tablas staging: normalizadas, limpias, con linaje          ║
-- ║  Ejecutar: psql -U postgres -d reniec_dwh -f este_archivo   ║
-- ╚══════════════════════════════════════════════════════════════╝

CREATE SCHEMA IF NOT EXISTS silver;

-- ── Certificados C4 ──────────────────────────────────────────────────────────
CREATE TABLE IF NOT EXISTS silver.stg_certificados (
    id                SERIAL PRIMARY KEY,
    anio              INTEGER     NOT NULL,
    num_mes           INTEGER     NOT NULL CHECK (num_mes BETWEEN 1 AND 12),
    mes               TEXT        NOT NULL,
    departamento      TEXT        NOT NULL,
    sexo              TEXT        NOT NULL,
    rango_edad        TEXT        NOT NULL,
    cant_certificados INTEGER     NOT NULL CHECK (cant_certificados >= 0),
    _source_file      TEXT,
    _loaded_at        TIMESTAMP   DEFAULT NOW(),
    CONSTRAINT uq_cert UNIQUE (anio, num_mes, departamento, sexo, rango_edad)
);

-- ── Centros de atención ───────────────────────────────────────────────────────
CREATE TABLE IF NOT EXISTS silver.stg_centros (
    id             SERIAL PRIMARY KEY,
    nombre_local   TEXT    NOT NULL,
    departamento   TEXT    NOT NULL,
    provincia      TEXT    NOT NULL,
    distrito       TEXT    NOT NULL,
    estado         TEXT,
    es_operativo   INTEGER DEFAULT 0,
    es_lima        INTEGER DEFAULT 0,
    horario        TEXT,
    direccion      TEXT,
    anio           INTEGER,
    _source_file   TEXT,
    _loaded_at     TIMESTAMP DEFAULT NOW(),
    CONSTRAINT uq_centro UNIQUE (nombre_local, anio)
);

-- ── Transacciones por local ───────────────────────────────────────────────────
CREATE TABLE IF NOT EXISTS silver.stg_transacciones (
    id                  SERIAL PRIMARY KEY,
    anio                INTEGER     NOT NULL,
    num_mes             INTEGER     NOT NULL CHECK (num_mes BETWEEN 1 AND 12),
    mes                 TEXT        NOT NULL,
    departamento        TEXT        NOT NULL,
    provincia           TEXT,
    distrito            TEXT,
    local               TEXT        NOT NULL,
    tipo_transaccion    TEXT        NOT NULL,
    cant_transacciones  INTEGER     NOT NULL CHECK (cant_transacciones > 0),
    nivel_carga         TEXT        NOT NULL CHECK (nivel_carga IN ('ALTA','MEDIA','BAJA')),
    _source_file        TEXT,
    _loaded_at          TIMESTAMP   DEFAULT NOW(),
    CONSTRAINT uq_transaccion UNIQUE (anio, num_mes, local, tipo_transaccion)
);

-- ── Actas OTI ─────────────────────────────────────────────────────────────────
CREATE TABLE IF NOT EXISTS silver.stg_actas_oti (
    id                           SERIAL PRIMARY KEY,
    anio_registro                INTEGER     NOT NULL,
    num_mes                      INTEGER     NOT NULL CHECK (num_mes BETWEEN 1 AND 12),
    mes_registro                 TEXT        NOT NULL,
    tipo_acta                    TEXT        NOT NULL,
    de_genero                    TEXT,
    depart_ciudad_estado_dom_sol TEXT        NOT NULL,
    provincia_dom_sol            TEXT,
    cant_copias_emitidas         INTEGER     NOT NULL CHECK (cant_copias_emitidas > 0),
    _source_file                 TEXT,
    _loaded_at                   TIMESTAMP   DEFAULT NOW(),
    CONSTRAINT uq_acta UNIQUE (anio_registro, num_mes, tipo_acta,
                               depart_ciudad_estado_dom_sol, de_genero)
);

-- ── Índices para acelerar la carga al Gold ────────────────────────────────────
CREATE INDEX IF NOT EXISTS idx_stg_tx_dept  ON silver.stg_transacciones(departamento);
CREATE INDEX IF NOT EXISTS idx_stg_tx_local ON silver.stg_transacciones(local);
CREATE INDEX IF NOT EXISTS idx_stg_tx_anio  ON silver.stg_transacciones(anio);
CREATE INDEX IF NOT EXISTS idx_stg_actas_dept ON silver.stg_actas_oti(depart_ciudad_estado_dom_sol);

-- ── Log de ingestión (cargado por el paso Bronze) ─────────────────────────────
CREATE SCHEMA IF NOT EXISTS bronze;
CREATE TABLE IF NOT EXISTS bronze.ingestion_log (
    id           SERIAL PRIMARY KEY,
    filename     TEXT        NOT NULL,
    md5_hash     TEXT        NOT NULL,
    minio_path   TEXT        NOT NULL,
    rows_count   INTEGER,
    ingested_at  TIMESTAMP   NOT NULL DEFAULT NOW()
);
