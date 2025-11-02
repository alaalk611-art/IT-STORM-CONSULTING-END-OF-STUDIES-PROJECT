# src/rag/embeddings.py
import os
from functools import lru_cache

import numpy as np

# Modèle par défaut (rapide et dispo offline si déjà en cache HF)
_DEFAULT_MODEL = "sentence-transformers/all-MiniLM-L6-v2"


@lru_cache(maxsize=1)
def _load_model():
    from sentence_transformers import SentenceTransformer

    model_name = os.getenv("EMBEDDING_MODEL", _DEFAULT_MODEL)
    return SentenceTransformer(model_name)


def embed_texts(texts: list[str]) -> np.ndarray:
    """
    Retourne un array (n, d) float32 L2-normalisé pour cosine ultra-rapide (dot).
    """
    model = _load_model()
    vecs = model.encode(
        texts,
        batch_size=64,
        show_progress_bar=False,
        convert_to_numpy=True,
        normalize_embeddings=True,
    )
    return vecs.astype(np.float32)


def embed_query(text: str) -> np.ndarray:
    return embed_texts([text])[0]
