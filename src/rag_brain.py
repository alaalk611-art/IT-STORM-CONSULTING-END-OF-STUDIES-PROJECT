# -*- coding: utf-8 -*-
# src/rag_brain.py
# ============================================================
# RAG intelligent (version stricte, FR uniquement)
# - Réponses 100% ancrées sur extraits courts + citations (pas de génération libre)
# - Priorité forte à it_storm_1000_QA.txt (insensible à la casse/chemin)
# - Prise en compte des autres .txt pour enrichir la réponse (anti-dérive, diversité)
# - Late fusion Dense+BM25, rerank équilibré (MMR simple + anti-domination QA)
# - Blocage total PDF/Office (bruit), normalisation de noms de sources
# - Filtrage QA: ignore “Q:…”, préfère “A:…”
# - Agrégation “definition”: phrase-synthèse par couture de 2–3 citations (zéro hallucination)
# - Fallback sémantique contrôlé -> "Je ne sais pas." si insuffisant
# - Wrapper smart_rag_answer(*args, **kwargs) compatible UI (ignore lang/mode)
# - Maintenance intégrée: reindex_txt_file(), ensure_qa_indexed()
# ============================================================

from __future__ import annotations
import os
import re
import uuid
from dataclasses import dataclass, field
from typing import List, Dict, Any, Optional, Tuple
from collections import Counter

# ===== Dépendances minimales =====
try:
    import chromadb
    from chromadb.config import Settings
    from chromadb.utils import embedding_functions
except Exception as e:
    raise RuntimeError(f"[RAG] ChromaDB manquant: {e}")

try:
    from rank_bm25 import BM25Okapi
except Exception:
    BM25Okapi = None  # BM25 optionnel (late fusion plus robuste si présent)

# ===== ENV / Paramètres =====
DEFAULT_DB_PATH = os.getenv("VECTOR_DB_PATH", "./vectors")
DEFAULT_COLLECTION = os.getenv("VECTOR_COLLECTION", "consulting")
EMBED_MODEL_NAME = os.getenv("EMBED_MODEL", "all-MiniLM-L6-v2")

TOP_K_DENSE = int(os.getenv("RAG_TOP_K_DENSE", "48"))
TOP_K_BALANCED = int(os.getenv("RAG_TOP_K_BALANCED", "8"))
MAX_QUOTES = int(os.getenv("RAG_MAX_QUOTES", "6"))

# Confiance minimale pour construire autre chose qu'un fallback
CONF_MIN = float(os.getenv("RAG_CONF_MIN", "0.65"))

# Late fusion (dense vs bm25)
FUSION_DENSE_W = float(os.getenv("RAG_FUSION_DENSE_W", "0.6"))
FUSION_BM25_W  = float(os.getenv("RAG_FUSION_BM25_W", "0.4"))

# Diversité (MMR simplifiée)
MMR_LAMBDA = float(os.getenv("RAG_MMR_LAMBDA", "0.6"))

# Nombre minimal d'extraits pour accepter une réponse
MIN_QUOTES_OK = int(os.getenv("RAG_MIN_QUOTES_OK", "2"))

# Limiter la domination du fichier QA dans les citations
QA_MAX_QUOTE_SHARE = float(os.getenv("RAG_QA_MAX_QUOTE_SHARE", "0.6"))  # ex: 60% max des citations
MAX_QUOTES_PER_SOURCE = int(os.getenv("RAG_MAX_QUOTES_PER_SOURCE", "3"))

# Extensions bloquées (bruit) -> exclus dur
BLOCKED_EXTENSIONS = {".pdf", ".doc", ".docx", ".ppt", ".pptx"}

# Dossier data par défaut (pour maintenance/réindexation)
RAG_DATA_DIR = os.getenv(
    "RAG_DATA_DIR",
    r"C:\Users\ALA BEN LAKHAL\Desktop\intelligent_copilot IT-STORM\data"
)
QA_BASENAME = "it_storm_1000_QA.txt"  # IMPORTANT: basename exact
QA_DEFAULT_PATH = os.path.join(RAG_DATA_DIR, QA_BASENAME)
QA_BASENAME_L = QA_BASENAME.lower()

# ===== Regex utilitaires =====
_SENT_SPLIT = re.compile(r"(?<=[\.\!\?])\s+")
_WORD = re.compile(r"\w+", re.UNICODE)

# ===== Boosts par intention (par nom de fichier "basename") =====
INTENT_BOOSTS = {
    "benefits": {
        "Executive Summary.txt": 2.1,
        "Contexte Objectifs.txt": 1.8,
        "Pain Points.txt": 1.5,
        "it_storm_1000_QA.txt": 2.6,
    },
    "objectives": {
        "Contexte Objectifs.txt": 2.2,
        "Executive Summary.txt": 1.5,
        "it_storm_1000_QA.txt": 2.4,
    },
    "risks": {
        "Risques Et Attenuations.txt": 2.5,
        "it_storm_1000_QA.txt": 2.2,
    },
    "architecture": {
        "Architecture Solution.txt": 2.5,
        "Executive Summary.txt": 1.3,
        "it_storm_1000_QA.txt": 2.2,
    },
    "budget": {
        "Budget Et Effort.txt": 2.5,
        "it_storm_1000_QA.txt": 2.2,
    },
    "roadmap": {
        "Prochaines Etapes.txt": 2.5,
        "it_storm_1000_QA.txt": 2.2,
    },
    "definition": {
        "Executive Summary.txt": 1.9,
        "Contexte Objectifs.txt": 1.3,
        "it_storm_1000_QA.txt": 2.8,
    },
    "howto": {
        "Architecture Solution.txt": 2.0,
        "it_storm_1000_QA.txt": 2.3,
    },
    "compare": {
        "Executive Summary.txt": 1.4,
        "Architecture Solution.txt": 1.4,
        "it_storm_1000_QA.txt": 2.3,
    },
    "summary": {
        "Executive Summary.txt": 2.0,
        "it_storm_1000_QA.txt": 2.3,
    },
    "default": {
        "Executive Summary.txt": 1.3,
        "Contexte Objectifs.txt": 1.2,
        "it_storm_1000_QA.txt": 2.7,
    },
}

