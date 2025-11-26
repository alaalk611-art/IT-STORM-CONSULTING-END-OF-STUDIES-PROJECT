# -*- coding: utf-8 -*-
# Path: src/api/speech_stt.py
# Version 2025 — Whisper STT (faster-whisper) stable & robuste
# - auto mimetype detection
# - supports wav/mp3/m4a/ogg/webm
# - micro streamlit (webm) compatible

from __future__ import annotations

import os
import mimetypes
import warnings
from tempfile import NamedTemporaryFile
from typing import Optional

from fastapi import APIRouter, UploadFile, File, Query, HTTPException
from fastapi.responses import JSONResponse

warnings.filterwarnings("ignore", category=UserWarning)

# Whisper STT model
try:
    from faster_whisper import WhisperModel
except Exception:
    WhisperModel = None

# 🔹 Router utilisé dans main.py → OBLIGATOIRE
router = APIRouter()

# Taille modèle (tiny/base/small/medium/large-v2…)
MODEL_SIZE = os.getenv("WHISPER_MODEL_SIZE", "small")

# Lazy-load global
_whisper_model: Optional[object] = None


def _get_whisper_model() -> object:
    """Chargement lazy du modèle Whisper."""
    global _whisper_model

    if WhisperModel is None:
        raise RuntimeError("WhisperModel indisponible. Installe faster-whisper.")

    if _whisper_model is None:
        _whisper_model = WhisperModel(
            MODEL_SIZE,
            device="cpu",
            compute_type="int8",  # optimisé CPU local
        )

    return _whisper_model


def _detect_ext(filename: str) -> str:
    """
    Détecte automatiquement l'extension.
    Whisper s'attend à un fichier audio local.
    """
    ext = os.path.splitext(filename.lower())[1]
    if ext in {".wav", ".mp3", ".m4a", ".ogg", ".webm"}:
        return ext
    return ".wav"  # fallback


@router.post("/transcribe")
async def transcribe_audio(
    file: UploadFile = File(...),
    lang: str = Query("fr", max_length=5, description="Langue attendue (fr, en…)"),
):
    """
    Transcription audio → texte.
    Accepte wav/mp3/m4a/ogg/webm.
    """
    # Vérification modèle
    try:
        model = _get_whisper_model()
    except RuntimeError as e:
        raise HTTPException(status_code=500, detail=str(e))

    # Vérifier format fichier
    filename = (file.filename or "").lower()
    ext = _detect_ext(filename)

    if ext not in {".wav", ".mp3", ".m4a", ".ogg", ".webm"}:
        raise HTTPException(
            status_code=400,
            detail="Format non supporté. Utilise wav/mp3/m4a/ogg/webm.",
        )

    temp_path = None
    try:
        raw = await file.read()
        if not raw:
            raise HTTPException(status_code=400, detail="Fichier audio vide.")

        # Créer un fichier temporaire dans le bon format
        with NamedTemporaryFile(delete=False, suffix=ext) as tmp:
            tmp.write(raw)
            tmp.flush()
            temp_path = tmp.name

        # Transcription
        segments, info = model.transcribe(
            temp_path,
            language=lang,
            beam_size=5,
        )

        text = " ".join(
            s.text.strip()
            for s in segments
            if getattr(s, "text", "").strip()
        ).strip()

        if not text:
            raise HTTPException(
                status_code=422,
                detail="Impossible d’extraire du texte (audio silencieux ou bruité).",
            )

        return JSONResponse(
            {
                "text": text,
                "language": lang,
                "duration": getattr(info, "duration", None),
            }
        )

    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(
            status_code=500,
            detail=f"Erreur interne STT: {e}",
        )
    finally:
        if temp_path and os.path.exists(temp_path):
            try:
                os.remove(temp_path)
            except Exception:
                pass
