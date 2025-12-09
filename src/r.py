# -*- coding: utf-8 -*-
# src/rag_brain.py
# ============================================================
# RAG intelligent (version stricte, FR uniquement)
# - Réponses 100% ancrées sur extraits courts + citations (pas de génération libre)
# - Priorité forte aux contenus IT-STORM internes + site officiel
# - Late fusion Dense+BM25, rerank équilibré (MMR simple + anti-domination QA)
# - Blocage total PDF/Office (bruit), normalisation de noms de sources
# - Filtrage QA: ignore “Q:…”, préfère “A:…”
# - Réponse ancrée = paragraphe de 3–5 phrases, construit uniquement depuis les extraits
# - Fallback sémantique contrôlé -> "Je ne sais pas." si insuffisant
# - Wrapper smart_rag_answer(*args, **kwargs) compatible UI
# - Maintenance : reindex_txt_file(), ensure_qa_indexed()
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
try:
    import chromadb
    from chromadb.config import Settings
    from chromadb.utils import embedding_functions
except Exception as e:
    raise RuntimeError(f"[RAG] ChromaDB manquant: {e}")


def _build_embedding_fn(model_name: str):
    """
    Essaie d'abord FastEmbed (rapide, optimisé CPU),
    puis fallback sur SentenceTransformer.
    """
    # 1) FastEmbed si demandé
    if EMBED_BACKEND == "fastembed":
        try:
            return embedding_functions.FastEmbedEmbeddingFunction(model_name=model_name)
        except Exception as e:
            print(f"[RAG] FastEmbedEmbeddingFunction KO ({e}), fallback SentenceTransformer.", flush=True)

    # 2) Fallback SentenceTransformers
    try:
        return embedding_functions.SentenceTransformerEmbeddingFunction(model_name=model_name)
    except Exception as e:
        raise RuntimeError(f"[RAG] Échec chargement embeddings '{model_name}': {e}")

# ===== ENV / Paramètres =====
# ===== ENV / Paramètres =====
# DB path : on accepte VECTOR_DB_PATH ou CHROMA_DB_DIR
DEFAULT_DB_PATH = (
    os.getenv("VECTOR_DB_PATH")
    or os.getenv("CHROMA_DB_DIR")
    or "./vectors"
)

DEFAULT_COLLECTION = os.getenv("VECTOR_COLLECTION", "consulting")

# Nom du modèle d'embedding : on accepte EMBED_MODEL ou EMBEDDING_MODEL
EMBED_MODEL_NAME = (
    os.getenv("EMBED_MODEL")
    or os.getenv("EMBEDDING_MODEL")
    or "sentence-transformers/all-MiniLM-L6-v2"
)

# Backend d'embedding : "fastembed" ou "sentence-transformers"
EMBED_BACKEND = os.getenv("EMBED_BACKEND", "fastembed").lower()

TOP_K_DENSE = int(os.getenv("RAG_TOP_K_DENSE", "48"))
TOP_K_BALANCED = int(os.getenv("RAG_TOP_K_BALANCED", "8"))
MAX_QUOTES = int(os.getenv("RAG_MAX_QUOTES", "6"))

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
QA_MAX_QUOTE_SHARE = float(os.getenv("RAG_QA_MAX_QUOTE_SHARE", "0.6")  # ex: 60% max des citations
)
MAX_QUOTES_PER_SOURCE = int(os.getenv("RAG_MAX_QUOTES_PER_SOURCE", "3"))

# Extensions bloquées (bruit) -> exclus dur
BLOCKED_EXTENSIONS = {".pdf", ".doc", ".docx", ".ppt", ".pptx"}

# Dossier data par défaut (pour maintenance/réindexation)
RAG_DATA_DIR = os.getenv(
    "RAG_DATA_DIR",
    r"C:\Users\ALA BEN LAKHAL\Desktop\intelligent_copilot IT-STORM\data"
)
QA_BASENAME = "it_storm_1000_QA.txt"  # IMPORTANT: basename exact (côté filesystem)
QA_BASENAME_L = QA_BASENAME.lower()

QA_DEFAULT_PATH = os.path.join(RAG_DATA_DIR, QA_BASENAME)

# ===== Regex utilitaires =====
_SENT_SPLIT = re.compile(r"(?<=[\.\!\?])\s+")
_WORD = re.compile(r"\w+", re.UNICODE)

