"""
config/settings.py
──────────────────
Configuración centralizada del pipeline.
Lee variables desde .env (local) o desde el entorno del contenedor (Airflow/Docker).
Todos los módulos importan desde aquí — nunca hardcodees credenciales.
"""

import os
from pathlib import Path
from dotenv import load_dotenv

# Carga .env solo si existe (en local). En Docker las vars ya están en el entorno.
_env_path = Path(__file__).parent.parent / ".env"
if _env_path.exists():
    load_dotenv(_env_path)


# ─── PostgreSQL ───────────────────────────────────────────────────────────────
PG = {
    "host":     os.getenv("POSTGRES_HOST", "localhost"),
    "port":     int(os.getenv("POSTGRES_PORT", 5432)),
    "dbname":   os.getenv("POSTGRES_DB", "reniec_dwh"),
    "user":     os.getenv("POSTGRES_USER", "postgres"),
    "password": os.getenv("POSTGRES_PASSWORD", ""),
}

PG_URI = (
    f"postgresql+psycopg2://{PG['user']}:{PG['password']}"
    f"@{PG['host']}:{PG['port']}/{PG['dbname']}"
)


# ─── MinIO ────────────────────────────────────────────────────────────────────
MINIO = {
    "endpoint":   os.getenv("MINIO_ENDPOINT", "localhost:9000"),
    "access_key": os.getenv("MINIO_ACCESS_KEY", "minioadmin"),
    "secret_key": os.getenv("MINIO_SECRET_KEY", "minioadmin123"),
    "secure":     False,                          # True solo si usas HTTPS
}

BUCKET_BRONZE = os.getenv("MINIO_BUCKET_BRONZE", "reniec-bronze")


# ─── Rutas locales ────────────────────────────────────────────────────────────
DATA_RAW_PATH = Path(os.getenv("DATA_RAW_PATH", "data/raw"))

# Nombres exactos de los 4 archivos CSV fuente
CSV_FILES = {
    "certificados":  "Cantidad de Certificados de Inscripción.csv",
    "centros":       "Centros de atención del RENIEC a nivel nacional.csv",
    "transacciones": "Transacciones RENIEC.csv",
    "actas":         "OTI_CONSOLIDADO.csv",
}

# Separador de cada CSV (algunos usan coma, otros punto y coma)
CSV_SEPARATORS = {
    "certificados":  ",",
    "centros":       ",",
    "transacciones": ";",
    "actas":         ";",
}


# ─── Schemas PostgreSQL ───────────────────────────────────────────────────────
SCHEMA_SILVER = "silver"
SCHEMA_GOLD   = "gold"


# ─── Meses (normalización) ────────────────────────────────────────────────────
MESES_NUM = {
    "ENERO": 1,  "FEBRERO": 2,  "MARZO": 3,     "ABRIL": 4,
    "MAYO": 5,   "JUNIO": 6,    "JULIO": 7,      "AGOSTO": 8,
    "SEPTIEMBRE": 9, "OCTUBRE": 10, "NOVIEMBRE": 11, "DICIEMBRE": 12,
    "Enero": 1, "Febrero": 2, "Marzo": 3,
}