# ===== Filtrage strict "benefits" (anti dérive) =====
BENEFITS_ALLOW = {
    "Executive Summary.txt",
    "Contexte Objectifs.txt",
    "Pain Points.txt",
    "Architecture Solution.txt",
    "Prochaines Etapes.txt",
    "itstorm.txt",
    "it_storm_1000_QA.txt",
}

# ===== Normalisation noms sources (robuste casse/chemin) =====
def _norm_base(src: str) -> str:
    return os.path.basename(src or "").strip().lower()

def _ext(name: str) -> str:
    base = _norm_base(name)
    return "." + base.rsplit(".", 1)[-1] if "." in base else ""

def is_blocked_source(src: str) -> bool:
    return _ext(src) in BLOCKED_EXTENSIONS

# ===== Versions "lower" des tables =====
def _lower_map(d: Dict[str, float]) -> Dict[str, float]:
    return {k.lower(): v for k, v in d.items()}

def _lower_nested_map(d: Dict[str, Dict[str, float]]) -> Dict[str, Dict[str, float]]:
    return {k: _lower_map(v) for k, v in d.items()}

INTENT_BOOSTS_L = _lower_nested_map(INTENT_BOOSTS)
BENEFITS_ALLOW_L = {s.lower() for s in BENEFITS_ALLOW}

def benefits_allowed_source(src: str) -> bool:
    return _norm_base(src) in BENEFITS_ALLOW_L

# ===== Helpers texte =====
def split_sentences(text: str) -> List[str]:
    t = (text or "").strip()
    if not t:
        return []
    try:
        parts = _SENT_SPLIT.split(t)
        return [p.strip() for p in parts if p.strip()]
    except Exception:
        return [t]

def clean_text_for_quote(text: str) -> str:
    t = re.sub(r"\s+", " ", text or "").strip()
    t = re.sub(r"\[[^\]]+\]", "", t)
    t = re.sub(r"\([^\)]+\)", lambda m: m.group(0) if len(m.group(0).split()) < 10 else "", t)
    return t

def truncate_words(s: str, max_words: int = 12) -> str:
    toks = (s or "").strip().split()
    return (s or "").strip() if len(toks) <= max_words else " ".join(toks[:max_words]).strip()

def tokens_fr(s: str) -> List[str]:
    return [w.lower() for w in _WORD.findall(s or "")]

def humanize_fr(text: str) -> str:
    text = re.sub(r"\b(and|the|for|y|in|of)\b", "", text, flags=re.IGNORECASE)
    text = re.sub(r"\s{2,}", " ", text)
    text = re.sub(r"\s+([,;:.])", r"\1", text)
    return text.strip()

# --- Mode "paragraphe unique"
SINGLE_PARAGRAPH = os.getenv("RAG_SINGLE_PARAGRAPH", "1") == "1"

def _take_quote_texts(quotes, max_parts=4):
    parts, seen = [], set()
    for q in quotes:
        seg = (q.get("quote") or "").strip()
        if seg and seg not in seen:
            seen.add(seg)
            parts.append(seg)
        if len(parts) >= max_parts:
            break
    return parts

def paragraphize_from_quotes(quotes: List[Dict[str,str]], intent: str) -> str:
    parts = _take_quote_texts(quotes, max_parts=4)
    if not parts:
        return "Je ne sais pas."
    sent = assemble_human_sentence(parts)
    if not sent:
        sent = " ; ".join(f"« {p} »" for p in parts) + "."
    if intent == "definition" and not sent.lower().startswith("it-storm"):
        sent = "IT-STORM : " + " ; ".join(f"« {p} »" for p in parts) + "."
    return humanize_fr(sent)

def assemble_human_sentence(parts: List[str]) -> str:
    if not parts:
        return ""
    uniq = []
    for p in parts:
        p = p.strip(" .;")
        if len(p.split()) >= 3 and p not in uniq:
            uniq.append(p)
        if len(uniq) >= 3:
            break
    if not uniq:
        return ""
    sent = " ".join(uniq)
    sent = sent.replace("..", ".").replace(" ;", ";").strip()
    if not sent.endswith("."):
        sent += "."
    return humanize_fr(sent)

# ===== QA filtering helpers =====
QA_QUESTION_PREFIXES = ("q:", "question:")
QA_ANSWER_PREFIXES   = ("a:", "réponse:", "reponse:", "answer:")

def _strip_qa_prefix(s: str) -> str:
    s2 = s.strip()
    s2_low = s2.lower()
    for p in QA_QUESTION_PREFIXES + QA_ANSWER_PREFIXES:
        if s2_low.startswith(p):
            return s2[len(p):].strip()
    return s2

