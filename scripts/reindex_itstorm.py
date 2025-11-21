# scripts/reindex_itstorm.py
# -*- coding: utf-8 -*-

import os
import sys

# --- Ajouter la racine du projet au PYTHONPATH -------------------------------
# Chemin actuel : ...\intelligent_copilot IT-STORM\scripts\reindex_itstorm.py
# Racine projet : ...\intelligent_copilot IT-STORM
ROOT_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if ROOT_DIR not in sys.path:
    sys.path.insert(0, ROOT_DIR)

from src.rag_brain import reindex_txt_file, debug_list_sources

BASE_DIR = r"C:\Users\ALA BEN LAKHAL\Desktop\intelligent_copilot IT-STORM\data\raw"

FILES = [
    "itstorm_site.txt",         # 🆕 site officiel
    "itstorm_rag_global.txt",   # 🔥 interne global
    "itstorm_clean.txt",        # fallback clean
    "it_storm_1000_QA.txt",     # QA basse priorité
]



def main():
    print("=== Réindexation IT-STORM RAG ===")
    for name in FILES:
        path = os.path.join(BASE_DIR, name)
        print(f"\n--> Réindexation de : {path}")
        if not os.path.exists(path):
            print(f"   ⚠ FICHIER INTROUVABLE : {path}")
            continue
        res = reindex_txt_file(filepath=path, source_basename=name, max_words=220)
        print("   Résultat :", res)

    print("\n=== Sources visibles côté Chroma (debug_list_sources) ===")
    try:
        sources = debug_list_sources(50)
        print(sources)
    except Exception as e:
        print("⚠ Erreur debug_list_sources :", e)


if __name__ == "__main__":
    main()
