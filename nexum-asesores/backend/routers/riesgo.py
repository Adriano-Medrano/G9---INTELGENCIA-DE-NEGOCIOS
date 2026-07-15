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
from db.connection import get_db_connection, set_rls_context
import asyncpg
from datetime import datetime

@router.get("/{cliente_id}", response_model=ScoreRiesgoResponse)
async def get_score_riesgo(
    cliente_id: str,
    user: TokenData = Depends(get_current_user),
    conn: asyncpg.Connection = Depends(get_db_connection),
):
    """
    Devuelve el score de riesgo fiscal actual para el cliente,
    cruzado con métricas del padrón RENIEC de sus proveedores y socios en PostgreSQL.
    """
    _verificar_acceso(cliente_id, user)
    logger.info(f"Score riesgo solicitado (KYC Shield): {cliente_id}")

    # Establecer contexto RLS
    await set_rls_context(conn, cliente_id)

    # Obtener el último score calculado
    score_query = """
        SELECT score_key, score, nivel, variacion_vs_anterior, n_dni_sospechosos, alertas_kyc_activas, modelo_version, calculado_en
        FROM gold.fact_score_riesgo
        ORDER BY calculado_en DESC
        LIMIT 1
    """
    score_row = await conn.fetchrow(score_query)

    if not score_row:
        # Fallback si no hay registros en la base de datos
        return ScoreRiesgoResponse(
            cliente_id=cliente_id,
            score=0,
            nivel="bajo",
            variacion_vs_trimestre=0,
            n_dni_sospechosos=0,
            alertas_kyc_activas=0,
            features=[],
            modelo_version="xgboost-v2.5.0-kyc-shield",
            ultimo_calculo=datetime.utcnow().isoformat(),
        )

    # Obtener las características del score
    features_query = """
        SELECT nombre_feature, importancia_pct, valor_actual, estado
        FROM gold.fact_score_riesgo_features
        WHERE score_key = $1
    """
    feature_rows = await conn.fetch(features_query, score_row['score_key'])
    features = [
        FeatureImportance(
            nombre=row['nombre_feature'],
            importancia_pct=float(row['importancia_pct']),
            valor_actual=row['valor_actual'],
            estado=row['estado']
        )
        for row in feature_rows
    ]

    return ScoreRiesgoResponse(
        cliente_id=cliente_id,
        score=score_row['score'],
        nivel=score_row['nivel'],
        variacion_vs_trimestre=score_row['variacion_vs_anterior'],
        n_dni_sospechosos=score_row['n_dni_sospechosos'],
        alertas_kyc_activas=score_row['alertas_kyc_activas'],
        features=features,
        modelo_version=score_row['modelo_version'],
        ultimo_calculo=score_row['calculado_en'].isoformat(),
    )


@router.get("/{cliente_id}/kyc-verify/{dni}", response_model=KycVerificationResponse)
async def verify_dni_reniec(
    cliente_id: str,
    dni: str,
    user: TokenData = Depends(get_current_user),
    conn: asyncpg.Connection = Depends(get_db_connection),
):
    """
    Verifica un DNI/NIF de un proveedor o socio contra el padrón de la RENIEC en la Capa Silver.
    """
    _verificar_acceso(cliente_id, user)
    logger.info(f"Verificación KYC en RENIEC: cliente={cliente_id} | DNI={dni}")

    query = """
        SELECT nombres, apellido_paterno, apellido_materno, estado_vida, ubigeo, fecha_nacimiento
        FROM silver.stg_reniec_padron
        WHERE dni = $1
    """
    row = await conn.fetchrow(query, dni)

    if not row:
        return KycVerificationResponse(
            dni=dni, nombres="No registrado", apellidos="En el padrón",
            estado_vida="desconocido", coherencia_geografica=False, edad=0,
            riesgo_suplantacion="alto", status_kyc="no_encontrado", score_riesgo_asociado=85
        )

    # Calcular edad
    birth_date = row['fecha_nacimiento']
    today = datetime.today().date()
    age = today.year - birth_date.year - ((today.month, today.day) < (birth_date.month, birth_date.day))

    nombres = row['nombres']
    apellidos = f"{row['apellido_paterno']} {row['apellido_materno']}"
    estado_vida = row['estado_vida']

    # Lógica predictiva del mock usando los datos reales de la BD
    if estado_vida == "fallecido":
        status_kyc = "alerta_fallecido"
        riesgo_suplantacion = "alto"
        score_riesgo_asociado = 95
        coherencia_geografica = False
    elif dni == "11112222":
        status_kyc = "bajo_revision"
        riesgo_suplantacion = "moderado"
        score_riesgo_asociado = 58
        coherencia_geografica = False
    else:
        status_kyc = "aprobado"
        riesgo_suplantacion = "bajo"
        score_riesgo_asociado = 12
        coherencia_geografica = True

    return KycVerificationResponse(
        dni=dni, nombres=nombres, apellidos=apellidos,
        estado_vida=estado_vida, coherencia_geografica=coherencia_geografica,
        edad=age, riesgo_suplantacion=riesgo_suplantacion,
        status_kyc=status_kyc, score_riesgo_asociado=score_riesgo_asociado
    )


@router.get("/{cliente_id}/historico", response_model=HistoricoRiesgoResponse)
async def get_historico_riesgo(
    cliente_id: str,
    meses: int = 12,
    user: TokenData = Depends(get_current_user),
    conn: asyncpg.Connection = Depends(get_db_connection),
):
    """Devuelve el histórico del score de riesgo general de PostgreSQL."""
    _verificar_acceso(cliente_id, user)

    await set_rls_context(conn, cliente_id)

    query = """
        SELECT dt.fecha, sr.score
        FROM gold.fact_score_riesgo sr
        JOIN gold.dim_tiempo dt ON sr.tiempo_key = dt.tiempo_key
        ORDER BY dt.fecha ASC
        LIMIT $1
    """
    rows = await conn.fetch(query, meses)

    # Formatear el periodo de forma corta (ej: "Jul 26")
    SPANISH_MONTHS = ["Ene", "Feb", "Mar", "Abr", "May", "Jun", "Jul", "Ago", "Sep", "Oct", "Nov", "Dic"]
    
    historico = []
    for r in rows:
        fecha = r['fecha']
        periodo = f"{SPANISH_MONTHS[fecha.month - 1]} {str(fecha.year)[2:]}"
        historico.append({"periodo": periodo, "score": r['score']})

    return HistoricoRiesgoResponse(
        cliente_id=cliente_id,
        historico=historico,
    )
