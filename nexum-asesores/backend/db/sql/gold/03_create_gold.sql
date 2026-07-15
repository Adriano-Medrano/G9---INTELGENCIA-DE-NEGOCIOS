-- ╔══════════════════════════════════════════════════════════════╗
-- ║  RENIEC — Schema GOLD (Esquema Estrella)                    ║
-- ║  5 dimensiones + 4 tablas de hechos                        ║
-- ║  Fuente directa para Power BI via DirectQuery               ║
-- ╚══════════════════════════════════════════════════════════════╝

CREATE SCHEMA IF NOT EXISTS gold;


-- ════════════════════════════════════════
--  DIMENSIONES
-- ════════════════════════════════════════

-- dim_tiempo: jerarquía temporal completa
CREATE TABLE IF NOT EXISTS gold.dim_tiempo (
    id_tiempo   INTEGER     PRIMARY KEY,   -- formato YYYYMM, ej. 202401
    anio        INTEGER     NOT NULL,
    num_mes     INTEGER     NOT NULL CHECK (num_mes BETWEEN 1 AND 12),
    mes_nombre  TEXT        NOT NULL,
    trimestre   INTEGER     NOT NULL CHECK (trimestre BETWEEN 1 AND 4),
    semestre    INTEGER     NOT NULL CHECK (semestre IN (1,2))
);

-- dim_local: centros de atención RENIEC
CREATE TABLE IF NOT EXISTS gold.dim_local (
    id_local     SERIAL  PRIMARY KEY,
    nombre_local TEXT    NOT NULL,
    departamento TEXT    NOT NULL,
    provincia    TEXT    NOT NULL,
    distrito     TEXT    NOT NULL,
    estado       TEXT,
    es_operativo INTEGER DEFAULT 0,   -- 1=activo
    es_lima      INTEGER DEFAULT 0,   -- 1=Lima (zona crítica)
    horario      TEXT,
    direccion    TEXT,
    anio_local   INTEGER,
    CONSTRAINT uq_local UNIQUE (nombre_local, anio_local)
);

-- dim_geografia: jerarquía geográfica
CREATE TABLE IF NOT EXISTS gold.dim_geografia (
    id_geo       SERIAL  PRIMARY KEY,
    departamento TEXT    NOT NULL,
    provincia    TEXT    NOT NULL,
    distrito     TEXT    NOT NULL,
    es_lima      INTEGER DEFAULT 0,
    CONSTRAINT uq_geo UNIQUE (departamento, provincia, distrito)
);

-- dim_tipo_transaccion: catálogo de servicios
CREATE TABLE IF NOT EXISTS gold.dim_tipo_transaccion (
    id_tipo          SERIAL PRIMARY KEY,
    tipo_transaccion TEXT   NOT NULL UNIQUE
);

-- dim_tipo_acta: catálogo de tipos de acta registral
CREATE TABLE IF NOT EXISTS gold.dim_tipo_acta (
    id_acta   SERIAL PRIMARY KEY,
    tipo_acta TEXT   NOT NULL UNIQUE
);


-- ════════════════════════════════════════
--  TABLAS DE HECHOS
-- ════════════════════════════════════════

-- fact_transacciones: medida principal de carga operativa
CREATE TABLE IF NOT EXISTS gold.fact_transacciones (
    id                 SERIAL  PRIMARY KEY,
    id_tiempo          INTEGER REFERENCES gold.dim_tiempo(id_tiempo),
    id_tipo            INTEGER REFERENCES gold.dim_tipo_transaccion(id_tipo),
    anio               INTEGER NOT NULL,
    num_mes            INTEGER NOT NULL,
    mes                TEXT    NOT NULL,
    departamento       TEXT    NOT NULL,
    local              TEXT    NOT NULL,
    tipo_transaccion   TEXT    NOT NULL,
    cant_transacciones INTEGER NOT NULL,
    nivel_carga        TEXT    NOT NULL,
    _source_file       TEXT,
    _loaded_at         TIMESTAMP
);

-- fact_certificados: certificados de inscripción C4
CREATE TABLE IF NOT EXISTS gold.fact_certificados (
    id                SERIAL  PRIMARY KEY,
    id_tiempo         INTEGER REFERENCES gold.dim_tiempo(id_tiempo),
    anio              INTEGER NOT NULL,
    num_mes           INTEGER NOT NULL,
    mes               TEXT    NOT NULL,
    departamento      TEXT    NOT NULL,
    sexo              TEXT    NOT NULL,
    rango_edad        TEXT    NOT NULL,
    cant_certificados INTEGER NOT NULL,
    _source_file      TEXT,
    _loaded_at        TIMESTAMP
);

