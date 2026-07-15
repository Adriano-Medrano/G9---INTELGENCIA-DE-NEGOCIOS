# ============================================================
# models/risk_model.py — Score de Riesgo Fiscal (XGBoost)
# Entrenamiento, predicción, feature importance y drift check.
# Ejecutado semanalmente por dag_retrain.py (Airflow).
# ============================================================

import os
import logging
import pickle
from datetime import datetime, timezone
from pathlib import Path
from typing import Dict, List, Optional

import numpy as np
import pandas as pd
from sklearn.model_selection import train_test_split, RandomizedSearchCV, StratifiedKFold
from sklearn.preprocessing import LabelEncoder
from sklearn.metrics import (
    accuracy_score, f1_score, roc_auc_score, classification_report
)
import xgboost as xgb

logger = logging.getLogger("nexum.models.risk")

# ── Paths ─────────────────────────────────────────────────────
MODEL_DIR = Path(os.getenv("NEXUM_MODEL_DIR", "/models/nexum"))
MODEL_DIR.mkdir(parents=True, exist_ok=True)
MODEL_PATH     = MODEL_DIR / "risk_model.pkl"
METADATA_PATH  = MODEL_DIR / "risk_model_metadata.json"

# ── Umbrales de riesgo ────────────────────────────────────────
RISK_THRESHOLDS = {"bajo": 40, "moderado": 70}  # >70 = alto

# ── Feature engineering ───────────────────────────────────────
SECTOR_RISK_MAP = {
    "manufactura": 3,
    "importacion": 3,
    "construccion": 2,
    "hosteleria": 2,
    "retail": 2,
    "servicios": 1,
    "tecnologia": 1,
}

FEATURES = [
    "dias_promedio_atraso",       # promedio días de atraso en declaraciones (12m)
    "pct_declaraciones_tarde",    # % declaraciones fuera de plazo (0-1)
    "ratio_iva_irpf",             # coherencia entre IVA declarado e IRPF
    "sector_riesgo_score",        # codificación de sector (1-3)
    "tiene_sanciones",            # 0/1
    "pct_contrapartes_fallecidas",# RENIEC: % facturas emitidas por fallecidos
    "pct_identidades_invalidas",  # RENIEC: % DNIs inexistentes en el padrón
    "desviacion_ubigeo_fiscal",   # RENIEC: discrepancia ubigeo vs domicilio fiscal
    "n_dni_sospechosos",          # RENIEC: Nro. DNIs asociados con fraude/usurpación
    "representante_suplantado_risk" # RENIEC: riesgo de suplantación de representante
]


def build_features(df: pd.DataFrame) -> pd.DataFrame:
    """
    Feature engineering a partir de datos de la capa Silver/Gold.
    Entrada: DataFrame con datos de un cliente por periodo.
    Salida:  DataFrame con FEATURES listo para el modelo.
    """
    result = pd.DataFrame()

    # Días de atraso (de stg_declaraciones)
    result["dias_promedio_atraso"]       = df["dias_atraso"].clip(lower=0).mean()
    result["max_dias_atraso"]            = df["dias_atraso"].clip(lower=0).max()
    result["pct_declaraciones_tarde"]    = (df["dias_atraso"] > 0).mean()

    # Coherencia IVA/IRPF (ratio de base imponible declarada)
    iva   = df.loc[df["modelo"] == "303", "base_imponible"].sum()
    irpf  = df.loc[df["modelo"] == "111", "base_imponible"].sum()
    result["ratio_iva_irpf"] = irpf / iva if iva > 0 else 0

    # Variación de facturación trimestral (de fact_flujo_caja)
    if "ingreso_bruto" in df.columns:
        result["variacion_facturacion_q"] = df["ingreso_bruto"].pct_change().iloc[-1]
    else:
        result["variacion_facturacion_q"] = 0

    # Requerimientos Hacienda
    result["n_requerimientos_3a"] = df.get("n_requerimientos", pd.Series([0])).sum()

    # Sector
    sector = df["sector"].iloc[0].lower() if "sector" in df.columns else "servicios"
    result["sector_riesgo_score"] = SECTOR_RISK_MAP.get(sector, 1)

    # Cumplimiento histórico
    total    = len(df)
    a_tiempo = (df["dias_atraso"] == 0).sum()
    result["pct_cumplimiento_historico"] = a_tiempo / total if total > 0 else 1.0

    # Sanciones y aplazamientos
    result["tiene_sanciones"]    = int(df.get("tiene_sancion", pd.Series([False])).any())
    result["tiene_aplazamientos"] = int(df.get("tiene_aplazamiento", pd.Series([False])).any())

    return result[FEATURES].fillna(0)


