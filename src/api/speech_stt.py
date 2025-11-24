# -*- coding: utf-8 -*-
# Path: src/api/speech_stt.py
# Role: API Speech-to-Text (STT) via faster-whisper
#

from __future__ import annotations
import warnings
warnings.filterwarnings("ignore", category=UserWarning)

import os
from tempfile import NamedTemporaryFile
from typing import Optional

from fastapi import APIRouter, UploadFile, File, HTTPException, Query
from fastapi.responses import JSONResponse

try:
    from faster_whisper import WhisperModel  # type: ignore
except Exception:  # pragma: no cover
    WhisperModel = None  # type: ignore

router = APIRouter()

# Taille du modèle (tiny / base / small / medium / large-v2 ...)
MODEL_SIZE = os.getenv("WHISPER_MODEL_SIZE", "small")

# Lazy-load : on charge le modèle au premier appel seulement
_whisper_model: Optional[object] = None


def _get_whisper_model() -> object:
    """
    Initialise (si besoin) et renvoie le modèle Whisper.
    On reste volontairement typé 'object' pour éviter les warnings mypy/pyright.
    """
    global _whisper_model

    if WhisperModel is None:
        # faster-whisper non installé ou import KO
        raise RuntimeError(
            "Le modèle Whisper n'est pas disponible. "
            "Installe d'abord 'faster-whisper' dans ton environnement."
        )

    if _whisper_model is None:
        # Initialisation unique (CPU only, quantization int8)
        _whisper_model = WhisperModel(
            MODEL_SIZE,
            device="cpu",
            compute_type="int8",
        )
    return _whisper_model


@router.post("/transcribe")
async def transcribe_audio(
    file: UploadFile = File(...),
    lang: str = Query(
        "fr",
        max_length=5,
        description="Langue attendue (fr, en, etc.)",
    ),
):
    """
    Reçoit un fichier audio (wav/mp3/m4a/ogg/webm) et renvoie le texte transcrit.
    """
    try:
        model = _get_whisper_model()
    except RuntimeError as e:
        raise HTTPException(status_code=500, detail=str(e))

    # Vérification du format
    filename = (file.filename or "").lower()
    if not any(filename.endswith(ext) for ext in (".wav", ".mp3", ".m4a", ".ogg", ".webm")):
        raise HTTPException(
            status_code=400,
            detail="Format audio non supporté. Utilise wav/mp3/m4a/ogg/webm.",
        )

    tmp_path: Optional[str] = None

    try:
        data = await file.read()
        if not data:
            raise HTTPException(status_code=400, detail="Fichier audio vide.")

        # Sauvegarde temporaire sur disque (plus simple pour faster-whisper)
        with NamedTemporaryFile(delete=False, suffix=".wav") as tmp:
            tmp.write(data)
            tmp.flush()
            tmp_path = tmp.name

        # Transcription
        # type: ignore parce que 'model' est vu comme object
        segments, info = model.transcribe(  # type: ignore[attr-defined]
            tmp_path,
            language=lang,
            beam_size=5,
        )

        text_parts = [seg.text.strip() for seg in segments if getattr(seg, "text", "").strip()]
        text = " ".join(text_parts).strip()

        if not text:
            raise HTTPException(
                status_code=422,
                detail="Impossible d'extraire du texte de l'audio.",
            )

        return JSONResponse(
            {
                "text": text,
                "language": lang,
                "duration": getattr(info, "duration", None),
            }
        )

    except HTTPException:
        # On laisse remonter les erreurs HTTP formatées
        raise
    except Exception as e:  # pragma: no cover
        raise HTTPException(
            status_code=500,
            detail=f"Erreur interne STT: {e}",
        )
    finally:
        if tmp_path and os.path.exists(tmp_path):
            try:
                os.remove(tmp_path)
            except OSError:
                pass
