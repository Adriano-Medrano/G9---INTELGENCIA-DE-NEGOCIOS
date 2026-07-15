# ============================================================
# dags/dag_bronze.py — Ingesta Bronze
# Schedule: diario a las 02:00 AM
# Descarga facturas, declaraciones y pagos → MinIO (staging)
# ============================================================

from datetime import datetime, timedelta
from airflow import DAG
from airflow.operators.python import PythonOperator
from airflow.operators.email import EmailOperator
from airflow.models import Variable
import logging

logger = logging.getLogger("nexum.dag.bronze")

default_args = {
    "owner":            "nexum-data-team",
    "depends_on_past":  False,
    "start_date":       datetime(2026, 1, 1),
    "email":            ["data@nexumasesores.es"],
    "email_on_failure": True,
    "email_on_retry":   False,
    "retries":          2,
    "retry_delay":      timedelta(minutes=10),
}

with DAG(
    dag_id="dag_bronze_ingest",
    description="Ingesta diaria de fuentes externas → Bronze (MinIO)",
    schedule_interval="0 2 * * *",   # 02:00 UTC diario
    default_args=default_args,
    catchup=False,
    tags=["nexum", "bronze", "etl"],
    doc_md="""
    ## DAG Bronze — Ingesta de fuentes externas

    Descarga datos de cada cliente activo desde:
    - API contable (facturas electrónicas XML/JSON)
    - AEAT: consulta declaraciones históricas
    - Extracto bancario (CSV)

    Deposita los archivos **sin modificar** en MinIO:
    `nexum-bronze/{cliente_id}/{YYYY}/{MM}/{DD}/`

    En caso de error en un cliente, continúa con los demás (fail_fast=False).
    """,
) as dag:

    def get_active_clients(**context):
        """
        Obtiene lista de clientes activos desde PostgreSQL Silver.
        En producción: query a silver.stg_clientes WHERE activo = TRUE
        """
        # from db.connection import get_sync_connection
        # conn = get_sync_connection()
        # rows = conn.execute("SELECT cliente_id FROM silver.stg_clientes WHERE activo = TRUE")
        # clients = [r["cliente_id"] for r in rows]

        # Mock para desarrollo
        clients = ["CL-2024-0042", "CL-2024-0043", "CL-2024-0044"]
        context["task_instance"].xcom_push(key="active_clients", value=clients)
        logger.info(f"Clientes activos: {len(clients)}")
        return clients

    def ingest_facturas(cliente_id: str, **context):
        """
        Descarga facturas electrónicas de la API contable del cliente.
        En España: AEAT → Suministro Inmediato de Información (SII)
        """
        import requests
        import json
        import os

        api_url   = Variable.get(f"api_contable_{cliente_id}", default_var=None)
        api_token = Variable.get(f"api_token_{cliente_id}",    default_var=None)

        if not api_url:
            logger.warning(f"No hay API configurada para {cliente_id}, saltando facturas")
            return

        # En producción:
        # resp = requests.get(f"{api_url}/facturas", headers={"Authorization": f"Bearer {api_token}"}, timeout=30)
        # facturas = resp.json()

        # Mock: genera datos de ejemplo
        facturas = [
            {"factura_id": f"{cliente_id}-F001", "total": 3500.00, "fecha": "2026-07-14", "tipo": "ingreso"},
            {"factura_id": f"{cliente_id}-F002", "total": 890.00,  "fecha": "2026-07-13", "tipo": "gasto"},
        ]

        # Guardar en MinIO (Bronze)
        # minio_client.put_object(
        #     bucket_name="nexum-bronze",
        #     object_name=f"{cliente_id}/2026/07/14/facturas.json",
        #     data=json.dumps(facturas).encode(),
        #     length=len(json.dumps(facturas)),
        # )

        logger.info(f"[{cliente_id}] Facturas ingestadas: {len(facturas)}")
        return len(facturas)

    def ingest_declaraciones(cliente_id: str, **context):
        """
        Consulta el historial de declaraciones del cliente en AEAT.
        Usa el certificado digital del despacho (poder representación).
        """
        logger.info(f"[{cliente_id}] Ingestando declaraciones AEAT...")
        # TODO: integrar con API de AEAT usando certificado digital
        # Depositar CSV en nexum-bronze/{cliente_id}/YYYY/MM/DD/declaraciones.csv
        return True

    def ingest_pagos(cliente_id: str, **context):
        """
        Descarga extracto bancario del cliente.
        Fuente: API PSD2 del banco (consentimiento del cliente)
        """
        logger.info(f"[{cliente_id}] Ingestando extracto bancario...")
        # TODO: integrar con API PSD2 (BBVA, Santander, etc.)
        return True

    def validate_bronze(**context):
        """
        Validación mínima de la ingesta:
        - Archivos existentes en MinIO
        - Tamaño > 0
        - JSON/CSV parseables
        Marca el DAG como FAILED si alguna validación crítica falla.
        """
        logger.info("Validando integridad de archivos Bronze...")
        # TODO: iterar MinIO y verificar archivos del día
        return True

    # ── Tasks ──────────────────────────────────────────────────
    t_get_clients = PythonOperator(
        task_id="get_active_clients",
        python_callable=get_active_clients,
    )

    # Ingesta paralela por cliente (un grupo de tasks por cliente)
    # En Airflow 2.x con TaskGroup y DynamicTaskMapping
    from airflow.utils.task_group import TaskGroup

    clients_demo = ["CL-2024-0042", "CL-2024-0043"]

    for cid in clients_demo:
        with TaskGroup(group_id=f"ingest_{cid.replace('-','_')}") as client_group:
            t_facturas = PythonOperator(
                task_id="facturas",
                python_callable=ingest_facturas,
                op_kwargs={"cliente_id": cid},
            )
            t_declaraciones = PythonOperator(
                task_id="declaraciones",
                python_callable=ingest_declaraciones,
                op_kwargs={"cliente_id": cid},
            )
            t_pagos = PythonOperator(
                task_id="pagos",
                python_callable=ingest_pagos,
                op_kwargs={"cliente_id": cid},
            )
            [t_facturas, t_declaraciones, t_pagos]

        t_get_clients >> client_group

    t_validate = PythonOperator(
        task_id="validate_bronze",
        python_callable=validate_bronze,
        trigger_rule="all_done",  # ejecutar aunque algún cliente falle
    )

    for cid in clients_demo:
        dag.get_task(f"ingest_{cid.replace('-','_')}.pagos") >> t_validate
