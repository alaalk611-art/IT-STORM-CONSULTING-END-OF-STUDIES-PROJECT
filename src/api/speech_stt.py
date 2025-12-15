# -*- coding: utf-8 -*-
# Path: src/api/speech_stt.py
# STT API robuste — Micro webm/ogg/m4a -> ffmpeg -> wav 16k mono -> faster-whisper
# Objectif : transcription stable (anti-hallucination) pour démo PFE

from __future__ import annotations

import os
import re
import tempfile
import subprocess
from typing import Optional

from fastapi import APIRouter, UploadFile, File, Query
from fastapi.responses import JSONResponse
from faster_whisper import WhisperModel

router = APIRouter()

# Modèle (CPU stable)
model = WhisperModel("small", device="cpu", compute_type="int8")


_BAD_PATTERNS = [
    r"amara\.org",
    r"sous-?titres.*amara",
    r"subtitles.*amara",
]

def _looks_like_hallucination(text: str) -> bool:
    t = (text or "").strip().lower()
    if not t:
        return True
    for p in _BAD_PATTERNS:
        if re.search(p, t):
            return True
    # Trop court / trop générique
    if len(t) < 3:
        return True
    return False


def _ffmpeg_to_wav16k_mono(src_path: str) -> str:
    """
    Convertit n'importe quel audio en WAV mono 16 kHz.
    Retourne le chemin du wav.
    """
    wav_path = src_path + ".wav"
    subprocess.run(
        ["ffmpeg", "-y", "-i", src_path, "-ac", "1", "-ar", "16000", wav_path],
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
        check=True,
    )
    return wav_path


def _transcribe_whisper(wav_path: str, lang: Optional[str]) -> str:
    """
    Transcription robuste :
    - 1) VAD soft (réduit bruit)
    - 2) fallback sans VAD si sortie vide/hallucinée
    """
    # 1) tentative avec VAD "soft"
    segments, info = model.transcribe(
        wav_path,
        language=lang if lang else None,
        task="transcribe",
        vad_filter=True,
        vad_parameters={
            "threshold": 0.3,
            "min_silence_duration_ms": 250,
        },
        beam_size=5,
        temperature=0.0,
        condition_on_previous_text=False,
    )
    parts = [s.text.strip() for s in segments if getattr(s, "text", "").strip()]
    text = " ".join(parts).strip()

    if text and not _looks_like_hallucination(text):
        return text

    # 2) fallback : sans VAD (utile si VAD coupe la voix)
    segments2, info2 = model.transcribe(
        wav_path,
        language=lang if lang else None,
        task="transcribe",
        vad_filter=False,
        beam_size=5,
        temperature=0.0,
        condition_on_previous_text=False,
    )
    parts2 = [s.text.strip() for s in segments2 if getattr(s, "text", "").strip()]
    text2 = " ".join(parts2).strip()

    return text2


@router.post("/transcribe")
async def transcribe(
    file: UploadFile = File(...),
    lang: str = Query("fr"),
):
    raw = await file.read()
    mime = (file.content_type or "").lower()
    name = (file.filename or "mic.webm").lower()

    print("🧪 STT DEBUG:", {"bytes": len(raw), "mime": mime, "filename": name, "lang": lang})

    if len(raw) < 3000:
        return JSONResponse(
            status_code=422,
            content={"text": "", "warning": "Audio trop court (parle 2–4 secondes)"},
        )

    # Extension adaptée (aide ffmpeg)
    suffix = ".webm"
    if name.endswith(".wav") or "wav" in mime:
        suffix = ".wav"
    elif name.endswith(".ogg") or "ogg" in mime:
        suffix = ".ogg"
    elif name.endswith(".mp3") or "mp3" in mime or "mpeg" in mime:
        suffix = ".mp3"
    elif name.endswith(".m4a") or "m4a" in mime or "mp4" in mime:
        suffix = ".m4a"

    src_path = None
    wav_path = None

    try:
        with tempfile.NamedTemporaryFile(delete=False, suffix=suffix) as tmp:
            tmp.write(raw)
            src_path = tmp.name

        print("🧪 STT DEBUG: src_path =", src_path)

        # Conversion WAV 16k mono (le plus important)
        try:
            wav_path = _ffmpeg_to_wav16k_mono(src_path)
        except Exception as e:
            print("❌ FFmpeg convert error:", repr(e))
            return JSONResponse(
                status_code=500,
                content={
                    "text": "",
                    "error": "ffmpeg_convert_failed",
                    "detail": str(e),
                    "hint": "ffmpeg doit être installé et accessible (ffmpeg -version).",
                },
            )

        print("🧪 STT DEBUG: wav_path =", wav_path)

        # Transcription (robuste)
        try:
            text = _transcribe_whisper(wav_path, lang)
        except Exception as e:
            print("❌ STT transcribe error:", repr(e))
            return JSONResponse(
                status_code=500,
                content={"text": "", "error": "whisper_transcribe_failed", "detail": str(e)},
            )

        text = (text or "").strip()
        print("🧪 STT DEBUG: text_len =", len(text))

        # Filtre hallucination / vide
        if _looks_like_hallucination(text):
            return JSONResponse(
                status_code=422,
                content={
                    "text": "",
                    "warning": "Aucun texte fiable détecté (bruit/silence ou voix trop faible).",
                },
            )

        return JSONResponse(
            status_code=200,
            content={
                "text": text,
                "language": lang,
                "source_mime": mime,
            },
        )

    finally:
        # Cleanup
        for p in [wav_path, src_path]:
            if p:
                try:
                    os.remove(p)
                except Exception:
                    pass
