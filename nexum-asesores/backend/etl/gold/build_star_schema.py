"""
etl/gold/build_star_schema.py
──────────────────────────────
PASO 3 — GOLD: Construye el esquema estrella en PostgreSQL schema gold.

Lee desde silver.stg_* y carga:
  DIMENSIONES   → dim_tiempo, dim_local, dim_geografia, dim_tipo_transaccion, dim_tipo_acta
  HECHOS        → fact_transacciones, fact_certificados, fact_actas_oti, fact_carga_operativa

Diseño:
  - Todas las tablas gold tienen clave surrogate (id SERIAL) + clave natural para JOIN
  - Las fact tables llevan FK a dimensiones (id_tiempo, id_local, etc.)
  - Idempotente: se puede correr varias veces sin duplicar datos (TRUNCATE + INSERT)

Cómo ejecutarlo:
  python etl/gold/build_star_schema.py
"""

import logging
import sys
from datetime import datetime
from pathlib import Path

import pandas as pd
from sqlalchemy import create_engine, text

sys.path.insert(0, str(Path(__file__).parent.parent.parent))
from config.settings import PG_URI, SCHEMA_SILVER, SCHEMA_GOLD

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s — %(message)s",
)
log = logging.getLogger("gold.build")

MESES_NOMBRE = {
    1:"ENERO", 2:"FEBRERO", 3:"MARZO", 4:"ABRIL",
    5:"MAYO",  6:"JUNIO",   7:"JULIO", 8:"AGOSTO",
    9:"SEPTIEMBRE", 10:"OCTUBRE", 11:"NOVIEMBRE", 12:"DICIEMBRE",
}


def get_engine():
    return create_engine(PG_URI)


def read_silver(engine, tabla: str) -> pd.DataFrame:
    df = pd.read_sql(f"SELECT * FROM {SCHEMA_SILVER}.{tabla}", engine)
    log.info(f"  Leído silver.{tabla}: {len(df):,} filas")
    return df


# ═══════════════════════════════════════════════════════════════
#  DIMENSIONES
# ═══════════════════════════════════════════════════════════════

def build_dim_tiempo(df_tx: pd.DataFrame, engine) -> pd.DataFrame:
    """Genera dim_tiempo a partir de los años presentes en transacciones."""
    anios = sorted(df_tx["anio"].dropna().unique().astype(int))
    rows = []
    for a in anios:
        for m in range(1, 13):
            rows.append({
                "id_tiempo":  int(f"{a}{m:02d}"),   # PK natural: YYYYMM
                "anio":       a,
                "num_mes":    m,
                "mes_nombre": MESES_NOMBRE[m],
                "trimestre":  (m - 1) // 3 + 1,
                "semestre":   1 if m <= 6 else 2,
            })
    dim = pd.DataFrame(rows).drop_duplicates("id_tiempo")
    _load_dim(dim, "dim_tiempo", engine)
    return dim


def build_dim_local(df_centros: pd.DataFrame, engine) -> pd.DataFrame:
    """Genera dim_local desde stg_centros."""
    df = df_centros.copy()
    if "anio" in df.columns:
        df.rename(columns={"anio": "anio_local"}, inplace=True)

    # Rellenar nulos en campos descriptivos de la dimensión local
    text_cols = ["nombre_local", "departamento", "provincia", "distrito", "estado", "horario", "direccion"]
    for col in text_cols:
        if col in df.columns:
            df[col] = df[col].fillna("DESCONOCIDO")

    keep = [c for c in ["nombre_local","departamento","provincia","distrito",
                         "estado","es_operativo","es_lima","horario","direccion","anio_local"]
            if c in df.columns]
    dim = df[keep].drop_duplicates(subset=["nombre_local","anio_local"]).reset_index(drop=True)
    dim.insert(0, "id_local", range(1, len(dim)+1))
    _load_dim(dim, "dim_local", engine)
    return dim


def build_dim_geografia(df_centros: pd.DataFrame, engine) -> pd.DataFrame:
    df = df_centros.copy()
    # Asegurar que no vayan nulos a las claves de geografía
    for col in ["departamento", "provincia", "distrito"]:
        df[col] = df[col].fillna("DESCONOCIDO")
    
    dim = (df_centros[["departamento","provincia","distrito"]]
           .drop_duplicates()
           .reset_index(drop=True))
    dim.insert(0, "id_geo", range(1, len(dim)+1))
    dim["es_lima"] = (dim["departamento"] == "LIMA").astype(int)
    _load_dim(dim, "dim_geografia", engine)
    return dim


