# src/ingestion/pipeline.py
import os
from pathlib import Path

from chromadb import PersistentClient
from langchain_chroma import Chroma
from langchain_huggingface import HuggingFaceEmbeddings

from src.config.settings import PROC_DIR, RAW_DIR
from src.ingestion.chunking import chunk_words
from src.ingestion.extract_text import extract_any
from src.utils.io import write_jsonl

RAG_DB = Path(os.getenv("RAG_DB", "data/chroma-consulting"))
COLLECTION = os.getenv("COLLECTION_NAME", "itstorm_docs")
EMB_MODEL = os.getenv("EMBEDDING_MODEL", "sentence-transformers/all-MiniLM-L6-v2")


def run(in_dir=RAW_DIR, out_path=PROC_DIR / "chunks.jsonl"):
    records = []
    for p in Path(in_dir).glob("*"):
        text = extract_any(p)
        if not text:
            continue
        for i, ch in enumerate(chunk_words(text)):
            records.append({"id": f"{p.name}:{i}", "source": str(p), "text": ch})

    write_jsonl(records, out_path)
    print(f"💾 Saved {len(records)} chunks -> {out_path}")

    if not records:
        print("⚠️ Aucun document à indexer.")
        return

    embeddings = HuggingFaceEmbeddings(model_name=EMB_MODEL)

    # IMPORTANT: client persistant + pas de .persist() à appeler
    client = PersistentClient(path=str(RAG_DB))
    db = Chroma(
        client=client,
        collection_name=COLLECTION,
        embedding_function=embeddings,
    )

    # reset soft de la collection
    try:
        db._collection.delete(where={})
    except Exception:
        pass

    db.add_texts(
        texts=[r["text"] for r in records],
        metadatas=[{"source": r["source"], "id": r["id"]} for r in records],
        ids=[r["id"] for r in records],
    )

    # Rien à appeler comme persist ici : le PersistentClient gère le stockage
    print(
        f"✅ Ingestion terminée. Fichiers: {len(list(Path(in_dir).glob('*')))}, Chunks: {len(records)}"
    )


if __name__ == "__main__":
    run()
