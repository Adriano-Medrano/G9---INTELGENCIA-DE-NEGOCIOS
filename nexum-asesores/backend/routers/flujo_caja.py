# ============================================================
# routers/flujo_caja.py — Proyección de flujo de caja (Prophet)
# GET /flujo-caja/{cliente_id}
# GET /flujo-caja/{cliente_id}/proyeccion?dias=30|60|90
# ============================================================

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel
from typing import List, Optional
from datetime import date
import logging

from routers.auth import get_current_user, TokenData

router = APIRouter()
logger = logging.getLogger("nexum.flujo_caja")


# ── Schemas ───────────────────────────────────────────────────
class PuntoFlujoCaja(BaseModel):
    fecha: str           # "YYYY-MM-DD" o etiqueta legible
    real: Optional[float]       # None si es proyección futura
    proyectado: Optional[float]
    lower_80: Optional[float]   # banda de confianza 80%
    upper_80: Optional[float]


class AlertaProvision(BaseModel):
    vencimiento: str
    fecha_vencimiento: str
    importe_estimado: float
    fecha_provision_recomendada: str  # N días antes
    dias_restantes: int
    caja_proyectada_ese_dia: float
    margen: float   # caja - importe (positivo = OK, negativo = riesgo)
    alerta: bool


class FlujoCajaResponse(BaseModel):
    cliente_id: str
    saldo_actual: float
    proyeccion_30d: float
    proyeccion_60d: float
    proyeccion_90d: float
    serie: List[PuntoFlujoCaja]
    alertas_provision: List[AlertaProvision]
    modelo_version: str
    ultimo_retrain: str


# ── Helper tenant ─────────────────────────────────────────────
def _check_access(cliente_id: str, user: TokenData):
    if user.cliente_id != cliente_id:
        raise HTTPException(403, "Acceso denegado.")


# ── Endpoints ─────────────────────────────────────────────────
@router.get("/{cliente_id}", response_model=FlujoCajaResponse)
async def get_flujo_caja(
    cliente_id: str,
    dias: int = Query(default=90, ge=30, le=180),
    user: TokenData = Depends(get_current_user),
):
    """
    Devuelve la proyección de flujo de caja desde la capa Gold.

    Consulta SQL principal:
    ──────────────────────
    -- Serie real (fact_flujo_caja)
    SELECT
        dt.fecha,
        fc.ingreso_bruto - fc.gasto_total AS flujo_neto,
        NULL AS proyectado,
        NULL AS lower_80,
        NULL AS upper_80
    FROM gold.fact_flujo_caja fc
    JOIN gold.dim_tiempo dt ON fc.tiempo_key = dt.tiempo_key
    JOIN gold.dim_cliente c ON fc.cliente_key = c.cliente_key
    WHERE c.cliente_id = :cliente_id
      AND dt.fecha >= CURRENT_DATE - INTERVAL '6 months'
    ORDER BY dt.fecha

    UNION ALL

    -- Serie proyectada (fact_prediccion_caja)
    SELECT
        pc.fecha_prediccion AS fecha,
        NULL AS flujo_neto,
        pc.yhat AS proyectado,
        pc.yhat_lower AS lower_80,
        pc.yhat_upper AS upper_80
    FROM gold.fact_prediccion_caja pc
    JOIN gold.dim_cliente c ON pc.cliente_key = c.cliente_key
    WHERE c.cliente_id = :cliente_id
      AND pc.fecha_prediccion > CURRENT_DATE
      AND pc.fecha_prediccion <= CURRENT_DATE + INTERVAL ':dias days'
    ORDER BY pc.fecha_prediccion;
    """
    _check_access(cliente_id, user)
    logger.info(f"Flujo de caja solicitado: {cliente_id} | periodo: {dias}d")

    # Mock data — en prod reemplazar con query anterior
    serie = [
        PuntoFlujoCaja(fecha="Ene", real=38200, proyectado=None, lower_80=None, upper_80=None),
        PuntoFlujoCaja(fecha="Feb", real=29800, proyectado=None, lower_80=None, upper_80=None),
        PuntoFlujoCaja(fecha="Mar", real=41500, proyectado=None, lower_80=None, upper_80=None),
        PuntoFlujoCaja(fecha="Abr", real=35600, proyectado=None, lower_80=None, upper_80=None),
        PuntoFlujoCaja(fecha="May", real=44200, proyectado=None, lower_80=None, upper_80=None),
        PuntoFlujoCaja(fecha="Jun", real=31800, proyectado=31800, lower_80=30100, upper_80=33500),
        PuntoFlujoCaja(fecha="Jul (p)", real=None, proyectado=28400, lower_80=25200, upper_80=31600),
        PuntoFlujoCaja(fecha="Ago (p)", real=None, proyectado=24800, lower_80=20400, upper_80=29200),
        PuntoFlujoCaja(fecha="Sep (p)", real=None, proyectado=18200, lower_80=13800, upper_80=22600),
        PuntoFlujoCaja(fecha="Oct (p)", real=None, proyectado=9100,  lower_80=5200,  upper_80=13000),
    ]

    alertas = [
        AlertaProvision(
            vencimiento="Modelo 111 + 115 Q2",
            fecha_vencimiento="2026-07-20",
            importe_estimado=4730,
            fecha_provision_recomendada="2026-07-18",
            dias_restantes=4,
            caja_proyectada_ese_dia=31450,
            margen=26720,
            alerta=False,
        ),
        AlertaProvision(
            vencimiento="Impuesto Sociedades 2025",
            fecha_vencimiento="2026-07-25",
            importe_estimado=12400,
            fecha_provision_recomendada="2026-07-22",
            dias_restantes=8,
            caja_proyectada_ese_dia=28400,
            margen=16000,
            alerta=False,
        ),
        AlertaProvision(
            vencimiento="IVA Q3 — Modelo 303",
            fecha_vencimiento="2026-10-20",
            importe_estimado=7240,
            fecha_provision_recomendada="2026-10-10",
            dias_restantes=88,
            caja_proyectada_ese_dia=9100,
            margen=1860,
            alerta=True,  # margen justo → alerta
        ),
    ]

    return FlujoCajaResponse(
        cliente_id=cliente_id,
        saldo_actual=31450,
        proyeccion_30d=24800,
        proyeccion_60d=18200,
        proyeccion_90d=9100,
        serie=serie,
        alertas_provision=alertas,
        modelo_version="prophet-v1.8.0",
        ultimo_retrain="2026-07-14T05:18:00Z",
    )
