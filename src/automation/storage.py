# -*- coding: utf-8 -*-
# Path: src/automation/storage.py

from __future__ import annotations
from pathlib import Path
from typing import List, Dict, Any
import json

# TODO-1: Ajuster si besoin le chemin du fichier JSON
WORKFLOW_FILE = Path("data/automation_workflows.json")


def load_workflows() -> List[Dict[str, Any]]:
    """
    Charge la liste des workflows depuis le fichier JSON.
    Retourne une liste vide si le fichier n'existe pas ou est invalide.
    """
    if not WORKFLOW_FILE.exists():
        # TODO-2: Plus tard, tu peux initialiser ici quelques workflows "démo" par défaut.
        return []

    try:
        raw = WORKFLOW_FILE.read_text(encoding="utf-8")
        data = json.loads(raw)
        if isinstance(data, list):
            return data
        # TODO-3: Ajouter une vraie validation de schéma si besoin.
        return []
    except Exception as e:
        # TODO-4: Logger proprement l'erreur si tu ajoutes un système de logs.
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
        # TODO-5: Logger proprement l'erreur si tu ajoutes un système de logs.
        print(f"[AutomationStorage] Erreur d'écriture: {e}")