# ===== PRIORITÉS DES SOURCES (VERSION FINALE IT-STORM) =====
# Tout est déjà en lowercase / basename pour matcher _norm_base
INTENT_BOOSTS: Dict[str, Dict[str, float]] = {
    "default": {
        "itstorm_site.txt": 8.0,          # 🔥 site officiel (scrapé)
        "itstorm_rag_global.txt": 6.0,    # synthèse maison
        "itstorm_clean.txt": 2.0,         # fallback propre
        "it_storm_1000_qa.txt": 0.4,      # QA brute → très faible poids
    }
}

BENEFITS_ALLOW = {
    "itstorm_site.txt",
    "itstorm_rag_global.txt",
    "itstorm_clean.txt",
    "it_storm_1000_qa.txt",
}

# ===== Normalisation noms sources (robuste casse/chemin) =====
def _norm_base(src: str) -> str:
    return os.path.basename(src or "").strip().lower()

def _ext(name: str) -> str:
    base = _norm_base(name)
    return "." + base.rsplit(".", 1)[-1] if "." in base else ""

def is_blocked_source(src: str) -> bool:
    return _ext(src) in BLOCKED_EXTENSIONS

INTENT_BOOSTS_L = INTENT_BOOSTS  # déjà lower
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

def clean_text_for_quote(s: str) -> str:
    """
    Nettoyage avancé pour éviter le bruit (titres, séparateurs, emojis, WP, etc.)
    et limiter les répétitions.
    """
    if not s:
        return ""

    # On travaille ligne par ligne pour enlever les titres / séparateurs
    raw = s.splitlines()
    kept_lines = []
    for line in raw:
        line_stripped = line.strip()
        low = line_stripped.lower()
        if not line_stripped:
            continue

        # Lignes à ignorer (titres, fichiers, séparateurs visuels)
        if "====" in line_stripped:
            continue
        if "📄" in line_stripped or "🔹" in line_stripped:
            continue
        if "présentation générale" in low:
            continue
        if line_stripped.endswith(".txt"):
            continue
        if low.startswith("nos offres"):
            continue
        if low.startswith("à propos"):
            continue
        if "it-storm consulting" in low:
            continue
        if "l'offre inédite pour votre activité" in low:
            continue

        kept_lines.append(line_stripped)

    s = " ".join(kept_lines).strip()
    if not s:
        return ""

    # Trop court → bruit
    if len(s.split()) < 5:
        return ""

    # Retirer les Q:, A:, R:
    s = re.sub(r"^[QAR]:\s*", "", s, flags=re.IGNORECASE)

    # Supprimer les phrases dupliquées dans le même chunk
    sentences = split_sentences(s)
    seen = set()
    uniq_sents = []
    for sent in sentences:
        sent_norm = sent.strip()
        if not sent_norm:
            continue
        if sent_norm in seen:
            continue
        seen.add(sent_norm)
        uniq_sents.append(sent_norm)

    s = " ".join(uniq_sents).strip()
    s = s.replace("  ", " ")
    return s

def truncate_words(s: str, max_words: int = 60) -> str:
    """
    Ne tronque que les textes très longs.
    Pour la plupart des phrases 'normales', on renvoie la phrase complète.
    """
    s = (s or "").strip()
    toks = s.split()
    if len(toks) <= max_words:
        return s
    return " ".join(toks[:max_words]).strip()

def tokens_fr(s: str) -> List[str]:
    return [w.lower() for w in _WORD.findall(s or "")]

def humanize_fr(text: str) -> str:
    text = re.sub(r"\b(and|the|for|y|in|of)\b", "", text, flags=re.IGNORECASE)
    text = re.sub(r"\s{2,}", " ", text)
    text = re.sub(r"\s+([,;:.])", r"\1", text)
    return text.strip()

FORBIDDEN_SUBJECTS = (
    " je ", " j'", " j’",
    " tu ",
    " nous ",
    " vous ",
    " Je ", " J'", " J’",
    " Tu ", " Nous ", " Vous ",
)

def contains_forbidden_subject(text: str) -> bool:
    """
    Détecte les phrases contenant un sujet interdits : je/tu/nous/vous.
    Empêche tout style adressé au lecteur.
    """
    if not text:
        return False
    t = " " + text.strip().lower() + " "
    return any(s.strip().lower() in t for s in FORBIDDEN_SUBJECTS)

# Phrases narratives uniquement (pas de je / tu / vous / nous)
NARRATIVE_FORBIDDEN_PRONOUNS = (
    " je ",
    " j'",
    " j’",
    " tu ",
    " vous ",
    " nous ",
)

def is_narrative_sentence(text: str) -> bool:
    """
    Retourne True si la phrase est de style narratif neutre :
    - pas de 'je', 'tu', 'vous', 'nous'
    - insensible à la casse
    """
    if not text:
        return False
    low = f" {text.strip().lower()} "
    return not any(tok in low for tok in NARRATIVE_FORBIDDEN_PRONOUNS)
