# src/mlops/market_experiments.py
from __future__ import annotations
import os
import re
from datetime import datetime
from typing import Dict, Any, List
from mlflow import sklearn as mlflow_sklearn  

import mlflow
import numpy as np
import pandas as pd
from sklearn.cluster import KMeans
from sklearn.preprocessing import StandardScaler
from sklearn.metrics import silhouette_score

from src.ui.sections.market import _compute_indicators, _dl_autoencoder_anomaly_scores

# Tracking local avec SQLite
MLFLOW_URI = os.getenv("MLFLOW_STORE", "sqlite:///mlruns.db")
mlflow.set_tracking_uri(MLFLOW_URI)


def _sanitize_name(name: str) -> str:
    """
    Sanitize pour MLflow :
    - on garde uniquement [0-9A-Za-z_-]
    - on remplace tout le reste par '_'
    Exemples :
      '^FCHI'   -> 'FCHI'
      'BNP.PA'  -> 'BNP_PA'
    """
    return re.sub(r"[^0-9A-Za-z_-]", "_", name)


def fetch_market_data(
    fetch_func,
    symbols: List[str],
    interval: str = "1d",
    period: str = "1y",
) -> Dict[str, pd.DataFrame]:
    """
    fetch_func: fonction (symbol, interval, period) -> JSON OHLCV (ton backend)
    """
    data_dict: Dict[str, pd.DataFrame] = {}
    for sym in symbols:
        try:
            js = fetch_func(sym, interval, period)
            if js and "candles" in js:
                df = pd.DataFrame(js["candles"])
                if df.empty:
                    continue
                df = _compute_indicators(df, interval)
                data_dict[sym] = df
        except Exception:
            # on skippe le symbole en erreur (yfinance down, etc.)
            continue
    return data_dict


def train_kmeans(df: pd.DataFrame, n_clusters: int = 3):
    """
    KMeans sur features vectorisées (ret, vol20) avec StandardScaler.
    """
    feats = ["ret", "vol20"]
    X = df[feats].replace([np.inf, -np.inf], np.nan).fillna(0.0).to_numpy()

    scaler = StandardScaler()
    Xn = scaler.fit_transform(X)

    km = KMeans(n_clusters=n_clusters, random_state=0, n_init="auto")
    labels = km.fit_predict(Xn)

    sil = silhouette_score(Xn, labels) if len(set(labels)) > 1 else 0.0
    return km, scaler, float(sil)


def train_autoencoder(df: pd.DataFrame, quick: bool = False):
    """
    Entraîne l'autoencoder via helper existant.
    - quick=True → n_epochs réduits + tail des données
    """
    # On garde seulement la fin de l'historique pour accélérer
    if quick and len(df) > 300:
        df_ae = df.tail(300).copy()
    else:
        df_ae = df.copy()

    n_epochs = 5 if quick else 20

    scores, msg = _dl_autoencoder_anomaly_scores(df_ae, n_epochs=n_epochs)
    if scores is None:
        return None, None, msg

    recon_mean = float(scores.mean())
    return scores, recon_mean, msg


def run_market_experiment(
    fetch_func,
    symbols: List[str],
    quick: bool = False,
) -> Dict[str, Any]:
    """
    Lance un run complet MLOps pour les symboles donnés.

    quick=False :
        - period = 1y
        - autoencoder 20 epochs
        - toutes les lignes

    quick=True :
        - period = 1y (mais on optimise le training)
        - autoencoder 5 epochs
        - tail(300) pour AE
        - liste de symboles réduite (gérée dans mlops_market)
    """
    period = "1y"
    interval = "1d"

    data_map = fetch_market_data(fetch_func, symbols, interval=interval, period=period)
    results: Dict[str, Any] = {}
    ts = datetime.utcnow().isoformat()
    MLFLOW_STORE = os.getenv("MLFLOW_STORE", "sqlite:///mlruns.db")
    mlflow.set_tracking_uri(MLFLOW_STORE)
    mlflow.set_experiment("StormCopilot_Market_MLOps")
        # --- Hyperparamètres choisis pour l'expérience ---
    n_clusters = 3                     # ou le nombre que tu utilises dans train_kmeans
    ae_epochs = 5 if quick else 20     # cohérent avec QuickTrain vs FullTrain
    ae_hidden_dim = 8                  # ou ta dimension latente actuelle
    interval = "1d"
    period = period                    # tu l'as déjà dans ta fonction

    
    with mlflow.start_run(run_name=f"market_retrain_{ts}") as run:
        # 🔹 Hyperparamètres principaux
        mlflow.log_param("symbols", ",".join(symbols))
        mlflow.log_param("quick_mode", str(quick))   # stocké en string
        mlflow.log_param("period", period)
        mlflow.log_param("interval", interval)
        mlflow.log_param("n_clusters", n_clusters)
        mlflow.log_param("ae_epochs", ae_epochs)
        mlflow.log_param("ae_hidden_dim", ae_hidden_dim)

        # 🔹 Tags pour filtrer les runs dans MLflow UI
        mlflow.set_tags(
            {
                "app": "StormCopilot",
                "component": "Market_MLOps",
                "mode": "quick" if quick else "full",
                "author": "Ala BEN LAKHAL",
            }
        )

        for sym, df in data_map.items():
            if df.empty:
                continue

            safe_sym = _sanitize_name(sym)

            # -----------------------------
            # 1) KMeans regimes
            # -----------------------------
            km, scaler, sil = train_kmeans(df)
            mlflow.log_metric(f"{safe_sym}_silhouette", sil)

            # NOTE :
            # On NE loggue PAS les modèles dans MLflow (log_model),
            # pour éviter les problèmes de mlflow-artifacts + tracking URI HTTP.
            # Pour ton PFE, les métriques + run_id suffisent largement.

            # -----------------------------
            # 2) AutoEncoder anomalies
            # -----------------------------
            scores, recon_mean, msg = train_autoencoder(df, quick=quick)
            if recon_mean is not None:
                mlflow.log_metric(f"{safe_sym}_ae_recon", recon_mean)

            results[sym] = {
                "silhouette": sil,
                "ae_reconstruction": recon_mean,
                "autoencoder_msg": msg,
            }

        return {
            "run_id": run.info.run_id,
            "timestamp": ts,
            "results": results,
        }
