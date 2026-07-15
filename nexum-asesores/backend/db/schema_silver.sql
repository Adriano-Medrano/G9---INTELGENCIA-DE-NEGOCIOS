-- ============================================================
-- Nexum Asesores â€” Schema SILVER (PostgreSQL)
-- Datos normalizados, deduplicados y validados
-- Origen: Bronze (MinIO) â†’ Silver (este schema)
-- ============================================================

CREATE SCHEMA IF NOT EXISTS silver;

-- â”€â”€ Extensiones â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€
CREATE EXTENSION IF NOT EXISTS pgcrypto;  -- cifrado en reposo
CREATE EXTENSION IF NOT EXISTS pg_trgm;   -- bÃºsqueda fuzzy

-- â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•
-- stg_facturas â€” Facturas electrÃ³nicas normalizadas
-- Origen: XML/JSON de SUNAT / AEAT / API contable
-- â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•
CREATE TABLE IF NOT EXISTS silver.stg_facturas (
    factura_id          TEXT PRIMARY KEY,              -- ID del sistema origen
    cliente_id          TEXT NOT NULL,                 -- FK lÃ³gica a cliente
    fecha_emision       DATE NOT NULL,
    fecha_vencimiento   DATE,
    tipo                TEXT NOT NULL,                 -- "ingreso" | "gasto"
    concepto            TEXT,
    base_imponible      NUMERIC(14, 2) NOT NULL,
    tipo_iva_pct        NUMERIC(5, 2) DEFAULT 21.00,
    cuota_iva           NUMERIC(14, 2),
    total               NUMERIC(14, 2) NOT NULL,
    estado              TEXT NOT NULL DEFAULT 'emitida', -- emitida|cobrada|anulada
    proveedor_cliente   TEXT,                          -- NIF/CIF contraparte
    -- ValidaciÃ³n KYC (cruce con RENIEC)
    identidad_verificada BOOLEAN DEFAULT TRUE,
    contraparte_fallecida BOOLEAN DEFAULT FALSE,
    -- Metadatos ETL
    bronze_source_file  TEXT,
    cargado_en          TIMESTAMPTZ DEFAULT NOW(),
    hash_contenido      TEXT,                          -- SHA-256 para deduplicaciÃ³n
    -- Seguridad: cifrado de campo sensible
    nif_contraparte_enc BYTEA,                         -- pgp_sym_encrypt(nif, key)
    CONSTRAINT chk_tipo CHECK (tipo IN ('ingreso', 'gasto')),
    CONSTRAINT chk_estado CHECK (estado IN ('emitida','cobrada','anulada','vencida'))
);

CREATE INDEX IF NOT EXISTS idx_stg_facturas_cliente   ON silver.stg_facturas(cliente_id);
CREATE INDEX IF NOT EXISTS idx_stg_facturas_fecha     ON silver.stg_facturas(fecha_emision);
CREATE INDEX IF NOT EXISTS idx_stg_facturas_estado    ON silver.stg_facturas(estado);

-- â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•
-- stg_reniec_padron â€” PadrÃ³n nacional de identidad (RENIEC)
-- â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•
CREATE TABLE IF NOT EXISTS silver.stg_reniec_padron (
    dni                 TEXT PRIMARY KEY,
    nombres             TEXT NOT NULL,
    apellido_paterno    TEXT NOT NULL,
    apellido_materno    TEXT NOT NULL,
    fecha_nacimiento    DATE NOT NULL,
    sexo                CHAR(1) CHECK (sexo IN ('M', 'F')),
    estado_civil        TEXT,
    estado_vida         TEXT NOT NULL DEFAULT 'vivo',  -- "vivo" | "fallecido"
    ubigeo              TEXT,                          -- cÃ³digo geogrÃ¡fico de residencia
    direccion_declarada TEXT,
    fecha_emision_dni   DATE,
    cargado_en          TIMESTAMPTZ DEFAULT NOW(),
    CONSTRAINT chk_estado_vida CHECK (estado_vida IN ('vivo', 'fallecido'))
);

CREATE INDEX IF NOT EXISTS idx_reniec_estado_vida ON silver.stg_reniec_padron(estado_vida);
CREATE INDEX IF NOT EXISTS idx_reniec_nombres ON silver.stg_reniec_padron(nombres, apellido_paterno);

-- â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•
-- stg_declaraciones â€” Declaraciones fiscales histÃ³ricas
-- Origen: PDF/CSV + datos de AEAT
-- â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•
CREATE TABLE IF NOT EXISTS silver.stg_declaraciones (
    declaracion_id      TEXT PRIMARY KEY,
    cliente_id          TEXT NOT NULL,
    modelo_numero       TEXT NOT NULL,                 -- "303", "111", "200"...
    ejercicio           INT NOT NULL,                  -- 2024, 2025, 2026
    periodo             TEXT NOT NULL,                 -- "Q1", "Q2", "T1", "anual"
    fecha_vencimiento   DATE NOT NULL,
    fecha_presentacion  DATE,                          -- NULL si pendiente
    dias_atraso         INT GENERATED ALWAYS AS (
                            CASE
                                WHEN fecha_presentacion IS NOT NULL
                                THEN (fecha_presentacion - fecha_vencimiento)::INT
                                ELSE NULL
                            END
                        ) STORED,
    importe_liquidado   NUMERIC(14, 2),
    resultado           TEXT,                          -- "a_ingresar"|"a_devolver"|"cero"
    estado              TEXT NOT NULL DEFAULT 'pendiente',
    tiene_sancion       BOOLEAN DEFAULT FALSE,
    importe_sancion     NUMERIC(14, 2) DEFAULT 0,
    -- Metadatos ETL
    bronze_source_file  TEXT,
    cargado_en          TIMESTAMPTZ DEFAULT NOW(),
    CONSTRAINT chk_resultado CHECK (resultado IN ('a_ingresar','a_devolver','cero',NULL)),
    CONSTRAINT chk_estado_decl CHECK (estado IN ('pendiente','presentada','fuera_plazo','cancelada'))
);

