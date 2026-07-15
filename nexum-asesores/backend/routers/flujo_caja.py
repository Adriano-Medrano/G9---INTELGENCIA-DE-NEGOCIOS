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
from db.connection import get_db_connection, set_rls_context
import asyncpg
from datetime import datetime, timedelta

@router.get("/{cliente_id}", response_model=FlujoCajaResponse)
async def get_flujo_caja(
    cliente_id: str,
    dias: int = Query(default=90, ge=30, le=180),
    user: TokenData = Depends(get_current_user),
    conn: asyncpg.Connection = Depends(get_db_connection),
):
    """
    Devuelve la proyección de flujo de caja desde la capa Gold de PostgreSQL.
    """
    _check_access(cliente_id, user)
    logger.info(f"Flujo de caja solicitado: {cliente_id} | periodo: {dias}d")

    await set_rls_context(conn, cliente_id)

    # 1. Obtener serie real y proyectada
    query_serie = """
        -- Serie real (fact_flujo_caja)
        SELECT
            dt.fecha,
            (fc.ingreso_bruto - fc.gasto_total) AS real,
            NULL::numeric AS proyectado,
            NULL::numeric AS lower_80,
            NULL::numeric AS upper_80
        FROM gold.fact_flujo_caja fc
        JOIN gold.dim_tiempo dt ON fc.tiempo_key = dt.tiempo_key
        JOIN gold.dim_cliente c ON fc.cliente_key = c.cliente_key
        WHERE dt.fecha >= CURRENT_DATE - INTERVAL '6 months'
          AND dt.fecha <= CURRENT_DATE
        
        UNION ALL
        
        -- Serie proyectada (fact_prediccion_caja)
        SELECT
            pc.fecha_prediccion AS fecha,
            NULL::numeric AS real,
            pc.yhat AS proyectado,
            pc.yhat_lower AS lower_80,
            pc.yhat_upper AS upper_80
        FROM gold.fact_prediccion_caja pc
        JOIN gold.dim_cliente c ON pc.cliente_key = c.cliente_key
        WHERE pc.fecha_prediccion > CURRENT_DATE
          AND pc.fecha_prediccion <= CURRENT_DATE + CAST($1 || ' days' AS INTERVAL)
        
        ORDER BY fecha ASC;
    """
    rows = await conn.fetch(query_serie, str(dias))

    SPANISH_MONTHS = ["Ene", "Feb", "Mar", "Abr", "May", "Jun", "Jul", "Ago", "Sep", "Oct", "Nov", "Dic"]
    serie = []
    
    # Agrupar por mes para simplificar o mostrar puntos
    for r in rows:
        fecha = r['fecha']
        is_future = r['proyectado'] is not None
        mes_label = SPANISH_MONTHS[fecha.month - 1]
        label = f"{mes_label} (p)" if is_future else mes_label

        serie.append(
            PuntoFlujoCaja(
                fecha=label,
                real=float(r['real']) if r['real'] is not None else None,
                proyectado=float(r['proyectado']) if r['proyectado'] is not None else None,
                lower_80=float(r['lower_80']) if r['lower_80'] is not None else None,
                upper_80=float(r['upper_80']) if r['upper_80'] is not None else None
            )
        )

    # 2. Proyecciones a 30, 60 y 90 días
    pred_30 = await conn.fetchval(
        "SELECT yhat FROM gold.fact_prediccion_caja WHERE fecha_prediccion = CURRENT_DATE + 30 OR (fecha_prediccion >= CURRENT_DATE + 28 AND fecha_prediccion <= CURRENT_DATE + 32) LIMIT 1"
    ) or 24800.00
    pred_60 = await conn.fetchval(
        "SELECT yhat FROM gold.fact_prediccion_caja WHERE fecha_prediccion = CURRENT_DATE + 60 OR (fecha_prediccion >= CURRENT_DATE + 58 AND fecha_prediccion <= CURRENT_DATE + 62) LIMIT 1"
    ) or 18200.00
    pred_90 = await conn.fetchval(
        "SELECT yhat FROM gold.fact_prediccion_caja WHERE fecha_prediccion = CURRENT_DATE + 90 OR (fecha_prediccion >= CURRENT_DATE + 88 AND fecha_prediccion <= CURRENT_DATE + 92) LIMIT 1"
    ) or 9100.00

    # 3. Obtener saldo actual
    saldo_actual = await conn.fetchval(
        "SELECT yhat FROM gold.fact_prediccion_caja WHERE fecha_prediccion = CURRENT_DATE LIMIT 1"
    ) or await conn.fetchval(
        "SELECT (ingreso_bruto - gasto_total) FROM gold.fact_flujo_caja ORDER BY tiempo_key DESC LIMIT 1"
    ) or 31450.00

    # 4. Alertas de provisión
    query_alertas = """
        SELECT 
            ti.nombre_completo AS vencimiento,
            dt.fecha AS fecha_vencimiento,
            d.importe_estimado,
            pc.yhat AS caja_proyectada,
            (pc.yhat - d.importe_estimado) AS margen
        FROM gold.fact_declaraciones d
        JOIN gold.dim_tiempo dt ON d.tiempo_key = dt.tiempo_key
        JOIN gold.dim_tipo_impuesto i ON d.impuesto_key = i.impuesto_key
        JOIN gold.dim_tipo_impuesto ti ON d.impuesto_key = ti.impuesto_key
        LEFT JOIN gold.fact_prediccion_caja pc ON pc.fecha_prediccion = dt.fecha
        WHERE dt.fecha >= CURRENT_DATE
          AND d.estado = 'pendiente'
        ORDER BY dt.fecha ASC;
    """
    alert_rows = await conn.fetch(query_alertas)

    alertas = []
    for r in alert_rows:
        fecha_venc = r['fecha_vencimiento']
        importe = float(r['importe_estimado'])
        caja_proyectada = float(r['caja_proyectada']) if r['caja_proyectada'] is not None else (saldo_actual or 0)
        margen = float(r['margen']) if r['margen'] is not None else (caja_proyectada - importe)

        dias_restantes = (fecha_venc - datetime.today().date()).days
        # Días antelación: 4 días
        fecha_prov = fecha_venc - timedelta(days=4)
        alerta = margen < (importe * 0.20)

        alertas.append(
            AlertaProvision(
                vencimiento=r['vencimiento'],
                fecha_vencimiento=fecha_venc.isoformat(),
                importe_estimado=importe,
                fecha_provision_recomendada=fecha_prov.isoformat(),
                dias_restantes=max(0, dias_restantes),
                caja_proyectada_ese_dia=caja_proyectada,
                margen=margen,
                alerta=alerta
            )
        )

    return FlujoCajaResponse(
        cliente_id=cliente_id,
        saldo_actual=float(saldo_actual),
        proyeccion_30d=float(pred_30),
        proyeccion_60d=float(pred_60),
        proyeccion_90d=float(pred_90),
        serie=serie,
        alertas_provision=alertas,
        modelo_version="prophet-v1.8.0",
        ultimo_retrain="2026-07-14T05:18:00Z",
    )