def build_dim_tipo_transaccion(df_tx: pd.DataFrame, engine) -> pd.DataFrame:
    tipos = df_tx["tipo_transaccion"].dropna().unique()
    dim = pd.DataFrame({"id_tipo": range(1, len(tipos)+1), "tipo_transaccion": tipos})
    _load_dim(dim, "dim_tipo_transaccion", engine)
    return dim


def build_dim_tipo_acta(df_actas: pd.DataFrame, engine) -> pd.DataFrame:
    tipos = df_actas["tipo_acta"].dropna().unique()
    dim = pd.DataFrame({"id_acta": range(1, len(tipos)+1), "tipo_acta": tipos})
    _load_dim(dim, "dim_tipo_acta", engine)
    return dim


def _load_dim(df: pd.DataFrame, tabla: str, engine):
    """Carga dimensiones usando TRUNCATE para no romper las llaves foráneas."""
    with engine.begin() as conn:
        # 1. Limpiar los datos actuales sin borrar la estructura de la tabla
        # CASCADE asegura que si hubiera tablas dependientes, se manejen correctamente,
        # aunque en este caso solo estamos limpiando la dimensión.
        conn.execute(f"TRUNCATE TABLE gold.{tabla} CASCADE;")
        
        # 2. Insertar los nuevos datos
        df.to_sql(
            tabla, 
            con=conn, 
            schema="gold", 
            if_exists="append", # Cambiamos a 'append' porque ya limpiamos la tabla
            index=False
        )
    log.info(f"  gold.{tabla} → {len(df):,} filas insertadas")


# ═══════════════════════════════════════════════════════════════
#  HECHOS
# ═══════════════════════════════════════════════════════════════

def build_fact_transacciones(df_tx: pd.DataFrame, dim_tipo: pd.DataFrame, engine):
    df = df_tx.copy()
    
    # Tratamiento de Nulos Preventivo
    text_cols = ["mes", "departamento", "local", "tipo_transaccion", "nivel_carga"]
    for col in text_cols:
        if col in df.columns:
            df[col] = df[col].fillna("DESCONOCIDO")
    df["cant_transacciones"] = df["cant_transacciones"].fillna(0)

    tipo_map = dim_tipo.set_index("tipo_transaccion")["id_tipo"].to_dict()
    df["id_tipo"]   = df["tipo_transaccion"].map(tipo_map)
    df["id_tiempo"] = (df["anio"].astype(str) + df["num_mes"].apply(lambda x: f"{int(x):02d}")).astype(int)

    fact = df[["id_tiempo","id_tipo","anio","num_mes","mes","departamento",
               "local","tipo_transaccion","cant_transacciones","nivel_carga",
               "_source_file","_loaded_at"]].copy()
    _load_fact(fact, "fact_transacciones", engine)


def build_fact_certificados(df_cert: pd.DataFrame, engine):
    df = df_cert.copy()

    # Tratamiento de Nulos Preventivo
    text_cols = ["mes", "departamento", "sexo", "rango_edad"]
    for col in text_cols:
        if col in df.columns:
            df[col] = df[col].fillna("DESCONOCIDO")
    df["cant_certificados"] = df["cant_certificados"].fillna(0)

    df["id_tiempo"] = (df["anio"].astype(str) + df["num_mes"].apply(lambda x: f"{int(x):02d}")).astype(int)
    fact = df[["id_tiempo","anio","num_mes","mes","departamento",
               "sexo","rango_edad","cant_certificados",
               "_source_file","_loaded_at"]].copy()
    _load_fact(fact, "fact_certificados", engine)


