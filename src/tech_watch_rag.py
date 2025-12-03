# -*- coding: utf-8 -*-
# ============================================================
# Path: src/tech_watch_rag.py
# Role: Mini-RAG / résumé pour la veille technologique
# - Entrée : texte brut (extrait d'article, contenu de page web)
# - 3 modèles Ollama (mistral / llama3.2 / qwen2.5)
# - Résumé final : 2 phrases max, ton neutre, rien inventer
# - Score simple par modèle, sélection du meilleur
# - Fallback rule-based si Ollama indisponible
# ============================================================

from __future__ import annotations

import re
import time
from typing import Any, Dict, List, Optional

# ------------------------------------------------------------
# Dépendances facultatives
# ------------------------------------------------------------
try:
    # Ton client Ollama existant
    from src.llm.ollama_client import generate_ollama  # type: ignore
except Exception:  # pragma: no cover
    generate_ollama = None  # type: ignore

try:
    # On réutilise ton calcul de qualité depuis rag_sum
    from src.rag_sum import summary_quality_report  # type: ignore
except Exception:  # pragma: no cover
    summary_quality_report = None  # type: ignore


# ------------------------------------------------------------
# Config par défaut
# ------------------------------------------------------------
DEFAULT_MODELS: List[str] = [
    "mistral:7b-instruct",

]


# ------------------------------------------------------------
# Helpers texte
# ------------------------------------------------------------
def _clean_text(text: str) -> str:
    t = (text or "").strip()
    # On enlève les espaces multiples
    t = re.sub(r"\s+", " ", t)
    return t


def _split_sentences(text: str) -> List[str]:
    """Découpage très simple en phrases."""
    raw = (text or "").strip()
    if not raw:
        return []
    parts = re.split(r"(?<=[\.!\?…])\s+|\n+", raw)
    return [p.strip() for p in parts if p.strip()]


def _keep_max_two_sentences(text: str) -> str:
    """Garde au plus 2 phrases, proprement ponctuées."""
    sents = _split_sentences(text)
    if not sents:
        return ""
    kept = sents[:2]
    out = " ".join(kept).strip()
    # On force un point final si besoin
    if out and not re.search(r"[\.!\?…]$", out):
        out += "."
    return out


def _strip_llm_prefixes(text: str) -> str:
    """Supprime les débuts typiques 'Voici le résumé', 'Résumé:' etc."""
    t = (text or "").strip()
    if not t:
        return t

    patterns = [
        r"^voici un résumé[^:\n]*:\s*",
        r"^voici le résumé[^:\n]*:\s*",
        r"^résumé\s*:\s*",
        r"^summary\s*:\s*",
        r"^en résumé\s*:\s*",
    ]
    for pat in patterns:
        t = re.sub(pat, "", t, flags=re.I)
    return t.strip()


def _fallback_two_sentences(text: str) -> str:
    """
    Fallback sans LLM :
    - prend les 2 premières phrases 'porteuses' du texte.
    """
    sents = _split_sentences(text)
    if not sents:
        # On coupe brut si vraiment rien de structuré
        t = (text or "").strip()
        return t[:280] + "…" if len(t) > 280 else t
    return _keep_max_two_sentences(" ".join(sents))


# ------------------------------------------------------------
# Scoring simple basé sur summary_quality_report (si dispo)
# ------------------------------------------------------------
def _compute_score(source: str, summary: str) -> float:
    """
    Score dans [0,1] basé sur quelques métriques.
    Si summary_quality_report n'est pas dispo, on renvoie 0.5.
    """
    if not source or not summary:
        return 0.0

    if summary_quality_report is None:
        return 0.5

    try:
        rep = summary_quality_report(source, summary)  # type: ignore
    except Exception:
        return 0.5

    cos = float(rep.get("cosine", 0.0))
    r1 = float(rep.get("rouge1_f1", 0.0))
    kw = float(rep.get("keyword_overlap", 0.0))
    sent_ok = float(rep.get("complete_ratio", 0.0))

    # Pondération simple
    score = 0.40 * cos + 0.25 * r1 + 0.20 * kw + 0.15 * sent_ok
    if score < 0.0:
        score = 0.0
    if score > 1.0:
        score = 1.0
    return score


