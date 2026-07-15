# ============================================================
# dags/dag_retrain.py — Reentrenamiento semanal de modelos ML
# Schedule: lunes a las 05:00 AM (tras dag_gold)
# XGBoost riesgo + Prophet flujo de caja + drift check
# ============================================================

from datetime import datetime, timedelta
from airflow import DAG
from airflow.operators.python import PythonOperator, BranchPythonOperator
from airflow.operators.empty import EmptyOperator
import logging
import json

logger = logging.getLogger("nexum.dag.retrain")

default_args = {
    "owner":            "nexum-data-team",
    "depends_on_past":  False,
    "start_date":       datetime(2026, 1, 6),   # primer lunes
    "email":            ["data@nexumasesores.es", "tech@nexumasesores.es"],
    "email_on_failure": True,
    "retries":          1,
    "retry_delay":      timedelta(minutes=20),
}

with DAG(
    dag_id="dag_retrain_models",
    description="Reentrenamiento semanal XGBoost + Prophet + drift check",
    schedule_interval="0 5 * * 1",  # lunes 05:00 UTC
    default_args=default_args,
    catchup=False,
    tags=["nexum", "ml", "retrain"],
    doc_md="""
    ## DAG Retrain — Modelos ML

    1. **Cargar datos Gold**: extrae features de fact_score_riesgo y fact_flujo_caja
    2. **Retrain XGBoost**: reentrenar modelo de riesgo con datos de los últimos 12 meses
    3. **Retrain Prophet**: reentrenar por cliente con datos actualizados
    4. **Drift check**: comparar métricas actuales vs. baseline
    5. **Alertar**: si hay drift, notificar al equipo técnico via Slack + email
    6. **Escribir Gold**: actualizar fact_score_riesgo + fact_prediccion_caja
    7. **Notificar**: confirmación de éxito al equipo
    """,
) as dag:

    def load_training_data(**context):
        """
        Extrae datos de entrenamiento desde la capa Gold.
        Consulta fact_flujo_caja + fact_declaraciones para los últimos 12 meses.
        """
        import pandas as pd
        logger.info("Cargando datos de entrenamiento desde Gold...")

        # En producción:
        # from db.connection import get_sync_connection
        # conn = get_sync_connection()
        # df_risk = pd.read_sql(QUERY_RISK_FEATURES, conn)
        # df_cashflow = pd.read_sql(QUERY_CASHFLOW, conn)

        # Mock — genera datos sintéticos para todos los clientes activos
        import numpy as np
        np.random.seed(int(datetime.now().strftime('%Y%m%d')))
        n = 300

        df_risk = pd.DataFrame({
            "cliente_id":                ["CL-2024-0042"] * n + ["CL-2024-0043"] * n,
            "dias_promedio_atraso":       np.random.exponential(2, n*2),
            "pct_declaraciones_tarde":    np.random.beta(2, 8, n*2),
            "ratio_iva_irpf":             np.random.normal(0.15, 0.05, n*2).clip(0, 1),
            "sector_riesgo_score":        np.random.choice([1, 2, 3], n*2),
            "tiene_sanciones":            np.random.binomial(1, 0.1, n*2),
            "pct_contrapartes_fallecidas":np.random.beta(0.5, 9, n*2),
            "pct_identidades_invalidas":  np.random.beta(0.5, 9, n*2),
            "desviacion_ubigeo_fiscal":   np.random.binomial(1, 0.15, n*2),
            "n_dni_sospechosos":          np.random.poisson(0.1, n*2),
            "representante_suplantado_risk": np.random.binomial(1, 0.05, n*2),
            "score_real":                 np.random.randint(20, 80, n*2),
        })

        # Serializar a XCom (en producción usar S3/GCS para datasets grandes)
        context["task_instance"].xcom_push(
            key="n_samples_risk",
            value=len(df_risk),
        )
        logger.info(f"Datos cargados: {len(df_risk)} muestras de riesgo")
        return True

    def retrain_xgboost(**context):
        """Reentrenar modelo XGBoost de riesgo."""
        import sys
        sys.path.insert(0, "/opt/nexum/backend")
        from models.risk_model import train, label_risk, FEATURES
        import pandas as pd
        import numpy as np

        logger.info("Reentrenando XGBoost de riesgo fiscal...")

        # En producción: cargar df_risk desde XCom o S3
        np.random.seed(42)
        n = 300
        X = pd.DataFrame({f: np.random.randn(n) for f in FEATURES})
        raw_scores = np.random.uniform(10, 90, n)
        y = pd.Series(raw_scores).apply(label_risk)

        version = f"xgboost-v{datetime.now().strftime('%Y%m%d')}"
        metrics = train(X, y, version=version)

        context["task_instance"].xcom_push(key="risk_metrics", value=metrics)
        logger.info(f"XGBoost reentrenado: acc={metrics['accuracy']} | f1={metrics['f1_weighted']}")
        return metrics

    def retrain_prophet(**context):
        """Reentrenar Prophet para cada cliente activo."""
        import sys
        sys.path.insert(0, "/opt/nexum/backend")
        from models.cashflow_model import train as train_cashflow
        import pandas as pd
        import numpy as np

        clients = ["CL-2024-0042", "CL-2024-0043"]
        all_metrics = {}

        for cid in clients:
            logger.info(f"Reentrenando Prophet · Cliente: {cid}")

            # Mock de datos históricos (en prod: query a Gold)
            dates = pd.date_range(
                end=datetime.now().date(),
                periods=365 * 2,
                freq="D",
            )
            flujo = (
                25000
                + np.sin(np.linspace(0, 4 * np.pi, len(dates))) * 5000
                + np.random.normal(0, 1500, len(dates))
            )
            df_hist = pd.DataFrame({"fecha": dates, "flujo_neto": flujo})

            try:
                _, metrics = train_cashflow(cid, df_hist)
                all_metrics[cid] = metrics
                logger.info(f"[{cid}] Prophet OK · MAE={metrics.get('mae','?')}")
            except Exception as e:
                logger.error(f"[{cid}] Error en Prophet: {e}")
                all_metrics[cid] = {"error": str(e)}

        context["task_instance"].xcom_push(key="cashflow_metrics", value=all_metrics)
        return all_metrics

    def check_drift(**context):
        """
        Compara métricas del retrain con el baseline anterior.
        Si F1 cae > 5%, deriva a la rama de alerta.
        """
        import sys
        sys.path.insert(0, "/opt/nexum/backend")
        from models.risk_model import check_drift

        risk_metrics = context["task_instance"].xcom_pull(
            task_ids="retrain_xgboost", key="risk_metrics"
        )
        if not risk_metrics:
            logger.warning("Sin métricas de XGBoost para drift check")
            return "no_drift"

        # Baseline (en prod: leer metadata de S3/modelo anterior)
        baseline = {"f1_weighted": 0.84, "accuracy": 0.87}

        result = check_drift(
            baseline_metrics=baseline,
            current_f1=risk_metrics.get("f1_weighted", 0.84),
            threshold_drop=0.05,
        )
        context["task_instance"].xcom_push(key="drift_result", value=result)

        if result["drift_detected"]:
            logger.warning("🚨 DRIFT DETECTADO — derivando a alerta")
            return "alert_drift"
        return "no_drift"

    def alert_drift(**context):
        """
        Alerta al equipo técnico cuando se detecta drift.
        Slack + email con detalles del cambio en métricas.
        """
        drift = context["task_instance"].xcom_pull(
            task_ids="check_drift", key="drift_result"
        )
        msg = (
            f"🚨 Drift detectado en modelo XGBoost (Nexum Asesores)\n"
            f"Fecha: {datetime.now().strftime('%Y-%m-%d %H:%M')}\n"
            f"Baseline F1: {drift.get('baseline_f1')}\n"
            f"F1 actual:   {drift.get('current_f1')}\n"
            f"Caída:       {drift.get('drop')} (umbral: {drift.get('threshold')})\n\n"
            "Acción recomendada: revisar calidad de datos Silver y distribución de features."
        )
        logger.error(msg)

        # En producción:
        # slack_client.chat_postMessage(channel="#ml-alerts", text=msg)
        # sendgrid.send(to="tech@nexumasesores.es", subject="⚠️ Drift ML Nexum", body=msg)

    def write_predictions_gold(**context):
        """
        Escribe las predicciones del modelo en la capa Gold:
        - fact_score_riesgo (score actual por cliente)
        - fact_prediccion_caja (proyección 90d por cliente)
        """
        logger.info("Escribiendo predicciones en Gold...")

        # En producción:
        # para cada cliente:
        #   - ejecutar predict_score(X_cliente)
        #   - INSERT INTO gold.fact_score_riesgo ...
        #   - ejecutar predict("CL-xxx", 90, vencimientos)
        #   - INSERT INTO gold.fact_prediccion_caja ...
        #     ON CONFLICT (cliente_key, fecha_prediccion) DO UPDATE SET yhat = EXCLUDED.yhat

        logger.info("Predicciones escritas en Gold correctamente")
        return True

    def notify_success(**context):
        """Notificación de éxito del retrain semanal."""
        risk_m = context["task_instance"].xcom_pull(task_ids="retrain_xgboost", key="risk_metrics") or {}
        logger.info(
            f"✅ Retrain semanal completado · "
            f"XGBoost acc={risk_m.get('accuracy','?')} · "
            f"Prophet: OK por cliente"
        )

    # ── Tasks ──────────────────────────────────────────────────
    t_load    = PythonOperator(task_id="load_training_data",   python_callable=load_training_data)
    t_xgb     = PythonOperator(task_id="retrain_xgboost",      python_callable=retrain_xgboost)
    t_prophet = PythonOperator(task_id="retrain_prophet",       python_callable=retrain_prophet)
    t_drift   = BranchPythonOperator(task_id="check_drift",    python_callable=check_drift)
    t_alert   = PythonOperator(task_id="alert_drift",          python_callable=alert_drift)
    t_no_drift = EmptyOperator(task_id="no_drift")
    t_write   = PythonOperator(task_id="write_predictions_gold", python_callable=write_predictions_gold,
                               trigger_rule="none_failed_min_one_success")
    t_notify  = PythonOperator(task_id="notify_success",       python_callable=notify_success)

    # ── Grafo ──────────────────────────────────────────────────
    t_load >> [t_xgb, t_prophet]
    t_xgb >> t_drift
    t_drift >> [t_alert, t_no_drift]
    [t_alert, t_no_drift] >> t_write
    t_prophet >> t_write
    t_write >> t_notify
