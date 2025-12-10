# -*- coding: utf-8 -*-
# ============================================================
# Path: src/rag_sum.py
# Role: Moteur de résumé indépendant (texte / fichier)
# - Jury multi-modèles via Ollama (bi-prompt + vote re-scoré)
# - Règle extractive "Verbatim Bullets" pour petits textes
# - Fallback smart_rag_answer(mode="summarize") si dispo
# - Fallback extractif FORCÉ si sortie vide / "je ne sais pas"
# - Garde-fous anti-bavardage / anti-invention :
#     * Troncature proportionnelle (longueur ~ source, ratio 1.1)
#     * Filtre vocabulaire (pénalités mots hors source)
#     * Détection phrases non ancrées, dépollution [Source: …]
# - Ton naturel + ponctuation harmonisée (post-processing)
# - Indicateurs locaux (compression, cosine, ROUGE-1/2, keywords, unsupported)
# - Lecture .txt / .pdf (PyPDF2 optionnel)
# - API: summarize_text(), summarize_file(), summary_quality_report(), select_best()
# + Mode CLI spécial: --three = 3 résumés directs (mistral/llama/qwen)
# + Pipeline gros documents: chunking + jury 3-modèles (_summarize_chunks_three)
# ============================================================

from __future__ import annotations
import io
import re
import os
import math
import string
from typing import List, Dict, Any, Tuple, Optional
from collections import Counter

# =========================
# Imports facultatifs (rag_brain)
# =========================
try:
    import src.rag_brain as _rb
    _SMART_RAG_ANS = getattr(_rb, "smart_rag_answer", None)
    _ASK_MULTI     = getattr(_rb, "ask_multi_ollama", None)
except Exception:
    _SMART_RAG_ANS = None
    _ASK_MULTI     = None

# =========================
# Helpers texte / qualité
# =========================

def _tok(s: str) -> list[str]:
    return re.findall(r"\w+", (s or "").lower(), flags=re.UNICODE)

def _ngrams(tokens: list[str], n: int) -> list[tuple]:
    return [tuple(tokens[i:i+n]) for i in range(len(tokens)-n+1)] if n > 0 else []

def _rouge_prf(reference_text: str, summarized_text: str, n: int = 1) -> dict:
    """ROUGE-N (P/R/F1) robuste."""
    reference_tokens = _tok(reference_text)
    summary_tokens   = _tok(summarized_text)

    reference_ngrams = Counter(_ngrams(reference_tokens, n))
    summary_ngrams   = Counter(_ngrams(summary_tokens, n))

    overlap_count = sum((reference_ngrams & summary_ngrams).values())
    total_ref = sum(reference_ngrams.values()) or 1
    total_sum = sum(summary_ngrams.values()) or 1

    recall    = overlap_count / total_ref
    precision = overlap_count / total_sum
    f1 = (2 * precision * recall) / (precision + recall) if (precision + recall) > 0 else 0.0
    return {"P": precision, "R": recall, "F1": f1}

def _keyword_overlap(reference_text: str, summarized_text: str, k: int = 20) -> float:
    """
    Recouvrement des mots-clés entre source et résumé.
    k devient dynamique :
      - texte court   -> peu de mots-clés (8 max)
      - texte moyen   -> ~15
      - texte long    -> k (20 par défaut)
    """
    ref_tokens = [t for t in _tok(reference_text) if len(t) > 2]
    sum_unique = set([t for t in _tok(summarized_text) if len(t) > 2])

    if not ref_tokens or not sum_unique:
        return 0.0

    n = len(ref_tokens)
    if n <= 80:
        k_eff = min(8, n)
    elif n <= 200:
        k_eff = min(15, n)
    else:
        k_eff = min(k, n)

    top_terms = [w for w, _ in Counter(ref_tokens).most_common(k_eff)]
    hits = sum(1 for w in top_terms if w in sum_unique)
    return hits / max(1, len(top_terms))

def _cosine_sim(reference_text: str, summarized_text: str) -> float:
    """
    Similarité cosinus sur tokens.
    """
    reference_vector = Counter(_tok(reference_text))
    summary_vector   = Counter(_tok(summarized_text))
    if not reference_vector or not summary_vector:
        return 0.0

    common_terms = set(reference_vector) & set(summary_vector)
    numerator = sum(reference_vector[t] * summary_vector[t] for t in common_terms)

    reference_norm = math.sqrt(sum(v * v for v in reference_vector.values()))
    summary_norm   = math.sqrt(sum(v * v for v in summary_vector.values()))
    denom = reference_norm * summary_norm
    return (numerator / denom) if denom else 0.0

def _unsupported_sentences(reference_text: str, summarized_text: str, thr: float = 0.15) -> list[str]:
    """
    Phrases du résumé dont le chevauchement en 3-grammes avec la source
    est trop faible → possiblement non ancrées.
    """
    ref_3 = set(_ngrams(_tok(reference_text), 3))
    out = []
    for sent in re.split(r"(?<=[\.\!\?])\s+", (summarized_text or "").strip()):
        if not sent:
            continue
        s3 = _ngrams(_tok(sent), 3)
        if not s3:
            continue
        overlap = sum(1 for g in s3 if g in ref_3) / len(s3)
        if overlap < thr:
            out.append(sent.strip())
    return out

def _complete_sentence_ratio(summary: str) -> float:
    """
    Mesure simple: ratio de phrases qui se terminent par un signe de ponctuation
    fort (.?!…).
    Plus c'est proche de 1, plus le texte ressemble à des phrases complètes.
    """
    text = (summary or "").strip()
    if not text:
        return 0.0

    parts = re.split(r"(?<=[\.\!\?…])\s+|\n+", text)
    parts = [p.strip() for p in parts if p.strip()]
    if not parts:
        return 0.0

    good = 0
    for p in parts:
        if re.search(r"[\.!\?…]$", p):
            good += 1
    return good / len(parts)

# =========================
# 🔥 Réparation générale des phrases coupées
# =========================