# ------------------------------------------------------------
# Cœur : résumé multi-modèles pour un texte de veille
# ------------------------------------------------------------
def summarize_news_text(
    text: str,
    models: Optional[List[str]] = None,
    timeout: float = 120.0,
) -> Dict[str, Any]:
    """
    Résume un texte (article / page web) en 2 phrases max avec 3 modèles Ollama.

    Retourne :
    {
        "summary": str,        # meilleur résumé (2 phrases max)
        "model": str,          # modèle gagnant
        "score": float,        # score du modèle gagnant
        "candidates": [        # tous les candidats (pour debug ou UI avancée)
            {
                "model": str,
                "raw_answer": str,
                "summary_2_sent": str,
                "score": float,
                "time": float,
            },
            ...
        ]
    }
    """
    text = _clean_text(text)
    if not text:
        return {
            "summary": "",
            "model": "",
            "score": 0.0,
            "candidates": [],
            "used": "empty",
        }

    models = [m.strip() for m in (models or DEFAULT_MODELS) if m.strip()]

    # Si Ollama indispo ou aucun modèle -> fallback simple
    if generate_ollama is None or not models:  # type: ignore
        fb = _fallback_two_sentences(text)
        return {
            "summary": fb,
            "model": "rule-two-sentences",
            "score": 1.0,
            "candidates": [
                {
                    "model": "rule-two-sentences",
                    "raw_answer": fb,
                    "summary_2_sent": fb,
                    "score": 1.0,
                    "time": 0.0,
                }
            ],
            "used": "fallback",
        }

    # Contexte tronqué pour ne pas exploser le CPU
    max_chars = 3500
    snippet = text if len(text) <= max_chars else text[:max_chars] + "\n[Texte tronqué]"

    prompt = (
        "Tu es un assistant de veille technologique pour des consultants cloud, data, IA et DevOps.\n"
        "À partir du texte ci-dessous, écris un résumé en français de **deux phrases maximum**.\n"
        "- 2 phrases maximum.\n"
        "- Pas de puces, pas de liste.\n"
        "- Ne parle pas de toi, ne mentionne pas que tu es un modèle.\n"
        "- Ne rien inventer : reste fidèle au texte.\n\n"
        "TEXTE:\n"
        f"{snippet}\n\n"
        "RÉSUMÉ:"
    )

    candidates: List[Dict[str, Any]] = []
    total = len(models)

    for idx, mdl in enumerate(models, start=1):
        label = f"[{idx}/{total}] {mdl}"
        t0 = time.time()
        raw_answer = ""
        try:
            raw_answer = generate_ollama(  # type: ignore
                mdl,
                prompt,
                temperature=0.2,
                max_tokens=160,
                stream=True,
                timeout=timeout,
                options={
                    "num_ctx": 1536,
                    "top_k": 40,
                    "top_p": 0.9,
                    "repeat_penalty": 1.05,
                },
            ) or ""
        except Exception:
            raw_answer = ""

        dt = time.time() - t0
        raw_answer = _strip_llm_prefixes(raw_answer.strip())

        if not raw_answer:
            # Fallback par modèle -> 2 phrases rule-based
            fb = _fallback_two_sentences(text)
            cand_summary = fb
            score = _compute_score(text, cand_summary)
            candidates.append(
                {
                    "model": f"{mdl} (fallback)",
                    "raw_answer": fb,
                    "summary_2_sent": cand_summary,
                    "score": score,
                    "time": dt,
                }
            )
            continue

        cand_summary = _keep_max_two_sentences(raw_answer)
        score = _compute_score(text, cand_summary)

        candidates.append(
            {
                "model": mdl,
                "raw_answer": raw_answer,
                "summary_2_sent": cand_summary,
                "score": score,
                "time": dt,
            }
        )

    if not candidates:
        fb = _fallback_two_sentences(text)
        return {
            "summary": fb,
            "model": "rule-two-sentences",
            "score": 1.0,
            "candidates": [],
            "used": "fallback-no-candidate",
        }

    best = max(candidates, key=lambda c: c.get("score", 0.0))
    return {
        "summary": best.get("summary_2_sent", ""),
        "model": best.get("model", ""),
        "score": float(best.get("score", 0.0)),
        "candidates": candidates,
        "used": "ollama-3models",
    }



# ------------------------------------------------------------
# Entrée simple pour le backend de veille
# ------------------------------------------------------------
def summarize_for_tech_watch(text: str, max_len: int = 350) -> str:
    """
    Wrapper utilisé par src/api/tech_watch._smart_summarize.

    - Utilise summarize_news_text en mode "rapide" pour la veille :
      • 1 seul modèle (mistral:7b-instruct)
      • timeout court (40s)
    - Récupère le meilleur résumé (2 phrases max)
    - Tronque éventuellement à max_len caractères pour la base.
    """
    text = (text or "").strip()
    if not text:
        return ""

    # ⚡ Mode rapide pour la veille : 1 modèle, timeout réduit
    try:
        res = summarize_news_text(
            text,
            models=["mistral:7b-instruct"],  # un seul modèle pour limiter le temps
            timeout=40.0,                    # max 40s pour ce résumé
        )
    except Exception:
        # Si Ollama plante ou est indisponible → fallback interne
        res = summarize_news_text(text, models=[], timeout=5.0)

    summary = (res.get("summary") or "").strip()

    if max_len and len(summary) > max_len:
        summary = summary[:max_len].rstrip() + "…"

    return summary

# ------------------------------------------------------------
# Helper pratique pour un item de /tech/watch
# ------------------------------------------------------------
def summarize_tech_watch_item(
    item: Dict[str, Any],
    models: Optional[List[str]] = None,
    timeout: float = 120.0,
) -> Dict[str, Any]:
    """
    Prend un item de l'API /tech/watch/latest et ajoute un résumé 2 phrases.

    On utilise dans l'ordre :
      - item["summary_long"] si présent
      - item["summary"]
      - item["short_summary"]
    """
    text = (
        item.get("summary_long")
        or item.get("summary")
        or item.get("short_summary")
        or ""
    )

    res = summarize_news_text(text, models=models, timeout=timeout)

    out = dict(item)
    out["tw_summary_2_sent"] = res["summary"]
    out["tw_summary_model"] = res["model"]
    out["tw_summary_score"] = res["score"]
    return out
