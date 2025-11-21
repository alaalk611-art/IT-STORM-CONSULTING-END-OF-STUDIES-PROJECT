# -*- coding: utf-8 -*-
"""
Script: index_itstorm_for_iris.py
But :
  - Indexer data/raw/itstorm.txt dans Chroma via rag_brain.py
  - Ces données seront ensuite utilisées par IRIS (endpoint /chat)
Usage :
  (.venv) python scripts/index_itstorm_for_iris.py
"""

from __future__ import annotations

import os
import sys

# -------------------------------------------------------------------
# 1) S'assurer que la racine du projet est dans sys.path
#    (le script est dans .../scripts/, on remonte d'un dossier)
# -------------------------------------------------------------------
ROOT_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if ROOT_DIR not in sys.path:
    sys.path.insert(0, ROOT_DIR)

# Maintenant on peut importer src.rag_brain proprement
from src.rag_brain import reindex_txt_file, debug_has_file, debug_list_sources

ITSTORM_PATH = "data/raw/itstorm.txt"
ITSTORM_SOURCE = "itstorm.txt"   # nom de source dans Chroma


def main() -> None:
    print(f"[i] Réindexation de {ITSTORM_PATH} avec source='{ITSTORM_SOURCE}'...")
    res = reindex_txt_file(
        filepath=ITSTORM_PATH,
        source_basename=ITSTORM_SOURCE,
        max_words=220,   # même logique que pour les autres .txt
    )
    print("\n[résultat reindex_txt_file]")
    print(res)

    print("\n[i] Vérification présence dans l'index :")
    present = debug_has_file(ITSTORM_SOURCE)
    print(f" - debug_has_file('{ITSTORM_SOURCE}') => {present}")

    print("\n[i] Aperçu des sources visibles (sample) :")
    for s in debug_list_sources(30):
        print("  ·", s)


if __name__ == "__main__":
    main()