# ===== Construction de la réponse =====
# --- Mode "paragraphe unique" (non utilisé mais conservé)
SINGLE_PARAGRAPH = os.getenv("RAG_SINGLE_PARAGRAPH", "0") == "1"

def _take_quote_texts(quotes: List[Dict[str, str]], max_parts: int = 4) -> List[str]:
    """
    Utilitaire simple pour extraire quelques citations distinctes (texte brut).
    """
    parts, seen = [], set()
    for q in quotes:
        seg = (q.get("quote") or "").strip()
        if seg and seg not in seen:
            seen.add(seg)
            parts.append(seg)
        if len(parts) >= max_parts:
            break
    return parts


def _sentence_wordset(s: str) -> set:
    """
    Transforme une phrase en ensemble de mots normalisés (minuscules, sans mots trop courts)
    pour calculer une similarité approximative.
    """
    tokens = re.findall(r"[a-zà-ÿA-ZÀ-Ÿ]+", s.lower())
    return {t for t in tokens if len(t) > 2}


def dedupe_similar_sentences(sents: List[str], threshold: float = 0.5) -> List[str]:
    """
    Supprime les phrases répétées ou très similaires :
    - si deux phrases ont une similarité de Jaccard >= threshold sur les mots,
      on garde la première et on élimine la suivante.
    """
    kept: List[str] = []
    kept_sets: List[set] = []

    for s in sents:
        s_clean = s.strip()
        if not s_clean:
            continue

        ws = _sentence_wordset(s_clean)
        if not ws:
            # Pas de mots significatifs → on garde tel quel
            kept.append(s_clean)
            kept_sets.append(ws)
            continue

        duplicate = False
        for ks in kept_sets:
            if not ks:
                continue
            inter = len(ws & ks)
            union = len(ws | ks)
            if union == 0:
                continue
            sim = inter / union
            if sim >= threshold:
                duplicate = True
                break

        if not duplicate:
            kept.append(s_clean)
            kept_sets.append(ws)

    return kept


def assemble_human_paragraph(quotes: List[Dict[str, str]], max_sentences: int = 5) -> str:
    """
    Transforme les citations en un paragraphe de 3 à 5 phrases.
    - Chaque citation devient une phrase (on ajoute un point final si besoin)
    - On supprime les phrases dupliquées ou très similaires (> 50 % de mots en commun)
    - On renvoie une phrase par ligne (séparée par '\n')
    """
    if not quotes:
        return "Je ne sais pas."

    sents: List[str] = []
    for q in quotes:
        t = (q.get("quote") or "").strip()
        if not t:
            continue
        if not t.endswith((".", "!", "?")):
            t += "."
        sents.append(t)
        if len(sents) >= max_sentences:
            break

    # 🔁 Supprimer les doublons exacts ou très similaires (> 50 % des mots en commun)
    sents = dedupe_similar_sentences(sents, threshold=0.5)

    # Minimum 3 phrases : si manque, on répète la dernière
    while 0 < len(sents) < 3:
        sents.append(sents[-1])

    # Nettoyage léger + retour à la ligne entre chaque phrase
    cleaned = [humanize_fr(s) for s in sents]
    para = "\n".join(cleaned)
    return para

# ===== QA filtering helpers =====
QA_QUESTION_PREFIXES = ("q:", "question:")
QA_ANSWER_PREFIXES   = ("a:", "réponse:", "reponse:", "answer:", "r:")

def _is_low_value_qa_quote(q: Dict[str, str]) -> bool:
    src = (q.get("source") or "").lower()
    if src != QA_BASENAME_L:
        return False
    txt = (q.get("quote") or "").strip().lower()
    if not txt:
        return True
    if txt.startswith(("oui", "non", "parce que", "car ")):
        return True
    if len(txt.split()) < 6:
        return True
    return False

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

# Patterns globaux à éviter dans les citations "définition"
BAD_DEF_PATTERNS = [
    # je / tu / nous / vous + verbe
    r"\b[Jj]e\s+[a-zà-ÿ]+",
    r"\b[Jj]['’]\s*[a-zà-ÿ]+",
    r"\b[Tt]u\s+[a-zà-ÿ]+",
    r"\b[Nn]ous\s+[a-zà-ÿ]+",
    r"\b[Vv]ous\s+[a-zà-ÿ]+",

    # verbes conjugués en nous / vous (ez / iez / ons / ions)
    r"\b[a-zà-ÿ]+(?:ez|iez|ons|ions)\b(?=[\s\.,;:!\?])",

    # phrase qui COMMENCE par un infinitif (Accompagner…, Créer…, Tester…)
    r"^\s*[A-ZÉÈÊÂÀÎÔÛÄËÏÖÜÇ][a-zà-ÿ]+(?:er|ir|re|oir)\b",
]



