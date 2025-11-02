# =============================
# 📍 Path: src/rag_brain.py
# Description: Cerveau RAG unifié (aligné avec generate_docs_rag)
# - Chroma PersistentClient (correct)
# - Dossier vectors/ + collection itstorm_docs (alignement)
# - ENV homogènes (EMBEDDING_MODEL / LLM_MODEL / VECTOR_DB_DIR / COLLECTION_NAME)
# - Réponses fluides, fallback extractif
# =============================
from __future__ import annotations
import os, re, json
from pathlib import Path
from typing import List, Tuple, Dict

import numpy as np

# Embeddings / DB
from sentence_transformers import SentenceTransformer
import chromadb
from chromadb.config import Settings as ChromaSettings

# LLM local (optionnel). On supporte seq2seq (Flan-T5) ou causal (TinyLlama)
_HF_OK = True
try:
    from transformers import AutoTokenizer, AutoModelForSeq2SeqLM, AutoModelForCausalLM, pipeline
except Exception:
    _HF_OK = False

# Export (utilitaires facultatifs)
try:
    from docx import Document
except Exception:
    Document = None  # type: ignore
try:
    from pptx import Presentation
except Exception:
    Presentation = None  # type: ignore
try:
    from PyPDF2 import PdfReader
except Exception:
    PdfReader = None  # type: ignore

# =============================
# ENV / Defaults — harmonisés avec generate_docs_rag.py
# =============================
ROOT = Path(__file__).resolve().parents[1]
VECTOR_DB = os.getenv("VECTOR_DB_DIR", str(ROOT / "vectors"))
COLLECTION_NAME = os.getenv("COLLECTION_NAME", "itstorm_docs")
EMBED_MODEL = os.getenv("EMBEDDING_MODEL", "sentence-transformers/all-MiniLM-L6-v2")
LLM_MODEL = os.getenv("LLM_MODEL", "google/flan-t5-base")  # par défaut seq2seq cpu-friendly

ALLOWED = {
    "it storm","it-storm","devops","cloud","data","pipeline","pipelines",
    "rag","pfe","consulting","kubernetes","aws","gcp","azure","ml","ia","ai",
}

SECTIONS_FR = [
    "Executive Summary","Contexte & Objectifs","Pain Points","Architecture Solution",
    "Données & Qualité","Plan de Mise en œuvre","Sécurité & Conformité","Prochaines Étapes",
]
SECTIONS_EN = [
    "Executive Summary","Context & Objectives","Pain Points","Solution Architecture",
    "Data & Quality","Implementation Plan","Security & Compliance","Next Steps",
]

# =============================
# Helpers
# =============================

def _clean(x: str) -> str:
    return re.sub(r"\s+", " ", (x or "").strip())


def _allowed(q: str) -> bool:
    ql = q.lower()
    return any(k in ql for k in ALLOWED)


def _lang_pick(lang: str):
    l = (lang or "auto").lower()
    if l == "en":
        return SECTIONS_EN, "en"
    return SECTIONS_FR, "fr"

# =============================
# Embedder + VectorDB (Chroma PersistentClient)
# =============================
class Embedder:
    def __init__(self, model_name: str = EMBED_MODEL):
        self.model = SentenceTransformer(model_name)
    def encode(self, texts: List[str]) -> np.ndarray:
        return np.asarray(self.model.encode(texts, convert_to_numpy=True, normalize_embeddings=True))


