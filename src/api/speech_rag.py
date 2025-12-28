# -*- coding: utf-8 -*-
# Path: src/api/speech_rag.py
# RAG API — /ask (ancré) + /generate (LLM pur) + /hybrid (RAG->contexte->LLM)

from __future__ import annotations

import os
import re
from typing import Any, Dict, List, Optional, Tuple

import requests
from fastapi import APIRouter, HTTPException
from fastapi.responses import JSONResponse
from pydantic import BaseModel

router = APIRouter()

# -------- optional import rag_brain --------
try:
    from src import rag_brain  # type: ignore
except Exception as e:
    rag_brain = None
    _IMPORT_ERR = str(e)


# ----------------- Models -----------------
class RagAskRequest(BaseModel):
    question: str
    top_k: int = 6


# ----------------- Helpers -----------------
def _extract_user_question(maybe_prompt: str) -> str:
    """
    Ton front envoie parfois un "prompt enrichi" contenant des règles + 'Question : ...'
    On récupère la vraie question pour améliorer la recherche RAG.
    """
    t = (maybe_prompt or "").strip()
    if not t:
        return ""
    m = re.search(r"\bQuestion\s*:\s*(.+)\s*$", t, flags=re.IGNORECASE | re.DOTALL)
    if m:
        return (m.group(1) or "").strip()
    return t


def _normalize_quotes(quotes: Any, max_items: int = 8) -> List[Dict[str, str]]:
    """
    Supporte plusieurs formats possibles (list[str], list[dict], dict…).
    Retourne une liste de {text, source?}.
    """
    out: List[Dict[str, str]] = []
    if not quotes:
        return out

    if isinstance(quotes, dict):
        # parfois: {"quotes":[...]}
        quotes = quotes.get("quotes")

    if isinstance(quotes, list):
        for q in quotes[:max_items]:
            if isinstance(q, str):
                s = q.strip()
                if s:
                    out.append({"text": s})
            elif isinstance(q, dict):
                txt = (q.get("text") or q.get("quote") or q.get("chunk") or "").strip()
                src = (q.get("source") or q.get("doc") or q.get("title") or "").strip()
                if txt:
                    d = {"text": txt}
                    if src:
                        d["source"] = src
                    out.append(d)
    return out


def _build_hybrid_prompt(user_q: str, quotes: List[Dict[str, str]]) -> str:
    """
    Prompt: réponse générée MAIS strictement basée sur le contexte.
    """
    ctx_lines: List[str] = []
    for i, q in enumerate(quotes, start=1):
        txt = (q.get("text") or "").strip()
        src = (q.get("source") or "").strip()
        if not txt:
            continue
        if src:
            ctx_lines.append(f"[{i}] {txt}\nSource: {src}")
        else:
            ctx_lines.append(f"[{i}] {txt}")

    context_block = "\n\n".join(ctx_lines).strip()

    return f"""
Tu es l’assistant vocal de StormCopilot.
Tu réponds en français, avec un ton naturel et professionnel.

Règles strictes :
- Réponds en 2 à 4 phrases maximum.
- Réponse générée, claire, utile, sans blabla.
- Appuie-toi UNIQUEMENT sur le Contexte ci-dessous.
- Si le contexte ne suffit pas pour répondre avec certitude, dis exactement : "Je ne sais pas."
- Ne cite pas de liens, ne fabrique pas de chiffres, ne devine pas.

Contexte :
{context_block if context_block else "(vide)"}

Question :
{user_q}

Réponse :
""".strip()


