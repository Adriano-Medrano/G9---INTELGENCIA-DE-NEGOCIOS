"""
airflow/dags/dag_03_gold.py
─────────────────────────────
DAG 3 — Gold: Construye el esquema estrella en PostgreSQL.gold.

Activación: manual o automática (disparado por dag_02)
Al terminar: los datos están listos para ser consumidos por Power BI
"""

from datetime import datetime, timedelta
from airflow import DAG
from airflow.operators.python import PythonOperator

import sys
sys.path.insert(0, "/opt/airflow")

default_args = {
    "owner":            "reniec_data",
    "retries":          1,
    "retry_delay":      timedelta(minutes=10),
    "email_on_failure": False,
}

with DAG(
    dag_id="dag_03_gold_build",
    description="PostgreSQL silver → gold (esquema estrella para Power BI)",
    default_args=default_args,
    start_date=datetime(2024, 1, 1),
    schedule_interval=None,
    catchup=False,
    tags=["reniec", "gold", "dwh", "estrella"],
) as dag:

    def _run_gold(**context):
        from etl.gold.build_star_schema import run
        run()

    tarea_gold = PythonOperator(
        task_id="build_star_schema",
        python_callable=_run_gold,
        doc_md="""
        Lee silver.stg_*, construye las 5 dimensiones y las 4 tablas
        de hechos del esquema estrella, y las carga en gold.dim_*/fact_*.
        Al terminar, Power BI puede refrescar el dataset directamente.
        """,
    )

    tarea_gold
