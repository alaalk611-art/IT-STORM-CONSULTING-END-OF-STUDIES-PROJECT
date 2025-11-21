# scripts/reindex_itstorm_raw.py

import sys, os
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from pathlib import Path
from src.rag_brain import reindex_txt_file

RAW_DIR = Path("data/raw")

def main():
    txt_files = sorted(RAW_DIR.glob("*.txt"))

    print(f"[RAG] Réindexation des .txt dans {RAW_DIR} …")
    for p in txt_files:
        print(f"\n=== {p.name} ===")
        try:
            report = reindex_txt_file(str(p))
            print(report)
        except Exception as e:
            print(f"[ERR] {p}: {e}")

if __name__ == "__main__":
    main()
