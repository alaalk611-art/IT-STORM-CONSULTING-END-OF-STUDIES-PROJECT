# src/rag/chain.py
from __future__ import annotations
import os
from pathlib import Path
from dataclasses import dataclass
from typing import List, Dict, Any, Tuple, Optional
from sentence_transformers import SentenceTransformer
import numpy as np
import json
import re
import unicodedata
from difflib import SequenceMatcher

from .llm import get_llm

# --------------------------------------------------------------------
# Config & chemins  (✅ version dynamique, sans chemins hardcodés)
# --------------------------------------------------------------------
from pathlib import Path

# Racine du projet (…/src/rag/chain.py -> remonte de 2 niveaux)
_PROJECT_ROOT = Path(__file__).resolve().parents[2]

# Dossier DATA configurable (par défaut: "<project>/data")
_DATA_DIR = Path(os.getenv("DATA_DIR", str(_PROJECT_ROOT / "data")))
_RAW_DIR = _DATA_DIR / "raw"

# 1) Sources (docs) — par défaut: tous les .txt dans data/raw/
_default_sources: list[str] = []
if _RAW_DIR.exists():
    _default_sources = [str(p) for p in _RAW_DIR.glob("*.txt")]

# 1bis) Fallback: /mnt/data (utile quand tu as uploadé des .txt dans la session)
if not _default_sources:
    _FALLBACK_DIR = Path("/mnt/data")
    if _FALLBACK_DIR.exists():
        # Essaie de prendre uniquement les fichiers connus si présents,
        # sinon prends tous les .txt.
        preferred_names = [
            "Executive Summary.txt",
            "Contexte Objectifs.txt",
            "Pain Points.txt",
            "Architecture Solution.txt",
            "Budget Et Effort.txt",
            "Risques Et Attenuations.txt",
            "Roadmap Jalons.txt",
            "Prochaines Etapes.txt",
        ]
        picked = []
        for name in preferred_names:
            p = _FALLBACK_DIR / name
            if p.exists():
                picked.append(str(p))
        if not picked:
            picked = [str(p) for p in _FALLBACK_DIR.glob("*.txt")]
        _default_sources = picked

# 1ter) Override via env: RAG_SOURCE_FILES = "path1;path2;..."
_env_sources = os.getenv("RAG_SOURCE_FILES", "").strip()
if _env_sources:
    _DEFAULT_SOURCES = [p for p in _env_sources.split(";") if p.strip()]
else:
    _DEFAULT_SOURCES = _default_sources

# 2) Fichiers QA (train/val/test) — par défaut: dans "data/"
_default_qas: list[str] = []
_candidates = [(_DATA_DIR / "train.txt"), (_DATA_DIR / "val.txt"), (_DATA_DIR / "test.txt")]
for p in _candidates:
    if p.exists():
        _default_qas.append(str(p))

# Fallback /mnt/data si rien trouvé dans data/
if not _default_qas:
    _FALLBACK_DIR = Path("/mnt/data")
    if _FALLBACK_DIR.exists():
        for name in ["train.txt", "val.txt", "test.txt"]:
            q = _FALLBACK_DIR / name
            if q.exists():
                _default_qas.append(str(q))

# Override via env: RAG_QA_FILES = "path1;path2;path3"
_env_qas = os.getenv("RAG_QA_FILES", "").strip()
if _env_qas:
    _DEFAULT_QA_FILES = [p for p in _env_qas.split(";") if p.strip()]
else:
    _DEFAULT_QA_FILES = _default_qas

# Modèles / params
EMBEDDING_MODEL = os.getenv("EMBEDDING_MODEL", "sentence-transformers/all-MiniLM-L6-v2")
CHUNK_SIZE = int(os.getenv("RAG_CHUNK_SIZE", "800"))
CHUNK_OVERLAP = int(os.getenv("RAG_CHUNK_OVERLAP", "120"))
TOP_K = int(os.getenv("RAG_TOPK", "4"))

