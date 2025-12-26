import os
import json
import uuid
from pathlib import Path
from collections import defaultdict

def _repair_vertical_tab_path(s: str) -> str:
    # corrige le caractère invisible "\x0b" (vertical tab) causé par "\v"
    return (s or "").replace("\x0b", r"\v")

def main():
    # Fix ENV avant import rag_brain
    os.environ["CHROMA_DB_DIR"] = _repair_vertical_tab_path(os.getenv("CHROMA_DB_DIR", ""))

    from src import rag_brain

    repo = Path(__file__).resolve().parents[2]
    chunks_path = repo / "data" / "processed" / "chunks.jsonl"
    if not chunks_path.exists():
        print(json.dumps({"ok": False, "error": "chunks.jsonl introuvable"}, ensure_ascii=False))
        return 2

    eng = rag_brain.get_engine()

    by_source = defaultdict(list)
    chunks_total = 0

    with open(chunks_path, "r", encoding="utf-8") as f:
        for line in f:
            line = (line or "").strip()
            if not line:
                continue
            chunks_total += 1
            try:
                row = json.loads(line)
            except Exception:
                continue

            src = (row.get("source") or "unknown").strip()
            txt = (row.get("text") or "").strip()
            if not txt:
                continue

            by_source[Path(src).name].append(txt)

    sources_purged = 0
    chunks_indexed = 0

    for src_base, chunks in by_source.items():
        try:
            eng.col.delete(where={"source": src_base})
            sources_purged += 1
        except Exception:
            pass

        ids = [f"{src_base}::{uuid.uuid4().hex}" for _ in chunks]
        metas = [{"source": src_base, "id": ids[i]} for i in range(len(ids))]

        eng.col.add(ids=ids, documents=chunks, metadatas=metas)
        chunks_indexed += len(chunks)

    print(json.dumps({
        "ok": True,
        "docs_seen": len(by_source),
        "chunks_total": chunks_total,
        "chunks_indexed": chunks_indexed,
        "sources_purged": sources_purged,
    }, ensure_ascii=False))

    return 0

if __name__ == "__main__":
    raise SystemExit(main())