class VectorDB:
    def __init__(self, persist_dir: str = VECTOR_DB, collection_name: str = COLLECTION_NAME):
        os.makedirs(persist_dir, exist_ok=True)
        # ✅ PersistentClient (API correcte)
        self.client = chromadb.PersistentClient(path=persist_dir, settings=ChromaSettings())
        try:
            self.col = self.client.get_collection(collection_name)
        except Exception:
            self.col = self.client.create_collection(collection_name, metadata={"hnsw:space": "cosine"})
        self.embedder = Embedder()

    def search(self, query: str, k: int = 6):
        qv = self.embedder.encode([query])[0].tolist()
        res = self.col.query(query_embeddings=[qv], n_results=k)
        docs = res.get("documents", [[]])[0]
        metas = res.get("metadatas", [[]])[0]
        dists = res.get("distances", [[]])[0]
        out = []
        for i, txt in enumerate(docs):
            out.append({
                "text": _clean(txt or ""),
                "meta": metas[i] if i < len(metas) else {},
                "score": 1.0 - float(dists[i] if i < len(dists) else 0.0),
            })
        return out

    def top_score(self, query: str) -> float:
        hits = self.search(query, k=1)
        return float(hits[0]["score"]) if hits else 0.0

# =============================
# LLM local — support seq2seq (Flan‑T5) prioritaire, sinon causal
# =============================
class LocalLLM:
    def __init__(self, model_name: str = LLM_MODEL):
        self.ok = False
        self.pipe = None
        if not _HF_OK:
            return
        try:
            if "flan" in model_name.lower() or "t5" in model_name.lower():
                tok = AutoTokenizer.from_pretrained(model_name)
                mdl = AutoModelForSeq2SeqLM.from_pretrained(model_name)
                self.pipe = pipeline("text2text-generation", model=mdl, tokenizer=tok)
            else:
                tok = AutoTokenizer.from_pretrained(model_name)
                mdl = AutoModelForCausalLM.from_pretrained(model_name)
                self.pipe = pipeline("text-generation", model=mdl, tokenizer=tok)
            self.ok = True
        except Exception:
            self.ok = False

    def gen(self, prompt: str, max_new_tokens: int = 320) -> str:
        if not self.ok or self.pipe is None:
            return ""
        try:
            out = self.pipe(prompt, max_new_tokens=max_new_tokens, do_sample=False, temperature=0.0)
            if isinstance(out, list) and out and isinstance(out[0], dict):
                return _clean(out[0].get("generated_text", out[0].get("summary_text", "")))
            return _clean(str(out))
        except Exception:
            return ""

# Singletons
_db = VectorDB()
_llm = LocalLLM()

# =============================
# Public API
# =============================

def generer_brief(question: str, lang: str = "fr") -> str:
    """Réponse concise (<=6 phrases), contextuelle, sans invention."""
    if not _allowed(question):
        return (
            "Ce moteur couvre le périmètre IT‑STORM (cloud/devops/data/IA). Merci de reformuler dans ce contexte."
            if lang == "fr" else
            "This engine covers IT‑STORM scope (cloud/devops/data/AI). Please reformulate within scope."
        )
    hits = _db.search(question, k=6)
    if not hits:
        return "Je ne sais pas." if lang == "fr" else "I don't know."

    ctx_lines = [f"- {h['text']}" for h in hits[:6] if h.get('text')]
    sources = [Path((h.get('meta') or {}).get('source', 'unknown')).name for h in hits]

    if _llm.ok:
        if lang == "fr":
            prompt = (
                "Tu es un assistant interne. Réponds UNIQUEMENT depuis ces extraits.\n"
                "- 4 à 6 phrases, ton clair et professionnel.\n"
                "- Si l'info manque, dis 'Je ne sais pas'.\n"
                "- Cite au moins une source: [Source: fichier].\n\n"
                f"Question : {question}\n\nContexte :\n{os.linesep.join(ctx_lines)}\n\nRéponse :"
            )
        else:
            prompt = (
                "You are an internal assistant. Answer ONLY from the snippets.\n"
                "- 4–6 sentences, clear professional tone.\n"
                "- If missing, say 'I don't know'.\n"
                "- Cite at least one source: [Source: filename].\n\n"
                f"Question: {question}\n\nContext:\n{os.linesep.join(ctx_lines)}\n\nAnswer:"
            )
        out = _llm.gen(prompt, max_new_tokens=300)
        out = _clean(out)
        if out:
            # Ajoute une source si absente
            if sources and all(f"[Source: {Path(s).name}]" not in out for s in sources):
                out += f"\n[Source: {sources[0]}]"
            # Coupe à 6 phrases max
            sents = re.split(r"(?<=[\.!?])\s+(?=[A-ZÀ-ÖØ-Þ0-9])", out)
            if len(sents) > 6:
                out = " ".join(sents[:6]).strip()
            return out

    # Fallback extractif
    txt = ("Réponse (extraits) :\n" if lang == "fr" else "Answer (extracts):\n") + "\n".join(ctx_lines)
    if sources:
        txt += f"\n[Source: {sources[0]}]"
    return txt


