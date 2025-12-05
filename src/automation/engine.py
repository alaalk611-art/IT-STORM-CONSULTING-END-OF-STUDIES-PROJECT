# -*- coding: utf-8 -*-
# Path: src/automation/engine.py

from __future__ import annotations

from typing import Dict, Any, List
from datetime import datetime
import os
import requests

from src.automation.storage import load_workflows, save_workflows
from src.automation.logs import append_log
# ============================================================
# CONFIG BACKEND
# ============================================================

BACKEND_BASE = (
    os.getenv("BACKEND_API_BASE_URL")
    or os.getenv("MARKET_API_BASE_URL")
    or "http://127.0.0.1:8001"
).rstrip("/")

DEFAULT_MARKET_SYMBOLS = ["^FCHI", "BNP.PA", "AIR.PA", "MC.PA", "OR.PA", "ORA.PA"]


# ============================================================
# ACTIONS — APPELS RÉELS
# ============================================================

def action_refresh_tech_watch(params: Dict[str, Any]) -> Dict[str, Any]:
    """
    Rafraîchir la veille techno via le backend FastAPI.
    POST /tech/watch/refresh
    """
    url = f"{BACKEND_BASE}/tech/watch/refresh"
    timeout = int(params.get("timeout", 90))

    try:
        r = requests.post(url, timeout=timeout)
        r.raise_for_status()
        data = r.json()
        return {
            "status": "ok",
            "message": "Tech Watch rafraîchie via backend.",
            "backend_status": data.get("status"),
            "nb_ok": data.get("nb_ok"),
            "nb_err": data.get("nb_err"),
            "total": data.get("total"),
            "truncated": data.get("truncated"),
        }
    except Exception as e:
        return {
            "status": "error",
            "message": "Échec du rafraîchissement Tech Watch.",
            "error": str(e),
            "backend_url": url,
        }


def action_refresh_market(params: Dict[str, Any]) -> Dict[str, Any]:
    """
    Rafraîchir les données de marché pour une liste de symboles.
    GET /v1/ohlcv/{symbol}
    """
    symbols = params.get("symbols") or DEFAULT_MARKET_SYMBOLS
    if isinstance(symbols, str):
        symbols = [s.strip() for s in symbols.split(",") if s.strip()]

    interval = params.get("interval", "1d")
    period = params.get("period", "1y")
    timeout = int(params.get("timeout", 30))

    results: List[Dict[str, Any]] = []
    nb_ok, nb_err = 0, 0

    for sym in symbols:
        url = f"{BACKEND_BASE}/v1/ohlcv/{sym}"
        try:
            r = requests.get(
                url,
                params={"interval": interval, "period": period},
                timeout=timeout,
            )
            r.raise_for_status()
            data = r.json()
            candles = data.get("candles") or data.get("bars") or []
            results.append(
                {
                    "symbol": sym,
                    "status": "ok",
                    "nb_candles": len(candles),
                    "interval": interval,
                    "period": period,
                    "source": data.get("source", "backend"),
                }
            )
            nb_ok += 1
        except Exception as e:
            results.append(
                {
                    "symbol": sym,
                    "status": "error",
                    "error": str(e),
                    "interval": interval,
                    "period": period,
                }
            )
            nb_err += 1

    if nb_ok > 0 and nb_err == 0:
        status = "ok"
    elif nb_ok > 0:
        status = "partial"
    else:
        status = "error"

    return {
        "status": status,
        "message": f"{nb_ok} symbole(s) rafraîchi(s), {nb_err} en erreur.",
        "backend_base": BACKEND_BASE,
        "interval": interval,
        "period": period,
        "symbols": symbols,
        "results": results,
    }


def action_generate_rag_summary(params: Dict[str, Any]) -> Dict[str, Any]:
    """
    Générer un résumé RAG (placeholder pour l’instant).
    """
    target = params.get("target", "generic")
    return {
        "status": "todo",
        "message": f"Résumé RAG pour la cible '{target}' non encore branché.",
        "target": target,
    }


# ============================================================
# REGISTRY DES ACTIONS
# ============================================================

ACTION_REGISTRY = {
    "refresh_tech_watch": action_refresh_tech_watch,
    "refresh_market": action_refresh_market,
    "generate_rag_summary": action_generate_rag_summary,
}


# ============================================================
# EXÉCUTION D'UNE ÉTAPE / D'UN WORKFLOW
# ============================================================

def run_step(step: Dict[str, Any]) -> Dict[str, Any]:
    step_type = step.get("type")
    params = step.get("params") or {}

    if step_type not in ACTION_REGISTRY:
        raise ValueError(f"Action inconnue: {step_type}")

    func = ACTION_REGISTRY[step_type]
    result = func(params)

    return {
        "step_type": step_type,
        "params": params,
        "result": result,
        "timestamp": datetime.utcnow().isoformat() + "Z",
    }


def run_workflow(workflow: Dict[str, Any]) -> Dict[str, Any]:
    """
    Exécute un workflow complet (séquence de steps) et loggue le résultat.
    """
    name = workflow.get("name", "Unnamed Workflow")
    steps: List[Dict[str, Any]] = workflow.get("steps", []) or []

    logs: List[Dict[str, Any]] = []

    for idx, step in enumerate(steps):
        try:
            # exécute une step (refresh_tech_watch, refresh_market, etc.)
            step_log = run_step(step)
            step_log["index"] = idx
            logs.append(step_log)
        except Exception as e:
            # on capture l’erreur dans les logs, mais on continue le workflow
            logs.append(
                {
                    "index": idx,
                    "step_type": step.get("type"),
                    "error": str(e),
                    "timestamp": datetime.utcnow().isoformat() + "Z",
                }
            )

    # objet global d’exécution
    execution_result: Dict[str, Any] = {
        "workflow_name": name,
        "executed_at": datetime.utcnow().isoformat() + "Z",
        "logs": logs,
    }

    # 🔴 partie CRITIQUE : on pousse ça dans automation_logs.jsonl
    append_log(execution_result)

    return execution_result

# ============================================================
# LISTE & SAUVEGARDE DES WORKFLOWS
# ============================================================

def get_all_workflows() -> List[Dict[str, Any]]:
    return load_workflows()


def save_all_workflows(workflows: List[Dict[str, Any]]) -> None:
    save_workflows(workflows)
