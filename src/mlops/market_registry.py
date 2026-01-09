# src/mlops/market_registry.py
import json
from pathlib import Path
from typing import Dict, Any

REGISTRY_PATH = Path("mlops_registry.json")


def load_registry() -> Dict[str, Any]:
    if REGISTRY_PATH.exists():
        return json.load(open(REGISTRY_PATH, "r", encoding="utf-8"))
    return {}


def save_registry(reg: Dict[str, Any]):
    json.dump(reg, open(REGISTRY_PATH, "w", encoding="utf-8"), indent=2)


def update_champion(symbol: str, metrics: dict, run_id: str):
    reg = load_registry()

    old = reg.get(symbol)
    # Robust scoring (handle None safely)
    sil = metrics.get("silhouette")
    sil = float(sil) if sil is not None else 0.0
 
    ae = metrics.get("ae_reconstruction")
    ae = float(ae) if ae is not None else 0.0
 
     # Higher silhouette is better, lower reconstruction error is better
    new_score = sil - ae

    if old:
        old_score = old["score"]
        if new_score <= old_score:
            return False  # Challenger worse than champion

    reg[symbol] = {
        "run_id": run_id,
        "metrics": metrics,
        "score": float(new_score),
    }

    save_registry(reg)
    return True


def get_champions() -> Dict[str, Any]:
    return load_registry()