def _is_questionish(s: str) -> bool:
    s2 = s.strip()
    if not s2:
        return False
    low = s2.lower()
    if low.startswith(QA_QUESTION_PREFIXES):
        return True
    if s2.endswith("?"):
        return True
    if low.startswith(("qu’est-ce", "qu'est-ce", "que ", "quoi ", "comment ", "pourquoi ", "où ", "ou ", "quand ")):
        return True
    return False

def _looks_like_answer(s: str) -> bool:
    low = s.strip().lower()
    if low.startswith(QA_ANSWER_PREFIXES):
        return True
    return ("?" not in s) and (len(s.split()) >= 3)

# ===== Détection d’intention (FR) =====
def detect_intent(q: str) -> str:
    ql = (q or "").lower()
    if any(w in ql for w in ["bénéfice", "benefice", "benefit", "avantage", "roi"]):
        return "benefits"
    if any(w in ql for w in ["objectif", "goals", "target", "priorité", "priorite"]):
        return "objectives"
    if any(w in ql for w in ["risque", "atténuation", "attenuation", "risk", "mitigation"]):
        return "risks"
    if any(w in ql for w in ["architecture", "solution", "kubernetes", "ci/cd", "iac", "orchestration"]):
        return "architecture"
    if any(w in ql for w in ["budget", "effort", "coût", "cout", "charge"]):
        return "budget"
    if any(w in ql for w in ["roadmap", "étapes", "jalon", "prochaines étapes", "prochaines etapes"]):
        return "roadmap"
    if any(w in ql for w in ["qu'est-ce", "definition", "définition", "what is"]):
        return "definition"
    if any(w in ql for w in ["comment", "how to", "procédure", "procedure", "guide"]):
        return "howto"
    if any(w in ql for w in ["vs", "contre", "compar", "difference", "différence"]):
        return "compare"
    if any(w in ql for w in ["résume", "resume", "summary", "synthèse", "synthese"]):
        return "summary"
    return "default"

# ===== Data classes =====
@dataclass
class RetrievedChunk:
    doc_id: str
    source: str
    text: str
    score_dense: float
    score_bm25: float = 0.0
    score_final: float = 0.0

@dataclass
class SmartRAGResult:
    answer: str
    sources: List[str]
    quotes: List[Dict[str, str]]  # {"source":..., "quote":...}
    confidence: float
    quality: Dict[str, float]
    dbg: Dict[str, Any] = field(default_factory=dict)

