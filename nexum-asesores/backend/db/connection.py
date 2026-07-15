# ============================================================
# db/connection.py — Pool de conexiones PostgreSQL
# Utiliza asyncpg para el backend FastAPI (async)
# y psycopg2 para los scripts ETL de Airflow (sync)
# ============================================================

import os
import asyncpg
import psycopg2
import psycopg2.pool
import logging

logger = logging.getLogger("nexum.db")

# ── Config ────────────────────────────────────────────────────
DB_URL_ASYNC = os.getenv(
    "NEXUM_DB_URL",
    "postgresql+asyncpg://nexum:nexum_secret@localhost:5432/nexum_db"
)
DB_URL_SYNC = os.getenv(
    "NEXUM_DB_SYNC_URL",
    "postgresql://nexum:nexum_secret@localhost:5432/nexum_db"
)

_pool: asyncpg.Pool | None = None


# ── Pool Async (FastAPI) ──────────────────────────────────────
async def init_pool():
    """Inicializa el pool de conexiones async al arrancar la app."""
    global _pool
    _pool = await asyncpg.create_pool(
        dsn=DB_URL_ASYNC.replace("postgresql+asyncpg://", "postgresql://"),
        min_size=2,
        max_size=10,
        command_timeout=30,
    )
    logger.info("Pool PostgreSQL (async) inicializado")


async def get_db_connection() -> asyncpg.Connection:
    """
    Dependency de FastAPI para obtener una conexión del pool.

    Uso:
        @router.get("/{cliente_id}")
        async def endpoint(conn=Depends(get_db_connection)):
            row = await conn.fetchrow("SELECT ...")
    """
    if _pool is None:
        raise RuntimeError("Pool no inicializado. Llama a init_pool() al arrancar la app.")
    async with _pool.acquire() as conn:
        yield conn


async def close_pool():
    """Cierra el pool al detener la app."""
    global _pool
    if _pool:
        await _pool.close()
        logger.info("Pool PostgreSQL cerrado")


# ── Sync (Airflow / scripts ETL) ─────────────────────────────
_sync_pool: psycopg2.pool.ThreadedConnectionPool | None = None


def get_sync_pool() -> psycopg2.pool.ThreadedConnectionPool:
    global _sync_pool
    if _sync_pool is None:
        _sync_pool = psycopg2.pool.ThreadedConnectionPool(
            minconn=1, maxconn=5, dsn=DB_URL_SYNC
        )
    return _sync_pool


def get_sync_connection():
    """Conexión sincrónica para scripts ETL (Airflow tasks)."""
    pool = get_sync_pool()
    conn = pool.getconn()
    try:
        yield conn
        conn.commit()
    except Exception:
        conn.rollback()
        raise
    finally:
        pool.putconn(conn)


# ── Helper: Row-Level Security ────────────────────────────────
async def set_rls_context(conn: asyncpg.Connection, cliente_id: str):
    """
    Establece el cliente_id en la sesión PostgreSQL para que
    las políticas RLS de la capa Gold funcionen correctamente.

    Llamar al inicio de cada query en endpoints de cliente.
    """
    await conn.execute(
        f"SET LOCAL app.client_id = '{cliente_id}'"
    )
