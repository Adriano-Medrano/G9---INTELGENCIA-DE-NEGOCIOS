# Guía de Colaboración e Integración — Nexum KYC & Tax Shield (Grupo 9)

Esta guía explica a los responsables de **ETL/Data Pipeline** y de **Modelos Predictivos (ML)** cómo integrar sus partes en el repositorio de GitHub utilizando el nuevo servicio de verificación de identidad cruzado con la **RENIEC**.

---

## 📁 Dónde colocar cada parte (Mapa de Integración)

Cada compañero debe trabajar en su respectivo directorio dentro de `nexum-asesores/backend/`:

```
nexum-asesores/
└── backend/
    ├── dags/            ◄── [COMPAÑERO DE ETL] DAGs de Airflow (ingesta y carga)
    ├── db/              ◄── [COMPAÑERO DE ETL] Esquemas DDL SQL (Silver + Gold + RENIEC)
    ├── etl/             ◄── [COMPAÑERO DE ETL] Scripts Python de cruce RENIEC
    ├── models/          ◄── [COMPAÑERO DE ML] Scripts de XGBoost (KYC Shield) y Prophet
    └── routers/         ◄── [AMBOS] API FastAPI (endpoints de consulta kyc-verify)
```

---

## 🛠️ Guía para el Compañero de ETL (Data Pipeline)

Tu objetivo es cruzar los datos de identidad ciudadana de la **RENIEC** con los registros de compras e ingresos de la PYME en la base de datos de PostgreSQL.

### 1. Definición de la Base de Datos (`backend/db/`)
*   **Capa Silver:** Revisa y amplía [schema_silver.sql](file:///c:/Users/use/Desktop/Mesa-Virtual/G9---INTELGENCIA-DE-NEGOCIOS/nexum-asesores/backend/db/schema_silver.sql). 
    *   La tabla `silver.stg_reniec_padron` ya está declarada (DNI, nombres, estado_vida, ubigeo). Debes poblarla usando archivos de extracción del padrón.
    *   La tabla `silver.stg_facturas` tiene campos KYC (`identidad_verificada` y `contraparte_fallecida`) que debes marcar realizando un JOIN en tu pipeline de transformación.
*   **Capa Gold:** Revisa [schema_gold.sql](file:///c:/Users/use/Desktop/Mesa-Virtual/G9---INTELGENCIA-DE-NEGOCIOS/nexum-asesores/backend/db/schema_gold.sql).
    *   La tabla `gold.fact_score_riesgo` contiene campos para almacenar el agregado de fraudes (`n_dni_sospechosos`, `alertas_kyc_activas`).

### 2. Tareas de Limpieza y Cruce (`backend/etl/`)
*   Desarrolla tus scripts para automatizar el cruce de facturas con el padrón:
    ```sql
    -- Ejemplo de lógica para marcar facturas de proveedores fallecidos
    UPDATE silver.stg_facturas f
    SET contraparte_fallecida = TRUE
    FROM silver.stg_reniec_padron p
    WHERE f.proveedor_cliente = p.dni AND p.estado_vida = 'fallecido';
    ```

---

## 🤖 Guía para el Compañero de Modelos Predictivos (ML)

Tu objetivo es entrenar el clasificador XGBoost utilizando tanto factores financieros como indicadores de identidad de la RENIEC para estimar el score de riesgo general.

### 1. Características del Modelo XGBoost (`backend/models/risk_model.py`)
*   Abre el archivo [risk_model.py](file:///c:/Users/use/Desktop/Mesa-Virtual/G9---INTELGENCIA-DE-NEGOCIOS/nexum-asesores/backend/models/risk_model.py).
*   Las variables (`FEATURES`) del modelo predictivo han sido actualizadas a:
    1.  `dias_promedio_atraso` (atrasos en declaraciones)
    2.  `pct_declaraciones_tarde` (cumplimiento de plazos)
    3.  `ratio_iva_irpf` (consistencia tributaria)
    4.  `sector_riesgo_score` (riesgo por industria)
    5.  `tiene_sanciones` (historial negativo)
    6.  `pct_contrapartes_fallecidas` ◄── **[RENIEC]** Inconsistencias de facturas emitidas por personas registradas como fallecidas.
    7.  `pct_identidades_invalidas` ◄── **[RENIEC]** Invoices emitidos por DNIs que no figuran en el padrón nacional.
    8.  `desviacion_ubigeo_fiscal` ◄── **[RENIEC]** Discrepancia entre la dirección física de la compra y la dirección oficial RENIEC.
    9.  `n_dni_sospechosos` ◄── **[RENIEC]** Nro de proveedores en listas de suplantación de identidad.
    10. `representante_suplantado_risk` ◄── **[RENIEC]** Falla de correspondencia biométrica en firmas digitales de socios.

### 2. Script de Entrenamiento y Drift Check
*   Optimiza la función `train` con tu dataset de entrenamiento que combine estas métricas financieras y demográficas.
*   El script `check_drift` comparará el F1-score del modelo resultante contra la línea base para alertar en caso de que cambien los patrones de fraude del mercado.

---

## 🚀 Pruebas del Stack de Integración

Podéis levantar el entorno de desarrollo que incluye la base de datos Postgres con los esquemas creados, el padrón y la API FastAPI de la siguiente forma:

```bash
cd nexum-asesores/backend
docker compose up -d
```

Para probar manualmente el comportamiento del verificador de identidad (KYC), consultad el endpoint de la API:
`GET http://localhost:8000/riesgo/{cliente_id}/kyc-verify/{dni}`

Pruebas en Swagger Docs en `http://localhost:8000/docs`.