# --- Seuils / règles ---
QA_EXACT_NORMALIZE     = True
QA_MIN_RATIO_STRONG    = float(os.getenv("RAG_QA_MIN_RATIO_STRONG", "0.92"))
QA_MIN_RATIO_WEAK      = float(os.getenv("RAG_QA_MIN_RATIO_WEAK",   "0.86"))
CLARIFY_MIN_LEN        = int(os.getenv("RAG_CLARIFY_MIN_LEN", "18"))   # < → ambigu
CLARIFY_MIN_TOKENS     = int(os.getenv("RAG_CLARIFY_MIN_TOKENS", "3")) # < → ambigu

# Gate domaine (hors-sujet)
DOMAIN_MIN_SIM         = float(os.getenv("RAG_DOMAIN_MIN_SIM", "0.78"))
DOMAIN_MSG = os.getenv(
    "RAG_DOMAIN_MSG",
    "Ce système répond uniquement aux questions liées à IT Storm (cloud, DevOps, IaC, pipelines data, IA métier) et au projet PFE interne. "
    "Merci de reformuler votre question dans ce périmètre."
)

# --------------------------------------------------------------------
# Utilitaires
# --------------------------------------------------------------------

def _read_text_file(path: Path) -> str:
    return path.read_text(encoding="utf-8", errors="ignore")

def _normalize_ws(text: str) -> str:
    return re.sub(r"\s+", " ", text).strip()

def _normalize_for_match(s: str) -> str:
    s = s.strip()
    s = re.sub(r"^\s*[QA]\s*:\s*", "", s, flags=re.IGNORECASE)
    s = unicodedata.normalize("NFKD", s)
    s = "".join(ch for ch in s if not unicodedata.combining(ch))
    s = s.lower()
    s = re.sub(r"\s+", " ", s)
    return s

def _token_count(s: str) -> int:
    return len([t for t in re.split(r"\s+", s.strip()) if t])

def _chunk_text(text: str, chunk_size: int, overlap: int) -> List[Tuple[str, int, int]]:
    text = _normalize_ws(text)
    chunks, start, n = [], 0, len(text)
    while start < n:
        end = min(n, start + chunk_size)
        chunks.append((text[start:end], start, end))
        if end == n:
            break
        start = max(0, end - overlap)
    return chunks

# --------------------------------------------------------------------
# QA Lookup (avec provenance)
# --------------------------------------------------------------------

@dataclass
class QAPair:
    q_raw: str
    a_raw: str
    q_norm: str
    path: str
    start: int
    end: int

_QA_BLOCK_RE = re.compile(
    r"^\s*Q\s*:\s*(?P<q>.+?)\r?\n\s*A\s*:\s*(?P<a>.+?)\s*(?:\r?\n\s*---\s*\r?\n|$)",
    re.IGNORECASE | re.DOTALL | re.MULTILINE,
)

def _parse_qa_blocks(txt: str, src_path: Path) -> List[QAPair]:
    items: List[QAPair] = []
    for m in _QA_BLOCK_RE.finditer(txt):
        q_raw = m.group("q").strip()
        a_raw = m.group("a").strip()
        start, end = m.span()
        items.append(QAPair(
            q_raw=q_raw,
            a_raw=a_raw,
            q_norm=_normalize_for_match(q_raw),
            path=str(src_path),
            start=start,
            end=end,
        ))
    return items

def _load_qa_pairs(paths: List[Path]) -> List[QAPair]:
    all_pairs: List[QAPair] = []
    for p in paths:
        if not p.exists():
            continue
        txt = _read_text_file(p)
        all_pairs.extend(_parse_qa_blocks(txt, p))
    return all_pairs

