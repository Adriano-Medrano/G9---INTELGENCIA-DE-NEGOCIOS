# ============================================================
# models/cashflow_model.py — Proyección de Flujo de Caja (Prophet)
# Entrenamiento, predicción a 30/60/90 días y alertas de provisión.
# Ejecutado diariamente tras dag_gold y semanalmente para retrain.
# ============================================================

import os
import logging
import pickle
from datetime import datetime, timedelta
from pathlib import Path
from typing import Dict, List, Optional, Tuple

import numpy as np
import pandas as pd
from prophet import Prophet
from prophet.diagnostics import cross_validation, performance_metrics
from sklearn.metrics import mean_absolute_error, mean_squared_error

logger = logging.getLogger("nexum.models.cashflow")

MODEL_DIR = Path(os.getenv("NEXUM_MODEL_DIR", "/models/nexum"))
MODEL_DIR.mkdir(parents=True, exist_ok=True)


def _model_path(cliente_id: str) -> Path:
    """Cada cliente tiene su propio modelo Prophet (serie temporal personalizada)."""
    return MODEL_DIR / f"cashflow_{cliente_id}.pkl"


# ── Feature engineering — Regresores externos ────────────────
def add_regressors(df: pd.DataFrame, vencimientos: pd.DataFrame) -> pd.DataFrame:
    """
    Añade regresores externos a la serie de Prophet:
    - Importe de vencimientos fiscales en ese día (presión de salida de caja)
    - Dummy de fin de trimestre (mayor facturación típica)

    Args:
        df: DataFrame Prophet {'ds': date, 'y': flujo_neto, ...}
        vencimientos: DataFrame {'fecha': date, 'importe': float}

    Returns:
        df enriquecido con columnas 'vencimiento_importe' y 'fin_trimestre'
    """
    df = df.copy()

    # Regresor: importe de vencimiento fiscal
    venc_map = vencimientos.set_index("fecha")["importe"].to_dict()
    df["vencimiento_importe"] = df["ds"].map(venc_map).fillna(0)

    # Regresor: fin de trimestre (último mes del Q)
    df["fin_trimestre"] = df["ds"].dt.month.isin([3, 6, 9, 12]).astype(int)

    return df


