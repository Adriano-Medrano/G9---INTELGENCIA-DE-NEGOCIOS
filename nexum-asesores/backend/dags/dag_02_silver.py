"""
airflow/dags/dag_02_silver.py
──────────────────────────────
DAG 2 — Silver: Transforma los CSV de MinIO y carga en PostgreSQL.silver.

Activación: manual o automática (disparado por dag_01)
Siguiente:  dag_03_gold se activa al terminar este
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
    "email_on_failure": False,
}

with DAG(
    dag_id="dag_02_silver_transform",
    description="MinIO CSV → PostgreSQL silver (limpieza y validación)",
    default_args=default_args,
    start_date=datetime(2024, 1, 1),
    schedule_interval=None,     # solo se activa por trigger desde dag_01
    catchup=False,
    tags=["reniec", "silver", "transformación"],
) as dag:

    def _run_transform(**context):
        from etl.silver.transform import run
        run()

    tarea_transform = PythonOperator(
        task_id="transform_silver",
        python_callable=_run_transform,
        doc_md="""
        Lee el CSV más reciente de cada dataset desde MinIO,
        aplica limpieza, deduplicación, validación de rangos y
        carga en las tablas stg_* del schema silver de PostgreSQL.
        """,
    )

    disparar_gold = TriggerDagRunOperator(
        task_id="trigger_dag_gold",
        trigger_dag_id="dag_03_gold_build",
        wait_for_completion=False,
    )

    tarea_transform >> disparar_gold