def _qa_lookup_conservative(pairs: List[QAPair], question: str) -> Optional[QAPair]:
    """Match direct seulement si la question n'est PAS ambiguë et que le match est fort/strict."""
    if not pairs:
        return None
    qn = _normalize_for_match(question)
    if len(qn) < CLARIFY_MIN_LEN or _token_count(qn) < CLARIFY_MIN_TOKENS:
        return None  # ambigu → pas de réponse directe

    # Exact strict
    if QA_EXACT_NORMALIZE:
        for p in pairs:
            if qn == p.q_norm:
                return p

    # Similarité forte
    best_ratio, best_pair = 0.0, None
    for p in pairs:
        r = SequenceMatcher(None, qn, p.q_norm).ratio()
        if r > best_ratio:
            best_ratio, best_pair = r, p
    if best_ratio >= QA_MIN_RATIO_STRONG:
        return best_pair

    # Un peu moins strict si la question est longue
    if len(qn) >= CLARIFY_MIN_LEN * 2 and best_ratio >= QA_MIN_RATIO_WEAK:
        return best_pair
    return None

# --------------------------------------------------------------------
# Index vectoriel (documents) + Suggesteur QA
# --------------------------------------------------------------------

@dataclass
class VectorIndex:
    model_name: str
    docs: List[Dict[str, Any]]
    _emb_model: SentenceTransformer = None
    _emb_matrix: np.ndarray = None

    @classmethod
    def from_files(cls, paths: List[Path], model_name: str) -> "VectorIndex":
        emb = SentenceTransformer(model_name)
        docs: List[Dict[str, Any]] = []
        for p in paths:
            if not p.exists():
                continue
            raw = _read_text_file(p)
            for i, (chunk, s, e) in enumerate(_chunk_text(raw, CHUNK_SIZE, CHUNK_OVERLAP)):
                docs.append({
                    "id": f"{p.name}::chunk_{i}",
                    "text": chunk,
                    "path": str(p),
                    "start": s,
                    "end": e,
                })
        if not docs:
            raise RuntimeError("Aucune source trouvée pour construire l'index vectoriel.")
        embeddings = emb.encode([d["text"] for d in docs], convert_to_numpy=True, show_progress_bar=False)
        idx = cls(model_name=model_name, docs=docs)
        idx._emb_model = emb
        idx._emb_matrix = embeddings
        return idx

    def search(self, query: str, k: int = TOP_K) -> List[Dict[str, Any]]:
        q_emb = self._emb_model.encode([query], convert_to_numpy=True)[0]
        sims = self._emb_matrix @ q_emb / (
            (np.linalg.norm(self._emb_matrix, axis=1) * np.linalg.norm(q_emb)) + 1e-12
        )
        top_idx = np.argsort(-sims)[:k]
        out = []
        for i in top_idx:
            d = self.docs[i].copy()
            d["score"] = float(sims[i])
            out.append(d)
        return out

@dataclass
class QASuggester:
    pairs: List[QAPair]
    model_name: str
    _emb_model: SentenceTransformer = None
    _q_embs: Optional[np.ndarray] = None

    @classmethod
    def build(cls, pairs: List[QAPair], model_name: str) -> "QASuggester":
        inst = cls(pairs=pairs, model_name=model_name)
        if not pairs:
            return inst
        emb = SentenceTransformer(model_name)
        inst._emb_model = emb
        q_texts = [p.q_norm for p in pairs]
        inst._q_embs = emb.encode(q_texts, convert_to_numpy=True, show_progress_bar=False)
        return inst

    def suggest(self, query: str, topn: int = 5) -> List[QAPair]:
        if not self.pairs or self._q_embs is None or self._emb_model is None:
            return []
        qn = _normalize_for_match(query)
        q_emb = self._emb_model.encode([qn], convert_to_numpy=True)[0]
        sims = self._q_embs @ q_emb / (
            (np.linalg.norm(self._q_embs, axis=1) * np.linalg.norm(q_emb)) + 1e-12
        )
        order = np.argsort(-sims)[:topn]
        return [self.pairs[i] for i in order]

    def max_similarity(self, query: str) -> float:
        if not self.pairs or self._q_embs is None or self._emb_model is None:
            return 0.0
        qn = _normalize_for_match(query)
        q_emb = self._emb_model.encode([qn], convert_to_numpy=True)[0]
        sims = self._q_embs @ q_emb / (
            (np.linalg.norm(self._q_embs, axis=1) * np.linalg.norm(q_emb)) + 1e-12
        )
        return float(np.max(sims)) if sims.size else 0.0

