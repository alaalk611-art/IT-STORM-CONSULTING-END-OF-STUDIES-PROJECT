# src/rag/retriever.py
import json
from pathlib import Path
from typing import Any, Dict, List

import numpy as np

from .embeddings import embed_query, embed_texts


class NumpyRetriever:
    """
    Index mémoire avec embeddings L2-normalisés (cosine via dot).
    Cache:
      - data/processed/chunks.npy        (float32, shape: n,d)
      - data/processed/chunks_meta.jsonl (id, text, source)
    Reconstruit l'index si le cache est absent ou si chunks.jsonl est plus récent.
    """

    def __init__(
        self,
        chunks_jsonl: Path | str,
        emb_cache: Path | str,
        meta_cache: Path | str,
    ):
        self.chunks_path = Path(chunks_jsonl)
        self.emb_cache = Path(emb_cache)
        self.meta_cache = Path(meta_cache)
        self.meta: List[Dict[str, Any]] = []
        self.emb: np.ndarray | None = None
        self._load_or_build()

    def _cache_is_valid(self) -> bool:
        if not (self.emb_cache.exists() and self.meta_cache.exists()):
            return False
        try:
            return (
                self.emb_cache.stat().st_mtime >= self.chunks_path.stat().st_mtime
                and self.meta_cache.stat().st_mtime >= self.chunks_path.stat().st_mtime
            )
        except FileNotFoundError:
            return False

    def _load_or_build(self):
        if self._cache_is_valid():
            try:
                self.emb = np.load(self.emb_cache)
                with open(self.meta_cache, "r", encoding="utf-8") as f:
                    self.meta = [json.loads(l) for l in f if l.strip()]
                return
            except Exception:
                pass  # on reconstruit ci-dessous

        # (Re)construction depuis chunks.jsonl
        items: List[Dict[str, Any]] = []
        if self.chunks_path.exists():
            with open(self.chunks_path, "r", encoding="utf-8") as f:
                for line in f:
                    line = line.strip()
                    if not line:
                        continue
                    try:
                        items.append(json.loads(line))
                    except Exception:
                        pass
        texts = [it.get("text", "") for it in items]
        self.emb = embed_texts(texts) if texts else np.zeros((0, 384), dtype=np.float32)
        self.meta = [
            {"id": it.get("id"), "text": it.get("text"), "source": it.get("source")}
            for it in items
        ]

        # Sauvegarde cache
        self.emb_cache.parent.mkdir(parents=True, exist_ok=True)
        np.save(self.emb_cache, self.emb)
        with open(self.meta_cache, "w", encoding="utf-8") as f:
            for m in self.meta:
                f.write(json.dumps(m, ensure_ascii=False) + "\n")

    def top_k(self, query: str, k: int = 4) -> List[Dict[str, Any]]:
        if self.emb is None or self.emb.shape[0] == 0:
            return []
        q = embed_query(query).astype(np.float32)
        scores = self.emb @ q  # cosine (embeddings déjà normalisés)
        k = max(1, k)
        if k >= len(scores):
            idx = np.argsort(-scores)
        else:
            idx = np.argpartition(-scores, kth=k - 1)[:k]
            idx = idx[np.argsort(-scores[idx])]
        out = []
        for i in idx:
            m = self.meta[int(i)].copy()
            m["_score"] = float(scores[int(i)])
            out.append(m)
        return out
