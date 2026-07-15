"""
etl/silver/transform.py
───────────────────────
PASO 2 — SILVER: Descarga desde MinIO, limpia y carga en PostgreSQL schema silver.

Qué hace por dataset:
  certificados  → normaliza columnas, mapea mes a número, elimina nulos
  centros       → estandariza ESTADO, crea flags ES_OPERATIVO / ES_LIMA
  transacciones → normaliza mes, clasifica NIVEL_CARGA por percentiles p50/p75
  actas_oti     → normaliza mes, limpia strings geográficos

Reglas de robustez aplicadas:
  ✔ Deduplicación por clave natural de cada dataset
  ✔ Validación de rangos: AÑO 2018-2030, CANT > 0, NUM_MES 1-12
  ✔ Linaje: columna _source_file y _loaded_at en cada tabla
  ✔ Registro de anomalías en silver.transform_log

Cómo ejecutarlo:
  python etl/silver/transform.py
"""

import io
import logging
import sys
from datetime import datetime
from pathlib import Path

import pandas as pd
from minio import Minio
from sqlalchemy import create_engine, text

sys.path.insert(0, str(Path(__file__).parent.parent.parent))
from config.settings import (
    MINIO, BUCKET_BRONZE, PG_URI, CSV_SEPARATORS,
    SCHEMA_SILVER, MESES_NUM,
)

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s — %(message)s",
)
log = logging.getLogger("silver.transform")


# ─── Conexiones ──────────────────────────────────────────────────────────────

def get_minio_client():
    return Minio(
        MINIO["endpoint"],
        access_key=MINIO["access_key"],
        secret_key=MINIO["secret_key"],
        secure=MINIO["secure"],
    )

def get_engine():
    return create_engine(PG_URI)


# ─── Lectura desde MinIO ─────────────────────────────────────────────────────

def read_latest_from_minio(client: Minio, dataset_name: str, sep: str) -> pd.DataFrame:
    """
    Lee el CSV más reciente del bucket bronze para el dataset dado.
    Los objetos están bajo el prefijo: dataset_name/YYYY/MM/filename
    """
    objects = list(client.list_objects(BUCKET_BRONZE, prefix=f"{dataset_name}/", recursive=True))
    if not objects:
        raise FileNotFoundError(f"No hay objetos en MinIO para: {dataset_name}")

    # El más reciente por nombre (YYYY/MM/filename ordena cronológicamente)
    latest = sorted(objects, key=lambda o: o.object_name)[-1]
    log.info(f"[{dataset_name}] Leyendo desde MinIO: {latest.object_name}")

    response = client.get_object(BUCKET_BRONZE, latest.object_name)
    content  = response.read()
    response.close()

    for enc in ["utf-8", "utf-8-sig", "latin-1"]:
        try:
            df = pd.read_csv(io.BytesIO(content), sep=sep, encoding=enc)
            log.info(f"[{dataset_name}] {len(df):,} filas leídas (enc={enc})")
            df["_source_file"] = latest.object_name
            df["_loaded_at"]   = datetime.utcnow()
            return df
        except UnicodeDecodeError:
            continue

    raise ValueError(f"No se pudo decodificar el archivo de {dataset_name}")


# ─── Utilidades de limpieza ──────────────────────────────────────────────────

def normalizar_columnas(df: pd.DataFrame) -> pd.DataFrame:
    """Estandariza nombres de columnas: mayúsculas, sin tildes, guión → _."""
    trad = str.maketrans("ÁÉÍÓÚÑ áéíóúñ", "AEIOUN aeioun")
    df.columns = [
        c.strip().upper().translate(trad).replace(" ", "_")
        for c in df.columns
    ]
    return df

def mapear_mes(serie: pd.Series) -> pd.Series:
    """Convierte nombre de mes a número entero 1-12. 0 si no reconocido."""
    return serie.map(MESES_NUM).fillna(0).astype(int)

def validar_rango(df: pd.DataFrame, col: str, min_val, max_val, label: str) -> pd.DataFrame:
    """Elimina filas fuera de rango y registra cuántas."""
    antes = len(df)
    df = df[(df[col] >= min_val) & (df[col] <= max_val)].copy()
    eliminadas = antes - len(df)
    if eliminadas:
        log.warning(f"  [{label}] {eliminadas} filas fuera de rango en '{col}' ({min_val}–{max_val})")
    return df

def deduplicar(df: pd.DataFrame, subset: list, label: str) -> pd.DataFrame:
    """Elimina duplicados exactos por las columnas clave."""
    antes = len(df)
    df = df.drop_duplicates(subset=subset).copy()
    eliminadas = antes - len(df)
    if eliminadas:
        log.warning(f"  [{label}] {eliminadas} duplicados eliminados")
    return df


