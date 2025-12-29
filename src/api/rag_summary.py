# -*- coding: utf-8 -*-
# Path: src/api/rag_summary.py
# Endpoint résumé (texte + fichier) basé sur src/rag_sum.py

from __future__ import annotations
from typing import List, Optional, Any, Dict

from fastapi import APIRouter, UploadFile, File, HTTPException
from pydantic import BaseModel, Field

from src.rag_sum import summarize_text, summarize_file  # moteur résumé existant

router = APIRouter()


# ----------------------------
# Models
# ----------------------------
DEFAULT_MODELS = ["mistral:7b-instruct", "llama3.2:3b", "qwen2.5:7b"]


class SummaryTextIn(BaseModel):
    text: str = Field(..., min_length=1)
    models: Optional[List[str]] = None
    timeout: float = 90.0


class SummaryOut(BaseModel):
    summary: str
    model: str
    score: float
    confidence: float
    used: str
    flags: List[str]
    report: Dict[str, Any]
    meta: Dict[str, Any]


# ----------------------------
# Endpoints
# ----------------------------
@router.post("/rag/summary", response_model=SummaryOut)
def rag_summary(payload: SummaryTextIn) -> SummaryOut:
    text = (payload.text or "").strip()
    if not text:
        raise HTTPException(status_code=400, detail="text is required")

    models = payload.models or DEFAULT_MODELS
    try:
        res = summarize_text(text, models=models, timeout=float(payload.timeout))
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"summary engine error: {e}")

    best = (res.get("best") or {})
    report = (res.get("report") or {})
    flags = list(res.get("flags") or [])
    used = str(res.get("used") or "unknown")

    summary = (best.get("answer") or "").strip()
    if not summary:
        raise HTTPException(status_code=500, detail="empty summary returned")

    return SummaryOut(
        summary=summary,
        model=str(best.get("model") or "—"),
        score=float(best.get("score") or 0.0),
        confidence=float(best.get("confidence") or best.get("score") or 0.0),
        used=used,
        flags=flags,
        report=report,
        meta={
            "tokens_source": int(res.get("tokens_source") or 0),
            "tokens_summary": int(res.get("tokens_summary") or 0),
            "source_name": res.get("source_name"),
            "source_ext": res.get("source_ext"),
        },
    )

# ----------------------------
# FAST (1 modèle, sans param models)
# ----------------------------
FAST_MODEL = "mistral:7b-instruct"  # change ici si tu veux un autre modèle

class SummaryFastIn(BaseModel):
    text: str = Field(..., min_length=1)
    timeout: float = 60.0  # plus court = plus rapide

@router.post("/rag/summary_fast")
def rag_summary_fast(payload: SummaryFastIn):
    text = (payload.text or "").strip()
    if not text:
        raise HTTPException(status_code=400, detail="text is required")

    try:
        res = summarize_text(text, models=[FAST_MODEL], timeout=float(payload.timeout))
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"summary engine error: {e}")

    best = (res.get("best") or {})
    summary = (best.get("answer") or "").strip()
    if not summary:
        raise HTTPException(status_code=500, detail="empty summary returned")

    # Format “jury-like” (pratique pour n8n)
    return {
        "answer": summary,
        "selected_model": str(best.get("model") or FAST_MODEL),
        "score": float(best.get("score") or 0.0),
        "confidence": float(best.get("confidence") or best.get("score") or 0.0),
        "dbg": {
            "used": str(res.get("used") or "fast"),
            "flags": list(res.get("flags") or []),
            "report": res.get("report") or {},
            "meta": {
                "tokens_source": int(res.get("tokens_source") or 0),
                "tokens_summary": int(res.get("tokens_summary") or 0),
            },
        },
    }

@router.post("/rag/summary_file", response_model=SummaryOut)
async def rag_summary_file(
    file: UploadFile = File(...),
    models: Optional[str] = None,   # ex: "mistral:7b-instruct,llama3.2:3b"
    timeout: float = 90.0,
) -> SummaryOut:
    raw = await file.read()
    if not raw:
        raise HTTPException(status_code=400, detail="empty file")

    if models:
        model_list = [m.strip() for m in models.split(",") if m.strip()]
    else:
        model_list = DEFAULT_MODELS

    try:
        res = summarize_file(raw, file.filename or "upload", models=model_list, timeout=float(timeout))
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"summary file engine error: {e}")

    best = (res.get("best") or {})
    report = (res.get("report") or {})
    flags = list(res.get("flags") or [])
    used = str(res.get("used") or "unknown")

    summary = (best.get("answer") or "").strip()
    if not summary:
        raise HTTPException(status_code=500, detail="empty summary returned")

    return SummaryOut(
        summary=summary,
        model=str(best.get("model") or "—"),
        score=float(best.get("score") or 0.0),
        confidence=float(best.get("confidence") or best.get("score") or 0.0),
        used=used,
        flags=flags,
        report=report,
        meta={
            "tokens_source": int(res.get("tokens_source") or 0),
            "tokens_summary": int(res.get("tokens_summary") or 0),
            "source_name": res.get("source_name"),
            "source_ext": res.get("source_ext"),
        },
    )