def _clean_cut_sentences(text: str) -> str:
    """
    Supprime proprement les phrases tronquées sans jamais inventer de mots.
    Stratégie:
      - découpe en phrases
      - enlève celles qui ressemblent à une fin coupée (mot final très court,
        peu de mots, caractère final bizarre, etc.)
      - reconstruit un texte fluide.
    """
    if not text:
        return ""

    # Découpage en phrases (approx)
    sentences = re.split(r"(?<=[\.!\?…])\s+|\n+", text)
    clean: List[str] = []

    for s in sentences:
        s_strip = s.strip()
        if not s_strip:
            continue

        words = s_strip.split()
        if not words:
            continue

        last_word = words[-1].rstrip(".!?…")

        # Phrase très courte + mot final très court → probable coupure
        if len(words) < 4 and len(last_word) <= 3:
            continue

        # Mot final avec caractères bizarres → probable tronqué
        if not re.match(r"^[\w\-À-ÿ]+$", last_word):
            continue

        clean.append(s_strip)

    return " ".join(clean).strip()

def summary_quality_report(source_text: str, summary: str) -> dict:
    """Toujours sûr: jamais d'exception qui fait planter l'UI."""
    try:
        source_token_count  = len(_tok(source_text))
        summary_token_count = len(_tok(summary))
        compression = (1 - (summary_token_count / max(1, source_token_count))) if source_token_count else 0.0

        rouge1 = _rouge_prf(source_text, summary, n=1)
        rouge2 = _rouge_prf(source_text, summary, n=2)
        cosine = _cosine_sim(source_text, summary)
        kw_ol  = _keyword_overlap(source_text, summary, k=20)
        unsup  = _unsupported_sentences(source_text, summary, thr=0.15)
        complete_ratio = _complete_sentence_ratio(summary)

        return {
            "tokens_source":    source_token_count,
            "tokens_summary":   summary_token_count,
            "compression":      compression,
            "cosine":           cosine,
            "rouge1_f1":        rouge1["F1"],
            "rouge2_f1":        rouge2["F1"],
            "keyword_overlap":  kw_ol,
            "unsupported":      unsup,
            "complete_ratio":   complete_ratio,
        }
    except Exception:
        return {
            "tokens_source":    0,
            "tokens_summary":   0,
            "compression":      0.0,
            "cosine":           0.0,
            "rouge1_f1":        0.0,
            "rouge2_f1":        0.0,
            "keyword_overlap":  0.0,
            "unsupported":      [],
            "complete_ratio":   0.0,
        }

def _score_from_quality_report(rep: dict) -> float:
    """
    Score global dans [0,1] basé sur :
    - similarité (cosine)
    - ROUGE-1 / ROUGE-2
    - recouvrement de mots-clés
    - compression raisonnable (cible dynamique selon la taille de la source)
    - ratio de phrases complètes
    - pénalité si beaucoup de phrases non ancrées ("unsupported")
    """
    try:
        cos   = float(rep.get("cosine", 0.0))
        r1    = float(rep.get("rouge1_f1", 0.0))
        r2    = float(rep.get("rouge2_f1", 0.0))
        kw    = float(rep.get("keyword_overlap", 0.0))
        comp  = float(rep.get("compression", 0.0))
        comp_sent = float(rep.get("complete_ratio", 0.0))
        Ls    = float(rep.get("tokens_source", 0) or 0.0)
        unsupported = rep.get("unsupported", []) or []
    except Exception:
        return 0.0

    # --- Compression : cible dynamique selon la taille du document ---
    # Textes courts  -> cible modérée
    # Textes moyens  -> ~0.65
    # Gros docs      -> ~0.70
    if comp <= -0.05:
        comp_score = 0.0
    else:
        if Ls > 2500:
            target = 0.70
        elif Ls > 1000:
            target = 0.65
        else:
            target = 0.55
        dev = abs(comp - target) / max(target, 1e-6)
        dev = min(dev, 1.0)
        comp_score = 1.0 - dev   # 1 = compression idéale, 0 = très éloignée

    # --- Pondérations (somme = 1.0) ---
    # On met l'accent sur :
    #  - la cohérence au texte source (cosine, ROUGE, keywords)
    #  - une compression correcte
    #  - un minimum de phrases complètes
    w_cos   = 0.40
    w_r1    = 0.15
    w_r2    = 0.10
    w_kw    = 0.15
    w_comp  = 0.15
    w_sent  = 0.05

    base = (
        w_cos  * cos +
        w_r1   * r1  +
        w_r2   * r2  +
        w_kw   * kw  +
        w_comp * comp_score +
        w_sent * comp_sent
    )

    # --- Pénalité hallucinations / phrases non ancrées ---
    # Plus il y a de phrases "unsupported", plus on diminue légèrement le score.
    # On ne descend jamais en-dessous de 0.6 pour ne pas tout écraser.
    try:
        u = len(unsupported)
    except Exception:
        u = 0

    if u > 0:
        penalty = 1.0 - 0.07 * u  # ~7% de pénalité par phrase douteuse
        penalty = max(0.60, min(1.0, penalty))
        base *= penalty

    # Clamp final dans [0,1]
    if base < 0.0:
        base = 0.0
    if base > 1.0:
        base = 1.0
    return base

# =========================
# Lecture fichiers
# =========================

def _read_txt(b: bytes) -> str:
    return (b or b"").decode("utf-8", errors="ignore")

def _read_pdf(b: bytes) -> str:
    try:
        import PyPDF2
    except Exception:
        return ""
    try:
        reader = PyPDF2.PdfReader(io.BytesIO(b))
    except Exception:
        return ""
    pages = []
    for p in reader.pages:
        try:
            pages.append(p.extract_text() or "")
        except Exception:
            pages.append("")
    return "\n".join(pages)

def read_any_text(file_bytes: bytes, filename: str) -> Tuple[str, str]:
    name = (filename or "").lower()
    if name.endswith(".txt"):
        return _read_txt(file_bytes), ".txt"
    if name.endswith(".pdf"):
        return _read_pdf(file_bytes), ".pdf"
    return "", ""

# =========================
# Chunking haute qualité (docs longs)
# =========================

def _chunk_text(text: str, chunk_size: int = 4800, overlap: int = 300) -> List[str]:
    """
    Découpe un long texte en segments de taille ~chunk_size (en caractères),
    avec un recouvrement `overlap` pour ne pas casser le contexte.
    """
    text = (text or "").strip()
    if not text:
        return []
    n = len(text)
    chunks: List[str] = []
    start = 0
    while start < n:
        end = start + chunk_size
        if end >= n:
            chunk = text[start:]
        else:
            chunk = text[start:end]
            last_dot = chunk.rfind(".")
            if last_dot != -1 and last_dot > int(chunk_size * 0.4):
                chunk = chunk[: last_dot + 1]
        chunk = chunk.strip()
        if chunk:
            chunks.append(chunk)
        if end >= n:
            break
        start = end - overlap
        if start < 0:
            start = 0
    return chunks


