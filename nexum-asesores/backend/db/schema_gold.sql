-- ============================================================
-- Nexum Asesores — Schema GOLD (PostgreSQL)
-- Esquema estrella para analítica y ML
-- Silver → Gold vía gold_build.py (Airflow dag_gold)
-- ============================================================

CREATE SCHEMA IF NOT EXISTS gold;

-- ════════════════════════════════════════════════════════════
-- DIMENSIONES
-- ════════════════════════════════════════════════════════════

-- dim_tiempo — Calendario fiscal completo
CREATE TABLE IF NOT EXISTS gold.dim_tiempo (
    tiempo_key          SERIAL PRIMARY KEY,
    fecha               DATE UNIQUE NOT NULL,
    anio                INT,
    trimestre           INT,          -- 1-4
    mes                 INT,
    semana_iso          INT,
    dia_semana          INT,          -- 1=lunes ... 7=domingo
    es_festivo          BOOLEAN DEFAULT FALSE,
    es_dia_vencimiento  BOOLEAN DEFAULT FALSE,  -- 20 ene/abr/jul/oct, 25 jul...
    periodo_fiscal      TEXT,         -- "Q1-2026", "Q2-2026"...
    descripcion_periodo TEXT
);

CREATE INDEX IF NOT EXISTS idx_gold_dim_tiempo_fecha ON gold.dim_tiempo(fecha);

-- Población inicial: 2020-2030
INSERT INTO gold.dim_tiempo (fecha, anio, trimestre, mes, semana_iso, dia_semana, periodo_fiscal)
SELECT
    d::DATE,
    EXTRACT(YEAR  FROM d)::INT,
    EXTRACT(QUARTER FROM d)::INT,
    EXTRACT(MONTH FROM d)::INT,
    EXTRACT(WEEK  FROM d)::INT,
    EXTRACT(ISODOW FROM d)::INT,
    'Q' || EXTRACT(QUARTER FROM d)::TEXT || '-' || EXTRACT(YEAR FROM d)::TEXT
FROM generate_series('2020-01-01'::DATE, '2030-12-31'::DATE, '1 day') d
ON CONFLICT (fecha) DO NOTHING;

-- Marcar días de vencimiento AEAT (20 ene, 20 abr, 20 jul, 20 oct, 25 jul)
UPDATE gold.dim_tiempo SET es_dia_vencimiento = TRUE
WHERE (mes IN (1, 4, 10) AND EXTRACT(DAY FROM fecha) = 20)
   OR (mes = 7 AND EXTRACT(DAY FROM fecha) IN (20, 25));


