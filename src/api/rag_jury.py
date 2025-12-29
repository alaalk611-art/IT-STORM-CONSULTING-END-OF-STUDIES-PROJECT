# -*- coding: utf-8 -*-
# Path: src/api/rag_jury.py
# Endpoint RAG "jury" multi-modèles
# - Appelle plusieurs LLMs (Ollama)
# - Compare les réponses
# - Sélectionne la meilleure
# - speech_rag.py reste INTACT

from __future__ import annotations
from typing import List, Optional, Dict, Any
from fastapi import APIRouter
from pydantic import BaseModel

from src.rag_brain import smart_rag_answer  # moteur RAG existant

router = APIRouter()


# ------------------------------------------------------------------
# Request / Response models
# ------------------------------------------------------------------

class RagJuryRequest(BaseModel):
    question: str
    top_k: int = 2


class RagJuryResult(BaseModel):
    model: str
    answer: str
    sources: List[str]
    quotes: List[Dict[str, Any]]
    confidence: float
    dbg: Dict[str, Any]


# ------------------------------------------------------------------
# Scoring (simple, robuste, explicable)
# ------------------------------------------------------------------

def score_result(r: RagJuryResult) -> float:
    """
    Score simple :
    - confiance prioritaire
    - pénalise réponses vides
    - bonus léger si sources présentes
    """
    text_len = len((r.answer or "").strip())
    has_sources = len(r.sources or []) > 0

    score = r.confidence * 10
    score += min(text_len, 400) / 400.0
    if has_sources:
        score += 0.5

    if text_len < 10:
        score -= 5.0

    return score


# ------------------------------------------------------------------
# Endpoint principal
# ------------------------------------------------------------------

@router.post("/rag/jury")
def rag_jury(req: RagJuryRequest):
    question = req.question.strip()
    top_k = req.top_k or 2

    # Liste des modèles à comparer
    models = [
        "llama3.2:3b",
        "mistral:7b-instruct",
        "qwen2.5:7b",
    ]

    results: List[RagJuryResult] = []

    for model in models:
        try:
            out = smart_rag_answer(
                question=question,
                top_k=top_k,
                model=model,          # 🔑 clé : on force le modèle ici
                mode="fast_phone",    # cohérent avec speech_rag
            )

            results.append(
                RagJuryResult(
                    model=model,
                    answer=out.get("answer", ""),
                    sources=out.get("sources", []),
                    quotes=out.get("quotes", []),
                    confidence=float(out.get("confidence", 0.0)),
                    dbg=out.get("dbg", {}),
                )
            )

        except Exception as e:
            # En cas d'échec d'un modèle, on continue
            results.append(
                RagJuryResult(
                    model=model,
                    answer="",
                    sources=[],
                    quotes=[],
                    confidence=0.0,
                    dbg={"error": str(e)},
                )
            )

    # Sélection du meilleur
    scored = [(score_result(r), r) for r in results]
    scored.sort(key=lambda x: x[0], reverse=True)

    best_score, best = scored[0]
            
    return {
        "answer": best.answer,
        "sources": best.sources,
        "quotes": best.quotes,
        "confidence": best.confidence,
        "quality": {"mode": "jury_fast"},
        "dbg": {
            "selected_model": best.model,
            "score": best_score,
            "jury": [
                {
                    "model": r.model,
                    "confidence": r.confidence,
                    "sources": len(r.sources),
                }
                for r in results
            ],
        },
    }
