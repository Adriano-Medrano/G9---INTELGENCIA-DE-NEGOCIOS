"""
airflow/dags/dag_04_kyc.py
─────────────────────────────
DAG 4 — KYC: Cruce de facturación (Silver) con el padrón RENIEC (Silver).
Prepara los datos para el cálculo de riesgo (Modelos ML).

Activación: manual o automática
Al terminar: stg_facturas tiene contrapartes validadas.
"""

from datetime import datetime, timedelta
from airflow import DAG
from airflow.operators.python import PythonOperator

import sys
sys.path.insert(0, "/opt/airflow")

default_args = {
    "owner":            "kyc_data",
    "retries":          1,
    "retry_delay":      timedelta(minutes=10),
    "email_on_failure": False,
}

with DAG(
    dag_id="dag_04_kyc_transform",
    description="Transformación KYC cruzando Facturas con RENIEC",
    default_args=default_args,
    start_date=datetime(2024, 1, 1),
    schedule_interval=None,
    catchup=False,
    tags=["kyc", "silver", "reniec"],
) as dag:

    def _run_kyc(**context):
        import sys
        sys.path.insert(0, "/opt/airflow/backend")
        from etl.silver.kyc_etl import run_kyc_transform
        run_kyc_transform()

    tarea_kyc = PythonOperator(
        task_id="kyc_cross_verification",
        python_callable=_run_kyc,
        doc_md="""
        Actualiza `silver.stg_facturas` basándose en el padrón `silver.stg_reniec_padron`.
        Marca facturas de proveedores fallecidos o no encontrados.
        """,
    )

    tarea_kyc