def _fix_sentences(text: str) -> str:
    """
    Post-traitement simple pour harmoniser un bloc de texte:
    - normalise les espaces
    - supprime "..." multiples
    - ajoute un point final si besoin
    """
    if not text:
        return ""
    txt = re.sub(r"\s+", " ", text).strip()
    txt = re.sub(r"\.\.\.++", ".", txt)
    if txt and txt[-1] not in ".!?…":
        txt += "."
    return txt

# =========================
# Normalisation & tri
# =========================

def _safe_num(x, d=0.0) -> float:
    try:
        return float(x)
    except Exception:
        return d

def _score_from_result(r: Dict[str, Any]) -> float:
    if "score" in r:
        return _safe_num(r["score"])
    if "confidence" in r:
        return _safe_num(r["confidence"])
    return 0.0

def normalize_results(results: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    out = []
    for r in (results or []):
        met = r.get("metrics") or {}
        out.append({
            "model": r.get("model", "—"),
            "answer": r.get("answer", ""),
            "score":  _safe_num(r.get("score", 0.0)),
            "confidence": _safe_num(met.get("confidence", r.get("score", 0.0))),

            "grounding":  _safe_num(met.get("grounding", 0.0)),
            "coverage":   _safe_num(met.get("coverage", 0.0)),
            "style":      _safe_num(met.get("style", 0.0)),
            "time":       _safe_num(r.get("time", 0.0)),
        })
    return out

def select_best(results: List[Dict[str, Any]]) -> Dict[str, Any]:
    if not results:
        return {}
    return sorted(results, key=_score_from_result, reverse=True)[0]

# =========================
# Stopwords FR/EN & vocab check
# =========================

_STOPWORDS = {
    # français (extrait minimal)
    "le","la","les","un","une","des","du","de","d","au","aux","et","ou","où","dans","par","pour","avec","sans",
    "sur","sous","entre","chez","vers","en","à","a","est","sont","été","etre","être","ce","cet","cette","ces",
    "que","qui","quoi","dont","où","plus","moins","afin","ainsi","comme","car","donc","or","ni","mais",
    # anglais (extrait minimal)
    "the","a","an","and","or","but","for","with","without","to","in","on","at","by","of","from","as","is","are",
}

def _vocab_outlier_ratio(source: str, hyp: str) -> float:
    """Ratio de mots du résumé n'apparaissant pas dans la source (hors stopwords, chiffres)."""
    src_terms = set(w for w in _tok(source) if w not in _STOPWORDS and not w.isdigit())
    hyp_terms = [w for w in _tok(hyp)    if w not in _STOPWORDS and not w.isdigit()]
    if not hyp_terms:
        return 0.0
    out_of = sum(1 for w in hyp_terms if w not in src_terms)
    return out_of / len(hyp_terms)

def _clean_decorations(text: str) -> str:
    """Dépollution: supprime [Source: …], (source: …), espaces multiples."""
    t = (text or "")
    t = re.sub(r"\[?\s*source\s*:[^\]\n]+\]?", "", t, flags=re.I)
    t = re.sub(r"\(\s*source\s*:[^)]+\)", "", t, flags=re.I)
    t = re.sub(r"\s{2,}", " ", t)
    return t.strip()

# =========================
# Helpers de normalisation & dédoublonnage (évite redites)
# =========================

def _normalize_phrase(s: str) -> str:
    s = (s or "").strip()
    s = re.sub(r"\s+", " ", s)
    s = s.strip(string.punctuation + "·•-–—:;")
    s = s.lower()
    return s

def _dedupe_keep_order(items: List[str]) -> List[str]:
    seen = set()
    out = []
    for x in items:
        k = _normalize_phrase(x)
        if not k or k in seen:
            continue
        seen.add(k)
        out.append(x.strip())
    return out

def _is_subphrase(a: str, b: str) -> bool:
    """True si a est très proche / inclus dans b (normalisé)."""
    na, nb = _normalize_phrase(a), _normalize_phrase(b)
    return na and nb and (na in nb or nb in na)

def _clean_heading(s: str) -> str:
    """Supprime les entêtes / préfixes type 'IT Storm propose:' / puces."""
    s = (s or "").strip()
    s = re.sub(r"^\s*[•·\-–—]\s*", "", s)
    s = re.sub(r"^\s*[\w\s]+\s*:\s*", "", s)  # ex: "IT Storm propose:"
    return s.strip()

def _sentences_from_text(text: str) -> List[str]:
    raw = (text or "").strip()
    parts = re.split(r"(?<=[\.\!\?])\s+|\n+", raw)
    parts = [p.strip() for p in parts if p and p.strip()]
    return _dedupe_keep_order(parts)

# =========================
# Garde-fous (troncature, verbatim, post-ponctuation)
# =========================

def _truncate_like_source(src: str, hyp: str, ratio: float = 1.1) -> str:
    """Tronque le résumé si sa longueur dépasse ratio * longueur source (caractères)."""
    if not src or not hyp:
        return hyp
    lim = int(len(src) * ratio)
    return hyp if len(hyp) <= lim else hyp[:lim].rstrip() + "…"

def _extract_short_bullets(text: str, max_items: int = 5, avoid: Optional[str] = None) -> List[str]:
    """
    Construit des puces propres, sans doublons ni redites du paragraphe.
    """
    lines = [ln.strip() for ln in (text or "").splitlines() if ln.strip()]
    lines = [_clean_heading(ln) for ln in lines]
    if not lines:
        lines = _sentences_from_text(text)

    cand = _dedupe_keep_order(lines)
    cand = [c for c in cand if 2 <= len(c.split()) <= 18]

    if avoid:
        cand = [c for c in cand if not _is_subphrase(c, avoid)]

    final = []
    for c in cand:
        if any(_is_subphrase(c, x) or _is_subphrase(x, c) for x in final):
            continue
        final.append(c)
        if len(final) >= max_items:
            break

    out = []
    for c in final:
        cc = c[:1].upper() + c[1:]
        if not re.search(r"[.!?…]$", cc):
            cc += "."
        out.append(cc)
    return out

def _smooth_punctuation(s: str) -> str:
    """Harmonise la ponctuation: espaces & retours à la ligne."""
    if not s:
        return s
    s = re.sub(r'\s([?.!,;:])', r'\1', s)
    s = re.sub(r'([a-zA-Z0-9])\n([A-Z])', r'\1. \2', s)
    s = re.sub(r'\s{2,}', ' ', s)
    return s.strip()

def _repair_truncated_sentences(text: str) -> str:
    """
    Répare les fins de résumé manifestement coupées :
      - retire la toute dernière phrase si elle est très courte (<= 3 mots)
        ou se termine par un mot de liaison ("et", "ou", "mais", "car", "donc").
    Cela améliore le ratio de phrases complètes sans inventer de contenu.
    """
    txt = (text or "").strip()
    if not txt:
        return txt

    sentences = re.split(r"(?<=[\.!\?…])\s+|\n+", txt)
    sentences = [s.strip() for s in sentences if s.strip()]
    if not sentences:
        return txt

    last = sentences[-1]
    last_low = last.lower()
    last_words = last_low.split()

    liaison = {"et", "ou", "mais", "car", "donc", "or"}
    drop_last = False

    if len(last_words) <= 3:
        drop_last = True
    elif last_words[-1] in liaison:
        drop_last = True

    if drop_last and len(sentences) >= 2:
        sentences = sentences[:-1]

    return " ".join(sentences).strip()

# =========================
# Prompts jury (A = phrase+puces, B = puces-only)
# =========================

def _jury_prompt_A(text: str, max_chars: int = 6000) -> str:
    snippet = (text or "").strip()
    if len(snippet) > max_chars:
        snippet = snippet[:max_chars] + "\n[Texte tronqué]"
    return (
        "Résume le texte ci-dessous avec un ton naturel et humain, sans rien inventer. "
        "Fais un paragraphe fluide suivi de 3 à 5 puces claires et ponctuées. "
        "Utilise la même terminologie que dans le texte, sans extrapoler.\n\n"
        "TEXTE:\n" + snippet
    )

def _jury_prompt_B(text: str, max_chars: int = 6000) -> str:
    snippet = (text or "").strip()
    if len(snippet) > max_chars:
        snippet = snippet[:max_chars] + "\n[Texte tronqué]"
    return (
        "Fais une liste de 3 à 5 puces synthétiques et bien ponctuées résumant le texte ci-dessous. "
        "Ne rien inventer, rester fidèle au contenu et au ton du texte.\n\n"
        "TEXTE:\n" + snippet
    )

# =========================
# Vote / re-scoring du jury
# =========================

def _rescore_and_pick(text: str, candidates: List[Dict[str, Any]]) -> Tuple[Dict[str, Any], Dict[str, Any], List[str]]:
    """
    Re-score des résultats jury avec pénalités/bonus.
    Retourne (best_result, best_report, flags)
    """
    best = {}
    best_rep = {}
    best_s = -1.0
    flags: List[str] = []

    for r in (candidates or []):
        ans = _clean_decorations(r.get("answer", ""))
        rep = summary_quality_report(text, ans)
        s = _score_from_result(r)

        if rep.get("unsupported"):
            s -= 0.25
        if rep.get("compression", 0.0) < 0.0:
            s -= 0.15
        if rep.get("keyword_overlap", 0.0) < 0.35:
            s -= 0.10
        vratio = _vocab_outlier_ratio(text, ans)
        if vratio > 0.25:
            s -= 0.20

        if r.get("style", rep.get("style", 0.0)) > 0.7:
            s += 0.10

        s = max(0.0, min(1.0, s))

        if s > best_s:
            best_s = s
            best = dict(r)
            best["answer"] = ans
            best["score"] = s
            best_rep = rep

    if best_rep:
        if best_rep.get("compression", 0.0) < 0.0:
            flags.append("compression_negative")
        if best_rep.get("unsupported"):
            flags.append("unsupported_detected")
        if best_rep.get("keyword_overlap", 0.0) < 0.35:
            flags.append("low_keyword_overlap")
        if _vocab_outlier_ratio(text, best.get("answer", "")) > 0.25:
            flags.append("vocab_outlier")

    return best, best_rep, flags

# =========================
# Fallback extractif FORCÉ
# =========================

def _fallback_extractive_forced(text: str) -> Dict[str, Any]:
    """
    Résumé extractif toujours lisible, sans répétitions.
    """
    clean = (text or "").strip()
    sentences = _sentences_from_text(clean)

    # Paragraphe = première phrase "porteuse"
    para = ""
    for s in sentences:
        core = _clean_heading(s)
        if len(core.split()) >= 4:
            para = core
            break
    if not para:
        para = _clean_heading(sentences[0]) if sentences else clean

    if len(para) > 240:
        para = para[:240].rstrip() + "…"

    bullets = _extract_short_bullets(clean, max_items=5, avoid=para)

    pieces = []
    if para:
        p = para.strip()
        if not re.search(r"[.!?…]$", p):
            p += "."
        pieces.append(p)

    if bullets:
        pieces.append("• " + "\n• ".join(bullets))

    answer = "\n\n".join(pieces).strip()
    answer = _smooth_punctuation(answer)
    if not answer:
        answer = "Résumé non généré : le texte source est vide."

    best = {
        "model": "extractive-forced",
        "answer": answer,
        "score": 1.0,
        "confidence": 1.0,
        "grounding": 1.0,
        "coverage": 1.0,
        "style": 1.0,
        "time": 0.0,
    }
    return best

def _looks_unknown(s: str) -> bool:
    return bool(re.search(r"\b(je ne sais pas|i don'?t know|unknown|no context)\b", (s or "").lower()))

# =========================
# Nettoyage post-LLM
# =========================

def _clean_llm_summary(raw: str) -> str:
    """
    Nettoyage léger:
    - supprime les intros du style "Voici un résumé..."
    - supprime les entêtes "Résumé:" / "Summary:"
    - supprime la dernière puce manifestement coupée
    - ajoute un point final aux lignes non vides sans ponctuation forte
    - supprime une éventuelle dernière phrase très courte et vide de sens
    """
    txt = (raw or "").strip()
    if not txt:
        return txt

    # 1) Enlever les intros typiques de LLM
    intro_patterns = [
        r"^voici un résumé[^:\n]*:\s*",
        r"^voici le résumé[^:\n]*:\s*",
        r"^résumé\s*:\s*",
        r"^summary\s*:\s*",
    ]
    for pat in intro_patterns:
        txt = re.sub(pat, "", txt, flags=re.I)

    # 2) Travail ligne par ligne (pour les puces)
    lines = [l.rstrip() for l in txt.splitlines()]
    cleaned_lines = []
    bullet_prefixes = ("- ", "* ", "• ")

    for l in lines:
        ll = l.strip()
        if not ll:
            cleaned_lines.append(l)
            continue
        cleaned_lines.append(l)

    # 3) Supprimer une dernière puce manifestement coupée
    if cleaned_lines:
        last = cleaned_lines[-1].strip()
        low = last.lower()
        if last.startswith(bullet_prefixes):
            last_words = low.split()
            if len(last_words) <= 4 or low.endswith((" et", " et les", " pour", " avec")):
                cleaned_lines = cleaned_lines[:-1]

    # 4) Ajouter un point aux lignes non vides sans ponctuation forte
    final_lines = []
    for l in cleaned_lines:
        s = l.rstrip()
        if not s:
            final_lines.append(s)
            continue
        if not re.search(r"[\.!\?…]$", s):
            s += "."
        final_lines.append(s)

    txt = "\n".join(final_lines).strip()

    # 5) Post-filtre: enlever une dernière phrase très courte et vide de sens
    sentences = re.split(r"(?<=[\.!\?…])\s+", txt)
    if sentences:
        last = sentences[-1].strip()
        low = last.lower()
        last_words = low.split()

        if len(last_words) <= 4 and (
            "propose également" in low
            or low in {"it storm.", "it storm propose.", "it storm propose également."}
        ):
            txt = " ".join(sentences[:-1]).strip()

    return txt

# =========================
# Chunked three-model pipeline pour textes longs
# =========================

def _summarize_chunks_three(
    text: str,
    models: List[str],
    timeout: float = 120.0,
    chunk_size: int = 2800,
    overlap: int = 300,
) -> Dict[str, Any]:
    """
    Pipeline haute qualité pour textes longs :
      1) chunking du texte source
      2) résumé de chaque chunk via _summarize_text_three_cli (jury 3 modèles)
      3) concaténation des meilleurs résumés locaux
      4) nouveau jury global sur le résumé combiné

    Retourne une structure compatible avec summarize_text() :
        {
            "best": {...},          # meilleur résumé global
            "results": [...],       # candidats du jury final
            "report": {...},        # quality_report global
            "used": "three-chunk",
            "flags": [...],
            "local_summaries": [...],
            "chunks_used": N,
        }
    """
    text = (text or "").strip()
    if not text:
        best = _fallback_extractive_forced(text)
        rep = summary_quality_report(text, best.get("answer", ""))
        return {
            "best": best,
            "results": [best],
            "report": rep,
            "used": "rule",
            "flags": ["forced_empty_input"],
        }

    chunks = _chunk_text(text, chunk_size=chunk_size, overlap=overlap)
    if len(chunks) <= 1:
        # Rien à découper : on repasse par le chemin standard.
        return summarize_text(text, models=models, timeout=timeout)

    local_summaries: List[Dict[str, Any]] = []
    for idx, ch in enumerate(chunks, start=1):
        # Jury direct sur le chunk
        try:
            res_list = _summarize_text_three_cli(ch, models=models, timeout=timeout)
        except TypeError:
            res_list = _summarize_text_three_cli(ch, models=models)
        except Exception:
            res_list = []

        if not res_list:
            continue

        best_loc = max(res_list, key=lambda x: x.get("score", 0.0))
        best_loc = dict(best_loc)
        best_loc["chunk_index"] = idx
        local_summaries.append(best_loc)

    if not local_summaries:
        # Tous les appels ont échoué : fallback global
        best = _fallback_extractive_forced(text)
        rep = summary_quality_report(text, best.get("answer", ""))
        return {
            "best": best,
            "results": [best],
            "report": rep,
            "used": "three-chunk-fallback",
            "flags": ["three_chunk_all_failed"],
        }

    # Tri chronologique par index de chunk
    local_summaries.sort(key=lambda r: r.get("chunk_index", 0))

    # Concaténation des résumés locaux
    combined = "\n\n".join(_fix_sentences(r.get("answer", "")) for r in local_summaries)

    # Jury global sur le "résumé des résumés"
    try:
        global_candidates = _summarize_text_three_cli(combined, models=models, timeout=timeout)
    except TypeError:
        global_candidates = _summarize_text_three_cli(combined, models=models)
    except Exception:
        global_candidates = []

    if not global_candidates:
        best = _fallback_extractive_forced(text)
        rep = summary_quality_report(text, best.get("answer", ""))
        return {
            "best": best,
            "results": [best],
            "report": rep,
            "used": "three-chunk-fallback",
            "flags": ["three_chunk_global_failed"],
            "local_summaries": local_summaries,
            "chunks_used": len(chunks),
        }

    best = max(global_candidates, key=lambda x: x.get("score", 0.0))
    best = dict(best)
    best_answer = _fix_sentences(best.get("answer", ""))
    best_answer = _smooth_punctuation(_truncate_like_source(text, best_answer, ratio=1.1))
    best["answer"] = best_answer

    report = summary_quality_report(text, best_answer)
    flags: List[str] = []
    if report.get("compression", 0.0) < 0.0:
        flags.append("compression_negative")
    if report.get("unsupported"):
        flags.append("unsupported_detected")
    if _vocab_outlier_ratio(text, best_answer) > 0.25:
        flags.append("vocab_outlier")

    return {
        "best": best,
        "results": global_candidates,
        "report": report,
        "used": "three-chunk",
        "flags": flags,
        "local_summaries": local_summaries,
        "chunks_used": len(chunks),
    }

# =========================
# Résumé (texte brut) – mode classique
# =========================

def summarize_text(text: str, models: List[str], timeout: float = 90.0) -> Dict[str, Any]:
    """
    Résume 'text' avec jury Ollama (bi-prompt + vote re-scoré) si dispo.
    Règle extractive pour textes très courts.
    Fallback smart_rag_answer(mode='summarize') si dispo.
    Fallback extractif forcé si sortie vide / "je ne sais pas".
    """
    text = (text or "").strip()
    if not text:
        best = _fallback_extractive_forced(text)
        rep = summary_quality_report(text, best.get("answer", ""))
        return {"best": best, "results": [best], "report": rep, "used": "rule", "flags": ["forced_empty_input"]}

    if len(text) <= 300:
        best = _fallback_extractive_forced(text)
        rep = summary_quality_report(text, best.get("answer", ""))
        return {"best": best, "results": [best], "report": rep, "used": "rule", "flags": ["verbatim_mode"]}

    jury_candidates: List[Dict[str, Any]] = []
    if callable(_ASK_MULTI) and models:
        try:
            rawA = _ASK_MULTI(_jury_prompt_A(text), models=models, topk_context=0, timeout=timeout) or {}
            rawB = _ASK_MULTI(_jury_prompt_B(text), models=models, topk_context=0, timeout=timeout) or {}
            candA = normalize_results(rawA.get("results") or [])
            candB = normalize_results(rawB.get("results") or [])
            jury_candidates = candA + candB
        except TypeError:
            try:
                rawA = _ASK_MULTI(_jury_prompt_A(text), models=models) or {}
                rawB = _ASK_MULTI(_jury_prompt_B(text), models=models) or {}
                candA = normalize_results(rawA.get("results") or [])
                candB = normalize_results(rawB.get("results") or [])
                jury_candidates = candA + candB
            except Exception:
                jury_candidates = []
        except Exception:
            jury_candidates = []

        if jury_candidates:
            best, report, flags = _rescore_and_pick(text, jury_candidates)
            best_answer = _smooth_punctuation(_truncate_like_source(text, best.get("answer", ""), ratio=1.1))
            if not best_answer.strip() or _looks_unknown(best_answer):
                best = _fallback_extractive_forced(text)
                report = summary_quality_report(text, best.get("answer", ""))
                flags = list(set(flags + ["forced_fallback_unknown"]))
            else:
                if best_answer != best.get("answer", ""):
                    best["answer"] = best_answer
                    report = summary_quality_report(text, best_answer)
                    if "compression_negative" not in flags and len(best_answer) > int(len(text) * 1.1):
                        flags.append("compression_trim_applied")
            return {"best": best, "results": jury_candidates, "report": report, "used": "jury", "flags": flags}

    if callable(_SMART_RAG_ANS):
        try:
            base = _SMART_RAG_ANS(question=_jury_prompt_A(text), mode="summarize") or {}
            cleaned = _clean_decorations(base.get("answer", ""))
            ans = _smooth_punctuation(_truncate_like_source(text, cleaned, ratio=1.1))
            if not ans.strip() or _looks_unknown(ans):
                best = _fallback_extractive_forced(text)
                report = summary_quality_report(text, best.get("answer", ""))
                return {"best": best, "results": [best], "report": report, "used": "rule", "flags": ["forced_fallback_unknown"]}
            best = {
                "model": "smart_rag_answer",
                "answer": ans,
                "score":  _safe_num(base.get("confidence", 0.0)),
                "confidence": _safe_num(base.get("confidence", 0.0)),
                "grounding":  _safe_num((base.get("quality") or {}).get("grounding", 0.0)),
                "coverage":   _safe_num((base.get("quality") or {}).get("coverage", 0.0)),
                "style":      _safe_num((base.get("quality") or {}).get("style", 0.0)),
                "time":       0.0,
            }
            report = summary_quality_report(text, ans)
            flags: List[str] = []
            if report.get("compression", 0.0) < 0.0:
                flags.append("compression_negative")
            if report.get("unsupported"):
                flags.append("unsupported_detected")
            if _vocab_outlier_ratio(text, ans) > 0.25:
                flags.append("vocab_outlier")
            return {"best": best, "results": [best], "report": report, "used": "rag", "flags": flags}
        except Exception:
            pass

    best = _fallback_extractive_forced(text)
    report = summary_quality_report(text, best.get("answer", ""))
    return {"best": best, "results": [best], "report": report, "used": "rule", "flags": ["forced_fallback_last"]}

# =========================
# Résumé (fichier uploadé)
# =========================

def summarize_text_keypoints(
    text: str,
    models: List[str],
    timeout: float = 90.0,
    max_points: int = 8,
) -> Dict[str, Any]:
    """
    Variante de summarize_text(...) pensée pour des paragraphes collés.

    - Utilise d'abord summarize_text(...) pour produire un résumé classique.
    - Puis condense ce résumé en une liste de points clés (puces courtes).
    - Retourne une structure compatible avec summarize_text (best/results/report/...).

    Args:
        text: texte source (brut, collé depuis une page web, un mail, etc.)
        models: liste de modèles Ollama à utiliser.
        timeout: timeout global (propage au moteur interne).
        max_points: nombre maximal de puces à renvoyer.

    Returns:
        dict avec clés:
          - best.answer : string contenant les puces "- …"
          - results     : résultats bruts du jury interne
          - report      : rapport qualité du meilleur résumé de base
          - used        : "llm" / "rag" / "rule" + suffixe "+keypoints"
          - flags       : liste de drapeaux ("post_keypoints", etc.)
    """
    # 1) On appelle la pipeline standard (jury / RAG / fallback règles)
    base = summarize_text(text, models=models, timeout=timeout)

    best = dict(base.get("best", {}) or {})
    summary = (best.get("answer") or "").strip()

    # 2) On essaie d'extraire des puces courtes à partir du résumé
    bullets = _extract_short_bullets(summary, max_items=max_points)

    # Si jamais le résumé est vide ou peu exploitable, on tente directement sur le texte source
    if not bullets:
        bullets = _extract_short_bullets(text, max_items=max_points)

    # Si on n'a toujours rien, on garde le résumé brut
    if bullets:
        bullets_txt = "\n".join(f"- {b}" for b in bullets)
    else:
        bullets_txt = summary

    best["answer"] = bullets_txt

    # 3) On propage le reste des infos (report, results, etc.)
    flags = list(dict.fromkeys((base.get("flags") or []) + ["post_keypoints"]))
    used = (base.get("used") or "rule") + "+keypoints"

    return {
        "best": best,
        "results": base.get("results") or [],
        "report": base.get("report") or {},
        "used": used,
        "flags": flags,
    }

#####===========================================================
# Résumé de fichiers uploadés (.txt / .pdf)

def summarize_file(file_bytes: bytes, filename: str, models: List[str], timeout: float = 90.0) -> Dict[str, Any]:
    """
    Lit le fichier (.txt/.pdf), applique automatiquement la meilleure stratégie :
      - texte court/moyen  -> summarize_text() (jury / RAG)
      - gros documents      -> pipeline chunké + jury 3-modèles
    """
    text, ext = read_any_text(file_bytes, filename)
    if not text:
        best = _fallback_extractive_forced(text)
        rep = summary_quality_report(text, best.get("answer", ""))
        return {
            "best": best,
            "results": [best],
            "report": rep,
            "used": "rule",
            "error": f"Impossible de lire: {filename}",
            "flags": ["forced_empty_input"],
        }

    length = len(text or "")
    if length >= 6000:
        out = _summarize_chunks_three(text, models=models, timeout=timeout)
    else:
        out = summarize_text(text, models=models, timeout=timeout)

    out["source_ext"] = ext
    out["source_name"] = filename
    out["tokens_source"] = len(_tok(text))
    out["tokens_summary"] = len(_tok(out.get("best", {}).get("answer", "")))
    return out


# ---------------------------------------------------------------------
# Instruction de résumé dynamique selon la taille du document
# ---------------------------------------------------------------------
def _build_summary_instruction(total_chars: int) -> str:
    """
    Retourne une consigne de résumé adaptée à la taille du document complet.
    Objectif : ne pas compresser trop fort les très gros PDF.
    """
    if total_chars <= 8000:
        # Documents courts
        return (
            "Résume le texte en 5 à 8 phrases claires, en gardant toutes les idées essentielles "
            "sans trop compresser."
        )
    elif total_chars <= 25000:
        # Documents moyens
        return (
            "Résume le texte en 8 à 12 lignes, garde les points clés et les notions importantes, "
            "sans compression excessive."
        )
    elif total_chars <= 50000:
        # Grands documents
        return (
            "Résume le texte en 12 à 18 lignes structurées (2 à 3 paragraphes), en conservant les "
            "idées majeures, les éléments de contexte, les concepts clés, les enjeux et les chiffres importants."
        )
    else:
        # Très gros PDF (comme ton PEPS)
        return (
            "Résume le texte en 18 à 25 lignes structurées (plusieurs paragraphes), en conservant toutes "
            "les idées majeures, les arguments principaux, les propositions, les éléments de contexte et "
            "les chiffres importants. Ne compresse pas trop : mieux vaut un résumé un peu plus long mais fidèle."
        )

# ============================================================
# Mode spécial CLI: --three (3 résumés directs via Ollama)
# ============================================================

def _summarize_text_three_cli(text: str, models: List[str], timeout: float = 60.0) -> List[Dict[str, Any]]:
    """
    Utilisé uniquement par la CLI avec --three :
    - Appelle directement Ollama, sans RAG, une fois par modèle.
    - Toujours renvoyer un résumé non vide (fallback extractif en dernier recours).
    - Ajoute des logs lisibles pour suivre la génération (CPU lent).
    - Optimisations pour éviter les timeouts sur CPU + 7B:
        * Timeout LLM minimum 180s
        * Contexte tronqué à 2500 caractères
        * max_tokens dynamique selon la taille du texte
        * num_ctx = 1536
        * temperature = 0.0 + seed pour plus de déterminisme
    """
    import time

    text = (text or "").strip()
    if not text:
        fb = _fallback_extractive_forced(text)
        rep = summary_quality_report(text, fb["answer"])
        fb["report"] = rep
        fb["flags"] = ["forced_empty_input"]
        return [fb]

    try:
        from src.llm.ollama_client import generate_ollama
    except Exception:
        fb = _fallback_extractive_forced(text)
        rep = summary_quality_report(text, fb["answer"])
        fb["report"] = rep
        fb["flags"] = ["ollama_unavailable", "forced_rule"]
        out: List[Dict[str, Any]] = []
        for name in (models or ["mistral:7b-instruct", "llama3.2:3b", "qwen2.5:7b"]):
            c = dict(fb)
            c["model"] = f"{name} (rule)"
            out.append(c)
        return out

    llm_timeout = max(float(timeout), 180.0)

    # --- Paramètres dynamiques selon la taille du texte ---
    text_len = len(text)

    if text_len <= 1500:
        max_chars = min(text_len, 1500)
        max_tokens = 150
    elif text_len <= 6000:
        max_chars = min(text_len, 4000)
        max_tokens = 220
    else:
        max_chars = min(text_len, 6500)
        max_tokens = 260

    # Contexte LLM (num_ctx) approximatif en fonction du snippet
    approx_ctx = int(max_chars / 3)  # 3–4 chars ≈ 1 token
    approx_ctx = max(1536, min(3072, approx_ctx))

    snippet = text if text_len <= max_chars else text[:max_chars] + "\n[Texte tronqué pour le résumé]"

    # 🔥 max_tokens dynamique selon la taille du snippet
    dynamic_max_tokens = int(len(snippet) / 22)  # ~4.5 chars/token
    dynamic_max_tokens = max(220, min(dynamic_max_tokens, 450))

    # 🔥 Instruction de résumé dynamique en fonction de la taille du document complet
    instruction = _build_summary_instruction(text_len)

    prompt_tpl = (
        "Résume le texte ci-dessous en français, avec un ton naturel et humain, sans rien inventer.\n"
        f"{instruction}\n"
        "- Ne parle pas d'Ollama ni du fait que tu es un modèle.\n\n"
        "TEXTE:\n"
        f"{snippet}\n\n"
        "RÉSUMÉ:"
    )


    summaries: List[Dict[str, Any]] = []
    total_models = len(models or [])

    for idx, mdl in enumerate(models or []):
        mdl = mdl.strip()
        if not mdl:
            continue

        label = f"[{idx + 1}/{total_models}] {mdl}"
        print(f"\n⏳ Génération du résumé avec {label} ...", flush=True)
        t0 = time.time()

        try:
            ans = generate_ollama(
                mdl,
                prompt_tpl,
                temperature=0.3,
                max_tokens=dynamic_max_tokens,
                stream=True,
                timeout=llm_timeout,
                options={
                    "num_ctx": 1536,
                    "top_k": 40,
                    "top_p": 0.9,
                    "repeat_penalty": 1.05,
                    #"seed": 1,
                },
            )
            ans = (ans or "").strip()
            ans = _clean_llm_summary(ans)
            ans = _clean_cut_sentences(ans)  # 🔥 réparation générale des phrases coupées
            dt = time.time() - t0
            print(f"✅ {label} terminé en ~{dt:.1f}s", flush=True)
        except Exception as e:
            dt = time.time() - t0
            print(f"⚠️ {label} a échoué après ~{dt:.1f}s : {e}", flush=True)
            ans = ""

        if not ans:
            fb = _fallback_extractive_forced(text)
            rep = summary_quality_report(text, fb["answer"])
            fb["model"] = f"{mdl} (fallback)"
            fb["report"] = rep
            fb["flags"] = ["llm_error_or_empty"]
            fb["time"] = dt

            s = _score_from_quality_report(rep)
            fb["score"] = s
            fb["confidence"] = s
            fb["grounding"] = rep.get("cosine", 0.0)
            fb["coverage"] = rep.get("keyword_overlap", 0.0)
            summaries.append(fb)
            continue

        rep = summary_quality_report(text, ans)
        s = _score_from_quality_report(rep)

        summaries.append(
            {
                "model": mdl,
                "answer": ans,
                "score": s,
                "confidence": s,
                "grounding": rep.get("cosine", 0.0),
                "coverage": rep.get("keyword_overlap", 0.0),
                "style": 1.0,
                "time": dt,
                "report": rep,
                "flags": [],
            }
        )

    if not summaries:
        fb = _fallback_extractive_forced(text)
        rep = summary_quality_report(text, fb["answer"])
        fb["report"] = rep
        fb["flags"] = ["no_model"]
        return [fb]

    return summaries


# ============================================================
# CLI
# ============================================================
if __name__ == "__main__":
    import argparse, sys

    p = argparse.ArgumentParser(
        description="Résumé de documents (txt/pdf) avec métriques + option 3 modèles Ollama."
    )
    p.add_argument("--file", type=str, help="Chemin d'un .txt ou .pdf")
    p.add_argument("--text", type=str, help="Texte brut à résumer")
    p.add_argument(
        "--models",
        type=str,
        default="mistral:7b-instruct,llama3.2:3b,qwen2.5:7b",
        help="Liste de modèles Ollama séparés par des virgules (pour --three).",
    )
    p.add_argument(
        "--timeout",
        type=float,
        default=2000.0,
        help="Timeout par appel LLM (secondes).",
    )
    p.add_argument(
        "--three",
        action="store_true",
        help="Génère 3 résumés (1 par modèle) en appelant directement Ollama (sans RAG).",
    )

    args = p.parse_args()
    models = [m.strip() for m in (args.models or "").split(",") if m.strip()]

    if args.three:
        if args.file:
            if not os.path.exists(args.file):
                print(f"[rag_sum] Fichier introuvable: {args.file}", file=sys.stderr)
                sys.exit(1)
            with open(args.file, "rb") as f:
                raw = f.read()
            text, _ext = read_any_text(raw, os.path.basename(args.file))
        else:
            text = args.text or ""

        print("=== MODE UTILISÉ: three-direct")
        print("=== FICHIER:", args.file or "(texte brut)")
        print("=== MODÈLES (demandés):", ", ".join(models) or "—")
        print(f"=== Longueur texte: {len(text)} caractères\n", flush=True)

        summaries = _summarize_text_three_cli(text, models=models, timeout=args.timeout)

        print("=== MODÈLES (effectifs):", ", ".join([s.get("model", "?") for s in summaries]))

        llm_candidates = [s for s in summaries if not str(s.get("model", "")).endswith("(fallback)")]
        if llm_candidates:
            best = max(llm_candidates, key=lambda x: x.get("score", 0.0))
        else:
            best = max(summaries, key=lambda x: x.get("score", 0.0)) if summaries else None

        if best:
            print("\n=== MEILLEUR RÉSUMÉ (score global) ===")
            print(f"Modèle: {best.get('model','?')}")
            print(f"Score:  {best.get('score',0.0):.3f}")
            print("Résumé:")
            print(best.get("answer",""))

        print("\n=== RÉSUMÉS PAR MODÈLE ===")
        for s in summaries:
            rep = s.get("report", {}) or {}
            print("\n--- Modèle:", s.get("model", "?"))
            print(f"Score:        {s.get('score',0.0):.3f}")
            print(f"Compression:  {rep.get('compression',0.0):.2f}")
            print(f"Cosine:       {rep.get('cosine',0.0):.2f}")
            print(f"ROUGE-1 F1:   {rep.get('rouge1_f1',0.0):.2f}")
            print(f"ROUGE-2 F1:   {rep.get('rouge2_f1',0.0):.2f}")
            print(f"Keywords %:   {rep.get('keyword_overlap',0.0)*100:.0f}%")
            print(f"Phrases OK %: {rep.get('complete_ratio',0.0)*100:.0f}%")
            print("Résumé:")
            print(s.get("answer", ""))

        sys.exit(0)

    if args.file:
        if not os.path.exists(args.file):
            print(f"[rag_sum] Fichier introuvable: {args.file}", file=sys.stderr)
            sys.exit(1)
        with open(args.file, "rb") as f:
            raw = f.read()
        base = os.path.basename(args.file)
        res = summarize_file(raw, base, models=models, timeout=args.timeout)
    else:
        if not args.text:
            print("[rag_sum] Spécifie --file ou --text", file=sys.stderr)
            sys.exit(1)
        res = summarize_text(args.text, models=models, timeout=args.timeout)

    best = res.get("best", {})
    print("=== MODE UTILISÉ:", res.get("used", "none"))
    print("=== FLAGS:", ", ".join(res.get("flags", [])) or "—")
    print("=== MODÈLE:", best.get("model", "—"))
    print("=== SCORE:", f"{best.get('score', 0.0):.3f}")
    print("=== RÉSUMÉ ===")
    print(best.get("answer", ""))

    rep = res.get("report", {})
    if rep:
        print("\n=== QUALITÉ ===")
        print(f"Compression:  {rep.get('compression', 0.0):.2f}")
        print(f"Cosine:       {rep.get('cosine', 0.0):.2f}")
        print(f"ROUGE-1 F1:   {rep.get('rouge1_f1', 0.0):.2f}")
        print(f"ROUGE-2 F1:   {rep.get('rouge2_f1', 0.0):.2f}")
        print(f"Keywords %:   {rep.get('keyword_overlap', 0.0)*100:.0f}%")
        print(f"Phrases OK %: {rep.get('complete_ratio', 0.0)*100:.0f}%")
