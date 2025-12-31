# -*- coding: utf-8 -*-
# Path: src/api/rag_summary.py
# Résumé "jury-like" (aligné sur rag_jury.py)
# - Summary s'appuie sur src/rag_sum.py
# - Retourne le même format que /rag/jury : answer/confidence/quality/dbg(jury)
# - Compatible n8n : JSON + x-www-form-urlencoded + multipart
#
# Endpoints:
# - POST /rag/summary       -> jury multi-modèles (format jury)
# - POST /rag/summary_fast  -> 1 modèle (format jury)
# - POST /rag/summary_file  -> fichier (jury multi-modèles, format jury)

from __future__ import annotations
from typing import Any, Dict, List, Optional

from fastapi import APIRouter, UploadFile, File, HTTPException, Request

from src.rag_sum import summarize_text, summarize_file

router = APIRouter()

DEFAULT_MODELS = ["llama3.2:3b", "mistral:7b-instruct", "qwen2.5:7b"]
FAST_MODEL = "llama3.2:3b"


# ------------------------------------------------------------------
# Helpers : accepter JSON + FORM (n8n-friendly)
# ------------------------------------------------------------------
async def _read_payload_any(request: Request) -> Dict[str, Any]:
    ctype = (request.headers.get("content-type") or "").lower()

    if "application/json" in ctype:
        try:
            data = await request.json()
            return data if isinstance(data, dict) else {}
        except Exception:
            return {}

    if ("application/x-www-form-urlencoded" in ctype) or ("multipart/form-data" in ctype):
        try:
            form = await request.form()
            return dict(form)
        except Exception:
            return {}

    # fallback (tenter json puis form)
    try:
        data = await request.json()
        return data if isinstance(data, dict) else {}
    except Exception:
        pass
    try:
        form = await request.form()
        return dict(form)
    except Exception:
        return {}


def _parse_timeout(v: Any, default: float) -> float:
    try:
        return float(v)
    except Exception:
        return float(default)


def _parse_models(v: Any) -> Optional[List[str]]:
    """
    Supporte:
    - ["m1","m2"]
    - "m1,m2"
    - "['m1','m2']" (string JSON)
    - "m1" (single)
    """
    if v is None:
        return None

    if isinstance(v, list):
        out = [str(x).strip() for x in v if str(x).strip()]
        return out or None

    s = str(v).strip()
    if not s:
        return None

    # "m1,m2"
    if "," in s and not (s.startswith("[") and s.endswith("]")):
        out = [x.strip() for x in s.split(",") if x.strip()]
        return out or None

    # string JSON list
    if s.startswith("[") and s.endswith("]"):
        try:
            import json
            arr = json.loads(s)
            if isinstance(arr, list):
                out = [str(x).strip() for x in arr if str(x).strip()]
                return out or None
        except Exception:
            return None

    return [s]


def _extract_text(payload: Dict[str, Any]) -> str:
    for k in ("text", "content", "message", "email_text"):
        if k in payload and payload.get(k) is not None:
            t = str(payload.get(k)).strip()
            if t:
                return t
    return ""


# ------------------------------------------------------------------
# Scoring (simple, robuste, explicable) — comme rag_jury.py
# ------------------------------------------------------------------
def _score_candidate(answer: str, confidence: float) -> float:
    text_len = len((answer or "").strip())
    score = float(confidence) * 10.0
    score += min(text_len, 400) / 400.0
    if text_len < 10:
        score -= 5.0
    return score


def _run_one_model(text: str, model: str, timeout: float) -> Dict[str, Any]:
    """
    Appelle summarize_text() en forçant un seul modèle.
    On normalise la sortie en "candidate" (model/answer/confidence/score/dbg).
    """
    try:
        res = summarize_text(text, models=[model], timeout=float(timeout))
        best = (res.get("best") or {})
        answer = (best.get("answer") or "").strip()
        conf = float(best.get("confidence") or best.get("score") or 0.0)
        used = str(res.get("used") or "unknown")
        flags = list(res.get("flags") or [])
        report = res.get("report") or {}
        meta = {
            "tokens_source": int(res.get("tokens_source") or 0),
            "tokens_summary": int(res.get("tokens_summary") or 0),
        }
        return {
            "model": model,
            "answer": answer,
            "confidence": conf,
            "dbg": {"used": used, "flags": flags, "report": report, "meta": meta},
        }
    except Exception as e:
        return {
            "model": model,
            "answer": "",
            "confidence": 0.0,
            "dbg": {"error": str(e)},
        }


