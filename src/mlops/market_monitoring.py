# src/mlops/market_monitoring.py
from __future__ import annotations
import pandas as pd
import numpy as np
from datetime import datetime
from pathlib import Path
from typing import Dict, Any
from src.ui.sections.market import _compute_indicators, _rolling_zscore_anomalies

METRICS_DIR = Path("mlops_metrics")
METRICS_DIR.mkdir(exist_ok=True)


def compute_daily_metrics(fetch_func, symbols) -> Dict[str, Any]:
    rows = []
    for sym in symbols:
        js = fetch_func(sym, interval="1d", period="1y")
        if not js or "candles" not in js:
            continue

        df = pd.DataFrame(js["candles"])
        df = _compute_indicators(df, "1d")

        last = df.iloc[-1]
        z_mask = _rolling_zscore_anomalies(df)
        drift = float(z_mask.tail(60).mean())

        rows.append({
            "symbol": sym,
            "price": float(last["close"]),
            "vol20": float(last["vol20"]) if not pd.isna(last["vol20"]) else None,
            "rsi14": float(last["rsi14"]) if not pd.isna(last["rsi14"]) else None,
            "drift_score": drift,
        })

    out = pd.DataFrame(rows)
    ts = datetime.utcnow().strftime("%Y-%m-%d")

    out_path = METRICS_DIR / f"daily_{ts}.csv"
    out.to_csv(out_path, index=False)

    return {
        "timestamp": ts,
        "metrics": rows,
    }
