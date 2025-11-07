# -*- coding: utf-8 -*-
# ============================================================
# Path: src/rag_sum.py
# Role: Moteur de résumé indépendant (texte / fichier)
# - Jury multi-modèles via Ollama (si dispo)
# - Fallback sur rag_brain.smart_rag_answer(mode="summarize")
# - Indicateurs de qualité locaux (compression, cosine, ROUGE-1/2, mots-clés, phrases non ancrées)
# - Lecture .txt / .pdf (PyPDF2 optionnel)
# - API: summarize_text(), summarize_file(), summary_quality_report(), select_best()
# ============================================================

from __future__ import annotations
import io
import re
import os
import math
from typing import List, Dict, Any, Tuple, Optional
from collections import Counter

# =========================
# Imports facultatifs
# =========================
try:
    # rag_brain: pour fallback robuste (zéro hallucination + citations)
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

def _rouge_prf(ref: str, hyp: str, n: int = 1) -> dict:
    r_toks, h_toks = _tok(ref), _tok(hyp)
    r_ngr, h_ngr = Counter(_ngrams(r_toks, n)), Counter(_ngrams(h_toks, n))
    overlap = sum((r_ngr & h_ngr).values())
    R = overlap / (sum(r_ngr.values()) or 1)
    P = overlap / (sum(h_ngr.values()) or 1)
    F = (2*P*R)/(P+R) if (P+R) > 0 else 0.0
    return {"P": P, "R": R, "F1": F}

def _keyword_overlap(ref: str, hyp: str, k: int = 20) -> float:
    rt = [t for t in _tok(ref) if len(t) > 2]
    ht = set([t for t in _tok(hyp) if len(t) > 2])
    if not rt or not ht:
        return 0.0
    top = [w for w, _ in Counter(rt).most_common(k)]
    hit = sum(1 for w in top if w in ht)
    return hit / max(1, len(top))

def _cosine_sim(ref: str, hyp: str) -> float:
    r, h = Counter(_tok(ref)), Counter(_tok(hyp))
    if not r or not h:
        return 0.0
    inter = set(r) & set(h)
    num = sum(r[w]*h[w] for w in inter)
    nr = math.sqrt(sum(v*v for v in r.values()))
    nh = math.sqrt(sum(v*v for v in h.values()))
    return num / (nr*nh) if nr*nh > 0 else 0.0

def _unsupported_sentences(ref: str, hyp: str, thr: float = 0.15) -> list[str]:
    """
    Heuristique : phrases du résumé dont le chevauchement en 3-grammes
    avec le texte source est très faible → potentielle hallucination.
    """
    ref_3 = set(_ngrams(_tok(ref), 3))
    out = []
    for sent in re.split(r"(?<=[\.\!\?])\s+", (hyp or "").strip()):
        if not sent:
            continue
        s3 = _ngrams(_tok(sent), 3)
        if not s3:
            continue
        overlap = sum(1 for g in s3 if g in ref_3) / len(s3)
        if overlap < thr:
            out.append(sent.strip())
    return out

def summary_quality_report(source_text: str, summary_text: str) -> dict:
    Ls, Lh = len(_tok(source_text)), len(_tok(summary_text))
    comp = (1 - (Lh / max(1, Ls))) if Ls else 0.0
    rouge1 = _rouge_prf(source_text, summary_text, n=1)
    rouge2 = _rouge_prf(source_text, summary_text, n=2)
    sim   = _cosine_sim(source_text, summary_text)
    kw    = _keyword_overlap(source_text, summary_text, k=20)
    unsup = _unsupported_sentences(source_text, summary_text, thr=0.15)
    return {
        "tokens_source": Ls,
        "tokens_summary": Lh,
        "compression": comp,         # viser ~0.6–0.9
        "cosine": sim,               # 0–1
        "rouge1_f1": rouge1["F1"],
        "rouge2_f1": rouge2["F1"],
        "keyword_overlap": kw,       # 0–1 (~≥0.4 rassurant)
        "unsupported": unsup,
    }

# =========================
# Lecture fichiers
# =========================

def _read_txt(b: bytes) -> str:
    return (b or b"").decode("utf-8", errors="ignore")

def _read_pdf(b: bytes) -> str:
    try:
        import PyPDF2  # facultatif
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
    """
    Retourne (texte, extension) pour .txt / .pdf. Vide si non lu.
    """
    name = (filename or "").lower()
    if name.endswith(".txt"):
        return _read_txt(file_bytes), ".txt"
    if name.endswith(".pdf"):
        return _read_pdf(file_bytes), ".pdf"
    return "", ""

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
# Résumé (texte brut)
# =========================

def _jury_summarize_prompt(text: str, max_chars: int = 6000) -> str:
    snippet = (text or "").strip()
    if len(snippet) > max_chars:
        snippet = snippet[:max_chars] + "\n[Texte tronqué pour résumé]"
    return (
        "Résume fidèlement le texte ci-dessous en français, sans inventer. "
        "Donne un paragraphe synthétique puis 3–5 puces clés.\n\n"
        "TEXTE:\n" + snippet
    )