def _ollama_generate(prompt: str) -> Dict[str, Any]:
    base = (os.getenv("OLLAMA_BASE_URL") or os.getenv("OLLAMA_URL") or "http://127.0.0.1:11434").rstrip("/")
    model = (os.getenv("VOICE_FAST_MODEL") or "llama3.2:3b").strip()
    timeout = int(os.getenv("VOICE_FAST_TIMEOUT") or "120")
    max_tokens = int(os.getenv("VOICE_FAST_MAX_TOKENS") or "220")

    url = f"{base}/api/generate"
    payload = {
        "model": model,
        "prompt": prompt,
        "stream": False,
        "options": {
            "num_predict": max_tokens,
            "temperature": 0.2,
        },
    }

    r = requests.post(url, json=payload, timeout=timeout)
    r.raise_for_status()
    j = r.json() if isinstance(r.json(), dict) else {}
    text = (j.get("response") or "").strip()
    return {"answer": text, "model": model, "raw": j}


# ----------------- Routes -----------------
@router.post("/ask")
async def rag_ask(req: RagAskRequest):
    """
    Réponse RAG "ancrée" (comportement historique).
    """
    if rag_brain is None:
        raise HTTPException(status_code=500, detail=f"rag_brain_import_failed: {_IMPORT_ERR}")

    q = (req.question or "").strip()
    if len(q) < 2:
        return JSONResponse(status_code=422, content={"answer": "", "sources": [], "quotes": []})

    try:
        out = rag_brain.smart_rag_answer(q, top_k=req.top_k)  # type: ignore[attr-defined]
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"rag_ask_failed: {e}")

    return JSONResponse(
        status_code=200,
        content={
            "answer": out.get("answer", ""),
            "sources": out.get("sources", []),
            "quotes": out.get("quotes", []),
            "confidence": out.get("confidence", 0.0),
            "quality": out.get("quality", {}),
            "dbg": out.get("dbg", {}),
        },
    )


@router.post("/generate")
async def llm_generate(req: RagAskRequest):
    """
    LLM pur (sans RAG).
    """
    q_raw = (req.question or "").strip()
    q = _extract_user_question(q_raw)
    if len(q) < 2:
        return JSONResponse(status_code=422, content={"answer": "", "sources": [], "quotes": []})

    try:
        out = _ollama_generate(q)
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"ollama_generate_failed: {e}")

    return JSONResponse(
        status_code=200,
        content={
            "answer": out.get("answer", ""),
            # on met une source "technique" pour éviter ton fallback antiHall côté JS
            "sources": [f"ollama:{out.get('model','')}"],
            "quotes": [],
            "confidence": 0.0,
            "quality": {"mode": "llm_only"},
            "dbg": {"backend": "ollama", "model": out.get("model", "")},
        },
    )


@router.post("/hybrid")
async def rag_hybrid(req: RagAskRequest):
    """
    Hybride = RAG récupère contexte + LLM génère réponse (basée sur le contexte).
    """
    if rag_brain is None:
        raise HTTPException(status_code=500, detail=f"rag_brain_import_failed: {_IMPORT_ERR}")

    q_raw = (req.question or "").strip()
    user_q = _extract_user_question(q_raw)
    if len(user_q) < 2:
        return JSONResponse(status_code=422, content={"answer": "", "sources": [], "quotes": []})

    try:
        rag_out = rag_brain.smart_rag_answer(user_q, top_k=req.top_k)  # type: ignore[attr-defined]
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"rag_retrieve_failed: {e}")

    sources = rag_out.get("sources", []) or []
    quotes_norm = _normalize_quotes(rag_out.get("quotes", []), max_items=min(8, max(3, req.top_k)))

    prompt = _build_hybrid_prompt(user_q, quotes_norm)

    try:
        llm_out = _ollama_generate(prompt)
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"ollama_hybrid_failed: {e}")

    return JSONResponse(
        status_code=200,
        content={
            "answer": llm_out.get("answer", ""),
            "sources": sources if isinstance(sources, list) else [],
            "quotes": quotes_norm,
            "confidence": rag_out.get("confidence", 0.0),
            "quality": {"mode": "hybrid_rag_context_llm"},
            "dbg": {
                "backend": "ollama",
                "model": llm_out.get("model", ""),
                "top_k": req.top_k,
            },
        },
    )