def build_fact_actas_oti(df_actas: pd.DataFrame, dim_acta: pd.DataFrame, engine):
    df = df_actas.copy()

    # Tratamiento de Nulos Preventivo
    text_cols = ["mes_registro", "tipo_acta", "de_genero", "depart_ciudad_estado_dom_sol", "provincia_dom_sol"]
    for col in text_cols:
        if col in df.columns:
            df[col] = df[col].fillna("DESCONOCIDO")
    df["cant_copias_emitidas"] = df["cant_copias_emitidas"].fillna(0)

    acta_map = dim_acta.set_index("tipo_acta")["id_acta"].to_dict()
    df["id_acta"]   = df["tipo_acta"].map(acta_map)
    df["id_tiempo"] = (df["anio_registro"].astype(str) + df["num_mes"].apply(lambda x: f"{int(x):02d}")).astype(int)

    fact = df[["id_tiempo","id_acta","anio_registro","num_mes","mes_registro",
               "tipo_acta","de_genero","depart_ciudad_estado_dom_sol",
               "provincia_dom_sol","cant_copias_emitidas",
               "_source_file","_loaded_at"]].copy()
    _load_fact(fact, "fact_actas_oti", engine)


def build_fact_carga_operativa(df_tx: pd.DataFrame, engine):
    """Tabla analítica agregada por local/mes — optimizada para Power BI."""
    df = df_tx.copy()

    # Tratamiento de Nulos Preventivo antes del GroupBy
    text_cols = ["mes", "departamento", "local", "nivel_carga"]
    for col in text_cols:
        if col in df.columns:
            df[col] = df[col].fillna("DESCONOCIDO")
    df["cant_transacciones"] = df["cant_transacciones"].fillna(0)

    df["id_tiempo"] = (df["anio"].astype(str) + df["num_mes"].apply(lambda x: f"{int(x):02d}")).astype(int)

    carga = (df.groupby(
        ["id_tiempo","anio","num_mes","mes","departamento","local","nivel_carga"],
        dropna=False)
    .agg(
        total_transacciones=("cant_transacciones","sum"),
        tipos_servicio      =("cant_transacciones","count"),
        pico_mensual        =("cant_transacciones","max"),
        promedio_mensual    =("cant_transacciones","mean"),
    )
    .reset_index())
    carga["promedio_mensual"] = carga["promedio_mensual"].round(1)
    _load_fact(carga, "fact_carga_operativa", engine)


def _load_fact(df: pd.DataFrame, tabla: str, engine):
    """Carga una tabla de hechos a gold."""
    # Usamos 'begin()' para manejar la transacción automáticamente
    with engine.begin() as conn:
        df.to_sql(
            tabla, 
            con=conn, 
            schema="gold", 
            if_exists="append", # Los hechos generalmente se añaden
            index=False,
            chunksize=5000
        )
    # ¡IMPORTANTE! Hemos eliminado la línea conn.commit() de aquí
    log.info(f"  gold.{tabla} → {len(df):,} filas insertadas")


# ═══════════════════════════════════════════════════════════════
#  MAIN
# ═══════════════════════════════════════════════════════════════

def run():
    log.info("══════════════════════════════════════════")
    log.info("  GOLD — Esquema estrella en PostgreSQL")
    log.info("══════════════════════════════════════════")

    engine = get_engine()

    # Crear schema si no existe
    with engine.connect() as conn:
        conn.execute(text("CREATE SCHEMA IF NOT EXISTS gold"))

    # Leer Silver
    df_cert   = read_silver(engine, "stg_certificados")
    df_centros= read_silver(engine, "stg_centros")
    df_tx     = read_silver(engine, "stg_transacciones")
    df_actas  = read_silver(engine, "stg_actas_oti")

    for df in [df_cert, df_centros, df_tx, df_actas]:
        df.columns = [c.lower() for c in df.columns]
        for c in ["ano", "año"]:
            if c in df.columns:
                df.rename(columns={c: "anio"}, inplace=True)

    # Dimensiones
    log.info("Construyendo dimensiones...")
    build_dim_tiempo(df_tx, engine)
    build_dim_local(df_centros, engine)
    build_dim_geografia(df_centros, engine)
    dim_tipo = build_dim_tipo_transaccion(df_tx, engine)
    dim_acta = build_dim_tipo_acta(df_actas, engine)

    # Hechos
    log.info("Construyendo tablas de hechos...")
    build_fact_transacciones(df_tx, dim_tipo, engine)
    build_fact_certificados(df_cert, engine)
    build_fact_actas_oti(df_actas, dim_acta, engine)
    build_fact_carga_operativa(df_tx, engine)

    log.info("\n✅ Gold completado — listo para Power BI.")


if __name__ == "__main__":
    run()