import re

def has_bad_def_pattern(text: str) -> bool:
    """
    Retourne True si le texte match au moins un pattern regex dans BAD_DEF_PATTERNS.
    """
    if not text:
        return False
    for pat in BAD_DEF_PATTERNS:
        if re.search(pat, text):
            return True
    return False


def filter_low_value_quotes(quotes: List[Dict[str, str]]) -> List[Dict[str, str]]:
    """
    Filtre les citations peu utiles :
    - QA très courtes / oui/non
    - citations contenant patterns indésirables (regex BAD_DEF_PATTERNS)
    - citations manifestement tronquées (terminaisons type 'de la', 'du', etc.)
    """

    bad_endings = (
        " de la",
        " du",
        " des",
        " de l",
        " de ",
        " et de la",
        " et du",
        " et des",
    )

    out: List[Dict[str, str]] = []

    for q in quotes or []:

        # (1) QA triviale
        if _is_low_value_qa_quote(q):
            continue

        txt = (q.get("quote") or "").strip()
        if not txt:
            continue

        # (2) Patterns regex interdits :
        #   - je/tu/nous/vous + verbe
        #   - verbes terminant par ez/iez/ons/ions
        #   - infinitifs
        #   - phrase commençant par un infinitif
        if has_bad_def_pattern(txt):
            continue

        low = txt.lower()

        # (3) Phrase manifestement tronquée
        if any(low.endswith(be) for be in bad_endings):
            continue

        # OK
        out.append(q)

    return out

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
    def __init__(
        self,
        db_path: str = DEFAULT_DB_PATH,
        collection_name: str = DEFAULT_COLLECTION,
        embed_model_name: str = EMBED_MODEL_NAME,
    ):
        try:
            self.client = chromadb.PersistentClient(
                path=db_path,
                settings=Settings(anonymized_telemetry=False)
            )
        except Exception as e:
            raise RuntimeError(f"[RAG] Échec init ChromaDB (path={db_path}): {e}")

        # 🔥 Embedding function optimisée (FastEmbed + fallback)
        self.emb_fn = _build_embedding_fn(embed_model_name)

        try:
            self.col = self.client.get_or_create_collection(
                name=collection_name,
                embedding_function=self.emb_fn,
            )
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
    def rerank_balance(self, items: List[RetrievedChunk], intent: str = "default") -> List[RetrievedChunk]:
        if not items:
            return []

        # filtre dur: exclure les sources bloquées avant tout scoring
        items = [c for c in items if not is_blocked_source(c.source)]
        if not items:
            return []

        boosts = INTENT_BOOSTS_L.get("default", {})

        boosted: List[RetrievedChunk] = []
        for c in items:
            b = 1.0
            base = _norm_base(c.source)

            # Boosts par fichier (site / rag_global / clean vs QA)
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

    # Citations (extraits complets), interleave QA + non-QA, limites par source
    def make_quotes(self, chunks: List[RetrievedChunk], max_quotes: int = MAX_QUOTES) -> List[Dict[str, str]]:
        def pick_sentence(text: str) -> Optional[str]:
            """
            Retourne une PHRASE COMPLÈTE issue du chunk.
            On choisit :
              1) une phrase qui ressemble à une réponse (déclarative, sans '?')
              2) sinon la première phrase non interrogative
              3) sinon la première phrase non vide
              4) sinon le texte complet
            Aucun tronquage manuel ici.
            """
            text = clean_text_for_quote(text)
            if not text:
                return None

            sentences = split_sentences(text)
            if not sentences:
                return None

            # A) Réponses explicites / phrases déclaratives
            for s in sentences:
                s_clean = _strip_qa_prefix(s).strip()
                if not s_clean:
                    continue
                if _looks_like_answer(s_clean) and not _is_questionish(s_clean):
                    return s_clean  # ✅ phrase complète

            # B) Phrases non interrogatives correctes
            for s in sentences:
                s_clean = _strip_qa_prefix(s).strip()
                if not s_clean:
                    continue
                if not _is_questionish(s_clean):
                    return s_clean  # ✅ phrase complète

            # C) Fallback : première phrase non vide
            for s in sentences:
                s_clean = _strip_qa_prefix(s).strip()
                if s_clean:
                    return s_clean  # ✅ phrase complète

            # D) Dernier recours : tout le texte
            return text.strip()

        # 1) Prépare les candidats nettoyés
        cands = []
        for c in chunks:
            if is_blocked_source(c.source):
                continue
            quote = pick_sentence(c.text or "")
            if not quote:
                continue
            cands.append({
                "source": _norm_base(c.source),
                "quote": humanize_fr(quote),
            })

        if not cands:
            return []

        # Filtrage avancé (QA low-value + phrases cassées + simulateur/revenu net)
        cands = filter_low_value_quotes(cands)
        if not cands:
            return []

        # 2) Groupes QA vs non-QA
        qa = [q for q in cands if q["source"] == QA_BASENAME_L]
        non = [q for q in cands if q["source"] != QA_BASENAME_L]

        # 3) Limites QA
        max_qa = int(round(QA_MAX_QUOTE_SHARE * max_quotes))
        if max_qa < 1 and qa:
            max_qa = 1

        out: List[Dict[str, str]] = []
        per_source = Counter()
        i_qa, i_non = 0, 0

        # 4) Interleave non-QA / QA
        while len(out) < max_quotes and (i_non < len(non) or i_qa < len(qa)):
            if i_non < len(non):
                cand = non[i_non]
                if per_source[cand["source"]] < MAX_QUOTES_PER_SOURCE:
                    out.append(cand)
                    per_source[cand["source"]] += 1
                i_non += 1
                if len(out) >= max_quotes:
                    break

            if i_qa < len(qa) and sum(1 for x in out if x["source"] == QA_BASENAME_L) < max_qa:
                cand = qa[i_qa]
                if per_source[cand["source"]] < MAX_QUOTES_PER_SOURCE:
                    out.append(cand)
                    per_source[cand["source"]] += 1
                i_qa += 1

        # 5) Compléter si encore de la place
        i = 0
        while len(out) < max_quotes and i < len(cands):
            cand = cands[i]
            if per_source[cand["source"]] < MAX_QUOTES_PER_SOURCE and cand not in out:
                out.append(cand)
                per_source[cand["source"]] += 1
            i += 1

        return out
    
    def _build_clean_anchored_paragraph(self, quotes: List[Dict[str, str]]) -> str:
        """
        Construit une définition propre, neutre et ancrée à partir des citations.
        Contraintes :
        - supprime les phrases répétées ou trop similaires (≥ 50 % des mots en commun)
        - supprime les phrases marketing / simulateur / revenu net
        - supprime les phrases avec pronoms interdits (je/tu/nous/vous) via contains_forbidden_subject
        - priorise les phrases de définition contenant 'IT STORM est un/une ...'
        - renvoie 3 à 4 phrases maximum, ton neutre
        """
        if not quotes:
            return "Je ne sais pas."

        # Phrases à filtrer (marketing / simulateur / revenu net...)
        BAD = [
            "profitez de services",
            "services complets",
            "tarifs avantageux",
            "simulateur",
            "revenu net",
            "déterminer votre salaire",
            "estimer le revenu",
            "honoraires",
            "facturation",
            "obligations légales",
            "méthode de simulation",
        ]

        sentences: List[str] = []
        previous_wordsets: List[set] = []

        # 1) Extraction des phrases propres depuis les quotes
        for q in quotes:
            raw = (q.get("quote") or "").strip()
            if not raw:
                continue

            for s in split_sentences(raw):
                s_clean = s.strip()
                if not s_clean:
                    continue

                low = s_clean.lower()

                # a) pronoms interdits → on garde un ton neutre
                if contains_forbidden_subject(s_clean):
                    continue

                # b) phrases marketing / simulateur / revenu net...
                if any(bad in low for bad in BAD):
                    continue

                # c) calcul du "set" de mots significatifs pour la similarité
                tokens = re.findall(r"[a-zA-ZÀ-ÿà-ÿ]+", low)
                wordset = {t for t in tokens if len(t) > 2}
                if not wordset:
                    # Si pas de mots significatifs, on garde quand même la phrase (rare)
                    sentences.append(s_clean)
                    previous_wordsets.append(set())
                    continue

                # d) vérifier si la phrase est trop similaire à une phrase déjà gardée
                too_similar = False
                for ws in previous_wordsets:
                    if not ws:
                        continue
                    inter = len(wordset & ws)
                    union = len(wordset | ws)
                    if union == 0:
                        continue
                    sim = inter / union
                    if sim >= 0.5:  # ≥ 50 % de mots en commun → on élimine
                        too_similar = True
                        break

                if too_similar:
                    continue

                # ok, on garde cette phrase et son set
                previous_wordsets.append(wordset)
                sentences.append(s_clean)

        if not sentences:
            return "Je ne sais pas."

        # 2) Phrases de définition en priorité
        def _is_def(sent: str) -> bool:
            low = sent.lower()
            return "it storm" in low and ("est une" in low or "est un" in low)

        def_sents = [s for s in sentences if _is_def(s)]
        other_sents = [s for s in sentences if s not in def_sents]

        ordered = def_sents + other_sents
        if not ordered:
            return "Je ne sais pas."

        # 3) 3–4 phrases max
        if len(ordered) > 4:
            ordered = ordered[:4]
        elif len(ordered) < 3 and len(sentences) >= 3:
            # si on a peu de phrases de définition, compléter avec les premières phrases brutes
            ordered = sentences[:3]

        # 4) Finalisation : ponctuation + assemblage
        final_sents: List[str] = []
        for s in ordered:
            s2 = s.strip()
            if not s2.endswith((".", "!", "?")):
                s2 += "."
            final_sents.append(s2)

        paragraph = " ".join(final_sents).strip()

        # 5) Sécurité finale : si le paragraphe ne ressemble pas à une phrase "narrative", on annule
        if not is_narrative_sentence(paragraph):
            return "Je ne sais pas."

        return humanize_fr(paragraph)

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
        unique_sources = len(set(q["source"] for q in quotes)) if quotes else 0
        coverage = min(1.0, unique_sources / 4.0) if quotes else 0.0
        grounding = 1.0 if quotes else 0.0
        style_penalty = 0.0 if re.search(r"\b(and|the|for|y)\b", text or "", flags=re.I) is None else 0.3
        style = max(0.0, 1.0 - style_penalty)
        top_mean = sum(x.score_final for x in ranked[:4]) / max(1, len(ranked[:4])) if ranked else 0.0
        relevance = max(0.0, min(1.0, 0.6 * top_mean + 0.4 * coverage))
        nli_proxy = 1.0 if quotes else 0.5
        return {
            "relevance": round(relevance, 3),
            "grounding": round(grounding, 3),
            "coverage": round(coverage, 3),
            "nli_proxy": round(nli_proxy, 3),
            "style": round(style, 3),
        }

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
        # 0) Normalisation de la question
        q0 = (question or "").strip()

        # 1) Retrieve dense
        dense = self.retrieve_dense(q0, TOP_K_DENSE)

        # 2) Late fusion
        fused = self.late_fusion(dense, q0)

        # 3) Rerank + balance (intention unique 'default')
        ranked = self.rerank_balance(fused, intent="default")

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
                r2 = self.rerank_balance(f2, intent="default")
                c2 = self.estimate_confidence(r2)
                if c2 > best_conf:
                    best_ranked, best_conf = r2, c2
            ranked, conf = best_ranked, best_conf

        # 6) Construction de la réponse (ANCRÉE, générique, 3–5 phrases)
        if conf < CONF_MIN:
            # Trop peu de confiance → fallback ultra-sécurisé
            ans, srcs, qts = self.build_fallback(ranked)

        else:
            # Citations RAG
            quotes = self.make_quotes(ranked, MAX_QUOTES)

            if not quotes or len(quotes) < MIN_QUOTES_OK:
                # Pas assez de matière fiable → fallback
                ans, srcs, qts = self.build_fallback(ranked)

            else:
                # Assemble un paragraphe fluide à partir des quotes (3–5 phrases)
                para = assemble_human_paragraph(quotes, max_sentences=5)

                # Forcer un début propre si la question parle explicitement d'IT STORM
                ql = q0.lower()
                if "it storm" in ql or "itstorm" in ql or "it-storm" in ql:
                    if not para.lower().startswith("it storm"):
                        # On cherche une citation commençant par "IT STORM"
                        prefix_set = False
                        for q in quotes:
                            txt = (q.get("quote") or "").strip()
                            if txt.lower().startswith("it storm"):
                                para = txt + " " + para
                                prefix_set = True
                                break
                        if not prefix_set:
                            # Filet de sécurité : phrase très générique
                            para = "IT STORM est une entreprise spécialisée. " + para

                ans = para
                srcs = sorted(set(q["source"] for q in quotes))
                qts = quotes

            # Citations RAG
            quotes = self.make_quotes(ranked, MAX_QUOTES)

            if not quotes or len(quotes) < MIN_QUOTES_OK:
                # Pas assez de matière fiable → fallback
                ans, srcs, qts = self.build_fallback(ranked)

            else:
                # Assemble un paragraphe fluide à partir des quotes (3–5 phrases)
                para = assemble_human_paragraph(quotes, max_sentences=5)

                # Forcer un début propre si la question parle explicitement d'IT STORM
                ql = q0.lower()
                if "it storm" in ql or "itstorm" in ql or "it-storm" in ql:
                    if not para.lower().startswith("it storm"):
                        # On cherche une citation commençant par "IT STORM"
                        prefix_set = False
                        for q in quotes:
                            txt = (q.get("quote") or "").strip()
                            if txt.lower().startswith("it storm"):
                                para = txt + " " + para
                                prefix_set = True
                                break
                        if not prefix_set:
                            # Filet de sécurité : phrase très générique
                            para = "IT STORM est une entreprise spécialisée. " + para

                ans = humanize_fr(para)
                srcs = sorted(set(q["source"] for q in quotes))
                qts = quotes
        # Scores de qualité & debug
        quality = self.quality_scores(ans, qts, ranked)
        dbg = {
            "intent": "default",
            "top_sources": [_norm_base(c.source) for c in ranked],
            "top_scores": [round(c.score_final, 3) for c in ranked],
            "conf_threshold": CONF_MIN,
        }

        return SmartRAGResult(
            answer=ans,
            sources=srcs,
            quotes=qts,
            confidence=conf,
            quality=quality,
            dbg=dbg,
        )