def resume_document(path: str, lang: str = "fr") -> str:
    p = Path(path)
    if not p.exists():
        return "Fichier introuvable." if lang == "fr" else "File not found."
    try:
        if PdfReader and p.suffix.lower() == ".pdf":
            reader = PdfReader(str(p))
            txt = "\n".join((page.extract_text() or "") for page in reader.pages)
        else:
            txt = p.read_text(encoding="utf-8", errors="ignore")
    except Exception as e:
        return f"Erreur lecture: {e}" if lang == "fr" else f"Read error: {e}"
    txt = _clean(txt)[:10000]
    if not txt:
        return "Document vide." if lang == "fr" else "Empty document."

    if _llm.ok:
        prompt = (f"Résumé factuel (<=6 phrases) :\n{txt}" if lang == "fr" else f"Summarize factually in <=6 sentences:\n{txt}")
        out = _llm.gen(prompt, max_new_tokens=280)
        if out:
            return out

    # Fallback extractif simple
    parts = [s.strip() for s in re.split(r"(?<=[\.!?])\s+", txt) if s.strip()][:6]
    bullet = "- " if lang == "fr" else "- "
    return ("Résumé (extraits):\n" if lang == "fr" else "Summary (extracts):\n") + "\n".join(bullet + s for s in parts)


def generate_full_sections(topic: str, lang: str = "fr") -> List[Tuple[str, str]]:
    sections, lang = _lang_pick(lang)
    out: List[Tuple[str, str]] = []
    for sec in sections:
        q = f"{topic} — {sec}"
        ans = generer_brief(q, lang=lang)
        out.append((sec, ans))
    return out

# ---------- Suggestions (facultatif) ----------

def _load_suggest_map() -> Dict[str, List[str]]:
    p = Path(os.getenv("SUGGEST_PATH", "./src/data/suggest_keywords.json"))
    if p.exists():
        try:
            return json.loads(p.read_text(encoding="utf-8"))
        except Exception:
            return {}
    return {
        "it storm": [
            "Quel est le cœur de métier d’IT Storm ?",
            "Quelles solutions IT Storm développe‑t‑elle pour la donnée ?",
            "Quelles priorités IT Storm met‑elle en avant (sécurité, coûts, fiabilité) ?",
        ],
        "data": [
            "Quelles solutions data IT Storm propose‑t‑elle (collecte, qualité, exploitation) ?",
            "Quels pipelines de données IT Storm met‑elle en place ?",
        ],
        "rag": [
            "Comment IT Storm met‑elle en œuvre une solution RAG pour un client ?",
            "Quelle valeur apporte le RAG aux consultants IT Storm ?",
        ],
    }


def suggest_queries(question: str, lang: str = "fr", max_suggestions: int = 5) -> List[str]:
    q = (question or "").lower()
    m = _load_suggest_map()
    cands: List[str] = []
    for k, lst in m.items():
        if k in q:
            cands.extend(lst)
    if not cands:  # génériques
        cands.extend([
            "Quel type de consulting propose IT Storm ?",
            "IT Storm utilise‑t‑elle Kubernetes et IaC ?",
            "Quels cas d’usage Data/IA IT Storm adresse‑t‑elle ?",
        ])
    # dedup
    seen=set(); out=[]
    for s in cands:
        if s not in seen:
            seen.add(s); out.append(s)
    return out[:max_suggestions]
