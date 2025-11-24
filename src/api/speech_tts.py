# -*- coding: utf-8 -*-
# Path: src/api/speech_tts.py
# Role: API Text-to-Speech (TTS) via gTTS

from __future__ import annotations

import base64
from io import BytesIO

from fastapi import APIRouter, HTTPException
from fastapi.responses import JSONResponse
from pydantic import BaseModel

try:
    from gtts import gTTS  # type: ignore
except Exception:
    gTTS = None  # type: ignore

router = APIRouter()


class TTSRequest(BaseModel):
    text: str
    lang: str = "fr"


@router.post("/synthesize")
async def synthesize_tts(req: TTSRequest):
    """
    Reçoit un texte + langue, renvoie un MP3 encodé en base64.
    """
    if gTTS is None:
        raise HTTPException(
            status_code=500,
            detail="gTTS n'est pas disponible. Installe d'abord le paquet 'gTTS'.",
        )

    if not req.text.strip():
        raise HTTPException(status_code=400, detail="Texte vide.")

    try:
        tts = gTTS(text=req.text, lang=req.lang)
        buf = BytesIO()
        tts.write_to_fp(buf)
        buf.seek(0)
        audio_b64 = base64.b64encode(buf.read()).decode("utf-8")

        return JSONResponse(
            {
                "audio_base64": audio_b64,
                "mime_type": "audio/mpeg",
            }
        )
    except Exception as e:
        raise HTTPException(
            status_code=500,
            detail=f"Erreur interne TTS: {e}",
        )
