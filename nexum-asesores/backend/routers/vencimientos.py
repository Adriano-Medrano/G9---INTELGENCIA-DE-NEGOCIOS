# ============================================================
# routers/vencimientos.py — Calendario de vencimientos
# GET /vencimientos/{cliente_id}
# GET /vencimientos/{cliente_id}/proximos?dias=30
# ============================================================

from fastapi import APIRouter, Depends, Query
from pydantic import BaseModel
from typing import List, Optional
import logging

from routers.auth import get_current_user, TokenData

router = APIRouter()
logger = logging.getLogger("nexum.vencimientos")


# ── Schemas ───────────────────────────────────────────────────
class Vencimiento(BaseModel):
    id: str
    modelo_fiscal: str          # "Modelo 303 — IVA Q2"
    descripcion: str
    fecha_vencimiento: str      # ISO date
    dias_restantes: int
    importe_estimado: float
    estado: str                 # "urgente" | "proximo" | "ok" | "completado"
    caja_disponible_ese_dia: Optional[float]  # del modelo Prophet
    margen_caja: Optional[float]              # diferencia
    fecha_provision_recomendada: Optional[str]


class VencimientosResponse(BaseModel):
    cliente_id: str
    total_urgente: int      # ≤ 7 días
    total_proximo: int      # 8-30 días
    importe_urgente: float
    importe_proximo_30d: float
    vencimientos: List[Vencimiento]


# ── Endpoint principal ────────────────────────────────────────
@router.get("/{cliente_id}", response_model=VencimientosResponse)
async def get_vencimientos(
    cliente_id: str,
    dias: int = Query(default=90, ge=7, le=365, description="Horizonte en días"),
    user: TokenData = Depends(get_current_user),
):
    """
    Devuelve todos los vencimientos fiscales del cliente en el
    horizonte solicitado, enriquecidos con la caja proyectada
    (JOIN con fact_prediccion_caja para alertas inteligentes).

    Consulta SQL (capa Gold):
    ──────────────────────────
    SELECT
        d.declaracion_id,
        ti.nombre_modelo,
        ti.descripcion,
        dt.fecha                          AS fecha_vencimiento,
        dt.fecha - CURRENT_DATE           AS dias_restantes,
        d.importe_estimado,
        d.estado,
        pc.yhat                           AS caja_proyectada,
        pc.yhat - d.importe_estimado      AS margen_caja,
        dt.fecha - INTERVAL '4 days'      AS fecha_provision_recomendada
    FROM gold.fact_declaraciones d
    JOIN gold.dim_tiempo dt        ON d.tiempo_key = dt.tiempo_key
    JOIN gold.dim_tipo_impuesto ti ON d.impuesto_key = ti.impuesto_key
    JOIN gold.dim_cliente c        ON d.cliente_key = c.cliente_key
    LEFT JOIN gold.fact_prediccion_caja pc
        ON pc.cliente_key = d.cliente_key
        AND pc.fecha_prediccion = dt.fecha
    WHERE c.cliente_id = :cliente_id
      AND dt.fecha BETWEEN CURRENT_DATE - INTERVAL '1 month'
                       AND CURRENT_DATE + INTERVAL ':dias days'
    ORDER BY dt.fecha ASC;
    """
    if user.cliente_id != cliente_id:
        from fastapi import HTTPException
        raise HTTPException(403, "Acceso denegado.")

    logger.info(f"Vencimientos solicitados: {cliente_id} | horizonte: {dias}d")

    # Mock data desde la capa Gold
    vencimientos = [
        Vencimiento(
            id="V-2026-0041", modelo_fiscal="Modelo 111 — IRPF Retenciones",
            descripcion="Retenciones trabajadores Q2 2026",
            fecha_vencimiento="2026-07-20", dias_restantes=6,
            importe_estimado=3840.00, estado="urgente",
            caja_disponible_ese_dia=31450, margen_caja=27610,
            fecha_provision_recomendada="2026-07-16",
        ),
        Vencimiento(
            id="V-2026-0042", modelo_fiscal="Modelo 115 — Alquiler",
            descripcion="Retención alquiler Q2 2026",
            fecha_vencimiento="2026-07-20", dias_restantes=6,
            importe_estimado=890.00, estado="urgente",
            caja_disponible_ese_dia=31450, margen_caja=30560,
            fecha_provision_recomendada="2026-07-16",
        ),
        Vencimiento(
            id="V-2026-0043", modelo_fiscal="Modelo 130 — IRPF fraccionado",
            descripcion="Pago fraccionado IRPF Q2 2026",
            fecha_vencimiento="2026-07-20", dias_restantes=6,
            importe_estimado=1200.00, estado="urgente",
            caja_disponible_ese_dia=31450, margen_caja=30250,
            fecha_provision_recomendada="2026-07-16",
        ),
        Vencimiento(
            id="V-2026-0044", modelo_fiscal="Modelo 200 — IS 2025",
            descripcion="Impuesto Sociedades ejercicio 2025",
            fecha_vencimiento="2026-07-25", dias_restantes=11,
            importe_estimado=12400.00, estado="proximo",
            caja_disponible_ese_dia=28400, margen_caja=16000,
            fecha_provision_recomendada="2026-07-22",
        ),
        Vencimiento(
            id="V-2026-0045", modelo_fiscal="Modelo 303 — IVA Q3",
            descripcion="IVA tercer trimestre 2026",
            fecha_vencimiento="2026-10-20", dias_restantes=98,
            importe_estimado=7240.00, estado="ok",
            caja_disponible_ese_dia=9100, margen_caja=1860,
            fecha_provision_recomendada="2026-10-10",
        ),
        Vencimiento(
            id="V-2026-0040", modelo_fiscal="Modelo 303 — IVA Q2",
            descripcion="IVA segundo trimestre 2026",
            fecha_vencimiento="2026-04-20", dias_restantes=0,
            importe_estimado=6840.00, estado="completado",
            caja_disponible_ese_dia=None, margen_caja=None,
            fecha_provision_recomendada=None,
        ),
    ]

    urgentes = [v for v in vencimientos if v.estado == "urgente"]
    proximos  = [v for v in vencimientos if v.estado == "proximo"]

    return VencimientosResponse(
        cliente_id=cliente_id,
        total_urgente=len(urgentes),
        total_proximo=len(proximos),
        importe_urgente=sum(v.importe_estimado for v in urgentes),
        importe_proximo_30d=sum(v.importe_estimado for v in proximos),
        vencimientos=vencimientos,
    )