# --------------------------------------------------------------------
# Classification de la requête : ambiguë / in-domain / out-of-domain
# --------------------------------------------------------------------

def _classify_query(query: str, qa_suggester: QASuggester) -> str:
    """
    Retourne l'un de: 'ambiguous', 'in_domain', 'out_of_domain'.
    - 'ambiguous' : courte / trop vague → on veut déclencher SUGGESTIONS (Je ne sais pas).
    - 'out_of_domain' : assez longue mais très peu similaire aux Q connues → message hors périmètre.
    - 'in_domain' : le reste → on essaie QA puis RAG.
    """
    qn = _normalize_for_match(query)
    if len(qn) < CLARIFY_MIN_LEN or _token_count(qn) < CLARIFY_MIN_TOKENS:
        return "ambiguous"

    max_sim = qa_suggester.max_similarity(query)
    if max_sim < DOMAIN_MIN_SIM:
        return "out_of_domain"

    return "in_domain"

# --------------------------------------------------------------------
# Chaîne principale
# --------------------------------------------------------------------

@dataclass
class RAGChain:
    index: VectorIndex
    qa_pairs: List[QAPair]
    qa_suggester: QASuggester
    top_k: int = TOP_K

    def _build_context(self, retrieved: List[Dict[str, Any]]) -> Tuple[str, List[Dict[str, Any]]]:
        ctx_parts, srcs = [], []
        for r in retrieved:
            tag = f"[{Path(r['path']).name} | {r['start']}–{r['end']}]"
            ctx_parts.append(f"{tag}\n{r['text']}")
            srcs.append({"id": r["id"], "path": r["path"], "span": [r["start"], r["end"]]})
        return "\n\n---\n\n".join(ctx_parts), srcs

    def invoke(self, query: str) -> Dict[str, Any]:
        # 0) Classifier
        cls = _classify_query(query, self.qa_suggester)

        if cls == "ambiguous":
            # → laisser la CLI proposer des reformulations
            return {"answer": "Je ne sais pas", "sources": []}

        if cls == "out_of_domain":
            # → hors périmètre : message standard, pas de suggestions
            return {"answer": DOMAIN_MSG, "sources": []}

        # 1) in_domain → essai QA direct conservateur
        qa_pair = _qa_lookup_conservative(self.qa_pairs, query)
        if qa_pair:
            qa_sources = [{
                "id": f"{Path(qa_pair.path).name}::qa",
                "path": qa_pair.path,
                "span": [qa_pair.start, qa_pair.end],
            }]
            return {"answer": qa_pair.a_raw, "sources": qa_sources}

        # 2) Fallback RAG + LLM strict
        retrieved = self.index.search(query, k=self.top_k)
        context, srcs = self._build_context(retrieved)
        llm = get_llm()
        answer = llm.generate(question=query, context=context, max_new_tokens=160)

        if not answer or ("je ne sais pas" in answer.lower()):
            return {"answer": "Je ne sais pas", "sources": srcs}
        return {"answer": answer, "sources": srcs}

    def suggest_questions(self, query: str, topn: int = 5) -> List[QAPair]:
        return self.qa_suggester.suggest(query, topn=topn)

# --------------------------------------------------------------------
# Factory
# --------------------------------------------------------------------

def build_rag_chain(k: int = TOP_K) -> RAGChain:
    src_paths = [Path(p) for p in _DEFAULT_SOURCES]
    qa_paths = [Path(p) for p in _DEFAULT_QA_FILES]

    index = VectorIndex.from_files(src_paths, model_name=EMBEDDING_MODEL)
    qa_pairs = _load_qa_pairs(qa_paths)
    qa_suggester = QASuggester.build(qa_pairs, model_name=EMBEDDING_MODEL)

    return RAGChain(index=index, qa_pairs=qa_pairs, qa_suggester=qa_suggester, top_k=k)
# ========= Fin src/rag/chain.py =========