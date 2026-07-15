# ============================================================
# routers/riesgo.py — Score de riesgo fiscal (KYC & Tax Shield)
# GET /riesgo/{cliente_id}
# GET /riesgo/{cliente_id}/kyc-verify/{dni}
# ============================================================

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel
from typing import List, Optional
import logging

from routers.auth import get_current_user, TokenData

router = APIRouter()
logger = logging.getLogger("nexum.riesgo")


# ── Schemas de respuesta ──────────────────────────────────────
class FeatureImportance(BaseModel):
    nombre: str
    importancia_pct: float   # 0-100
    valor_actual: str
    estado: str              # "ok" | "warn" | "bad"


class ScoreRiesgoResponse(BaseModel):
    cliente_id: str
    score: int               # 0-100
    nivel: str               # "bajo" | "moderado" | "alto"
    variacion_vs_trimestre: int
    n_dni_sospechosos: int
    alertas_kyc_activas: int
    features: List[FeatureImportance]
    modelo_version: str
    ultimo_calculo: str      # ISO 8601


class HistoricoRiesgoResponse(BaseModel):
    cliente_id: str
    historico: List[dict]    # [{periodo, score}]


class KycVerificationResponse(BaseModel):
    dni: str
    nombres: str
    apellidos: str
    estado_vida: str         # "vivo" | "fallecido"
    coherencia_geografica: bool
    edad: int
    riesgo_suplantacion: str # "bajo" | "moderado" | "alto"
    status_kyc: str          # "aprobado" | "alerta_fallecido" | "no_encontrado" | "bajo_revision"
    score_riesgo_asociado: int


# ── Helper: aislamiento tenant ────────────────────────────────
def _verificar_acceso(cliente_id: str, user: TokenData):
    if user.cliente_id != cliente_id:
        logger.warning(
            f"Intento de acceso no autorizado: "
            f"token={user.cliente_id} solicitó cliente={cliente_id}"
        )
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="No tienes permiso para acceder a estos datos.",
        )


# ── Endpoints ─────────────────────────────────────────────────
@router.get("/{cliente_id}", response_model=ScoreRiesgoResponse)
async def get_score_riesgo(
    cliente_id: str,
    user: TokenData = Depends(get_current_user),
):
    """
    Devuelve el score de riesgo fiscal actual para el cliente,
    cruzado con métricas del padrón RENIEC de sus proveedores y socios.
    """
    _verificar_acceso(cliente_id, user)
    logger.info(f"Score riesgo solicitado (KYC Shield): {cliente_id}")

    # Mock: datos de la capa Gold enriquecidos con RENIEC
    return ScoreRiesgoResponse(
        cliente_id=cliente_id,
        score=42,
        nivel="moderado",
        variacion_vs_trimestre=-8,
        n_dni_sospechosos=1,
        alertas_kyc_activas=2,
        features=[
            FeatureImportance(nombre="Días promedio atraso",         importancia_pct=38, valor_actual="2.3 días",         estado="ok"),
            FeatureImportance(nombre="Inconsistencias IVA/IRPF",     importancia_pct=25, valor_actual="0.04 ratio",        estado="ok"),
            FeatureImportance(nombre="Facturas contraparte fallecida", importancia_pct=72, valor_actual="1 (detectada)",   estado="bad"),
            FeatureImportance(nombre="Identidades inválidas en padrón",importancia_pct=65, valor_actual="0.0% de facturas", estado="ok"),
            FeatureImportance(nombre="Desviación de ubigeo fiscal",   importancia_pct=30, valor_actual="15% de compras",   estado="warn"),
            FeatureImportance(nombre="Suplantación de representante",  importancia_pct=15, valor_actual="No detectado",     estado="ok"),
        ],
        modelo_version="xgboost-v2.5.0-kyc-shield",
        ultimo_calculo="2026-07-14T05:12:00Z",
    )


@router.get("/{cliente_id}/kyc-verify/{dni}", response_model=KycVerificationResponse)
async def verify_dni_reniec(
    cliente_id: str,
    dni: str,
    user: TokenData = Depends(get_current_user),
):
    """
    Verifica un DNI/NIF de un proveedor o socio contra el padrón de la RENIEC,
    calculando la probabilidad de suplantación mediante el modelo predictivo.
    """
    _verificar_acceso(cliente_id, user)
    logger.info(f"Verificación KYC en RENIEC: cliente={cliente_id} | DNI={dni}")

    # Padrón de ciudadanos de prueba (mock)
    PADRON_MOCK = {
        "12345678": {
            "nombres": "JUAN CARLOS", "apellidos": "PEREZ RAMIREZ",
            "estado_vida": "vivo", "coherencia_geografica": True, "edad": 42,
            "riesgo_suplantacion": "bajo", "status_kyc": "aprobado", "score_riesgo_asociado": 12
        },
        "87654321": {
            "nombres": "MARIA ELENA", "apellidos": "GONZALES CASTRO",
            "estado_vida": "fallecido", "coherencia_geografica": False, "edad": 84,
            "riesgo_suplantacion": "alto", "status_kyc": "alerta_fallecido", "score_riesgo_asociado": 95
        },
        "11112222": {
            "nombres": "ANDRES AVELINO", "apellidos": "RODRIGUEZ CACERES",
            "estado_vida": "vivo", "coherencia_geografica": False, "edad": 21,
            "riesgo_suplantacion": "moderado", "status_kyc": "bajo_revision", "score_riesgo_asociado": 58
        }
    }

    if dni not in PADRON_MOCK:
        # DNI no registrado en el padrón electoral de RENIEC → Alto riesgo
        return KycVerificationResponse(
            dni=dni, nombres="No registrado", apellidos="En el padrón",
            estado_vida="desconocido", coherencia_geografica=False, edad=0,
            riesgo_suplantacion="alto", status_kyc="no_encontrado", score_riesgo_asociado=85
        )

    res = PADRON_MOCK[dni]
    return KycVerificationResponse(
        dni=dni, nombres=res["nombres"], apellidos=res["apellidos"],
        estado_vida=res["estado_vida"], coherencia_geografica=res["coherencia_geografica"],
        edad=res["edad"], riesgo_suplantacion=res["riesgo_suplantacion"],
        status_kyc=res["status_kyc"], score_riesgo_asociado=res["score_riesgo_asociado"]
    )


@router.get("/{cliente_id}/historico", response_model=HistoricoRiesgoResponse)
async def get_historico_riesgo(
    cliente_id: str,
    meses: int = 12,
    user: TokenData = Depends(get_current_user),
):
    """Devuelve el histórico del score de riesgo general."""
    _verificar_acceso(cliente_id, user)

    historico = [
        {"periodo": "Ago 25", "score": 68}, {"periodo": "Sep 25", "score": 72},
        {"periodo": "Oct 25", "score": 65}, {"periodo": "Nov 25", "score": 58},
        {"periodo": "Dic 25", "score": 61}, {"periodo": "Ene 26", "score": 55},
        {"periodo": "Feb 26", "score": 51}, {"periodo": "Mar 26", "score": 48},
        {"periodo": "Abr 26", "score": 46}, {"periodo": "May 26", "score": 44},
        {"periodo": "Jun 26", "score": 50}, {"periodo": "Jul 26", "score": 42},
    ]

    return HistoricoRiesgoResponse(
        cliente_id=cliente_id,
        historico=historico[-meses:],
    )
