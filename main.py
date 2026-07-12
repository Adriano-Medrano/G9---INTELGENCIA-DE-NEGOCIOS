"""
API RESTful - Proyecto RENIEC (Grupo 9)
=========================================
Expone endpoints simulados (Mock Data) para:
- Health Check
- Modelo Económico (Axl)
- Modelo Predictivo (Axel)

Sirve como conducto principal para que el equipo de Dashboard (Yuzo)
pueda comenzar la integración sin bloqueos.
"""

from fastapi import FastAPI
from pydantic import BaseModel

app = FastAPI(
    title="API RENIEC - Grupo 9",
    description="API con datos simulados para los modelos Económico y Predictivo del proyecto.",
    version="1.0.0",
)


# ---------------------------------------------------------------------------
# Modelos de datos (Pydantic) para las respuestas
# ---------------------------------------------------------------------------

class ModeloEconomicoData(BaseModel):
    pbi_proyectado: float
    inflacion_estimada: float
    tendencia: str


class ModeloEconomicoResponse(BaseModel):
    status: str
    data: ModeloEconomicoData


class PrediccionResponse(BaseModel):
    status: str
    prediccion_ventas: float
    nivel_confianza: float


# ---------------------------------------------------------------------------
# 4.1. Endpoint de Verificación (Health Check)
# ---------------------------------------------------------------------------

@app.get("/")
def health_check():
    """Verifica que la API esté en funcionamiento."""
    return {"mensaje": "¡La API está funcionando!"}


# ---------------------------------------------------------------------------
# 4.2. Endpoint Modelo Económico (Axl)
# ---------------------------------------------------------------------------

@app.get("/api/modelo-economico", response_model=ModeloEconomicoResponse)
def obtener_modelo_economico():
    """Devuelve los indicadores simulados del Modelo Económico."""
    return {
        "status": "success",
        "data": {
            "pbi_proyectado": 3.5,
            "inflacion_estimada": 2.1,
            "tendencia": "positiva",
        },
    }


# ---------------------------------------------------------------------------
# 4.3. Endpoint Modelo Predictivo (Axel)
# ---------------------------------------------------------------------------

@app.post("/api/prediccion", response_model=PrediccionResponse)
def obtener_prediccion():
    """Devuelve una predicción de ventas simulada."""
    return {
        "status": "success",
        "prediccion_ventas": 15420.50,
        "nivel_confianza": 0.95,
    }


if __name__ == "__main__":
    import uvicorn

    uvicorn.run("main:app", host="0.0.0.0", port=8000, reload=True)
