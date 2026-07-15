# ============================================================
# Nexum Asesores — Backend FastAPI
# Entry point: uvicorn main:app --reload
# ============================================================

import sys
import os
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from fastapi import FastAPI, Depends, HTTPException, status, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.middleware.trustedhost import TrustedHostMiddleware
from fastapi.responses import JSONResponse
import logging
import time

from routers import auth, riesgo, flujo_caja, vencimientos

# ── Logging ──────────────────────────────────────────────────
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s | %(levelname)s | %(name)s | %(message)s",
)
logger = logging.getLogger("nexum.api")

from contextlib import asynccontextmanager
from db.connection import init_pool, close_pool

# ── Lifespan ──────────────────────────────────────────────────
@asynccontextmanager
async def lifespan(app: FastAPI):
    await init_pool()
    yield
    await close_pool()

# ── App ───────────────────────────────────────────────────────
app = FastAPI(
    title="Nexum Asesores — API Fiscal",
    description=(
        "API interna para el portal de clientes de Nexum Asesores. "
        "Expone datos de la capa Gold (PostgreSQL) para el dashboard "
        "predictivo, el chatbot privado y Power BI Embedded."
    ),
    version="1.0.0",
    docs_url="/docs",
    redoc_url="/redoc",
    openapi_url="/openapi.json",
    lifespan=lifespan,
)

# ── CORS ──────────────────────────────────────────────────────
app.add_middleware(
    CORSMiddleware,
    allow_origins=[
        "https://www.nexumasesores.pe",
        "https://portal.nexumasesores.pe",
        "http://localhost:5500",   # desarrollo local
        "http://127.0.0.1:5500",
        "https://proyecto-in-g9.vercel.app", # Vercel production
    ],
    allow_credentials=True,
    allow_methods=["GET", "POST", "OPTIONS"],
    allow_headers=["Authorization", "Content-Type"],
)

# ── Middleware: Log de accesos con cliente_id ─────────────────
@app.middleware("http")
async def access_log_middleware(request: Request, call_next):
    start = time.perf_counter()
    response = await call_next(request)
    elapsed = round((time.perf_counter() - start) * 1000, 2)
    # El cliente_id se extrae del token JWT en los routers
    logger.info(
        f"{request.method} {request.url.path} "
        f"→ {response.status_code} ({elapsed}ms)"
    )
    return response

# ── Routers ───────────────────────────────────────────────────
app.include_router(auth.router,         prefix="/auth",         tags=["Auth"])
app.include_router(riesgo.router,       prefix="/riesgo",       tags=["Riesgo Fiscal"])
app.include_router(flujo_caja.router,   prefix="/flujo-caja",   tags=["Flujo de Caja"])
app.include_router(vencimientos.router, prefix="/vencimientos", tags=["Vencimientos"])

# ── Health check ──────────────────────────────────────────────
@app.get("/health", tags=["Sistema"])
async def health_check():
    """Endpoint para monitoreo y load balancer."""
    return {"status": "ok", "service": "nexum-api", "version": "1.0.0"}

# ── Error handlers ────────────────────────────────────────────
@app.exception_handler(HTTPException)
async def http_exception_handler(request: Request, exc: HTTPException):
    return JSONResponse(
        status_code=exc.status_code,
        content={
            "error": exc.detail,
            "status_code": exc.status_code,
            "path": str(request.url.path),
        },
    )

if __name__ == "__main__":
    import uvicorn
    uvicorn.run("main:app", host="127.0.0.1", port=8000, reload=True)