# ===== Moteur =====
class SmartRAG:
    def __init__(self,
                 db_path: str = DEFAULT_DB_PATH,
                 collection_name: str = DEFAULT_COLLECTION,
                 embed_model_name: str = EMBED_MODEL_NAME):
        try:
            self.client = chromadb.PersistentClient(path=db_path, settings=Settings(anonymized_telemetry=False))
        except Exception as e:
            raise RuntimeError(f"[RAG] Échec init ChromaDB (path={db_path}): {e}")
        try:
            self.emb_fn = embedding_functions.SentenceTransformerEmbeddingFunction(model_name=embed_model_name)
        except Exception as e:
            raise RuntimeError(f"[RAG] Échec chargement embeddings '{embed_model_name}': {e}")
        try:
            self.col = self.client.get_or_create_collection(name=collection_name, embedding_function=self.emb_fn)
        except Exception as e:
            raise RuntimeError(f"[RAG] Échec accès collection '{collection_name}': {e}")

    # Dense retrieve
    def retrieve_dense(self, query: str, k: int) -> List[RetrievedChunk]:
        res = self.col.query(query_texts=[query], n_results=k, include=["documents", "metadatas", "distances"])
        out: List[RetrievedChunk] = []
        if not res or not res.get("documents"):
            return out
        docs = res["documents"][0]
        metas = res.get("metadatas", [[]])[0]
        dists = res.get("distances", [[]])[0]
        sims = [1.0 / (1.0 + float(d)) if d is not None else 0.0 for d in dists]
        for i, d in enumerate(docs):
            md = metas[i] if i < len(metas) and metas[i] else {}
            source = md.get("source") or md.get("file") or "unknown"
            doc_id = md.get("id") or md.get("uuid") or f"doc_{i}"
            out.append(RetrievedChunk(doc_id=doc_id, source=source, text=d, score_dense=sims[i]))
        return out

    # BM25 sur candidats denses
    def bm25_scores(self, query: str, cands: List[RetrievedChunk]) -> List[float]:
        if not BM25Okapi or not cands:
            return [0.0] * len(cands)
        corpus = [tokens_fr(c.text) for c in cands]
        bm = BM25Okapi(corpus)
        qtok = tokens_fr(query)
        return list(bm.get_scores(qtok))

    @staticmethod
    def _minmax(xs: List[float]) -> List[float]:
        if not xs:
            return xs
        lo, hi = min(xs), max(xs)
        if hi - lo < 1e-9:
            return [0.0 for _ in xs]
        return [(x - lo) / (hi - lo) for x in xs]

    # Late fusion (robuste) + normalisation
    def late_fusion(self, dense_list: List[RetrievedChunk], query: str) -> List[RetrievedChunk]:
        if not isinstance(dense_list, list) or not dense_list:
            return []
        dense_norm = self._minmax([c.score_dense for c in dense_list])
        bm25_norm  = self._minmax(self.bm25_scores(query, dense_list))
        fused: List[RetrievedChunk] = []
        for i, c in enumerate(dense_list):
            score = FUSION_DENSE_W * dense_norm[i] + FUSION_BM25_W * bm25_norm[i]
            fused.append(RetrievedChunk(
                doc_id=c.doc_id, source=c.source, text=c.text,
                score_dense=c.score_dense, score_bm25=bm25_norm[i], score_final=score
            ))
        fused.sort(key=lambda x: x.score_final, reverse=True)
        return fused

    # Rerank + équilibrage + filtrage dur (PDF out) + anti-domination QA
    def rerank_balance(self, items: List[RetrievedChunk], intent: str) -> List[RetrievedChunk]:
        if not items:
            return []

        # filtre dur: exclure les sources bloquées avant tout scoring
        items = [c for c in items if not is_blocked_source(c.source)]
        if not items:
            return []

        boosts = INTENT_BOOSTS_L.get(intent, INTENT_BOOSTS_L["default"])
        boosted: List[RetrievedChunk] = []
        for c in items:
            b = 1.0
            base = _norm_base(c.source)

            # Boosts par fichier (intention + priorité QA contrôlée)
            b *= boosts.get(base, 1.0)

            # Bonus si le chunk ressemble à une réponse (A: ...)
            txt_low = (c.text or "").strip().lower()
            if txt_low.startswith(QA_ANSWER_PREFIXES):
                b *= 1.1

            boosted.append(RetrievedChunk(
                doc_id=c.doc_id, source=c.source, text=c.text,
                score_dense=c.score_dense, score_bm25=c.score_bm25,
                score_final=c.score_final * b
            ))

        # Sélection MMR avec pénalité plus forte sur répétitions de la même source
        selected: List[RetrievedChunk] = []
        used = Counter()
        cand = boosted[:]
        while cand and len(selected) < TOP_K_BALANCED:
            best, best_val = None, -1e9
            for x in cand:
                base = _norm_base(x.source)
                div_pen = 0.18 * used[base]
                if base == QA_BASENAME_L:
                    div_pen += 0.07 * used[base]
                val = MMR_LAMBDA * x.score_final - (1 - MMR_LAMBDA) * div_pen
                if val > best_val:
                    best, best_val = x, val
            if not best:
                break
            selected.append(best)
            used[_norm_base(best.source)] += 1
            cand.remove(best)

        # Garanti : au moins 1 élément non-QA s’il en existe parmi candidats
        if selected and all(_norm_base(s.source) == QA_BASENAME_L for s in selected):
            non_qa = [c for c in boosted if _norm_base(c.source) != QA_BASENAME_L]
            if non_qa:
                non_qa.sort(key=lambda z: z.score_final, reverse=True)
                selected[-1] = non_qa[0]

        selected.sort(key=lambda z: z.score_final, reverse=True)
        return selected

    # Citations (extraits courts), interleave QA + non-QA, limites par source
    def make_quotes(self, chunks: List[RetrievedChunk], max_quotes: int = MAX_QUOTES) -> List[Dict[str, str]]:
        def pick_sentence(text: str) -> Optional[str]:
            text = clean_text_for_quote(text)
            if not text:
                return None
            sentences = split_sentences(text)

            # A) Réponses explicites / phrases déclaratives sans "?"
            for s in sentences:
                s_clean = _strip_qa_prefix(s)
                if _looks_like_answer(s) and not _is_questionish(s):
                    if 3 <= len(s_clean.split()) <= 20:
                        return truncate_words(s_clean, 12)

            # B) Phrases non interrogatives correctes
            for s in sentences:
                s_clean = _strip_qa_prefix(s)
                if not _is_questionish(s) and 3 <= len(s_clean.split()) <= 20:
                    return truncate_words(s_clean, 12)

            # C) Fallback: première phrase non interrogative
            for s in sentences:
                s_clean = _strip_qa_prefix(s)
                if not _is_questionish(s):
                    return truncate_words(s_clean, 12)

            # D) Ultime fallback
            return truncate_words(text, 12)

        # 1) Prépare les candidats nettoyés
        cands = []
        for c in chunks:
            if is_blocked_source(c.source):
                continue
            quote = pick_sentence(c.text or "")
            if not quote:
                continue
            cands.append({"source": _norm_base(c.source), "quote": humanize_fr(quote)})

        if not cands:
            return []

        # 2) Groupes QA vs non-QA
        qa = [q for q in cands if q["source"] == QA_BASENAME_L]
        non = [q for q in cands if q["source"] != QA_BASENAME_L]

        # 3) Limites
        max_qa = int(round(QA_MAX_QUOTE_SHARE * max_quotes))
        if max_qa < 1 and qa:
            max_qa = 1  # garder au moins 1 QA si présent

        # 4) Interleave: priorité au non-QA pour amorcer la diversité
        out: List[Dict[str, str]] = []
        per_source = Counter()
        i_qa, i_non = 0, 0

        while len(out) < max_quotes and (i_non < len(non) or i_qa < len(qa)):
            # pick non-QA si dispo et quota source OK
            if i_non < len(non):
                cand = non[i_non]
                if per_source[cand["source"]] < MAX_QUOTES_PER_SOURCE:
                    out.append(cand)
                    per_source[cand["source"]] += 1
                i_non += 1
                if len(out) >= max_quotes:
                    break

            # pick QA si dispo, sous quotas globaux
            if i_qa < len(qa) and sum(1 for x in out if x["source"] == QA_BASENAME_L) < max_qa:
                cand = qa[i_qa]
                if per_source[cand["source"]] < MAX_QUOTES_PER_SOURCE:
                    out.append(cand)
                    per_source[cand["source"]] += 1
                i_qa += 1

        # 5) Complète si besoin
        i = 0
        while len(out) < max_quotes and i < len(cands):
            cand = cands[i]
            if per_source[cand["source"]] < MAX_QUOTES_PER_SOURCE and cand not in out:
                out.append(cand); per_source[cand["source"]] += 1
            i += 1

        return out

    # Confiance & Qualité
    def estimate_confidence(self, chunks: List[RetrievedChunk]) -> float:
        if not chunks:
            return 0.0
        top = chunks[:4]
        mean_score = sum(x.score_final for x in top) / max(1, len(top))
        uniq = len(set(_norm_base(c.source) for c in chunks))
        coverage = min(1.0, uniq / 4.0)
        mean_score = max(0.0, min(1.0, mean_score))
        return round(0.5 * mean_score + 0.5 * coverage, 3)

    def quality_scores(self, text: str, quotes: List[Dict[str,str]], ranked: List[RetrievedChunk]) -> Dict[str, float]:
        unique_sources = len(set(q["source"] for q in quotes))
        coverage = min(1.0, unique_sources / 4.0)
        grounding = 1.0 if quotes else 0.0
        style_penalty = 0.0 if re.search(r"\b(and|the|for|y)\b", text or "", flags=re.I) is None else 0.3
        style = max(0.0, 1.0 - style_penalty)
        top_mean = sum(x.score_final for x in ranked[:4]) / max(1, len(ranked[:4]))
        relevance = max(0.0, min(1.0, 0.6 * top_mean + 0.4 * coverage))
        nli_proxy = 1.0 if quotes else 0.5
        return {
            "relevance": round(relevance, 3),
            "grounding": round(grounding, 3),
            "coverage": round(coverage, 3),
            "nli_proxy": round(nli_proxy, 3),
            "style": round(style, 3),
        }

    # Builders (strictement extractifs)
    def _bulleted_from_quotes(self, header: str, quotes: List[Dict[str,str]], fallback_line: str) -> Tuple[str, List[str]]:
        out = [header, ""]
        if not quotes:
            out.append(f"- {fallback_line}")
        else:
            for qt in quotes[:4]:
                out.append(f"- *« {qt['quote']} »* ({qt['source']})")
        return "\n".join(out), sorted(set(q["source"] for q in quotes))

    def build_answer_benefits(self, chunks: List[RetrievedChunk]) -> Tuple[str, List[str], List[Dict[str,str]]]:
        focused = [c for c in chunks if benefits_allowed_source(c.source)]
        if not focused:
            focused = chunks
        quotes_all = self.make_quotes(focused, MAX_QUOTES)
        good_quotes = [q for q in quotes_all if benefits_allowed_source(q["source"])]
        if not good_quotes:
            # relance ciblée sans invention
            qx = "RAG bénéfices client énergie réduction temps cohérence réponses génération ancrée"
            d2 = self.retrieve_dense(qx, max(12, TOP_K_DENSE // 2))
            f2 = self.late_fusion(d2, qx)
            r2 = self.rerank_balance(f2, intent="benefits")
            quotes_all = self.make_quotes(r2, MAX_QUOTES)
            good_quotes = [q for q in quotes_all if benefits_allowed_source(q["source"])]

        def pick(src: str) -> Optional[str]:
            base = (src or "").lower()
            for q in good_quotes:
                if q["source"].lower() == base:
                    return q["quote"]
            return None

        candidates = [
            ("Réduction du temps de recherche d’informations critiques",
             pick("Contexte Objectifs.txt") or pick("Executive Summary.txt")),
            ("Cohérence des réponses (base documentaire unique, extraits cités)",
             pick("Executive Summary.txt")),
            ("Moins d’hallucinations (génération ancrée sur documents internes)",
             pick("Architecture Solution.txt") or pick("Executive Summary.txt")),
            ("Confidentialité et souveraineté (fonctionnement local)",
             pick("Executive Summary.txt")),
            ("Industrialisation (exports DOCX/PPTX, monitoring qualité)",
             pick("Prochaines Etapes.txt") or pick("Executive Summary.txt")),
            ("Accélération de la décision opérationnelle",
             pick("Pain Points.txt") or pick("Contexte Objectifs.txt")),
        ]
        bullets = [(t, q) for (t, q) in candidates if q][:5]

        if not bullets:
            header = "Bénéfices confirmés par la documentation interne :"
            ans, srcs = self._bulleted_from_quotes(header, good_quotes, "Aucun extrait fiable disponible.")
            return humanize_fr(ans), sorted(set(q["source"] for q in good_quotes)), good_quotes

        out = ["Bénéfices concrets du RAG (documents internes) :", ""]
        for (title, q) in bullets:
            out.append(f"- {title} — *« {q} »*")
        final_quotes = good_quotes if good_quotes else quotes_all
        return humanize_fr("\n".join(out)), sorted(set(q["source"] for q in final_quotes)), final_quotes

    def _aggregated_definition(self, quotes: List[Dict[str,str]], max_parts: int = 3) -> str:
        if not quotes:
            return "Je ne sais pas."
        seen = set()
        parts: List[str] = []
        for q in quotes:
            seg = q["quote"].strip()
            if seg and seg not in seen:
                seen.add(seg)
                parts.append(f"« {seg} »")
            if len(parts) >= max_parts:
                break
        if not parts:
            return "Je ne sais pas."
        return "IT-STORM : " + " ; ".join(parts) + "."

    def build_generic_from_quotes(self, label: str, chunks: List[RetrievedChunk]) -> Tuple[str, List[str], List[Dict[str,str]]]:
        quotes = self.make_quotes(chunks, MAX_QUOTES)
        if not quotes or len(quotes) < MIN_QUOTES_OK:
            return "Je ne sais pas.", [], []
        out = [f"{label} :", ""]
        for qt in quotes[:5]:
            out.append(f"- *« {qt['quote']} »* ({qt['source']})")
        return humanize_fr("\n".join(out)), sorted(set(q["source"] for q in quotes)), quotes

    def build_definition(self, chunks: List[RetrievedChunk]) -> Tuple[str, List[str], List[Dict[str,str]]]:
        quotes = self.make_quotes(chunks, MAX_QUOTES)
        if not quotes or len(quotes) < MIN_QUOTES_OK:
            return "Je ne sais pas.", [], []

        parts = [q["quote"] for q in quotes]
        headline = assemble_human_sentence(parts)
        if not headline:
            headline = self._aggregated_definition(quotes, max_parts=3)
        if not headline.lower().startswith("it-storm"):
            headline = "IT-STORM est " + headline[0].lower() + headline[1:]

        body = ["", "Extraits documentaires :", ""]
        listed = set()
        for qt in quotes[:4]:
            key = (qt["quote"], qt["source"])
            if key in listed:
                continue
            listed.add(key)
            body.append(f"- *« {qt['quote']} »* ({qt['source']})")

        ans = humanize_fr(headline + "\n" + "\n".join(body))
        return ans, sorted(set(q["source"] for q in quotes)), quotes

    def build_fallback(self, chunks: List[RetrievedChunk]) -> Tuple[str, List[str], List[Dict[str,str]]]:
        quotes = self.make_quotes(chunks, MAX_QUOTES)
        if len(quotes) < MIN_QUOTES_OK:
            return "Je ne sais pas.", [], []
        out = ["Ce que l’on sait avec certitude :", ""]
        for qt in quotes:
            out.append(f"- *« {qt['quote']} »* ({qt['source']})")
        out.append("")
        out.append("Données manquantes : précisez la question ou ajoutez des documents pertinents.")
        return humanize_fr("\n".join(out)), sorted(set(q["source"] for q in quotes)), quotes

    # API principale
    def ask(self, question: str) -> SmartRAGResult:
        q0 = (question or "").strip()
        intent = detect_intent(q0)

        # 1) Retrieve dense
        dense = self.retrieve_dense(q0, TOP_K_DENSE)
        # 2) Late fusion
        fused = self.late_fusion(dense, q0)
        # 3) Rerank + balance
        ranked = self.rerank_balance(fused, intent=intent)
        # 4) Confiance
        conf = self.estimate_confidence(ranked)

        # 5) Expansion sémantique contrôlée si confiance faible
        if conf < CONF_MIN:
            expansions = [
                q0 + " IT STORM consulting",
                q0 + " RAG IT STORM",
                q0 + " cloud data devops IT STORM",
            ]
            best_ranked, best_conf = ranked, conf
            for qx in expansions:
                d2 = self.retrieve_dense(qx, max(12, TOP_K_DENSE // 2))
                f2 = self.late_fusion(d2, qx)
                r2 = self.rerank_balance(f2, intent=intent)
                c2 = self.estimate_confidence(r2)
                if c2 > best_conf:
                    best_ranked, best_conf = r2, c2
            ranked, conf = best_ranked, best_conf

        # 6) Construction de réponse (strictement extractive)
        if conf < CONF_MIN:
            ans, srcs, qts = self.build_fallback(ranked)
        else:
            if intent == "benefits":
                ans, srcs, qts = self.build_answer_benefits(ranked)
            elif intent == "howto":
                ans, srcs, qts = self.build_generic_from_quotes("Procédure recommandée", ranked)
            elif intent == "definition":
                ans, srcs, qts = self.build_definition(ranked)
            elif intent == "risks":
                ans, srcs, qts = self.build_generic_from_quotes("Risques & atténuations", ranked)
            elif intent == "architecture":
                ans, srcs, qts = self.build_generic_from_quotes("Architecture & Solution", ranked)
            elif intent == "budget":
                ans, srcs, qts = self.build_generic_from_quotes("Budget & Effort", ranked)
            elif intent == "roadmap":
                ans, srcs, qts = self.build_generic_from_quotes("Prochaines étapes", ranked)
            else:
                quotes = self.make_quotes(ranked, MAX_QUOTES)
                if not quotes or len(quotes) < MIN_QUOTES_OK:
                    ans, srcs, qts = self.build_fallback(ranked)
                else:
                    header = "Réponse ancrée sur les documents internes :"
                    out = [header, ""]
                    for qt in quotes:
                        out.append(f"- *« {qt['quote']} »* ({qt['source']})")
                    ans = humanize_fr("\n".join(out))
                    srcs = sorted(set(q["source"] for q in quotes))
                    qts = quotes

        # --- Post-traitement : tout en un seul paragraphe (zéro hallucination)
        if SINGLE_PARAGRAPH and qts and len(qts) >= MIN_QUOTES_OK:
            ans = paragraphize_from_quotes(qts, intent)

        # Humanize quotes
        for q in qts:
            q["quote"] = humanize_fr(q["quote"])

        quality = self.quality_scores(ans, qts, ranked)
        dbg = {
            "intent": intent,
            "top_sources": [_norm_base(c.source) for c in ranked],
            "top_scores": [round(c.score_final, 3) for c in ranked],
            "conf_threshold": CONF_MIN,
        }
        return SmartRAGResult(answer=ans, sources=srcs, quotes=qts, confidence=conf, quality=quality, dbg=dbg)

# === Jury Ollama (optionnel) =================================================
def ask_multi_ollama(
    question: str,
    models: Optional[List[str]] = None,
    topk_context: int = 6,
    timeout: float = 60.0
) -> Dict[str, Any]:
    """
    Pose la même question à plusieurs modèles Ollama avec un contexte EXTRACTIF
    (snippets RAG), calcule des métriques et recommande le meilleur.
    Retourne:
      {
        "question": ...,
        "context_snippets": [...],
        "results": [{"model","answer","time","metrics","score"}...],
        "suggestion": {"model","score","time"}
      }
    """
    models = models or [
        "mistral:7b-instruct",
        "llama3.2:3b",
        "qwen2.5:7b",
    ]

    # 1) Récupère un petit contexte strictement extractif via le moteur existant
    eng = get_engine()
    ranked = eng.rerank_balance(
        eng.late_fusion(eng.retrieve_dense(question, k=TOP_K_DENSE), question),
        intent=detect_intent(question)
    )
    quotes = eng.make_quotes(ranked, max_quotes=min(max(3, topk_context), MAX_QUOTES))
    snippets = [q["quote"] for q in quotes]
    context = "\n\n".join(f"- {s}" for s in snippets) if snippets else ""

    if not context.strip():
        return {
            "question": question,
            "context_snippets": [],
            "results": [],
            "suggestion": None
        }

    # 2) Prompt "réponse UNIQUEMENT depuis le contexte"
    prompt = (
        "Tu es un assistant interne. Réponds UNIQUEMENT depuis le contexte ci-dessous.\n"
        "- Réponse courte (1 paragraphe, 2–4 phrases), claire, sans puces.\n"
        "- Si l'info manque, réponds: \"Je ne sais pas.\".\n"
        "- Ajoute une citation [Source: extrait] à la fin.\n\n"
        f"Question : {question}\n\nContexte :\n{context}\n\nRéponse :"
    )

    # 3) Appels Ollama
    try:
        from src.llm.ollama_client import generate_ollama, ping, list_models
    except Exception as e:
        return {
            "question": question,
            "context_snippets": snippets,
            "results": [{"model":"(ollama)", "answer": f"[Erreur import ollama_client] {e}", "time": 0.0, "metrics": {}}],
            "suggestion": None
        }

    try:
        if not ping():
            raise RuntimeError("Ollama n'est pas joignable (ping KO).")
    except Exception as e:
        return {
            "question": question,
            "context_snippets": snippets,
            "results": [{"model":"(ollama)", "answer": f"[Ping Ollama KO] {e}", "time": 0.0, "metrics": {}}],
            "suggestion": None
        }

    import time, re

    def _coverage(ans: str, ctx_parts: List[str]) -> float:
        if not ans or not ctx_parts: return 0.0
        ans_low = ans.lower()
        total = 0.0
        for s in ctx_parts:
            s_low = s.lower()
            if not s_low.strip(): continue
            aw = set(re.findall(r"\w+", ans_low))
            sw = set(re.findall(r"\w+", s_low))
            if not sw: continue
            inter = len(aw & sw); union = len(sw)
            total += inter / max(1, union)
        return round(total / max(1, len(ctx_parts)), 2)

    def _style(ans: str) -> float:
        if not ans: return 0.0
        L = len(ans.strip())
        has_src = "[source:" in ans.lower()
        punc = 1.0 if re.search(r"[.;!?]", ans) else 0.8
        if 60 <= L <= 400: base = 1.0
        elif L < 40: base = 0.6
        else: base = 0.8
        return round(min(1.0, base * (1.05 if has_src else 1.0) * punc), 2)

    def _grounding(ans: str) -> float:
        has_src = "[source:" in (ans or "").lower()
        cov = _coverage(ans, snippets)
        if has_src and cov >= 0.10: return round(min(1.0, 0.85 + 0.15*cov), 2)
        return round(max(0.0, 0.6*cov), 2)

    def _confidence(ans: str) -> float:
        g = _grounding(ans); cov = _coverage(ans, snippets); sty = _style(ans)
        L = len((ans or "").strip())
        len_score = 1.0 if 60 <= L <= 400 else (0.7 if L > 400 else 0.6)
        conf = 0.45*g + 0.25*cov + 0.20*len_score + 0.10*sty
        if g >= 0.95 and cov >= 0.30 and 60 <= L <= 220:
            conf = max(conf, 0.95)
        return round(min(1.0, max(0.0, conf)), 2)

    def _score(m):
        return round(0.4*m.get("confidence",0) + 0.3*m.get("grounding",0) + 0.2*m.get("coverage",0) + 0.1*m.get("style",0), 3)

    results = []
    for mdl in models:
        t0 = time.time()
        try:
            ans = generate_ollama(
                mdl, prompt,
                temperature=0.0,
                max_tokens=180,
                stream=True,
                timeout=float(timeout),
                options={"num_ctx": 1536, "top_k": 40, "top_p": 0.9, "repeat_penalty": 1.1}
            )
            if "[source:" not in ans.lower():
                ans = ans.rstrip() + " [Source: extrait]"
            dt = time.time() - t0
            metrics = {
                "coverage": _coverage(ans, snippets),
                "grounding": _grounding(ans),
                "style": _style(ans),
            }
            metrics["confidence"] = _confidence(ans)
            score = _score(metrics)
            results.append({"model": mdl, "answer": ans, "time": round(dt,2), "metrics": metrics, "score": score})
        except Exception as e:
            dt = time.time() - t0
            results.append({"model": mdl, "answer": f"[Erreur LLM {mdl}] {e}", "time": round(dt,2), "metrics": {}, "score": 0.0})

    valid = [r for r in results if not r["answer"].strip().startswith("[Erreur LLM")]
    suggestion = max(valid, key=lambda x: x["score"]) if valid else None
    return {
        "question": question,
        "context_snippets": snippets,
        "results": results,
        "suggestion": {"model": suggestion["model"], "score": suggestion["score"], "time": suggestion["time"]} if suggestion else None
    }

# ===== Singleton & wrapper =====
_engine_singleton: Optional[SmartRAG] = None

def get_engine() -> SmartRAG:
    global _engine_singleton
    if _engine_singleton is None:
        _engine_singleton = SmartRAG(
            db_path=DEFAULT_DB_PATH,
            collection_name=DEFAULT_COLLECTION,
            embed_model_name=EMBED_MODEL_NAME,
        )
    return _engine_singleton

# Wrapper *ultra-robuste* pour compat UI (ignore lang/mode/...)
def smart_rag_answer(*args, **kwargs) -> Dict[str, Any]:
    """
    UI legacy-friendly :
      - question en positionnel ou nommé
      - lang/mode ignorés
      - sortie standardisée
    """
    question = None
    if args:
        question = args[0]
    if question is None:
        question = kwargs.get("question") or kwargs.get("q") or ""
    eng = get_engine()
    r = eng.ask(question=str(question).strip())
    return {
        "answer": r.answer,
        "sources": r.sources,
        "quotes": r.quotes,
        "confidence": r.confidence,
        "quality": r.quality,
        "dbg": r.dbg,
    }

# ===== Aides debug (optionnelles) =====
def debug_list_sources(limit: int = 50) -> List[str]:
    """Retourne une liste de basenames (normalisés) visibles via retrieve_dense."""
    eng = get_engine()
    dense = eng.retrieve_dense("it storm consulting cloud data ia rag", k=limit)
    return sorted({_norm_base(c.source) for c in dense})

def debug_has_file(name: str) -> bool:
    """Vérifie rapidement si un fichier (basename) est visible côté index."""
    target = _norm_base(name)
    return target in set(debug_list_sources(200))

# ===== Chunking utilitaire pour (ré)indexation =====
def _split_chunks(text: str, max_words: int = 220, sep_pattern: str = r"\n{2,}") -> List[str]:
    """
    Découpe un long .txt en petits blocs (≈220 mots) pour de meilleures citations.
    """
    parts = re.split(sep_pattern, text or "")
    out, buf, count = [], [], 0
    for p in parts:
        p = (p or "").strip()
        if not p:
            continue
        n = len(p.split())
        if count + n > max_words and buf:
            out.append("\n".join(buf))
            buf, count = [p], n
        else:
            buf.append(p)
            count += n
    if buf:
        out.append("\n".join(buf))
    return [c for c in out if c.strip()]

# ===== Maintenance / Réindexation =====
def reindex_txt_file(filepath: str,
                     source_basename: Optional[str] = None,
                     max_words: int = 220) -> Dict[str, Any]:
    """
    Réindexe un fichier .txt dans la collection Chroma en fixant la métadonnée 'source'
    au basename fourni (ou déduit). Purge d'abord l'ancienne source si présente.
    """
    eng = get_engine()
    if not os.path.exists(filepath):
        return {"status": "error", "error": f"File not found: {filepath}"}

    base = _norm_base(source_basename or os.path.basename(filepath))
    if _ext(base) != ".txt":
        base = (base.rsplit(".", 1)[0] if "." in base else base) + ".txt"

    with open(filepath, "r", encoding="utf-8", errors="ignore") as f:
        text = f.read()
    chunks = _split_chunks(text, max_words=max_words)
    if not chunks:
        return {"status": "error", "error": "No chunks produced from file.", "source": base}

    purged = False
    try:
        eng.col.delete(where={"source": base})
        purged = True
    except Exception:
        purged = False  # versions anciennes de Chroma peuvent ne pas supporter where

    ids = [f"{base}::{uuid.uuid4().hex}" for _ in chunks]
    metas = [{"source": base, "id": ids[i]} for i in range(len(ids))]
    eng.col.add(ids=ids, documents=chunks, metadatas=metas)

    return {
        "status": "ok",
        "source": base,
        "n_chunks": len(chunks),
        "purged_before": purged,
    }

def ensure_qa_indexed(possible_paths: Optional[List[str]] = None) -> Dict[str, Any]:
    """
    Vérifie si 'it_storm_1000_QA.txt' est visible côté index (via retrieve_dense).
    Si absent, tente de le (ré)indexer depuis QA_DEFAULT_PATH ou une liste fournie.
    """
    if debug_has_file(QA_BASENAME):
        return {"status": "present", "source": QA_BASENAME}

    paths = possible_paths or [QA_DEFAULT_PATH]
    for p in paths:
        if os.path.exists(p):
            res = reindex_txt_file(filepath=p, source_basename=QA_BASENAME, max_words=220)
            if res.get("status") == "ok" and debug_has_file(QA_BASENAME):
                return {"status": "reindexed", "source": QA_BASENAME, **res}
            else:
                return {"status": "error", "tried": p, "detail": res}

    return {"status": "missing", "tried": paths, "hint": "Place the file and call ensure_qa_indexed([...])"}