# ── Etiquetado de entrenamiento ────────────────────────────────
def label_risk(score: float) -> int:
    """Convierte score continuo a categoría: 0=bajo, 1=moderado, 2=alto."""
    if score <= RISK_THRESHOLDS["bajo"]:    return 0
    if score <= RISK_THRESHOLDS["moderado"]: return 1
    return 2


# ── Entrenamiento ─────────────────────────────────────────────
def train(X: pd.DataFrame, y: pd.Series, version: str = "auto") -> Dict:
    """
    Entrena el modelo XGBoost de clasificación de riesgo.

    Args:
        X: DataFrame de features (columnas = FEATURES)
        y: Series de etiquetas (0, 1, 2)
        version: string de versión, "auto" usa timestamp

    Returns:
        Dict con métricas de evaluación.
    """
    if version == "auto":
        version = f"xgboost-v{datetime.now().strftime('%Y%m%d-%H%M')}"

    logger.info(f"Iniciando entrenamiento · Versión: {version} · Muestras: {len(X)}")

    X_train, X_test, y_train, y_test = train_test_split(
        X, y, test_size=0.2, random_state=42, stratify=y
    )

    # Definir el modelo base
    base_model = xgb.XGBClassifier(
        objective="multi:softprob",
        num_class=3,
        eval_metric="mlogloss",
        random_state=42,
        n_jobs=-1,
    )
    
    # Grid de hiperparámetros para la búsqueda
    param_distributions = {
        'n_estimators': [100, 200, 300],
        'max_depth': [3, 5, 7],
        'learning_rate': [0.01, 0.05, 0.1],
        'subsample': [0.8, 1.0],
        'colsample_bytree': [0.8, 1.0],
        'min_child_weight': [1, 3, 5],
        'gamma': [0, 0.1, 0.2]
    }
    
    cv = StratifiedKFold(n_splits=3, shuffle=True, random_state=42)
    
    logger.info("Optimizando hiperparámetros con RandomizedSearchCV...")
    search = RandomizedSearchCV(
        estimator=base_model,
        param_distributions=param_distributions,
        n_iter=10,
        scoring='f1_weighted',
        cv=cv,
        verbose=0,
        random_state=42,
        n_jobs=-1
    )
    
    search.fit(X_train, y_train)
    model = search.best_estimator_
    logger.info(f"Mejores parámetros encontrados: {search.best_params_}")

    logger.info("Re-entrenando el mejor modelo con early_stopping...")
    model.set_params(early_stopping_rounds=10)
    model.fit(
        X_train, y_train,
        eval_set=[(X_test, y_test)],
        verbose=False,
    )

    # Métricas
    y_pred = model.predict(X_test)
    y_prob = model.predict_proba(X_test)

    acc  = accuracy_score(y_test, y_pred)
    f1   = f1_score(y_test, y_pred, average="weighted")
    auc  = roc_auc_score(y_test, y_prob, multi_class="ovr", average="weighted")

    metrics = {
        "version": version,
        "accuracy": round(acc, 4),
        "f1_weighted": round(f1, 4),
        "auc_roc": round(auc, 4),
        "n_train": len(X_train),
        "n_test":  len(X_test),
        "trained_at": datetime.now(timezone.utc).isoformat(),
        "feature_importances": dict(zip(FEATURES, model.feature_importances_.tolist())),
    }

    logger.info(f"Métricas: acc={acc:.3f} | f1={f1:.3f} | auc={auc:.3f}")
    logger.info(f"\n{classification_report(y_test, y_pred, target_names=['bajo','moderado','alto'])}")

    # Persistir modelo
    with open(MODEL_PATH, "wb") as f:
        pickle.dump({"model": model, "version": version, "features": FEATURES}, f)

    import json
    with open(METADATA_PATH, "w") as f:
        json.dump(metrics, f, indent=2)

    logger.info(f"Modelo guardado en {MODEL_PATH}")
    return metrics


# ── Predicción ────────────────────────────────────────────────
def predict_score(X: pd.DataFrame) -> List[Dict]:
    """
    Predice el score de riesgo para un cliente.

    Returns:
        Lista de dicts con {score, nivel, proba_bajo, proba_med, proba_alto}
    """
    if not MODEL_PATH.exists():
        raise FileNotFoundError(f"Modelo no encontrado en {MODEL_PATH}. Ejecuta train() primero.")

    with open(MODEL_PATH, "rb") as f:
        artifact = pickle.load(f)

    model: xgb.XGBClassifier = artifact["model"]
    X_ordered = X[FEATURES].fillna(0)

    probas = model.predict_proba(X_ordered)
    labels = model.predict(X_ordered)

    results = []
    for proba, label in zip(probas, labels):
        # Score continuo 0-100: ponderación por clase
        score_continuo = int(proba[0] * 20 + proba[1] * 55 + proba[2] * 85)
        nivel = ["bajo", "moderado", "alto"][label]
        results.append({
            "score":         score_continuo,
            "nivel":         nivel,
            "proba_bajo":    round(float(proba[0]), 4),
            "proba_moderado": round(float(proba[1]), 4),
            "proba_alto":    round(float(proba[2]), 4),
        })

    return results