-- fact_actas_oti: copias de actas registrales
CREATE TABLE IF NOT EXISTS gold.fact_actas_oti (
    id                           SERIAL  PRIMARY KEY,
    id_tiempo                    INTEGER REFERENCES gold.dim_tiempo(id_tiempo),
    id_acta                      INTEGER REFERENCES gold.dim_tipo_acta(id_acta),
    anio_registro                INTEGER NOT NULL,
    num_mes                      INTEGER NOT NULL,
    mes_registro                 TEXT    NOT NULL,
    tipo_acta                    TEXT    NOT NULL,
    de_genero                    TEXT,
    depart_ciudad_estado_dom_sol TEXT    NOT NULL,
    provincia_dom_sol            TEXT,
    cant_copias_emitidas         INTEGER NOT NULL,
    _source_file                 TEXT,
    _loaded_at                   TIMESTAMP
);

-- fact_carga_operativa: tabla agregada por local/mes (optimizada para Power BI)
CREATE TABLE IF NOT EXISTS gold.fact_carga_operativa (
    id                  SERIAL  PRIMARY KEY,
    id_tiempo           INTEGER REFERENCES gold.dim_tiempo(id_tiempo),
    anio                INTEGER NOT NULL,
    num_mes             INTEGER NOT NULL,
    mes                 TEXT    NOT NULL,
    departamento        TEXT    NOT NULL,
    local               TEXT    NOT NULL,
    nivel_carga         TEXT    NOT NULL,
    total_transacciones INTEGER NOT NULL,
    tipos_servicio      INTEGER NOT NULL,
    pico_mensual        INTEGER,
    promedio_mensual    NUMERIC(10,1)
);


-- ════════════════════════════════════════
--  ÍNDICES (rendimiento en Power BI)
-- ════════════════════════════════════════

CREATE INDEX IF NOT EXISTS idx_ft_dept    ON gold.fact_transacciones(departamento);
CREATE INDEX IF NOT EXISTS idx_ft_local   ON gold.fact_transacciones(local);
CREATE INDEX IF NOT EXISTS idx_ft_tiempo  ON gold.fact_transacciones(id_tiempo);
CREATE INDEX IF NOT EXISTS idx_ft_nivel   ON gold.fact_transacciones(nivel_carga);
CREATE INDEX IF NOT EXISTS idx_ft_anio    ON gold.fact_transacciones(anio);
CREATE INDEX IF NOT EXISTS idx_fc_dept    ON gold.fact_certificados(departamento);
CREATE INDEX IF NOT EXISTS idx_fo_dept    ON gold.fact_actas_oti(depart_ciudad_estado_dom_sol);
CREATE INDEX IF NOT EXISTS idx_fco_local  ON gold.fact_carga_operativa(local);
CREATE INDEX IF NOT EXISTS idx_fco_dept   ON gold.fact_carga_operativa(departamento);
CREATE INDEX IF NOT EXISTS idx_fco_nivel  ON gold.fact_carga_operativa(nivel_carga);


-- ════════════════════════════════════════
--  VISTAS analíticas (útiles en Power BI)
-- ════════════════════════════════════════

CREATE OR REPLACE VIEW gold.vw_kpis_globales AS
SELECT
    (SELECT SUM(cant_transacciones)   FROM gold.fact_transacciones)       AS total_transacciones,
    (SELECT SUM(cant_certificados)    FROM gold.fact_certificados)          AS total_certificados,
    (SELECT SUM(cant_copias_emitidas) FROM gold.fact_actas_oti)             AS total_copias_actas,
    (SELECT COUNT(DISTINCT local)     FROM gold.fact_transacciones)         AS locales_distintos,
    (SELECT COUNT(DISTINCT departamento) FROM gold.fact_transacciones)      AS departamentos,
    ROUND(
        100.0 * (SELECT SUM(cant_transacciones) FROM gold.fact_transacciones
                  WHERE departamento = 'LIMA')
             / NULLIF((SELECT SUM(cant_transacciones) FROM gold.fact_transacciones), 0),
    1) AS pct_concentracion_lima;


CREATE OR REPLACE VIEW gold.vw_carga_por_local AS
SELECT
    local,
    departamento,
    anio,
    SUM(cant_transacciones)              AS total_tx,
    ROUND(AVG(cant_transacciones), 1)    AS promedio_tx,
    MAX(cant_transacciones)              AS pico_tx,
    COUNT(DISTINCT tipo_transaccion)     AS tipos_servicio
FROM gold.fact_transacciones
GROUP BY local, departamento, anio;


CREATE OR REPLACE VIEW gold.vw_tendencia_mensual AS
SELECT
    anio,
    num_mes,
    mes,
    departamento,
    SUM(cant_transacciones)  AS total_tx,
    COUNT(DISTINCT local)    AS locales_activos
FROM gold.fact_transacciones
GROUP BY anio, num_mes, mes, departamento;


CREATE OR REPLACE VIEW gold.vw_sobrecarga_lima AS
SELECT
    local,
    anio,
    num_mes,
    mes,
    tipo_transaccion,
    SUM(cant_transacciones) AS total_tx,
    nivel_carga
FROM gold.fact_transacciones
WHERE departamento = 'LIMA'
GROUP BY local, anio, num_mes, mes, tipo_transaccion, nivel_carga;
