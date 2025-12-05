# -*- coding: utf-8 -*-
# Path: src/automation/logs.py

from __future__ import annotations

from pathlib import Path
from typing import Dict, Any, List
from datetime import datetime
import json

# ============================================================
# BASE DIR du projet (racine) + chemin absolu vers /data
# ============================================================

# __file__ = src/automation/logs.py
# parents[0] = automation, parents[1] = src, parents[2] = racine du projet
BASE_DIR = Path(__file__).resolve().parents[2]
DATA_DIR = BASE_DIR / "data"
LOG_PATH = DATA_DIR / "automation_logs.jsonl"


def _ensure_data_dir() -> None:
    """
    Crée le dossier data/ et le fichier de logs s'ils n'existent pas.
    """
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    if not LOG_PATH.exists():
        LOG_PATH.touch()


def append_log(entry: Dict[str, Any]) -> None:
    """
    Ajoute une exécution de workflow dans le fichier JSONL.
    1 ligne = 1 run de workflow.
    """
    _ensure_data_dir()

    # copie pour ne pas modifier l'objet passé
    record = dict(entry)
    if "logged_at" not in record:
        record["logged_at"] = datetime.utcnow().isoformat() + "Z"

    try:
        print(f"[AutomationLogs] append_log -> {LOG_PATH}")
        with LOG_PATH.open("a", encoding="utf-8") as f:
            json.dump(record, f, ensure_ascii=False)
            f.write("\n")
    except Exception as e:
        # important pour diagnostiquer si jamais ça plante en écriture
        print(f"[AutomationLogs] ERREUR append_log: {e}")


def load_logs(limit: int = 50) -> List[Dict[str, Any]]:
    """
    Charge les logs les plus récents (par défaut 50).
    Retourne une liste triée du plus récent au plus ancien.
    """
    _ensure_data_dir()
    if not LOG_PATH.exists():
        print(f"[AutomationLogs] load_logs -> fichier inexistant: {LOG_PATH}")
        return []

    logs: List[Dict[str, Any]] = []
    try:
        with LOG_PATH.open("r", encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if not line:
                    continue
                try:
                    logs.append(json.loads(line))
                except Exception:
                    # on ignore les lignes corrompues
                    continue
    except Exception as e:
        print(f"[AutomationLogs] ERREUR load_logs: {e}")
        return []

    # tri du plus récent au plus ancien
    logs.sort(
        key=lambda x: x.get("executed_at") or x.get("logged_at") or "",
        reverse=True,
    )

    if limit is not None and limit > 0:
        return logs[:limit]
    return logs


def load_logs_for_workflow(name: str, limit: int = 50) -> List[Dict[str, Any]]:
    """
    Charge les logs pour UN workflow donné.
    """
    all_logs = load_logs(limit=None)
    filtered = [log for log in all_logs if log.get("workflow_name") == name]

    filtered.sort(
        key=lambda x: x.get("executed_at") or x.get("logged_at") or "",
        reverse=True,
    )

    if limit is not None and limit > 0:
        return filtered[:limit]
    return filtered
