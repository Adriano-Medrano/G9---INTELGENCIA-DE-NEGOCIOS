"""
etl/bronze/ingest.py
────────────────────
PASO 1 — BRONZE: Ingesta de CSV locales a MinIO.

Qué hace:
  1. Lee cada CSV desde DATA_RAW_PATH
  2. Calcula un hash MD5 para detectar si el archivo ya fue ingestado
  3. Si es nuevo o cambió → lo sube al bucket reniec-bronze/ en MinIO
  4. Registra la ingestión en la tabla bronze.ingestion_log de PostgreSQL

Cómo ejecutarlo:
  python etl/bronze/ingest.py

Desde Airflow:
  Lo invoca dag_01_ingest.py automáticamente.
"""

import hashlib
import logging
import sys
from datetime import datetime
from pathlib import Path

import pandas as pd
import psycopg2
from minio import Minio
from minio.error import S3Error

sys.path.insert(0, str(Path(__file__).parent.parent.parent))
from config.settings import DATA_RAW_PATH, CSV_FILES, MINIO, BUCKET_BRONZE, PG

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s — %(message)s",
)
log = logging.getLogger("bronze.ingest")


# ─── Conexiones ──────────────────────────────────────────────────────────────

def get_minio_client():
    return Minio(
        MINIO["endpoint"],
        access_key=MINIO["access_key"],
        secret_key=MINIO["secret_key"],
        secure=MINIO["secure"],
    )

def get_pg_conn():
    return psycopg2.connect(**PG)


# ─── Utilidades ──────────────────────────────────────────────────────────────

def md5_file(path: Path) -> str:
    """Calcula el hash MD5 del archivo para detectar cambios."""
    h = hashlib.md5()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(8192), b""):
            h.update(chunk)
    return h.hexdigest()


def ensure_bucket(client: Minio, bucket: str):
    """Crea el bucket en MinIO si no existe."""
    if not client.bucket_exists(bucket):
        client.make_bucket(bucket)
        log.info(f"Bucket creado: {bucket}")


def already_ingested(conn, filename: str, md5: str) -> bool:
    """Verifica si este archivo (con este hash) ya fue ingestado antes."""
    with conn.cursor() as cur:
        cur.execute(
            """
            SELECT 1 FROM bronze.ingestion_log
            WHERE filename = %s AND md5_hash = %s
            """,
            (filename, md5),
        )
        return cur.fetchone() is not None

def exists_in_minio(client: Minio, bucket: str, path: str) -> bool:
    try:
        client.stat_object(bucket, path)
        return True
    except S3Error as e:
        if e.code == "NoSuchKey":
            return False
        raise

def log_ingestion(conn, filename: str, md5: str, minio_path: str, rows: int):
    """Registra la ingestión exitosa en la tabla de log."""
    with conn.cursor() as cur:
        cur.execute(
            """
            INSERT INTO bronze.ingestion_log
                (filename, md5_hash, minio_path, rows_count, ingested_at)
            VALUES (%s, %s, %s, %s, %s)
            """,
            (filename, md5, minio_path, rows, datetime.utcnow()),
        )
    conn.commit()


def ensure_log_table(conn):
    """Crea el schema bronze y la tabla de log si no existen."""
    with conn.cursor() as cur:
        cur.execute("CREATE SCHEMA IF NOT EXISTS bronze;")
        cur.execute(
            """
            CREATE TABLE IF NOT EXISTS bronze.ingestion_log (
                id           SERIAL PRIMARY KEY,
                filename     TEXT NOT NULL,
                md5_hash     TEXT NOT NULL,
                minio_path   TEXT NOT NULL,
                rows_count   INTEGER,
                ingested_at  TIMESTAMP NOT NULL DEFAULT NOW()
            );
            """
        )
    conn.commit()
    log.info("Schema bronze y tabla ingestion_log verificados.")


# ─── Ingestión principal ─────────────────────────────────────────────────────

def ingest_file(dataset_name: str, filename: str, minio_client: Minio, pg_conn):
    """Sube un archivo CSV a MinIO si es nuevo o cambió."""
    local_path = DATA_RAW_PATH / filename

    if not local_path.exists():
        log.warning(f"Archivo no encontrado: {local_path} — saltando.")
        return False

    md5 = md5_file(local_path)
    log.info(f"[{dataset_name}] MD5: {md5[:8]}… | archivo: {filename}")

    now = datetime.utcnow()
    minio_path = f"{dataset_name}/{now.year}/{now.month:02d}/{filename}"
    
    en_db = already_ingested(pg_conn, filename, md5)
    en_minio = exists_in_minio(minio_client, BUCKET_BRONZE, minio_path)

    if en_db and en_minio:
        log.info(f"[{dataset_name}] Sin cambios desde la última ingestión — omitido.")
        return False
    elif en_db and not en_minio:
        log.warning(f"[{dataset_name}] El MD5 coincide pero no está en MinIO. Forzando subida...")

    # Contar filas del CSV para el log
    try:
        sep = ";" if dataset_name in ("transacciones", "actas") else ","
        df_sample = pd.read_csv(local_path, sep=sep, encoding="utf-8", nrows=0)
        # Contar sin cargar todo en memoria
        with open(local_path, encoding="utf-8", errors="replace") as f:
            rows = sum(1 for _ in f) - 1   # restar header
    except Exception:
        rows = -1

    try:
        minio_client.fput_object(
            bucket_name=BUCKET_BRONZE,
            object_name=minio_path,
            file_path=str(local_path),
            content_type="text/csv",
        )
        log.info(f"[{dataset_name}] Subido a MinIO → {BUCKET_BRONZE}/{minio_path}  ({rows:,} filas)")
    except S3Error as e:
        log.error(f"[{dataset_name}] Error al subir a MinIO: {e}")
        raise

    log_ingestion(pg_conn, filename, md5, minio_path, rows)
    return True


def run():
    log.info("══════════════════════════════════════════")
    log.info("  BRONZE — Ingestión CSV → MinIO")
    log.info("══════════════════════════════════════════")

    minio_client = get_minio_client()
    pg_conn      = get_pg_conn()

    ensure_bucket(minio_client, BUCKET_BRONZE)
    ensure_log_table(pg_conn)

    resultados = {}
    for name, filename in CSV_FILES.items():
        try:
            subido = ingest_file(name, filename, minio_client, pg_conn)
            resultados[name] = "subido" if subido else "sin_cambios"
        except Exception as e:
            log.error(f"Error en {name}: {e}")
            resultados[name] = f"error: {e}"

    pg_conn.close()

    log.info("\nResumen de ingestión:")
    for name, status in resultados.items():
        log.info(f"  {name:<20} → {status}")

    if any("error" in v for v in resultados.values()):
        sys.exit(1)

    log.info("\n✅ Bronze completado.")


if __name__ == "__main__":
    run()