-- dim_cliente — Maestro de clientes
CREATE TABLE IF NOT EXISTS gold.dim_cliente (
    cliente_key         SERIAL PRIMARY KEY,
    cliente_id          TEXT UNIQUE NOT NULL,
    razon_social        TEXT NOT NULL,
    sector              TEXT,
    codigo_cnae         TEXT,
    regimen_iva         TEXT,
    plan_nexum          TEXT,
    asesor_asignado     TEXT,
    fecha_alta          DATE,
    activo              BOOLEAN DEFAULT TRUE,
    -- SCD Tipo 1 (última versión)
    ultima_actualizacion TIMESTAMPTZ DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_gold_dim_cliente_id ON gold.dim_cliente(cliente_id);


-- dim_tipo_impuesto — Catálogo de modelos fiscales
CREATE TABLE IF NOT EXISTS gold.dim_tipo_impuesto (
    impuesto_key        SERIAL PRIMARY KEY,
    codigo_modelo       TEXT UNIQUE NOT NULL,   -- "303", "111", "200"
    nombre_completo     TEXT NOT NULL,
    descripcion         TEXT,
    periodicidad        TEXT,                   -- "trimestral"|"anual"|"mensual"
    fecha_vencimiento_tipica TEXT,              -- "20 del mes siguiente al Q"
    aplica_pyme         BOOLEAN DEFAULT TRUE
);

-- Catálogo base de modelos AEAT
INSERT INTO gold.dim_tipo_impuesto (codigo_modelo, nombre_completo, periodicidad, fecha_vencimiento_tipica)
VALUES
    ('303',  'IVA — Autoliquidación trimestral',           'trimestral', '20 ene/abr/jul/oct'),
    ('111',  'IRPF — Retenciones e ingresos a cuenta',     'trimestral', '20 ene/abr/jul/oct'),
    ('115',  'Retenciones arrendamiento inmueble',          'trimestral', '20 ene/abr/jul/oct'),
    ('130',  'IRPF — Pago fraccionado (estimación directa)','trimestral', '20 ene/abr/jul/oct'),
    ('200',  'Impuesto sobre Sociedades',                   'anual',      '25 días tras 6 meses del cierre'),
    ('349',  'Declaración recapitulativa operaciones intracomunitarias', 'mensual/trimestral', 'Último día del mes siguiente'),
    ('390',  'IVA — Resumen anual',                        'anual',      '30 enero año siguiente'),
    ('100',  'IRPF — Declaración anual (autónomos SL)',    'anual',      '30 junio año siguiente')
ON CONFLICT (codigo_modelo) DO NOTHING;


-- ════════════════════════════════════════════════════════════
-- TABLAS DE HECHOS (FACTS)
-- ════════════════════════════════════════════════════════════

-- fact_flujo_caja — Flujo de caja real mensual por cliente
CREATE TABLE IF NOT EXISTS gold.fact_flujo_caja (
    flujo_key           BIGSERIAL PRIMARY KEY,
    tiempo_key          INT REFERENCES gold.dim_tiempo(tiempo_key),
    cliente_key         INT REFERENCES gold.dim_cliente(cliente_key),
    ingreso_bruto       NUMERIC(16, 2) DEFAULT 0,
    ingreso_cobrado     NUMERIC(16, 2) DEFAULT 0,
    gasto_total         NUMERIC(16, 2) DEFAULT 0,
    gasto_fiscal        NUMERIC(16, 2) DEFAULT 0,     -- impuestos pagados
    flujo_neto          NUMERIC(16, 2) GENERATED ALWAYS AS (ingreso_cobrado - gasto_total) STORED,
    n_facturas_emitidas INT DEFAULT 0,
    n_facturas_cobradas INT DEFAULT 0,
    cargado_en          TIMESTAMPTZ DEFAULT NOW(),
    UNIQUE (tiempo_key, cliente_key)
);

CREATE INDEX IF NOT EXISTS idx_fact_flujo_cliente ON gold.fact_flujo_caja(cliente_key);
CREATE INDEX IF NOT EXISTS idx_fact_flujo_tiempo  ON gold.fact_flujo_caja(tiempo_key);


-- fact_declaraciones — Declaraciones con métricas de cumplimiento
CREATE TABLE IF NOT EXISTS gold.fact_declaraciones (
    declaracion_key     BIGSERIAL PRIMARY KEY,
    tiempo_key          INT REFERENCES gold.dim_tiempo(tiempo_key),     -- fecha vencimiento
    cliente_key         INT REFERENCES gold.dim_cliente(cliente_key),
    impuesto_key        INT REFERENCES gold.dim_tipo_impuesto(impuesto_key),
    declaracion_id      TEXT,
    ejercicio           INT,
    periodo             TEXT,
    fecha_presentacion  DATE,
    dias_atraso         INT DEFAULT 0,       -- 0 = a tiempo; >0 = tardío; NULL = pendiente
    importe_estimado    NUMERIC(14, 2),
    resultado           TEXT,
    estado              TEXT,
    tiene_sancion       BOOLEAN DEFAULT FALSE,
    importe_sancion     NUMERIC(14, 2) DEFAULT 0,
    cargado_en          TIMESTAMPTZ DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_fact_decl_cliente ON gold.fact_declaraciones(cliente_key);
CREATE INDEX IF NOT EXISTS idx_fact_decl_tiempo  ON gold.fact_declaraciones(tiempo_key);


-- fact_score_riesgo — Score XGBoost por cliente (actualización semanal)
CREATE TABLE IF NOT EXISTS gold.fact_score_riesgo (
    score_key           BIGSERIAL PRIMARY KEY,
    tiempo_key          INT REFERENCES gold.dim_tiempo(tiempo_key),
    cliente_key         INT REFERENCES gold.dim_cliente(cliente_key),
    score               INT NOT NULL CHECK (score BETWEEN 0 AND 100),
    nivel               TEXT NOT NULL CHECK (nivel IN ('bajo','moderado','alto')),
    variacion_vs_anterior INT DEFAULT 0,
    -- Métricas de KYC / RENIEC
    n_dni_sospechosos   INT DEFAULT 0,
    alertas_kyc_activas INT DEFAULT 0,
    modelo_version      TEXT,
    calculado_en        TIMESTAMPTZ DEFAULT NOW(),
    UNIQUE (tiempo_key, cliente_key)
);

-- Tabla auxiliar: SHAP values por feature (feature importance por cliente)
CREATE TABLE IF NOT EXISTS gold.fact_score_riesgo_features (
    feature_key         BIGSERIAL PRIMARY KEY,
    score_key           BIGINT REFERENCES gold.fact_score_riesgo(score_key),
    nombre_feature      TEXT NOT NULL,
    shap_value          NUMERIC(8, 4),          -- contribución al score
    importancia_pct     NUMERIC(5, 2),          -- 0-100
    valor_actual        TEXT,
    estado              TEXT CHECK (estado IN ('ok','warn','bad'))
);

CREATE INDEX IF NOT EXISTS idx_fact_score_cliente  ON gold.fact_score_riesgo(cliente_key);
CREATE INDEX IF NOT EXISTS idx_fact_feature_score  ON gold.fact_score_riesgo_features(score_key);


-- fact_prediccion_caja — Proyección Prophet por cliente (actualización diaria post-Gold)
CREATE TABLE IF NOT EXISTS gold.fact_prediccion_caja (
    prediccion_key      BIGSERIAL PRIMARY KEY,
    cliente_key         INT REFERENCES gold.dim_cliente(cliente_key),
    fecha_prediccion    DATE NOT NULL,
    yhat                NUMERIC(14, 2),        -- valor central Prophet
    yhat_lower          NUMERIC(14, 2),        -- banda inferior 80%
    yhat_upper          NUMERIC(14, 2),        -- banda superior 80%
    horizonte_dias      INT,                   -- 30, 60 o 90
    modelo_version      TEXT,
    generado_en         TIMESTAMPTZ DEFAULT NOW(),
    UNIQUE (cliente_key, fecha_prediccion)
);

CREATE INDEX IF NOT EXISTS idx_fact_pred_cliente ON gold.fact_prediccion_caja(cliente_key);
CREATE INDEX IF NOT EXISTS idx_fact_pred_fecha   ON gold.fact_prediccion_caja(fecha_prediccion);


-- ════════════════════════════════════════════════════════════
-- ROW-LEVEL SECURITY — Cada cliente solo ve sus datos
-- ════════════════════════════════════════════════════════════

-- Habilitar RLS en tablas de hechos
ALTER TABLE gold.fact_flujo_caja       ENABLE ROW LEVEL SECURITY;
ALTER TABLE gold.fact_declaraciones    ENABLE ROW LEVEL SECURITY;
ALTER TABLE gold.fact_score_riesgo     ENABLE ROW LEVEL SECURITY;
ALTER TABLE gold.fact_prediccion_caja  ENABLE ROW LEVEL SECURITY;

-- Política: el cliente_id en el JWT debe coincidir con el de la fila
-- La API FastAPI establece: SET LOCAL app.client_id = :cliente_id
CREATE POLICY client_isolation_flujo
    ON gold.fact_flujo_caja
    USING (
        cliente_key = (
            SELECT cliente_key FROM gold.dim_cliente
            WHERE cliente_id = current_setting('app.client_id', TRUE)
        )
    );

CREATE POLICY client_isolation_decl
    ON gold.fact_declaraciones
    USING (
        cliente_key = (
            SELECT cliente_key FROM gold.dim_cliente
            WHERE cliente_id = current_setting('app.client_id', TRUE)
        )
    );

CREATE POLICY client_isolation_score
    ON gold.fact_score_riesgo
    USING (
        cliente_key = (
            SELECT cliente_key FROM gold.dim_cliente
            WHERE cliente_id = current_setting('app.client_id', TRUE)
        )
    );

CREATE POLICY client_isolation_pred
    ON gold.fact_prediccion_caja
    USING (
        cliente_key = (
            SELECT cliente_key FROM gold.dim_cliente
            WHERE cliente_id = current_setting('app.client_id', TRUE)
        )
    );


-- ════════════════════════════════════════════════════════════
-- VISTAS ANALÍTICAS (para Power BI DirectQuery)
-- ════════════════════════════════════════════════════════════

-- Vista: resumen ejecutivo por cliente (portada del dashboard)
CREATE OR REPLACE VIEW gold.v_resumen_cliente AS
SELECT
    c.cliente_id,
    c.razon_social,
    c.sector,
    c.plan_nexum,
    sr.score                     AS score_riesgo_actual,
    sr.nivel                     AS nivel_riesgo,
    sr.variacion_vs_anterior     AS variacion_score,
    sr.calculado_en              AS score_calculado_en,
    pred_30.yhat                 AS proyeccion_caja_30d,
    pred_60.yhat                 AS proyeccion_caja_60d,
    pred_90.yhat                 AS proyeccion_caja_90d,
    -- Cumplimiento: ratio declaraciones a tiempo
    ROUND(
        100.0 * COUNT(fd.declaracion_key) FILTER (
            WHERE fd.dias_atraso = 0 AND fd.estado = 'presentada'
        ) / NULLIF(COUNT(fd.declaracion_key), 0), 1
    )                            AS pct_cumplimiento_anio
FROM gold.dim_cliente c
LEFT JOIN gold.fact_score_riesgo sr
    ON sr.cliente_key = c.cliente_key
    AND sr.calculado_en = (
        SELECT MAX(calculado_en) FROM gold.fact_score_riesgo
        WHERE cliente_key = c.cliente_key
    )
LEFT JOIN gold.fact_prediccion_caja pred_30
    ON pred_30.cliente_key = c.cliente_key
    AND pred_30.fecha_prediccion = CURRENT_DATE + 30
LEFT JOIN gold.fact_prediccion_caja pred_60
    ON pred_60.cliente_key = c.cliente_key
    AND pred_60.fecha_prediccion = CURRENT_DATE + 60
LEFT JOIN gold.fact_prediccion_caja pred_90
    ON pred_90.cliente_key = c.cliente_key
    AND pred_90.fecha_prediccion = CURRENT_DATE + 90
LEFT JOIN gold.fact_declaraciones fd
    ON fd.cliente_key = c.cliente_key
    AND fd.ejercicio = EXTRACT(YEAR FROM CURRENT_DATE)::INT
WHERE c.activo = TRUE
GROUP BY
    c.cliente_id, c.razon_social, c.sector, c.plan_nexum,
    sr.score, sr.nivel, sr.variacion_vs_anterior, sr.calculado_en,
    pred_30.yhat, pred_60.yhat, pred_90.yhat;

COMMENT ON SCHEMA gold IS
    'Capa Gold: esquema estrella para analítica, ML y Power BI. '
    'Con RLS por cliente y vistas para DirectQuery. '
    'Alimentada por gold_build.py (Airflow dag_gold, diario 04:00).';

-- ════════════════════════════════════════════════════════════
-- SEED DATA (Datos semilla de prueba)
-- ════════════════════════════════════════════════════════════

-- 1. Insertar clientes
INSERT INTO silver.stg_clientes (cliente_id, razon_social, sector, activo)
VALUES ('CL-2024-0042', 'Tecnopyme SL', 'Servicios profesionales', TRUE)
ON CONFLICT (cliente_id) DO NOTHING;

INSERT INTO gold.dim_cliente (cliente_id, razon_social, sector, activo)
VALUES ('CL-2024-0042', 'Tecnopyme SL', 'Servicios profesionales', TRUE)
ON CONFLICT (cliente_id) DO NOTHING;

-- 2. Insertar usuario para la demo
INSERT INTO silver.stg_usuarios (email, password_hash, cliente_id, nombre)
VALUES ('demo@pyme.es', '$2b$12$t6WUEMmwp52pgMINh.91guEJStaeyZrkMC2MvsRot5MgCj0Nfcu0a', 'CL-2024-0042', 'Tecnopyme SL')
ON CONFLICT (email) DO NOTHING;

-- 3. Insertar padrón de ciudadanos (RENIEC) en silver
INSERT INTO silver.stg_reniec_padron (dni, nombres, apellido_paterno, apellido_materno, fecha_nacimiento, sexo, estado_civil, estado_vida, ubigeo, direccion_declarada)
VALUES 
    ('12345678', 'JUAN CARLOS', 'PEREZ', 'RAMIREZ', '1984-06-15', 'M', 'casado', 'vivo', 'Lima', 'Av. Larco 123, Lima'),
    ('87654321', 'MARIA ELENA', 'GONZALES', 'CASTRO', '1942-11-20', 'F', 'viudo', 'fallecido', 'Arequipa', 'Calle Melgar 456, Arequipa'),
    ('11112222', 'ANDRES AVELINO', 'RODRIGUEZ', 'CACERES', '2005-01-10', 'M', 'soltero', 'vivo', 'Ayacucho', 'Jr. 28 de Julio 789, Ayacucho')
ON CONFLICT (dni) DO NOTHING;

-- 4. Insertar facturas en silver
INSERT INTO silver.stg_facturas (factura_id, cliente_id, fecha_emision, fecha_vencimiento, tipo, concepto, base_imponible, total, estado, proveedor_cliente, identidad_verificada, contraparte_fallecida)
VALUES
    ('F-2026-0001', 'CL-2024-0042', CURRENT_DATE - 5, CURRENT_DATE + 25, 'ingreso', 'Servicios de Consultoría TI', 3500.00, 4235.00, 'emitida', '20456789012', TRUE, FALSE),
    ('F-2026-0002', 'CL-2024-0042', CURRENT_DATE - 10, CURRENT_DATE + 20, 'gasto', 'Licencia de software anual', 890.00, 1076.90, 'emitida', '87654321', FALSE, TRUE)
ON CONFLICT (factura_id) DO NOTHING;

-- 5. Insertar declaraciones de impuestos en silver
INSERT INTO silver.stg_declaraciones (declaracion_id, cliente_id, modelo_numero, ejercicio, periodo, fecha_vencimiento, fecha_presentacion, importe_liquidado, resultado, estado)
VALUES
    ('DEC-2026-111', 'CL-2024-0042', '111', 2026, 'Q2', '2026-07-20', NULL, 3840.00, 'a_ingresar', 'pendiente'),
    ('DEC-2026-115', 'CL-2024-0042', '115', 2026, 'Q2', '2026-07-20', NULL, 890.00, 'a_ingresar', 'pendiente'),
    ('DEC-2026-130', 'CL-2024-0042', '130', 2026, 'Q2', '2026-07-20', NULL, 1200.00, 'a_ingresar', 'pendiente'),
    ('DEC-2025-200', 'CL-2024-0042', '200', 2025, 'anual', '2026-07-25', NULL, 12400.00, 'a_ingresar', 'pendiente'),
    ('DEC-2026-303-Q3', 'CL-2024-0042', '303', 2026, 'Q3', '2026-10-20', NULL, 7240.00, 'a_ingresar', 'pendiente'),
    ('DEC-2026-303-Q2', 'CL-2024-0042', '303', 2026, 'Q2', '2026-04-20', '2026-04-20', 6840.00, 'a_ingresar', 'presentada')
ON CONFLICT (declaracion_id) DO NOTHING;

-- 6. Insertar declaraciones en gold.fact_declaraciones
INSERT INTO gold.fact_declaraciones (tiempo_key, cliente_key, impuesto_key, declaracion_id, ejercicio, periodo, fecha_presentacion, dias_atraso, importe_estimado, resultado, estado)
SELECT 
    t.tiempo_key,
    c.cliente_key,
    i.impuesto_key,
    d.declaracion_id,
    d.ejercicio,
    d.periodo,
    d.fecha_presentacion,
    COALESCE(d.dias_atraso, 0),
    d.importe_liquidado,
    d.resultado,
    d.estado
FROM silver.stg_declaraciones d
JOIN gold.dim_cliente c ON c.cliente_id = d.cliente_id
JOIN gold.dim_tipo_impuesto i ON i.codigo_modelo = d.modelo_numero
JOIN gold.dim_tiempo t ON t.fecha = d.fecha_vencimiento
ON CONFLICT (declaracion_key) DO NOTHING;

-- 7. Insertar historial de score de riesgo (gold.fact_score_riesgo)
INSERT INTO gold.fact_score_riesgo (tiempo_key, cliente_key, score, nivel, variacion_vs_anterior, n_dni_sospechosos, alertas_kyc_activas, modelo_version, calculado_en)
SELECT
    t.tiempo_key,
    c.cliente_key,
    42,
    'moderado',
    -8,
    1,
    2,
    'xgboost-v2.5.0-kyc-shield',
    CURRENT_TIMESTAMP
FROM gold.dim_cliente c
JOIN gold.dim_tiempo t ON t.fecha = CURRENT_DATE
ON CONFLICT (tiempo_key, cliente_key) DO NOTHING;

-- 8. Insertar características del score de riesgo (gold.fact_score_riesgo_features)
INSERT INTO gold.fact_score_riesgo_features (score_key, nombre_feature, shap_value, importancia_pct, valor_actual, estado)
SELECT
    sr.score_key,
    f.nombre,
    f.shap,
    f.pct,
    f.valor,
    f.est
FROM gold.fact_score_riesgo sr
CROSS JOIN (
    VALUES
        ('Días promedio atraso',         0.12, 38.0, '2.3 días',         'ok'),
        ('Inconsistencias IVA/IRPF',     0.05, 25.0, '0.04 ratio',        'ok'),
        ('Facturas contraparte fallecida', 0.45, 72.0, '1 (detectada)',   'bad'),
        ('Identidades inválidas en padrón',0.00, 65.0, '0.0% de facturas', 'ok'),
        ('Desviación de ubigeo fiscal',   0.15, 30.0, '15% de compras',   'warn'),
        ('Suplantación de representante',  0.02, 15.0, 'No detectado',     'ok')
) AS f(nombre, shap, pct, valor, est)
WHERE sr.cliente_key = (SELECT cliente_key FROM gold.dim_cliente WHERE cliente_id = 'CL-2024-0042')
ON CONFLICT (feature_key) DO NOTHING;

-- 9. Insertar histórico de flujo de caja real (gold.fact_flujo_caja)
INSERT INTO gold.fact_flujo_caja (tiempo_key, cliente_key, ingreso_bruto, ingreso_cobrado, gasto_total, gasto_fiscal, n_facturas_emitidas, n_facturas_cobradas)
SELECT 
    t.tiempo_key,
    c.cliente_key,
    f.ingreso,
    f.ingreso,
    f.gasto,
    0,
    10,
    10
FROM gold.dim_cliente c
CROSS JOIN (
    VALUES
        ('2026-01-15', 38200.00, 0.00),
        ('2026-02-15', 29800.00, 0.00),
        ('2026-03-15', 41500.00, 0.00),
        ('2026-04-15', 35600.00, 0.00),
        ('2026-05-15', 44200.00, 0.00),
        ('2026-06-15', 31800.00, 0.00)
) AS f(fecha, ingreso, gasto)
JOIN gold.dim_tiempo t ON t.fecha = f.fecha::DATE
ON CONFLICT (tiempo_key, cliente_key) DO NOTHING;

-- 10. Insertar proyección de flujo de caja (gold.fact_prediccion_caja)
INSERT INTO gold.fact_prediccion_caja (cliente_key, fecha_prediccion, yhat, yhat_lower, yhat_upper, horizonte_dias, modelo_version, generado_en)
SELECT
    c.cliente_key,
    p.fecha::DATE,
    p.yhat,
    p.lower,
    p.upper,
    90,
    'prophet-v1.8.0',
    CURRENT_TIMESTAMP
FROM gold.dim_cliente c
CROSS JOIN (
    VALUES
        ('2026-06-15', 31800.00, 30100.00, 33500.00),
        ('2026-07-15', 28400.00, 25200.00, 31600.00),
        ('2026-07-20', 31450.00, 26000.00, 31800.00),
        ('2026-07-25', 28400.00, 23000.00, 29400.00),
        ('2026-08-15', 24800.00, 20400.00, 29200.00),
        ('2026-09-15', 18200.00, 13800.00, 22600.00),
        ('2026-10-15', 9100.00,  5200.00,  13000.00),
        ('2026-10-20', 9100.00,  5200.00,  13000.00)
) AS p(fecha, yhat, lower, upper)
WHERE c.cliente_id = 'CL-2024-0042'
ON CONFLICT (cliente_key, fecha_prediccion) DO NOTHING;
