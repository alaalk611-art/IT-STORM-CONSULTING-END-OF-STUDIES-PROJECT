# tools/reindex_qa.py
import os, re, uuid
import chromadb
from chromadb.config import Settings
from chromadb.utils import embedding_functions

# --- CONFIG (doit matcher ton app) ---
DB_PATH = os.getenv("VECTOR_DB_PATH", r"C:\Users\ALA BEN LAKHAL\Desktop\intelligent_copilot IT-STORM\vectors")
COLL    = os.getenv("VECTOR_COLLECTION", "consulting")
MODEL   = os.getenv("EMBED_MODEL", "all-MiniLM-L6-v2")

QA_PATH = r"C:\Users\ALA BEN LAKHAL\Desktop\intelligent_copilot IT-STORM\data\it_storm_1000_QA.txt"
BASENAME = "it_storm_1000_QA.txt"  # IMPORTANT: basename EXACT (en minuscules conseillé)

# --- helpers chunking ---
def split_chunks(txt: str, max_tokens=500, sep=r"\n{2,}"):
    parts = re.split(sep, txt)
    out = []
    buf = []
    count = 0
    for p in parts:
        p = p.strip()
        if not p: 
            continue
        n = len(p.split())
        if count + n > max_tokens and buf:
            out.append("\n".join(buf))
            buf, count = [p], n
        else:
            buf.append(p); count += n
    if buf:
        out.append("\n".join(buf))
    return [c for c in out if c.strip()]

def main():
    if not os.path.exists(QA_PATH):
        raise FileNotFoundError(QA_PATH)
    with open(QA_PATH, "r", encoding="utf-8", errors="ignore") as f:
        text = f.read()

    chunks = split_chunks(text, max_tokens=220)  # petits chunks = meilleures citations
    print(f"[QA] {len(chunks)} chunks à indexer depuis {QA_PATH}")

    client = chromadb.PersistentClient(path=DB_PATH, settings=Settings(anonymized_telemetry=False))
    emb = embedding_functions.SentenceTransformerEmbeddingFunction(model_name=MODEL)
    col = client.get_or_create_collection(name=COLL, embedding_function=emb)

    # 1) purger les anciens éléments de cette source (si ton Chroma supporte delete_where)
    try:
        col.delete(where={"source": {"$eq": BASENAME}})
        print("[QA] Purge ancienne source OK")
    except Exception as e:
        print("[QA] Purge ignorée (version Chroma) :", e)

    # 2) ajouter
    ids = [f"qa::{uuid.uuid4().hex}" for _ in chunks]
    metas = [{"source": BASENAME, "id": ids[i]} for i in range(len(ids))]
    col.add(ids=ids, documents=chunks, metadatas=metas)
    print("[QA] Ajout terminé")

    # 3) sanity
    q = "IT STORM cloud data devops RAG"
    res = col.query(query_texts=[q], n_results=5, include=["metadatas"])
    print("[QA] top sources:", sorted({ (m.get("source") or "").lower() for m in res.get("metadatas", [[]])[0] }))

if __name__ == "__main__":
    main()