CREATE INDEX IF NOT EXISTS idx_stg_decl_cliente   ON silver.stg_declaraciones(cliente_id);
CREATE INDEX IF NOT EXISTS idx_stg_decl_venc      ON silver.stg_declaraciones(fecha_vencimiento);
CREATE INDEX IF NOT EXISTS idx_stg_decl_modelo    ON silver.stg_declaraciones(modelo_numero);

-- â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•
-- stg_pagos â€” Pagos y cobros registrados
-- Origen: extracto bancario / API contable
-- â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•
CREATE TABLE IF NOT EXISTS silver.stg_pagos (
    pago_id             TEXT PRIMARY KEY,
    cliente_id          TEXT NOT NULL,
    fecha_operacion     DATE NOT NULL,
    fecha_valor         DATE,
    tipo                TEXT NOT NULL,                 -- "cobro" | "pago"
    concepto            TEXT,
    importe             NUMERIC(14, 2) NOT NULL,
    saldo_resultante    NUMERIC(14, 2),
    categoria           TEXT,                          -- "factura"|"impuesto"|"nomina"|"alquiler"
    factura_id_ref      TEXT REFERENCES silver.stg_facturas(factura_id),
    declaracion_id_ref  TEXT REFERENCES silver.stg_declaraciones(declaracion_id),
    cargado_en          TIMESTAMPTZ DEFAULT NOW(),
    CONSTRAINT chk_tipo_pago CHECK (tipo IN ('cobro','pago'))
);

CREATE INDEX IF NOT EXISTS idx_stg_pagos_cliente ON silver.stg_pagos(cliente_id);
CREATE INDEX IF NOT EXISTS idx_stg_pagos_fecha   ON silver.stg_pagos(fecha_operacion);

-- â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•
-- stg_clientes â€” Maestro de clientes
-- â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•
CREATE TABLE IF NOT EXISTS silver.stg_clientes (
    cliente_id          TEXT PRIMARY KEY,
    razon_social        TEXT NOT NULL,
    nif_enc             BYTEA,                         -- NIF cifrado
    dni_representante   TEXT,                          -- Cruzado con RENIEC
    identidad_representante_confirmada BOOLEAN DEFAULT TRUE,
    sector              TEXT,
    codigo_cnae         TEXT,
    regimen_iva         TEXT,
    regimen_irpf        TEXT,
    fecha_alta          DATE,
    plan_nexum          TEXT,                          -- consulta|recurrente|integral
    asesor_asignado     TEXT,
    activo              BOOLEAN DEFAULT TRUE,
    cargado_en          TIMESTAMPTZ DEFAULT NOW()
);

-- â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•
-- 2. stg_usuarios â€” Usuarios del portal (para autenticaciÃ³n)
-- â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•
CREATE TABLE IF NOT EXISTS silver.stg_usuarios (
    usuario_id          SERIAL PRIMARY KEY,
    email               TEXT UNIQUE NOT NULL,
    password_hash       TEXT NOT NULL,                 -- hash bcrypt
    cliente_id          TEXT REFERENCES silver.stg_clientes(cliente_id),
    nombre              TEXT NOT NULL,
    cargado_en          TIMESTAMPTZ DEFAULT NOW()
);

-- â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•
-- Audit log â€” registro de accesos a datos sensibles
-- â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•
CREATE TABLE IF NOT EXISTS silver.audit_log (
    log_id              BIGSERIAL PRIMARY KEY,
    cliente_id          TEXT,
    usuario_email       TEXT,
    endpoint            TEXT,
    accion              TEXT,
    ip_origen           TEXT,
    user_agent          TEXT,
    timestamp_utc       TIMESTAMPTZ DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_audit_cliente ON silver.audit_log(cliente_id);
CREATE INDEX IF NOT EXISTS idx_audit_ts      ON silver.audit_log(timestamp_utc DESC);

-- â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•
-- Vista de calidad de datos (usada por silver_transform.py)
-- â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•
CREATE OR REPLACE VIEW silver.v_calidad_facturas AS
SELECT
    cliente_id,
    COUNT(*)                                         AS total_facturas,
    COUNT(*) FILTER (WHERE total IS NULL)            AS sin_importe,
    COUNT(*) FILTER (WHERE hash_contenido IS NULL)   AS sin_hash,
    COUNT(*) FILTER (WHERE fecha_emision > NOW())    AS fecha_futura,
    ROUND(
        100.0 * COUNT(*) FILTER (WHERE total IS NOT NULL AND hash_contenido IS NOT NULL)
        / NULLIF(COUNT(*), 0), 2
    )                                                AS pct_calidad
FROM silver.stg_facturas
GROUP BY cliente_id;

COMMENT ON SCHEMA silver IS
    'Capa Silver: datos normalizados y validados, listos para enriquecimiento. '
    'Alimentada por el ETL silver_transform.py (Airflow dag_silver).';

