# -*- coding: utf-8 -*-
# Path: src/api/speech_rag.py
# RAG API — question -> rag_brain.smart_rag_answer() -> réponse + sources + quotes

from __future__ import annotations

from fastapi import APIRouter, HTTPException
from fastapi.responses import JSONResponse
from pydantic import BaseModel

try:
    from src import rag_brain
except Exception as e:
    rag_brain = None
    _IMPORT_ERR = str(e)
else:
    _IMPORT_ERR = ""

router = APIRouter()

class RagAskRequest(BaseModel):
    question: str

@router.post("/ask")
async def rag_ask(req: RagAskRequest):
    if rag_brain is None:
        raise HTTPException(status_code=500, detail=f"rag_brain import failed: {_IMPORT_ERR}")

    q = (req.question or "").strip()
    if len(q) < 2:
        return JSONResponse(status_code=422, content={"answer": "", "warning": "Question vide/trop courte."})

    try:
        out = rag_brain.smart_rag_answer(question=q)  # moteur unique 
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