def summarize_text(text: str, models: List[str], timeout: float = 90.0) -> Dict[str, Any]:
    """
    Résume 'text' avec jury Ollama si dispo, sinon fallback smart_rag_answer(mode='summarize').
    Retourne:
      {
        "best": {...},                  # meilleur résultat normalisé
        "results": [...],               # tous les résultats normalisés (jury)
        "report": {...},                # quality report (sur 'best')
        "used": "jury" | "rag"
      }
    """
    if not text or not text.strip():
        return {"best": {}, "results": [], "report": {}, "used": "none"}

    # 1) Jury multi-modèles si accessible
    if callable(_ASK_MULTI) and models:
        prompt = _jury_summarize_prompt(text)
        try:
            raw = _ASK_MULTI(prompt, models=models, topk_context=0, timeout=timeout) or {}
            results = normalize_results(raw.get("results") or [])
            if results:
                best = select_best(results)
                report = summary_quality_report(text, best.get("answer", ""))
                return {"best": best, "results": results, "report": report, "used": "jury"}
        except Exception:
            pass

    # 2) Fallback smart_rag (mode summarize)
    if callable(_SMART_RAG_ANS):
        try:
            prompt = _jury_summarize_prompt(text)
            base = _SMART_RAG_ANS(question=prompt, mode="summarize") or {}
            best = {
                "model": "smart_rag_answer",
                "answer": base.get("answer", ""),
                "score":  _safe_num(base.get("confidence", 0.0)),
                "confidence": _safe_num(base.get("confidence", 0.0)),
                "grounding":  _safe_num((base.get("quality") or {}).get("grounding", 0.0)),
                "coverage":   _safe_num((base.get("quality") or {}).get("coverage", 0.0)),
                "style":      _safe_num((base.get("quality") or {}).get("style", 0.0)),
                "time":       0.0,
            }
            report = summary_quality_report(text, best.get("answer", ""))
            return {"best": best, "results": [best], "report": report, "used": "rag"}
        except Exception:
            pass

    return {"best": {}, "results": [], "report": {}, "used": "none"}

# =========================
# Résumé (fichier uploadé)
# =========================

def summarize_file(file_bytes: bytes, filename: str, models: List[str], timeout: float = 90.0) -> Dict[str, Any]:
    """
    Lit le fichier (.txt/.pdf), appelle summarize_text(), renvoie la même structure.
    """
    text, ext = read_any_text(file_bytes, filename)
    if not text:
        return {"best": {}, "results": [], "report": {}, "used": "none", "error": f"Impossible de lire: {filename}"}
    out = summarize_text(text, models=models, timeout=timeout)
    out["source_ext"] = ext
    out["source_name"] = filename
    out["tokens_source"] = len(_tok(text))
    out["tokens_summary"] = len(_tok(out.get("best", {}).get("answer", "")))
    return out

# =========================
# Petit CLI de test (optionnel)
# =========================
if __name__ == "__main__":
    import argparse, sys
    p = argparse.ArgumentParser(description="RAG Summarizer (jury + fallback)")
    p.add_argument("--file", type=str, help="Chemin d'un .txt ou .pdf")
    p.add_argument("--text", type=str, help="Texte brut à résumer")
    p.add_argument("--models", type=str, default="mistral:7b-instruct,llama3.2:3b,qwen2.5:7b",
                   help="Modèles Ollama séparés par des virgules")
    p.add_argument("--timeout", type=float, default=90.0)
    args = p.parse_args()

    models = [m.strip() for m in (args.models or "").split(",") if m.strip()]
    if args.file:
        try:
            with open(args.file, "rb") as f:
                b = f.read()
        except Exception as e:
            print(f"[ERR] Lecture {args.file}: {e}", file=sys.stderr)
            sys.exit(1)
        res = summarize_file(b, os.path.basename(args.file), models=models, timeout=args.timeout)
    else:
        text = (args.text or "").strip()
        if not text:
            print("Fournir --file ou --text", file=sys.stderr)
            sys.exit(2)
        res = summarize_text(text, models=models, timeout=args.timeout)

    best = res.get("best", {})
    print("=== MODE UTILISÉ:", res.get("used", "none"))
    print("=== MODÈLE:", best.get("model", "—"))
    print("=== SCORE:", best.get("score", 0.0))
    print("=== RÉSUMÉ ===")
    print(best.get("answer", ""))
    rep = res.get("report", {})
    if rep:
        print("\n=== QUALITÉ ===")
        print(f"Compression: {rep.get('compression', 0.0):.2f}")
        print(f"Cosine:      {rep.get('cosine', 0.0):.2f}")
        print(f"ROUGE-1 F1:  {rep.get('rouge1_f1', 0.0):.2f}")
        print(f"ROUGE-2 F1:  {rep.get('rouge2_f1', 0.0):.2f}")
        print(f"Keywords %:  {rep.get('keyword_overlap', 0.0)*100:.0f}%")
        if rep.get("unsupported"):
            print("Phrases possiblement non ancrées:")
            for s in rep["unsupported"]:
                print("- ", s)