# ── Drift check ───────────────────────────────────────────────
def check_drift(
    baseline_metrics: Dict,
    current_f1: float,
    threshold_drop: float = 0.05,
) -> Dict:
    """
    Compara métricas actuales contra baseline del último retrain.
    Si F1 cae más de `threshold_drop`, emite alerta.

    Ejecutado por dag_retrain.py después del reentrenamiento.
    """
    baseline_f1 = baseline_metrics.get("f1_weighted", 1.0)
    drop = baseline_f1 - current_f1
    drift_detected = drop > threshold_drop

    result = {
        "drift_detected": drift_detected,
        "baseline_f1":    baseline_f1,
        "current_f1":     current_f1,
        "drop":           round(drop, 4),
        "threshold":      threshold_drop,
        "timestamp":      datetime.now(timezone.utc).isoformat(),
    }

    if drift_detected:
        logger.warning(
            f"⚠️  DRIFT DETECTADO: F1 cayó {drop:.3f} "
            f"(baseline={baseline_f1:.3f} → actual={current_f1:.3f}). "
            "Investigar calidad de datos o cambio en distribución."
        )
    else:
        logger.info(f"Drift check OK: caída F1 = {drop:.4f} < umbral {threshold_drop}")

    return result


if __name__ == "__main__":
    # 1. Datos sintéticos de ejemplo - BASELINE
    np.random.seed(42)
    n = 300
    
    def generate_demo_data(n_samples, fraud_multiplier=1.0):
        X = pd.DataFrame({
            "dias_promedio_atraso":       np.random.exponential(2, n_samples),
            "pct_declaraciones_tarde":    np.random.beta(2, 8, n_samples),
            "ratio_iva_irpf":             np.random.normal(0.15, 0.05, n_samples).clip(0, 1),
            "sector_riesgo_score":        np.random.choice([1, 2, 3], n_samples),
            "tiene_sanciones":            np.random.binomial(1, 0.1, n_samples),
            "pct_contrapartes_fallecidas":np.random.beta(0.5, 9, n_samples) * fraud_multiplier, 
            "pct_identidades_invalidas":  np.random.beta(0.5, 9, n_samples) * fraud_multiplier,
            "desviacion_ubigeo_fiscal":   np.random.binomial(1, min(1.0, 0.15 * fraud_multiplier), n_samples),
            "n_dni_sospechosos":          np.random.poisson(0.1 * fraud_multiplier, n_samples),
            "representante_suplantado_risk": np.random.binomial(1, min(1.0, 0.05 * fraud_multiplier), n_samples),
        })
        raw_score = (
            X["dias_promedio_atraso"] * 4 +
            X["pct_contrapartes_fallecidas"] * 120 +
            X["pct_identidades_invalidas"] * 150 +
            X["n_dni_sospechosos"] * 25 +
            X["representante_suplantado_risk"] * 40 +
            X["tiene_sanciones"] * 15 +
            np.random.normal(0, 5, n_samples)
        ).clip(0, 100)
        y = raw_score.apply(label_risk)
        return X, y

    X_baseline, y_baseline = generate_demo_data(n, fraud_multiplier=1.0)
    
    print("\n--- ENTRENAMIENTO BASELINE ---")
    baseline_metrics = train(X_baseline, y_baseline, version="xgboost-v2.5.0-kyc-shield")
    print("\nMétricas de entrenamiento demo:", baseline_metrics)

    print("\n--- SIMULANDO DRIFT (CAMBIO EN PATRONES DE FRAUDE) ---")
    # Aumentamos el multiplicador de fraude para simular un cambio en el mercado
    X_drift, y_drift = generate_demo_data(n, fraud_multiplier=5.0)
    
    # Hacemos predicciones con el modelo actual pero evaluamos con las nuevas etiquetas
    preds_drift = predict_score(X_drift)
    # Extraemos solo las etiquetas (0, 1, 2)
    y_pred_drift = [{"bajo": 0, "moderado": 1, "alto": 2}[p["nivel"]] for p in preds_drift]
    current_f1 = f1_score(y_drift, y_pred_drift, average="weighted")
    
    print(f"F1 actual en nuevos datos con alto fraude: {current_f1:.4f}")
    
    # Ejecutamos el check_drift que alertará de la caída
    print("\n--- EJECUTANDO DRIFT CHECK ---")
    check_drift(baseline_metrics, current_f1, threshold_drop=0.05)
