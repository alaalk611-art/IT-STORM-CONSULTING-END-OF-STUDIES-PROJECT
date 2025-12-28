# -*- coding: utf-8 -*-
# Path: src/api/speech_stt.py
# STT API robuste — Micro webm/ogg/m4a -> ffmpeg -> wav 16k mono -> faster-whisper
# Objectif : transcription stable (anti-hallucination) pour démo PFE

from __future__ import annotations
import unicodedata
import os
import re
import tempfile
import subprocess
from typing import Any, Dict, List, Optional, Tuple
from fastapi import APIRouter, UploadFile, File, Query
from fastapi.responses import JSONResponse
from faster_whisper import WhisperModel

router = APIRouter()

# Modèle (CPU stable)
model = WhisperModel("small", device="cpu", compute_type="int8")

_DOMAIN_TERMS = [
    "IT-STORM", "StormCopilot", "portage salarial", "consulting", "mission",
    "client", "contrat", "facturation", "indépendant", "société de portage",
]

# Corrections ultra ciblées (anti "IT Store")
_PROPER_NOUN_FIXES = {
    r"\bit\s*store\b": "IT-STORM",
    r"\bit\s*storm\b": "IT-STORM",
    r"\bit\s*storme\b": "IT-STORM",
    r"\bstorm\s*copilot\b": "StormCopilot",
}

def _clean_text(t: str) -> str:
    t = (t or "").strip()
    # espaces propres
    t = re.sub(r"\s+", " ", t)
    # éviter ponctuation bizarre répétée
    t = re.sub(r"[•·]+", " ", t).strip()
    return t

def _apply_domain_fixes(t: str) -> str:
    out = t
    for pat, rep in _PROPER_NOUN_FIXES.items():
        out = re.sub(pat, rep, out, flags=re.IGNORECASE)
    return out

def _quality_score(text: str, info: Any) -> float:
    """
    Score simple de qualité.
    On combine longueur + logprob + no_speech_prob si dispo.
    """
    t = (text or "").strip()
    if not t:
        return -999.0

    # longueur (évite les 1-2 mots)
    L = len(t)
    len_score = min(1.0, L / 40.0)

    # faster-whisper info peut contenir ces champs selon version
    avg_logprob = getattr(info, "avg_logprob", None)
    no_speech_prob = getattr(info, "no_speech_prob", None)

    lp = 0.0
    if isinstance(avg_logprob, (int, float)):
        # typiquement ~[-1.5 .. -0.1], plus haut = mieux
        lp = max(-2.0, min(0.0, float(avg_logprob)))  # clamp
        lp = (lp + 2.0) / 2.0  # map [-2..0] -> [0..1]

    ns = 0.0
    if isinstance(no_speech_prob, (int, float)):
        # plus no_speech_prob est grand = pire
        ns = 1.0 - max(0.0, min(1.0, float(no_speech_prob)))

    # pondérations
    return 0.55 * len_score + 0.35 * lp + 0.10 * ns

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
    Transcription robuste multi-stratégies :
    - A) VAD soft + beam (stable)
    - B) sans VAD + beam (si VAD coupe)
    - C) VAD + sampling léger (si beam donne du "faux propre")
    Puis on choisit le meilleur candidat via un score de qualité.
    + initial_prompt pour préserver noms propres (IT-STORM, StormCopilot, portage salarial)
    + post-correction ciblée (IT Store -> IT-STORM)
    """
    initial_prompt = (
        "Contexte : IT-STORM (avec un tiret), StormCopilot, portage salarial, consulting, mission client. "
        "Ne pas confondre IT-STORM avec IT Store. "
        "Mots importants : portage salarial, société de portage, contrat, facturation."
    )

    candidates: List[Tuple[str, float]] = []

    def run_once(vad: bool, beam: bool) -> Tuple[str, Any]:
        kwargs = dict(
            language=lang if lang else None,
            task="transcribe",
            condition_on_previous_text=False,
            temperature=0.0 if beam else 0.2,  # sampling léger si pas beam
            initial_prompt=initial_prompt,
        )
        if vad:
            kwargs["vad_filter"] = True
            kwargs["vad_parameters"] = {"threshold": 0.3, "min_silence_duration_ms": 250}
        else:
            kwargs["vad_filter"] = False

        if beam:
            kwargs["beam_size"] = 5
        else:
            # sampling contrôlé (réduit les "corrections automatiques")
            kwargs["beam_size"] = 1

        segments, info = model.transcribe(wav_path, **kwargs)
        parts = [s.text.strip() for s in segments if getattr(s, "text", "").strip()]
        txt = _clean_text(" ".join(parts))
        txt = _apply_domain_fixes(txt)
        return txt, info

    # A) VAD + beam
    tA, infoA = run_once(vad=True, beam=True)
    if tA and not _looks_like_hallucination(tA):
        candidates.append((tA, _quality_score(tA, infoA)))

    # B) no VAD + beam
    tB, infoB = run_once(vad=False, beam=True)
    if tB and not _looks_like_hallucination(tB):
        candidates.append((tB, _quality_score(tB, infoB)))

    # C) VAD + sampling léger (parfois meilleur pour noms propres)
    tC, infoC = run_once(vad=True, beam=False)
    if tC and not _looks_like_hallucination(tC):
        candidates.append((tC, _quality_score(tC, infoC)))

    if not candidates:
        # dernier recours : renvoyer la "moins pire" (même si vide)
        return _apply_domain_fixes(_clean_text(tA or tB or tC or ""))

    # choisir meilleur score
    candidates.sort(key=lambda x: x[1], reverse=True)
    best = candidates[0][0]

    return best

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