# ── Entrenamiento ─────────────────────────────────────────────
def train(
    cliente_id: str,
    df_historico: pd.DataFrame,
    vencimientos: Optional[pd.DataFrame] = None,
    forecast_horizon: int = 90,
) -> Tuple[Prophet, Dict]:
    """
    Entrena un modelo Prophet para la serie de flujo de caja del cliente.

    Args:
        cliente_id:       ID del cliente (para persistir el modelo)
        df_historico:     DataFrame con columnas {fecha, flujo_neto}
                          mínimo 12 meses de datos diarios/semanales
        vencimientos:     DataFrame con {fecha, importe} de vencimientos futuros
        forecast_horizon: días a proyectar (default 90)

    Returns:
        (model, metrics_dict)
    """
    logger.info(f"Entrenando Prophet · Cliente: {cliente_id} · Muestras: {len(df_historico)}")

    # Preparar datos para Prophet
    df = df_historico.rename(columns={"fecha": "ds", "flujo_neto": "y"}).copy()
    df["ds"] = pd.to_datetime(df["ds"])
    df = df.sort_values("ds").reset_index(drop=True)

    # Añadir regresores si hay vencimientos disponibles
    use_regressors = vencimientos is not None and len(vencimientos) > 0
    if use_regressors:
        df = add_regressors(df, vencimientos)

    # Modelo Prophet con estacionalidad fiscal peruana
    model = Prophet(
        yearly_seasonality=True,
        weekly_seasonality=True,
        daily_seasonality=False,
        seasonality_mode="multiplicative",  # fluctuaciones proporcionales
        interval_width=0.80,               # banda de confianza 80%
        changepoint_prior_scale=0.05,      # regularización de cambios de tendencia
    )

    # Estacionalidad trimestral fiscal (IGV, Impuesto a la Renta)
    model.add_seasonality(
        name="trimestral_fiscal",
        period=91.25,
        fourier_order=5,
    )

    # Festivos Perú
    try:
        from prophet.make_holidays import make_holidays_df
        holidays_es = make_holidays_df(year_list=list(range(2020, 2031)), country="ES")
        model.add_country_holidays(country_name="ES")
    except Exception:
        logger.warning("No se pudieron cargar festivos de Perú — Prophet continuará sin ellos")

    # Regresores externos
    if use_regressors:
        model.add_regressor("vencimiento_importe", standardize=True)
        model.add_regressor("fin_trimestre")

    model.fit(df)

    # Validación cruzada (ventana deslizante de 30 días)
    try:
        cv_results = cross_validation(
            model,
            initial=f"{max(180, len(df)//2)} days",
            period="30 days",
            horizon="90 days",
            parallel="processes",
        )
        pm = performance_metrics(cv_results)
        mae  = float(pm["mae"].mean())
        rmse = float(pm["rmse"].mean())
        mape = float(pm["mape"].mean()) * 100  # %
        logger.info(f"CV: MAE={mae:.0f}S/ | RMSE={rmse:.0f}S/ | MAPE={mape:.1f}%")
    except Exception as e:
        logger.warning(f"CV no disponible (datos insuficientes): {e}")
        mae, rmse, mape = None, None, None

    metrics = {
        "cliente_id":        cliente_id,
        "version":           f"prophet-v{datetime.now().strftime('%Y%m%d-%H%M')}",
        "n_samples":         len(df),
        "forecast_horizon":  forecast_horizon,
        "mae":               mae,
        "rmse":              rmse,
        "mape_pct":          mape,
        "use_regressors":    use_regressors,
        "trained_at":        datetime.utcnow().isoformat(),
    }

    # Persistir modelo por cliente
    path = _model_path(cliente_id)
    with open(path, "wb") as f:
        pickle.dump({
            "model": model,
            "metrics": metrics,
            "use_regressors": use_regressors,
        }, f)

    logger.info(f"Modelo guardado: {path}")
    return model, metrics


# ── Predicción ────────────────────────────────────────────────
def predict(
    cliente_id: str,
    horizonte_dias: int = 90,
    vencimientos_futuros: Optional[pd.DataFrame] = None,
) -> pd.DataFrame:
    """
    Genera proyección de flujo de caja para el cliente.

    Returns:
        DataFrame con columnas:
        {ds, yhat, yhat_lower, yhat_upper, horizonte_dias}
        Filtrado solo a fechas futuras (> hoy)
    """
    path = _model_path(cliente_id)
    if not path.exists():
        raise FileNotFoundError(f"Modelo Prophet no encontrado para {cliente_id}")

    with open(path, "rb") as f:
        artifact = pickle.load(f)

    model: Prophet = artifact["model"]
    use_regressors: bool = artifact["use_regressors"]

    # Futuro
    future = model.make_future_dataframe(periods=horizonte_dias, freq="D")

    if use_regressors and vencimientos_futuros is not None:
        future = add_regressors(future, vencimientos_futuros)
    elif use_regressors:
        future["vencimiento_importe"] = 0
        future["fin_trimestre"] = future["ds"].dt.month.isin([3, 6, 9, 12]).astype(int)

    forecast = model.predict(future)

    # Solo fechas futuras
    hoy = pd.Timestamp.now().normalize()
    result = forecast[forecast["ds"] > hoy][
        ["ds", "yhat", "yhat_lower", "yhat_upper"]
    ].copy()
    result["horizonte_dias"] = horizonte_dias

    logger.info(
        f"Predicción generada: {cliente_id} | {len(result)} días | "
        f"[30d={result.iloc[29]['yhat']:.0f}S/ | "
        f"60d={result.iloc[59]['yhat']:.0f}S/ | "
        f"90d={result.iloc[89]['yhat']:.0f}S/]" if len(result) >= 90 else ""
    )

    return result.reset_index(drop=True)


