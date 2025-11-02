# src/ingestion/chunking.py
from typing import Iterable, List


def chunk_words(text: str, chunk_size: int = 200, overlap: int = 50) -> Iterable[str]:
    """
    Découpe naïvement par mots avec un recouvrement.
    Utilisé par les tests (voir tests/test_chunking.py).
    """
    if not text:
        return []
    tokens: List[str] = text.split()
    if chunk_size <= 0:
        chunk_size = 200
    if overlap < 0:
        overlap = 0
    step = max(1, chunk_size - overlap)
    out = []
    for start in range(0, len(tokens), step):
        window = tokens[start : start + chunk_size]
        if not window:
            break
        out.append(" ".join(window))
        if start + chunk_size >= len(tokens):
            break
    return out


# src/ingestion/chunking.py
from typing import Iterable, List


def chunk_words(text: str, chunk_size: int = 200, overlap: int = 50) -> Iterable[str]:
    """
    Découpe par mots avec recouvrement (utilisé par les tests).
    """
    if not text:
        return []
    tokens: List[str] = text.split()
    if chunk_size <= 0:
        chunk_size = 200
    if overlap < 0:
        overlap = 0
    step = max(1, chunk_size - overlap)
    out = []
    for start in range(0, len(tokens), step):
        window = tokens[start : start + chunk_size]
        if not window:
            break
        out.append(" ".join(window))
        if start + chunk_size >= len(tokens):
            break
    return out
