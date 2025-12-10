# -*- coding: utf-8 -*-
# Path: src/automation/storage.py

from __future__ import annotations
from pathlib import Path
from typing import List, Dict, Any
import json
import os

WORKFLOW_FILE = Path("data/automation_workflows.json")


def _default_workflows() -> List[Dict[str, Any]]:
    """
    Workflows par défaut alignés avec n8n & Streamlit :
    - Tech Radar (n8n)
    - Market Radar (n8n)  [1d / 1y]
    - Daily Full · Tech + Market (via n8n)
    """
    n8n_base = os.getenv("N8N_BASE_URL", "http://127.0.0.1:5678").rstrip("/")

    return [
        {
            "name": "Tech Radar (n8n)",
            "trigger": "manual",
            "steps": [
                {
                    "type": "n8n_webhook",
                    "params": {
                        "url": f"{n8n_base}/webhook/tech-radar",
                        "timeout": 120,
                        "payload": {"scope": "tech_only", "timeout": 90},
                    },
                }
            ],
        },
        {
            "name": "Market Radar (n8n)",
            "trigger": "manual",
            "steps": [
                {
                    "type": "n8n_webhook",
                    "params": {
                        "url": f"{n8n_base}/webhook/market-radar",
                        "timeout": 120,
                        "payload": {
                            "symbols": "^FCHI,BNP.PA,AIR.PA,MC.PA,OR.PA,ORA.PA",
                            "interval": "1d",
                            "period": "1y",
                        },
                    },
                }
            ],
        },
        {
            "name": "Daily Full · Tech + Market (via n8n)",
            "trigger": "manual",
            "steps": [
                {
                    "type": "n8n_webhook",
                    "params": {
                        "url": f"{n8n_base}/webhook/daily-full",
                        "timeout": 160,
                        "payload": {},
                    },
                }
            ],
        },
    ]


def load_workflows() -> List[Dict[str, Any]]:
    """
    Charge la liste des workflows depuis le fichier JSON.
    Si le fichier n'existe pas, on l'initialise avec les 3 workflows par défaut.
    """
    if not WORKFLOW_FILE.exists():
        workflows = _default_workflows()
        try:
            WORKFLOW_FILE.parent.mkdir(parents=True, exist_ok=True)
            WORKFLOW_FILE.write_text(
                json.dumps(workflows, ensure_ascii=False, indent=2),
                encoding="utf-8",
            )
        except Exception as e:
            print(f"[AutomationStorage] Erreur d'initialisation: {e}")
        return workflows

    try:
        raw = WORKFLOW_FILE.read_text(encoding="utf-8")
        data = json.loads(raw)
        if isinstance(data, list):
            return data
        return []
    except Exception as e:
        print(f"[AutomationStorage] Erreur de lecture: {e}")
        return []


def save_workflows(workflows: List[Dict[str, Any]]) -> None:
    """
    Sauvegarde la liste des workflows dans le fichier JSON.
    Crée le dossier data/ si nécessaire.
    """
    try:
        WORKFLOW_FILE.parent.mkdir(parents=True, exist_ok=True)
        WORKFLOW_FILE.write_text(
            json.dumps(workflows, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )
    except Exception as e:
        print(f"[AutomationStorage] Erreur d'écriture: {e}")