# ── Alertas de provisión ──────────────────────────────────────
def generar_alertas_provision(
    prediccion: pd.DataFrame,
    vencimientos: pd.DataFrame,
    dias_antelacion: int = 4,
) -> List[Dict]:
    """
    Cruza la proyección Prophet con los vencimientos fiscales para
    determinar si habrá caja suficiente y cuándo provisionar.

    Args:
        prediccion:    DataFrame de predicción (ds, yhat, yhat_lower, yhat_upper)
        vencimientos:  DataFrame con {fecha, modelo, importe_estimado}
        dias_antelacion: días antes del vencimiento para recomendar provisión

    Returns:
        Lista de alertas con recomendación de acción.
    """
    alertas = []
    pred_indexed = prediccion.set_index("ds")["yhat"].to_dict()

    for _, venc in vencimientos.iterrows():
        fecha_venc    = pd.Timestamp(venc["fecha"])
        fecha_prov    = fecha_venc - timedelta(days=dias_antelacion)
        importe       = float(venc["importe_estimado"])
        caja_ese_dia  = pred_indexed.get(fecha_venc, None)

        margen = (caja_ese_dia - importe) if caja_ese_dia is not None else None
        alerta = margen is not None and margen < importe * 0.20  # margen <20% del pago

        alertas.append({
            "modelo":                    str(venc.get("modelo", "")),
            "fecha_vencimiento":         fecha_venc.date().isoformat(),
            "importe_estimado":          importe,
            "caja_proyectada_ese_dia":   round(caja_ese_dia, 2) if caja_ese_dia else None,
            "margen":                    round(margen, 2) if margen is not None else None,
            "fecha_provision_recomendada": fecha_prov.date().isoformat(),
            "alerta":                    alerta,
            "mensaje": (
                f"⚠️ Margen ajustado ({margen:.0f}S/). Provisionar {importe:.0f}S/ antes del {fecha_prov.date()}"
                if alerta else
                f"✅ Caja suficiente ({caja_ese_dia:.0f}S/ disponibles)"
            ) if caja_ese_dia else "ℹ️ Sin datos de caja para esta fecha",
        })

    return sorted(alertas, key=lambda x: x["fecha_vencimiento"])


# ── CLI demo ──────────────────────────────────────────────────
if __name__ == "__main__":
    # Datos sintéticos de ejemplo (24 meses diarios)
    dates = pd.date_range("2024-01-01", periods=730, freq="D")
    np.random.seed(42)
    flujo_real = (
        25000
        + np.sin(np.linspace(0, 4 * np.pi, 730)) * 5000  # estacionalidad anual
        + np.random.normal(0, 1500, 730)                   # ruido
        - np.where(dates.month.isin([1, 4, 7, 10]) & (dates.day == 20), 4000, 0)  # pago impuestos
    )

    df_demo = pd.DataFrame({"fecha": dates, "flujo_neto": flujo_real})

    venc_demo = pd.DataFrame({
        "fecha":            pd.to_datetime(["2026-07-20", "2026-10-20"]),
        "importe":          [5930, 7240],
        "modelo":           ["Varios modelos julio", "IGV Q3"],
        "importe_estimado": [5930, 7240],
    })

    model, metrics = train("CL-DEMO-001", df_demo, venc_demo)
    print("Métricas:", metrics)

    pred = predict("CL-DEMO-001", horizonte_dias=90, vencimientos_futuros=venc_demo)
    print("Primeros 5 días proyectados:")
    print(pred.head())

    alertas = generar_alertas_provision(pred, venc_demo)
    print("\nAlertas de provisión:")
    for a in alertas:
        print(f"  {a['modelo']}: {a['mensaje']}")
