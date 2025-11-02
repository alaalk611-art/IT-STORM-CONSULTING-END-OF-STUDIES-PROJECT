# src/rag/ingest.py
import json
import os
from pathlib import Path
from typing import Dict, List

from langchain_chroma import Chroma
from langchain_community.embeddings import HuggingFaceEmbeddings

from src.ingestion.chunking import chunk_words

DEF_RAW_DIR = Path("data/raw")
DEF_OUT_DIR = Path("data/processed")
DEF_OUT_FILE = DEF_OUT_DIR / "chunks.jsonl"

RAG_DB = Path(os.getenv("RAG_DB", "data/chroma-consulting"))
COLLECTION = os.getenv("COLLECTION_NAME", "itstorm_docs")
EMB_MODEL = os.getenv("EMBEDDING_MODEL", "sentence-transformers/all-MiniLM-L6-v2")


def run_ingest(
    raw_dir: Path | str = DEF_RAW_DIR,
    out_dir: Path | str = DEF_OUT_DIR,
    chunk_size: int = 200,
    overlap: int = 50,
) -> Dict[str, int]:
    """
    - Lit tous les .txt sous data/raw
    - Découpe en chunks
    - Écrit data/processed/chunks.jsonl
    - (NOUVEAU) Insère les chunks dans la base Chroma
    Retour: {"files": n, "chunks": m}
    """
    raw_dir = Path(raw_dir)
    out_dir = Path(out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)

    files = list(raw_dir.glob("*.txt"))
    chunks_count = 0

    records: List[dict] = []
    with open(DEF_OUT_FILE, "w", encoding="utf-8") as f:
        for fp in files:
            text = fp.read_text(encoding="utf-8", errors="ignore").strip()
            if not text:
                continue
            for i, ch in enumerate(
                chunk_words(text, chunk_size=chunk_size, overlap=overlap)
            ):
                rec = {"id": f"{fp.name}:{i}", "text": ch, "source": str(fp)}
                f.write(json.dumps(rec, ensure_ascii=False) + "\n")
                records.append(rec)
                chunks_count += 1

    # --- Alimentation Chroma ---
    embeddings = HuggingFaceEmbeddings(model_name=EMB_MODEL)
    db = Chroma(
        collection_name=COLLECTION,
        embedding_function=embeddings,
        persist_directory=str(RAG_DB),
    )

    # reset collection (sécurisé si Chroma récent)
    try:
        db._collection.delete(where={})
    except Exception:
        pass

    if records:
        db.add_texts(
            texts=[r["text"] for r in records],
            metadatas=[{"source": r["source"], "id": r["id"]} for r in records],
            ids=[r["id"] for r in records],
        )
        db.persist()

    return {"files": len(files), "chunks": chunks_count}


if __name__ == "__main__":
    info = run_ingest()
    print(f"✅ Ingestion terminée. Fichiers: {info['files']}, Chunks: {info['chunks']}")
