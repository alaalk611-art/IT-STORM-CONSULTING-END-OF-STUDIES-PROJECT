# -*- coding: utf-8 -*-
"""
tools/qa_cli_pretty.py

Petit moteur FAQ offline pour IRIS :
- Lit data/train.txt
- Format attendu :

    ---
    Q: ....
    A: ....
    ---

- Fournit : answer_from_cli_backend(question: str) -> str
- Aucun modèle HF, aucun RAG.
"""

from __future__ import annotations

import re
from functools import lru_cache
from pathlib import Path
from typing import Dict


# ------------------------------------------------------------------
# PATH DU FICHIER train.txt
# ------------------------------------------------------------------
# Chemin absolu (ton projet)
TRAIN_PATH = Path(
    r"C:\Users\ALA BEN LAKHAL\Desktop\intelligent_copilot IT-STORM\data\train.txt"
)

# Fallback relatif si tu déplaces le projet
if not TRAIN_PATH.exists():
    rel = Path(__file__).resolve().parents[1] / "data" / "train.txt"
    if rel.exists():
        TRAIN_PATH = rel


# ------------------------------------------------------------------
# Normalisation de texte (comme dans main.py)
# ------------------------------------------------------------------
def _normalize(s: str) -> str:
    if not s:
        return ""
    s = s.replace("’", "'")
    s = s.strip().lower()
    s = re.sub(r"\s+", " ", s)
    s = re.sub(r"[?!.]+$", "", s)
    return s


# ------------------------------------------------------------------
# Chargement et parsing de train.txt
# ------------------------------------------------------------------
@lru_cache(maxsize=1)
def _load_qa() -> Dict[str, str]:
    """
    Retourne un dict :
        { normalized_question -> answer }
    basé sur data/train.txt
    """
    if not TRAIN_PATH.exists():
        raise FileNotFoundError(f"train.txt introuvable : {TRAIN_PATH}")

    raw = TRAIN_PATH.read_text(encoding="utf-8", errors="ignore")

    # Séparation sur les blocs "---"
    blocks = re.split(r"\n-{3,}\s*\n", raw)
    qa_map: Dict[str, str] = {}

    for block in blocks:
        block = block.strip()
        if not block:
            continue

        # Chercher Q: et A:
        m_q = re.search(r"^Q:\s*(.+)", block, flags=re.MULTILINE)
        m_a = re.search(r"^A:\s*(.+)", block, flags=re.MULTILINE | re.DOTALL)

        if not m_q or not m_a:
            continue

        q = m_q.group(1).strip()
        a = m_a.group(1).strip()

        nq = _normalize(q)
        if nq and nq not in qa_map:
            qa_map[nq] = a

    return qa_map


# ------------------------------------------------------------------
# Matching souple : exact -> inclusion -> overlap de tokens
# ------------------------------------------------------------------
def _best_answer(query: str) -> str:
    qa_map = _load_qa()
    nq = _normalize(query)

    if not nq:
        return "Je ne sais pas."

    # 1) Match exact sur la question normalisée
    if nq in qa_map:
        return qa_map[nq]

    # 2) Inclusion (la question utilisateur inclut une Q de train.txt ou inversement)
    for q_norm, ans in qa_map.items():
        if nq in q_norm or q_norm in nq:
            return ans

    # 3) Overlap de tokens (approche simple mais robuste)
    tokens = set(nq.split())
    best_score = 0.0
    best_ans = None

    for q_norm, ans in qa_map.items():
        q_tokens = set(q_norm.split())
        inter = len(tokens & q_tokens)
        if not inter:
            continue

        score = inter / max(len(tokens), len(q_tokens))
        if score > best_score:
            best_score = score
            best_ans = ans

    if best_ans and best_score >= 0.5:
        return best_ans

    return "Je ne sais pas."


# ------------------------------------------------------------------
# API appelée par main.py
# ------------------------------------------------------------------
def answer_from_cli_backend(question: str) -> str:
    """
    Fonction utilisée par /chat dans main.py
    On se contente de chercher la meilleure réponse dans train.txt
    """
    try:
        return _best_answer(question)
    except Exception as e:
        # On garde un message propre (sans stacktrace)
        return f"Je ne sais pas. (erreur backend FAQ: {e})"


if __name__ == "__main__":
    # Petit test rapide en local
    for qtest in [
        "Quels services IA IT Storm propose-t-elle (POC et intégrations IA) ?",
        "Quels services IA propose IT Storm ?",
        "Quelle est la spécialité principale d’IT Storm ?",
    ]:
        print("Q:", qtest)
        print("A:", answer_from_cli_backend(qtest))
        print("---")
