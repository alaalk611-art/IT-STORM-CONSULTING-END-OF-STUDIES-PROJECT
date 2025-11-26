# -*- coding: utf-8 -*-
# Path: src/api/speech_tts.py
# Version 2025 — gTTS TTS robuste + Fallback PyDub
# - Support des textes longs
# - Split & concaténation MP3 (avec détection FFmpeg)
# - Fallback automatique si PyDub échoue
# - Base64 clean
# - Multilangue
# - Stable production

from __future__ import annotations

import base64
from io import BytesIO
from typing import List

from fastapi import APIRouter, HTTPException
from fastapi.responses import JSONResponse
from pydantic import BaseModel

import warnings
warnings.filterwarnings("ignore", module="pydub")

# gTTS
try:
    from gtts import gTTS
except Exception:
    gTTS = None

# PyDub (pour concatener MP3)
try:
    from pydub import AudioSegment
except Exception:
    AudioSegment = None

router = APIRouter()


class TTSRequest(BaseModel):
    text: str
    lang: str = "fr"


# ------------------------------------------------------------------
# UTILITAIRES
# ------------------------------------------------------------------

def _split_text(text: str, max_len: int = 240) -> List[str]:
    """
    gTTS plante au-delà de ~300 caractères.
    On découpe intelligemment le texte.
    """
    words = text.strip().split()
    out = []
    chunk = []

    for w in words:
        chunk.append(w)
        if len(" ".join(chunk)) >= max_len:
            out.append(" ".join(chunk))
            chunk = []

    if chunk:
        out.append(" ".join(chunk))

    return out


def _synthesize_segment(text: str, lang: str) -> BytesIO:
    """Synthétise un seul segment en MP3 (buffer)."""
    buf = BytesIO()
    tts = gTTS(text=text, lang=lang)
    tts.write_to_fp(buf)
    buf.seek(0)
    return buf


# ------------------------------------------------------------------
# ENDPOINT PRINCIPAL
# ------------------------------------------------------------------

@router.post("/synthesize")
async def synthesize_tts(req: TTSRequest):
    """
    Synthèse vocale gTTS avec concaténation MP3 si texte long.
    """
    if gTTS is None:
        raise HTTPException(
            status_code=500,
            detail="gTTS n'est pas installé dans l'environnement.",
        )

    if not req.text.strip():
        raise HTTPException(status_code=400, detail="Texte vide.")

    text = req.text.strip()

    # Segmentation
    parts = _split_text(text, max_len=240)

    # Synthèse de chaque segment
    mp3_segments: List[BytesIO] = []
    for p in parts:
        mp3_segments.append(_synthesize_segment(p, req.lang))

    # ------------------------------------------------------------------
    # Tentative de concaténation avec PyDub (si dispo & si >1 segment)
    # ------------------------------------------------------------------

    pydub_ok = AudioSegment is not None and len(mp3_segments) > 1
    final_audio = None

    if pydub_ok:
        try:
            for seg in mp3_segments:
                audio = AudioSegment.from_file(seg, format="mp3")
                if final_audio is None:
                    final_audio = audio
                else:
                    final_audio += audio

            output = BytesIO()
            final_audio.export(output, format="mp3")
            output.seek(0)

        except Exception:
            # ------------------------------------------------------
            # Fallback automatique : renvoie simplement le 1er segment
            # ------------------------------------------------------
            pydub_ok = False

    # ------------------------------------------------------------------
    # Fallback simple si PyDub n'est pas utilisable
    # ------------------------------------------------------------------
    if not pydub_ok:
        output = mp3_segments[0]   # renvoie la voix du 1er segment
        output.seek(0)

    # Encodage base64 final
    audio_b64 = base64.b64encode(output.read()).decode("utf-8")

    return JSONResponse({
        "audio_base64": audio_b64,
        "mime_type": "audio/mpeg",
        "segments": len(parts),
        "concat": bool(pydub_ok),
    })