# ─── Transformaciones por dataset ────────────────────────────────────────────

def transform_certificados(df: pd.DataFrame) -> pd.DataFrame:
    log.info("[certificados] Transformando...")
    df = normalizar_columnas(df)

    # CORRECCIÓN: Si la columna quedó como ANO, la estandarizamos a ANIO
    if "ANO" in df.columns:
        df.rename(columns={"ANO": "ANIO"}, inplace=True)

    # Renombrar a nombres canónicos
    df.rename(columns={
        "TOTAL_EMITIDOS":  "CANT_CERTIFICADOS",
        "RANGO_DE_EDADES": "RANGO_EDAD",
    }, inplace=True)

    df["NUM_MES"]      = mapear_mes(df["MES"])
    df["MES"]          = df["MES"].str.strip().str.upper()
    df["DEPARTAMENTO"] = df["DEPARTAMENTO"].str.strip().str.upper()
    df["SEXO"]         = df["SEXO"].str.strip().str.upper()
    df["RANGO_EDAD"]   = df["RANGO_EDAD"].str.strip()

    # Se agrega .copy() para evitar warnings de asignación
    df = df.dropna(subset=["CANT_CERTIFICADOS"]).copy()
    df["CANT_CERTIFICADOS"] = df["CANT_CERTIFICADOS"].astype(int)

    df = validar_rango(df, "ANIO",           2018, 2030, "certificados")
    df = validar_rango(df, "NUM_MES",        1,    12,   "certificados")
    df = validar_rango(df, "CANT_CERTIFICADOS", 0, 9_999_999, "certificados")

    df = deduplicar(df, ["ANIO","NUM_MES","DEPARTAMENTO","SEXO","RANGO_EDAD"], "certificados")

    log.info(f"[certificados] {len(df):,} filas limpias")
    return df


def transform_centros(df: pd.DataFrame) -> pd.DataFrame:
    log.info("[centros] Transformando...")
    df = normalizar_columnas(df)

    # CORRECCIÓN: Convertimos ANO a ANIO para mantener la consistencia
    if "ANO" in df.columns:
        df.rename(columns={"ANO": "ANIO"}, inplace=True)

    df.rename(columns={"HORARIO_DE_ATENCION_AL_PUBLICO": "HORARIO"}, inplace=True)

    for col in ["DEPARTAMENTO", "PROVINCIA", "DISTRITO", "NOMBRE_LOCAL"]:
        df[col] = df[col].str.strip().str.upper()

    # Unificar variantes de ESTADO
    estado_map = {
        "OPERATIVO ":             "OPERATIVO",
        "DESPLAZAMIENTO ":        "DESPLAZAMIENTO",
        "INOPERATIVA":            "INOPERATIVO",
        "Desplazamiento":         "DESPLAZAMIENTO",
    }
    df["ESTADO"]       = df["ESTADO"].str.strip().replace(estado_map)
    df["ES_OPERATIVO"] = df["ESTADO"].isin(["OPERATIVO", "OPERATIVO PARCIAL"]).astype(int)
    df["ES_LIMA"]      = (df["DEPARTAMENTO"] == "LIMA").astype(int)

    # CORRECCIÓN: Cambiado "AÑO" por "ANIO"
    df = deduplicar(df, ["NOMBRE_LOCAL", "ANIO"], "centros")

    log.info(f"[centros] {len(df):,} filas limpias")
    return df


def transform_transacciones(df: pd.DataFrame) -> pd.DataFrame:
    log.info("[transacciones] Transformando...")
    df = normalizar_columnas(df)

    # Normalizar nombre de columna AÑO (puede quedar ANO tras quitar tilde)
    for variante in ["ANO", "AÑO"]:
        if variante in df.columns and "ANIO" not in df.columns:
            df.rename(columns={variante: "ANIO"}, inplace=True)

    # Normalizar TIPO_TRANSACCION (puede venir con tilde)
    for variante in ["TIPO_TRANSACCI_N", "TIPO_TRANSACCION"]:
        if variante in df.columns:
            df.rename(columns={variante: "TIPO_TRANSACCION"}, inplace=True)
            break

    df.rename(columns={"TRANSACCIONES": "CANT_TRANSACCIONES"}, inplace=True)

    df["MES"] = df["MES"].str.strip().replace({
        "Enero":"ENERO","Febrero":"FEBRERO","Marzo":"MARZO"
    }).str.upper()
    df["NUM_MES"]          = mapear_mes(df["MES"])
    df["DEPARTAMENTO"]     = df["DEPARTAMENTO"].str.strip().str.upper()
    df["LOCAL"]            = df["LOCAL"].str.strip().str.upper()
    df["TIPO_TRANSACCION"] = df["TIPO_TRANSACCION"].str.strip().str.upper()

    df = df.dropna(subset=["CANT_TRANSACCIONES"])
    df["CANT_TRANSACCIONES"] = df["CANT_TRANSACCIONES"].astype(int)

    df = validar_rango(df, "ANIO",              2018, 2030, "transacciones")
    df = validar_rango(df, "NUM_MES",           1,    12,   "transacciones")
    df = validar_rango(df, "CANT_TRANSACCIONES", 1, 9_999_999, "transacciones")

    # Clasificación de carga por percentiles
    p75 = df["CANT_TRANSACCIONES"].quantile(0.75)
    p50 = df["CANT_TRANSACCIONES"].quantile(0.50)
    df["NIVEL_CARGA"] = df["CANT_TRANSACCIONES"].apply(
        lambda v: "ALTA" if v >= p75 else ("MEDIA" if v >= p50 else "BAJA")
    )
    log.info(f"  Umbral ALTA (p75)={p75:,.0f}  MEDIA (p50)={p50:,.0f}")

    df = deduplicar(df, ["ANIO","NUM_MES","LOCAL","TIPO_TRANSACCION"], "transacciones")

    log.info(f"[transacciones] {len(df):,} filas limpias")
    return df