# ------------------------------------------------------------------
# Endpoints
# ------------------------------------------------------------------
@router.post("/rag/summary")
async def rag_summary_jury_like(request: Request):
    """
    Multi-modèles, format identique à /rag/jury.
    """
    payload = await _read_payload_any(request)
    text = _extract_text(payload)
    if not text:
        raise HTTPException(status_code=400, detail="text is required")

    timeout = _parse_timeout(payload.get("timeout"), 90.0)
    models = _parse_models(payload.get("models")) or DEFAULT_MODELS

    results: List[Dict[str, Any]] = []
    for m in models:
        results.append(_run_one_model(text=text, model=m, timeout=timeout))

    scored = [(_score_candidate(r.get("answer", ""), float(r.get("confidence", 0.0))), r) for r in results]
    scored.sort(key=lambda x: x[0], reverse=True)

    best_score, best = scored[0]
    best_answer = (best.get("answer") or "").strip()
    if not best_answer:
        raise HTTPException(status_code=500, detail="empty summary returned")

    return {
        "answer": best_answer,
        "sources": [],   # résumé ≠ RAG : pas de sources/quotes
        "quotes": [],
        "confidence": float(best.get("confidence") or 0.0),
        "quality": {"mode": "summary_jury"},
        "dbg": {
            "selected_model": str(best.get("model") or "—"),
            "score": float(best_score),
            "jury": [
                {
                    "model": r.get("model"),
                    "confidence": float(r.get("confidence") or 0.0),
                    "has_answer": bool((r.get("answer") or "").strip()),
                }
                for r in results
            ],
            "best_dbg": best.get("dbg") or {},
        },
    }


@router.post("/rag/summary_fast")
async def rag_summary_fast_jury_like(request: Request):
    """
    1 modèle, format identique à /rag/jury.
    Utile pour n8n (simple + stable).
    """
    payload = await _read_payload_any(request)
    text = _extract_text(payload)
    if not text:
        raise HTTPException(status_code=400, detail="text is required")

    timeout = _parse_timeout(payload.get("timeout"), 60.0)
    model = str(payload.get("model") or FAST_MODEL).strip() or FAST_MODEL

    cand = _run_one_model(text=text, model=model, timeout=timeout)
    answer = (cand.get("answer") or "").strip()
    if not answer:
        raise HTTPException(status_code=500, detail="empty summary returned")

    sc = _score_candidate(answer, float(cand.get("confidence") or 0.0))

    return {
        "answer": answer,
        "sources": [],
        "quotes": [],
        "confidence": float(cand.get("confidence") or 0.0),
        "quality": {"mode": "summary_fast"},
        "dbg": {
            "selected_model": cand.get("model"),
            "score": float(sc),
            "model_dbg": cand.get("dbg") or {},
        },
    }


@router.post("/rag/summary_file")
async def rag_summary_file_jury_like(
    file: UploadFile = File(...),
    models: Optional[str] = None,  # ex: "mistral:7b-instruct,llama3.2:3b"
    timeout: float = 90.0,
):
    raw = await file.read()
    if not raw:
        raise HTTPException(status_code=400, detail="empty file")

    model_list: List[str]
    if models:
        model_list = [m.strip() for m in models.split(",") if m.strip()]
    else:
        model_list = DEFAULT_MODELS

    try:
        res = summarize_file(raw, file.filename or "upload", models=model_list, timeout=float(timeout))
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"summary file engine error: {e}")

    best = (res.get("best") or {})
    answer = (best.get("answer") or "").strip()
    if not answer:
        raise HTTPException(status_code=500, detail="empty summary returned")

    conf = float(best.get("confidence") or best.get("score") or 0.0)
    sc = _score_candidate(answer, conf)

    return {
        "answer": answer,
        "sources": [],
        "quotes": [],
        "confidence": conf,
        "quality": {"mode": "summary_file"},
        "dbg": {
            "selected_model": str(best.get("model") or "—"),
            "score": float(sc),
            "used": str(res.get("used") or "unknown"),
            "flags": list(res.get("flags") or []),
            "report": res.get("report") or {},
            "meta": {
                "tokens_source": int(res.get("tokens_source") or 0),
                "tokens_summary": int(res.get("tokens_summary") or 0),
                "source_name": res.get("source_name"),
                "source_ext": res.get("source_ext"),
                "filename": file.filename,
            },
        },
    }
