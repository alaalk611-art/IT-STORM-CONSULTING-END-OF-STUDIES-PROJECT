# -*- coding: utf-8 -*-
"""
Script: extract_itstorm_questions_only.py
But :
  - Lire data/raw/it_storm_1000_QA.txt
  - Garder uniquement les lignes de questions ("Q: ...")
  - Écrire un fichier data/raw/it_storm_1000_Q_ONLY.txt
Usage :
  (.venv) python scripts/extract_itstorm_questions_only.py
"""

from __future__ import annotations

import os
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent

SRC = ROOT / "data" / "raw" / "it_storm_1000_QA.txt"
DST = ROOT / "data" / "raw" / "it_storm_1000_Q_ONLY.txt"


def main() -> None:
    if not SRC.exists():
        raise SystemExit(f"[ERR] Fichier source introuvable : {SRC}")

    questions = []

    with SRC.open("r", encoding="utf-8") as f:
        for line in f:
            s = line.strip()
            if not s:
                continue
            # On garde uniquement les lignes qui commencent par "Q:"
            if s.startswith("Q:"):
                # soit tu gardes le "Q: ..." complet :
                questions.append(s)
                # soit tu enlèves le "Q:" :
                # questions.append(s[2:].strip())

    if not questions:
        raise SystemExit("[ERR] Aucune question 'Q:' trouvée dans le fichier source.")

    DST.parent.mkdir(parents=True, exist_ok=True)
    with DST.open("w", encoding="utf-8") as out:
        for q in questions:
            out.write(q + "\n")

    print(f"[✓] {len(questions)} questions extraites.")
    print(f"[✓] Fichier écrit : {DST}")


if __name__ == "__main__":
    main()
