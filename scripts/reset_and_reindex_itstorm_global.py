# -*- coding: utf-8 -*-
"""
reset_and_reindex_itstorm_global.py
-----------------------------------
Vider la base Chroma, puis réindexer :
1) itstorm_rag_global.jsonl (source principale, propre)
2) it_storm_1000_qa.txt     (source secondaire, faible poids)

Usage :
    python -m scripts.reset_and_reindex_itstorm_global
"""

import json
from pathlib import Path
from chromadb import Client
from chromadb.config import Settings
from tqdm import tqdm

# ---------------------------------------------------------
# 📌 Configuration
# ---------------------------------------------------------
APP_ROOT = Path(__file__).resolve().parents[1]
DATA_DIR = APP_ROOT / "data" / "raw"

DB_DIR = APP_ROOT / "data" / "vectors"
DB_DIR.mkdir(parents=True, exist_ok=True)

JSONL_MAIN = DATA_DIR / "itstorm_rag_global.jsonl"
QA_FILE = DATA_DIR / "it_storm_1000_qa.txt"

COLLECTION_NAME = "itstorm_rag"

# ---------------------------------------------------------
# 📌 Connexion à Chroma
# ---------------------------------------------------------
client = Client(
    Settings(
        chroma_db_impl="duckdb+parquet",
        persist_directory=str(DB_DIR)
    )
)

# ---------------------------------------------------------
# 🔥 1. Purge complète
# ---------------------------------------------------------
def purge_chroma():
    print("🧹 Suppression complète de la collection…")
    try:
        client.delete_collection(COLLECTION_NAME)
    except Exception:
        pass

    try:
        client.create_collection(COLLECTION_NAME)
        print("   -> Nouvelle collection créée.")
    except Exception as e:
        print("⚠️ Erreur création collection :", e)

# ---------------------------------------------------------
# 📌 2. Indexation JSONL principal
# ---------------------------------------------------------
def index_main_jsonl(collection):
    print(f"\n📥 Indexation de : {JSONL_MAIN.name}")

    with JSONL_MAIN.open("r", encoding="utf-8") as f:
        lines = f.readlines()

    for i, line in enumerate(tqdm(lines)):
        data = json.loads(line)
        text = data["text"]
        source = data.get("source", "itstorm_rag_global.txt")

        collection.add(
            ids=[f"global_{i}"],
            documents=[text],
            metadatas=[{"source": source}]
        )

    print(f"   -> {len(lines)} chunks ajoutés.")

# ---------------------------------------------------------
# 📌 3. Indexation du fichier QA (faible poids)
# ---------------------------------------------------------
def index_qa_file(collection):
    print(f"\n📥 Indexation de : {QA_FILE.name}")

    if not QA_FILE.exists():
        print("⚠️ Fichier QA introuvable. Ignoré.")
        return

    with QA_FILE.open("r", encoding="utf-8") as f:
        lines = [l.strip() for l in f.readlines() if l.strip()]

    for i, line in enumerate(tqdm(lines)):
        collection.add(
            ids=[f"qa_{i}"],
            documents=[line],
            metadatas=[{"source": "it_storm_1000_qa.txt"}]
        )

    print(f"   -> {len(lines)} lignes QA indexées.")

# ---------------------------------------------------------
# 📌 4. Vérification des sources
# ---------------------------------------------------------
def list_sources(collection):
    all_meta = collection.get(include=["metadatas"])
    sources = set()

    for m in all_meta["metadatas"]:
        if m and "source" in m:
            sources.add(m["source"])

    print("\n🔎 Sources présentes dans Chroma :")
    for s in sorted(sources):
        print("   -", s)


# ---------------------------------------------------------
# 🚀 MAIN
# ---------------------------------------------------------
def main():
    print("🚀 Reset & Reindex IT-STORM RAG GLOBAL\n")

    purge_chroma()

    col = client.get_collection(COLLECTION_NAME)

    # Indexation principale
    index_main_jsonl(col)

    # Indexation QA
    index_qa_file(col)

    # Vérification
    list_sources(col)

    print("\n✅ Réindexation terminée avec succès.")

    client.persist()


if __name__ == "__main__":
    main()
