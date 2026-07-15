"""
airflow/dags/dag_01_ingest.py
──────────────────────────────
DAG 1 — Bronze: Ingestión diaria de CSV locales a MinIO.

Programación: todos los días a las 06:00 (hora Lima, UTC-5 → 11:00 UTC)
Dependencia:  ninguna (es el primer DAG del pipeline)
Siguiente:    dag_02_silver se activa automáticamente al terminar este
"""

from datetime import datetime, timedelta
from airflow import DAG
from airflow.operators.python import PythonOperator
from airflow.operators.trigger_dagrun import TriggerDagRunOperator

import sys
sys.path.insert(0, "/opt/airflow")

default_args = {
    "owner":            "reniec_data",
    "retries":          2,
    "retry_delay":      timedelta(minutes=5),
    "email_on_failure": False,   # cambia a True y configura SMTP en Airflow
    "email":            ["tu_email@reniec.pe"],
}

with DAG(
    dag_id="dag_01_bronze_ingest",
    description="Ingesta CSV RENIEC → MinIO (Bronze layer)",
    default_args=default_args,
    start_date=datetime(2024, 1, 1),
    schedule_interval="0 11 * * *",     # 06:00 Lima = 11:00 UTC
    catchup=False,
    tags=["reniec", "bronze", "ingestión"],
) as dag:

    def _run_ingest(**context):
        from etl.bronze.ingest import run
        run()

    tarea_ingest = PythonOperator(
        task_id="ingest_csv_to_minio",
        python_callable=_run_ingest,
        doc_md="""
        Lee los 4 CSV desde la carpeta montada `/opt/airflow/data/raw/`,
        calcula MD5, y sube solo los archivos nuevos o modificados a MinIO.
        """,
    )

    disparar_silver = TriggerDagRunOperator(
        task_id="trigger_dag_silver",
        trigger_dag_id="dag_02_silver_transform",
        wait_for_completion=False,
        doc_md="Dispara automáticamente el DAG de Silver al terminar.",
    )

    tarea_ingest >> disparar_silver