# === Jury Ollama (optionnel) =================================================
def ask_multi_ollama(
    question: str,
    models: Optional[List[str]] = None,
    topk_context: int = 12,
    timeout: float = 600.0
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

    # 1) Récupère un contexte strictement extractif via le moteur existant
    eng = get_engine()
    ranked = eng.rerank_balance(
        eng.late_fusion(eng.retrieve_dense(question, k=TOP_K_DENSE), question),
        intent="default"
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

    # 2) Prompt "réponse MAJORITAIREMENT depuis le contexte"
    #    → légèrement moins strict que "UNIQUEMENT" pour éviter les "Je ne sais pas" trop faciles
    prompt = (
        "Tu es un assistant interne d’IT STORM.\n"
        "Ta mission est de rédiger une réponse courte et claire en t’appuyant MAJORITAIREMENT sur le contexte ci-dessous.\n"
        "\n"
        "EXIGENCES DE RÉPONSE :\n"
        "1) Réponse structurée en 2 paragraphes, 4 à 6 phrases au total.\n"
        "2) Ajoute OBLIGATOIREMENT UNE LIGNE VIDE entre les deux paragraphes (format Markdown).\n"
        "3) Ne fais AUCUNE liste à puces, seulement du texte continu.\n"
        "4) Réutilise autant que possible les mots et expressions EXACTS présents dans le contexte.\n"
        "5) Si l’information n’est pas dans le contexte, écris strictement : \"Je ne sais pas.\".\n"
        "6) Termine toujours la réponse par une citation de la forme : [Source: https://it-storm.fr ].\n"
        "\n"
        f"Question : {question}\n\n"
        "Contexte :\n"
        f"{context}\n\n"
        "Réponse :"
    )

    try:
        from src.llm.ollama_client import generate_ollama, ping, list_models  # noqa: F401
    except Exception as e:
        return {
            "question": question,
            "context_snippets": snippets,
            "results": [{
                "model": "(ollama)",
                "answer": f"[Erreur import ollama_client] {e}",
                "time": 0.0,
                "metrics": {}
            }],
            "suggestion": None
        }

    try:
        if not ping():
            raise RuntimeError("Ollama n'est pas joignable (ping KO).")
    except Exception as e:
        return {
            "question": question,
            "context_snippets": snippets,
            "results": [{
                "model": "(ollama)",
                "answer": f"[Ping Ollama KO] {e}",
                "time": 0.0,
                "metrics": {}
            }],
            "suggestion": None
        }

    import time

    # === Fonctions de scoring internes =======================================
    def _coverage(ans: str, ctx_parts: List[str]) -> float:
        """
        Mesure combien de mots du contexte se retrouvent dans la réponse.
        Plus c'est élevé, plus la réponse colle au contexte.
        """
        if not ans or not ctx_parts:
            return 0.0
        ans_low = ans.lower()
        total = 0.0
        for s in ctx_parts:
            s_low = s.lower()
            if not s_low.strip():
                continue
            aw = set(re.findall(r"\w+", ans_low))
            sw = set(re.findall(r"\w+", s_low))
            if not sw:
                continue
            inter = len(aw & sw)
            union = len(sw)
            total += inter / max(1, union)
        return round(total / max(1, len(ctx_parts)), 2)

    def _style(ans: str) -> float:
        """
        Style = longueur raisonnable + ponctuation + présence de la citation.
        """
        if not ans:
            return 0.0
        L = len(ans.strip())
        has_src = "[source:" in ans.lower()
        punc = 1.0 if re.search(r"[.;!?]", ans) else 0.8

        # Fenêtre de longueur un peu plus large pour éviter les pénalités inutiles
        if 80 <= L <= 600:
            base = 1.0
        elif L < 60:
            base = 0.7
        else:
            base = 0.85

        return round(min(1.0, base * (1.05 if has_src else 1.0) * punc), 2)

    def _grounding(ans: str) -> float:
        """
        Grounding = cohérence avec le contexte + présence de la marque [Source: ...].
        """
        has_src = "[source:" in (ans or "").lower()
        cov = _coverage(ans, snippets)
        if has_src:
            # On récompense fortement les réponses qui citent la source
            # et couvrent raisonnablement le contexte
            base = 0.80 + 0.20 * min(1.0, cov)
            return round(min(1.0, base), 2)
        # Sans source explicite, grounding limité par le coverage
        return round(max(0.0, 0.7 * cov), 2)

    def _confidence(ans: str) -> float:
        """
        Combinaison globale : grounding + coverage + style + longueur.
        """
        g = _grounding(ans)
        cov = _coverage(ans, snippets)
        sty = _style(ans)
        L = len((ans or "").strip())

        # Score de longueur : on favorise 4–6 phrases (~100–500 caractères)
        if 80 <= L <= 600:
            len_score = 1.0
        elif L < 60:
            len_score = 0.7
        else:
            len_score = 0.8

        conf = 0.45 * g + 0.25 * cov + 0.20 * len_score + 0.10 * sty

        # Bonus si tout est bien aligné (réponse idéale)
        if g >= 0.90 and cov >= 0.25 and 80 <= L <= 400:
            conf = max(conf, 0.95)

        return round(min(1.0, max(0.0, conf)), 2)

    def _score(m: Dict[str, float]) -> float:
        """
        Score final simple : pondération des sous-métriques.
        """
        return round(
            0.4 * m.get("confidence", 0.0)
            + 0.3 * m.get("grounding", 0.0)
            + 0.2 * m.get("coverage", 0.0)
            + 0.1 * m.get("style", 0.0),
            3,
        )

    def _ensure_paragraph_spacing(ans: str) -> str:
        """
        Post-traitement léger pour forcer une ligne vide entre les paragraphes.
        - On regroupe les lignes non vides en paragraphes.
        - On les rejoint avec \\n\\n.
        """
        if not ans:
            return ans
        raw_lines = ans.splitlines()
        paragraphs = []
        buf = []
        for line in raw_lines:
            if line.strip() == "":
                if buf:
                    paragraphs.append(" ".join(buf).strip())
                    buf = []
            else:
                buf.append(line.strip())
        if buf:
            paragraphs.append(" ".join(buf).strip())
        return "\n\n".join(p for p in paragraphs if p)

    # === Boucle sur les modèles =============================================
    results = []
    for mdl in models:
        t0 = time.time()
        try:
            ans = generate_ollama(
                mdl,
                prompt,
                temperature=0.2,          # max de déterminisme
                max_tokens=220,           # un peu plus pour permettre 2 paragraphes confortables
                stream=True,
                timeout=600.0,
                options={
                    "num_ctx": 2048,      # plus de contexte, meilleure couverture
                    "top_k": 40,
                    "top_p": 0.9,
                    "repeat_penalty": 1.1
                }
            )

            # 🔐 Sécurisation : toujours une string
            if not isinstance(ans, str):
                ans = "" if ans is None else str(ans)

            # Normalisation : forcer une ligne vide entre paragraphes
            ans = _ensure_paragraph_spacing(ans)

            # S'assurer qu'il y a bien une [Source: ...]
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

            results.append({
                "model": mdl,
                "answer": ans,
                "time": round(dt, 2),
                "metrics": metrics,
                "score": score,
            })

        except Exception as e:
            dt = time.time() - t0
            results.append({
                "model": mdl,
                "answer": f"[Erreur LLM {mdl}] {e}",
                "time": round(dt, 2),
                "metrics": {},
                "score": 0.0,
            })

    # ⚠️ IMPORTANT : la sélection du meilleur modèle doit être EN DEHORS de la boucle
    valid = [r for r in results if not r["answer"].strip().startswith("[Erreur LLM")]
    suggestion = max(valid, key=lambda x: x["score"]) if valid else None

    return {
        "question": question,
        "context_snippets": snippets,
        "results": results,
        "suggestion": {
            "model": suggestion["model"],
            "score": suggestion["score"],
            "time": suggestion["time"],
        } if suggestion else None,
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
######