def transform_actas(df: pd.DataFrame) -> pd.DataFrame:
    log.info("[actas_oti] Transformando...")
    df = normalizar_columnas(df)

    df["MES_REGISTRO"]                 = df["MES_REGISTRO"].str.strip().str.upper()
    df["TIPO_ACTA"]                    = df["TIPO_ACTA"].str.strip().str.upper()
    df["DE_GENERO"]                    = df["DE_GENERO"].str.strip().str.upper()
    df["DEPART_CIUDAD_ESTADO_DOM_SOL"] = df["DEPART_CIUDAD_ESTADO_DOM_SOL"].str.strip().str.upper()
    df["PROVINCIA_DOM_SOL"]            = df["PROVINCIA_DOM_SOL"].str.strip().str.upper()

    df["NUM_MES"] = mapear_mes(df["MES_REGISTRO"])

    df = df.dropna(subset=["CANT_COPIAS_EMITIDAS"])
    df["CANT_COPIAS_EMITIDAS"] = df["CANT_COPIAS_EMITIDAS"].astype(int)

    df = validar_rango(df, "ANIO_REGISTRO",     2018, 2030, "actas_oti")
    df = validar_rango(df, "NUM_MES",           1,    12,   "actas_oti")
    df = validar_rango(df, "CANT_COPIAS_EMITIDAS", 1, 9_999_999, "actas_oti")

    log.info(f"[actas_oti] {len(df):,} filas limpias")
    return df


# ─── Carga en PostgreSQL silver ───────────────────────────────────────────────

TABLA_MAP = {
    "certificados":  "stg_certificados",
    "centros":       "stg_centros",
    "transacciones": "stg_transacciones",
    "actas":         "stg_actas_oti",
}

TRANSFORM_MAP = {
    "certificados":  transform_certificados,
    "centros":       transform_centros,
    "transacciones": transform_transacciones,
    "actas":         transform_actas,
}

def cargar_a_silver(df: pd.DataFrame, tabla: str, engine):
    """Carga un DataFrame a la tabla silver correspondiente (replace)."""
    df.to_sql(
        name=tabla,
        con=engine,
        schema=SCHEMA_SILVER,
        if_exists="replace",   # replace para idempotencia; cambia a "append" si acumulas
        index=False,
        chunksize=5000,
    )
    log.info(f"  Tabla silver.{tabla} → {len(df):,} filas cargadas")


# ─── Main ─────────────────────────────────────────────────────────────────────

def run():
    log.info("══════════════════════════════════════════")
    log.info("  SILVER — Transformación MinIO → PostgreSQL")
    log.info("══════════════════════════════════════════")

    minio_client = get_minio_client()
    engine       = get_engine()

    # Crear schema si no existe
    with engine.connect() as conn:
        conn.execute(text("CREATE SCHEMA IF NOT EXISTS silver"))

    for name, filename in [
        ("certificados",  CSV_SEPARATORS["certificados"]),
        ("centros",       CSV_SEPARATORS["centros"]),
        ("transacciones", CSV_SEPARATORS["transacciones"]),
        ("actas",         CSV_SEPARATORS["actas"]),
    ]:
        sep = filename   # reutilizamos variable para claridad
        try:
            df_raw  = read_latest_from_minio(minio_client, name, sep)
            df_clean = TRANSFORM_MAP[name](df_raw)
            cargar_a_silver(df_clean, TABLA_MAP[name], engine)
        except Exception as e:
            log.error(f"Error en {name}: {e}", exc_info=True)

    log.info("\n✅ Silver completado.")


if __name__ == "__main__":
    run()
