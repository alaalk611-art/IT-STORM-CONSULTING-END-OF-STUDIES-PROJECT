# src/api/routes/mlops_market.py
from __future__ import annotations
from typing import List, Optional

import os
import requests
from fastapi import APIRouter, Query

from src.mlops.market_experiments import run_market_experiment
from src.mlops.market_registry import update_champion, get_champions
from src.mlops.market_monitoring import compute_daily_metrics

API_BASE = os.getenv("BACKEND_API_BASE_URL", "http://127.0.0.1:8001").rstrip("/")

router = APIRouter(prefix="/mlops", tags=["MLOps"])


# -------------------------------------------------------------
# Fonction locale pour appeler ton endpoint OHLCV via HTTP
# -------------------------------------------------------------
def fetch_market_from_api(symbol: str, interval: str, period: str):
    url = f"{API_BASE}/v1/ohlcv/{symbol}"
    params = {"interval": interval, "period": period}
    resp = requests.get(url, params=params, timeout=10)
    resp.raise_for_status()
    return resp.json()


# -------------------------------------------------------------
# 1) TRAINING (KMeans + AutoEncoder) + MLflow + Registry
# -------------------------------------------------------------
@router.post("/train/market")
def train_market_models(
    symbols: Optional[List[str]] = Query(
        default=None,
        description="Liste de symboles. Laisse vide pour utiliser la liste par défaut."
    ),
    quick: bool = Query(
        default=False,
        description="Mode rapide (moins de données, moins d'epochs AE)."
    ),
):
    # Liste complète pour run 'complet'
    default_symbols_full = ["^FCHI", "BNP.PA", "AIR.PA", "MC.PA", "OR.PA", "ORA.PA"]
    # Liste réduite pour quick mode
    default_symbols_quick = ["^FCHI", "BNP.PA", "MC.PA"]

    if symbols is None:
        symbols = default_symbols_quick if quick else default_symbols_full

    res = run_market_experiment(fetch_market_from_api, symbols, quick=quick)

    # Update registry pour chaque symbole
    for sym, metrics in res["results"].items():
        update_champion(sym, metrics, res["run_id"])

    return res


# -------------------------------------------------------------
# 2) MONITORING QUOTIDIEN
# -------------------------------------------------------------
@router.post("/metrics/daily")
def compute_daily(symbols: Optional[List[str]] = Query(default=None)):
    default_symbols = ["^FCHI", "BNP.PA", "AIR.PA", "MC.PA", "OR.PA", "ORA.PA"]
    if symbols is None:
        symbols = default_symbols

    return compute_daily_metrics(fetch_market_from_api, symbols)


# -------------------------------------------------------------
# 3) LECTURE DES CHAMPIONS
# -------------------------------------------------------------
@router.get("/champions")
def get_all_champions():
    return get_champions()
