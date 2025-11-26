# -*- coding: utf-8 -*-
# Path: src/ui/sections/speech_chat.py
# Version: Premium 2025 — Voice → RAG → Voice
# Design modernisé, STT/TTS robustes, conversation continue optimisée.

from __future__ import annotations

import base64
import mimetypes
import os
from typing import Any, Dict, Optional, List
from datetime import datetime
import requests
import streamlit as st

# Micro (audio_recorder_streamlit)
try:
    from audio_recorder_streamlit import audio_recorder
except Exception:
    audio_recorder = None

# RAG local
try:
    from src import rag_brain
except Exception:
    rag_brain = None

API_BASE = os.getenv("BACKEND_API_BASE_URL", "http://127.0.0.1:8001").rstrip("/")


# --------------------------------------------------------------
#  HELPERS API
# --------------------------------------------------------------

def _detect_mimetype(filename: str) -> str:
    mime, _ = mimetypes.guess_type(filename)
    return mime or "audio/wav"


def _api_post_stt(file_bytes: bytes, filename: str, lang: str) -> Optional[Dict[str, Any]]:
    """Upload vers /stt/transcribe avec détection correcte du mimetype."""
    try:
        mime = _detect_mimetype(filename)
        files = {"file": (filename, file_bytes, mime)}
        r = requests.post(
            f"{API_BASE}/stt/transcribe",
            files=files,
            params={"lang": lang},
            timeout=1000,
        )
        r.raise_for_status()
        return r.json()
    except Exception as e:
        st.error(f"Erreur STT: {e}")
        return None


def _api_post_tts(text: str, lang: str) -> Optional[bytes]:
    """Appel au backend /tts/synthesize (gTTS amélioré)."""
    try:
        r = requests.post(
            f"{API_BASE}/tts/synthesize",
            json={"text": text, "lang": lang},
            timeout=1000,
        )
        r.raise_for_status()
        data = r.json()
        audio_b64 = data.get("audio_base64")
        if not audio_b64:
            st.error("Réponse TTS invalide.")
            return None
        return base64.b64decode(audio_b64)
    except Exception as e:
        st.error(f"Erreur TTS: {e}")
        return None


def _call_rag(question: str) -> str:
    """Appel RAG → rag_brain.smart_rag_answer."""
    if rag_brain is None:
        return "Module rag_brain indisponible."

    fn = getattr(rag_brain, "smart_rag_answer", None)
    if fn is None:
        return "Fonction smart_rag_answer absente."

    try:
        res = fn(question)
        if isinstance(res, dict):
            return str(res.get("answer") or res)
        return str(res)
    except Exception as e:
        return f"Erreur RAG: {e}"


# --------------------------------------------------------------
#  CSS Premium 2025
# --------------------------------------------------------------
def _inject_css():
    st.markdown("""
<style>
/* Wrapper global */
.voice-wrapper {
    padding: 30px;
    border-radius: 28px;
    background: rgba(15,18,26,0.88);
    backdrop-filter: blur(18px);
    border: 1px solid rgba(255,255,255,0.08);
    box-shadow: 0 12px 40px rgba(0,0,0,0.50);
}

/* Titre */
.voice-title {
    text-align: center;
    font-size: 33px !important;
    font-weight: 800 !important;
    margin-bottom: 4px;
    background: linear-gradient(90deg, #31D2FF, #5F76FF);
    -webkit-background-clip: text;
    color: transparent;
}

/* Sous-titre */
.voice-subtitle {
    text-align: center;
    font-size: 16px !important;
    opacity: 0.75;
    margin-top: -6px;
    margin-bottom: 22px;
}

/* Avatar IA */
.voice-avatar {
    width: 96px;
    height: 96px;
    border-radius: 50%;
    margin: 0 auto;
    background: radial-gradient(circle at 30% 30%, #FFFFFF, #00D7FF, #0061FF);
    box-shadow: 0 0 26px rgba(0,200,255,0.80);
    position: relative;
    display: flex;
    align-items: center;
    justify-content: center;
}
.voice-avatar::after {
    content: "";
    position: absolute;
    width: 140px;
    height: 140px;
    border-radius: 50%;
    background: radial-gradient(circle, rgba(0,221,255,0.22), transparent);
    animation: pulse 2.6s infinite ease-in-out;
}
@keyframes pulse {
    0%   { transform: scale(0.85); opacity: 0.35; }
    50%  { transform: scale(1.05); opacity: 0.80; }
    100% { transform: scale(0.85); opacity: 0.35; }
}
.voice-avatar-inner {
    width: 68px;
    height: 68px;
    border-radius: 50%;
    border: 2px solid rgba(255,255,255,0.65);
    display: flex;
    align-items: center;
    justify-content: center;
    font-size: 26px;
    color: white;
    font-weight: 700;
}

/* Ondes Siri */
.voice-wave {
    display: flex;
    justify-content: center;
    margin-top: 10px;
}
.voice-wave-bar {
    width: 5px;
    margin: 0 3px;
    border-radius: 999px;
    background: linear-gradient(180deg, #25E4FF, #5C7DFF);
    animation: bounce 1.2s infinite ease-in-out;
}
.voice-wave-bar:nth-child(1) { height: 12px; animation-delay: 0.0s; }
.voice-wave-bar:nth-child(2) { height: 24px; animation-delay: 0.12s; }
.voice-wave-bar:nth-child(3) { height: 38px; animation-delay: 0.24s; }
.voice-wave-bar:nth-child(4) { height: 24px; animation-delay: 0.36s; }
.voice-wave-bar:nth-child(5) { height: 12px; animation-delay: 0.48s; }
@keyframes bounce {
    0%,100% { transform: scaleY(0.3); opacity: 0.65; }
    50%     { transform: scaleY(1.3); opacity: 1; }
}

/* Bulles chat */
.voice-history-msg-user {
    background: rgba(0,150,255,0.18);
    border: 1px solid rgba(0,150,255,0.45);
    padding: 10px 14px;
    border-radius: 14px;
    margin-bottom: 8px;
}
.voice-history-msg-bot {
    background: rgba(255,255,255,0.06);
    border: 1px solid rgba(255,255,255,0.08);
    padding: 10px 14px;
    border-radius: 14px;
    margin-bottom: 8px;
}

/* Boutons */
.stButton > button {
    border-radius: 999px;
    padding: 10px 18px;
    background: linear-gradient(90deg,#2FBFFF,#587DFF);
    border: none;
    color: white;
    font-weight: 600;
}
.stButton > button:hover {
    filter: brightness(1.10);
}
</style>
""", unsafe_allow_html=True)


# --------------------------------------------------------------
#  RENDER
# --------------------------------------------------------------

def render() -> None:
    _inject_css()

    # Init state
    if "voice_transcript" not in st.session_state:
        st.session_state["voice_transcript"] = ""
    if "voice_answer" not in st.session_state:
        st.session_state["voice_answer"] = ""
    if "voice_last_tts" not in st.session_state:
        st.session_state["voice_last_tts"] = None
    if "voice_history" not in st.session_state:
        st.session_state["voice_history"] = []

    voice_history: List[Dict[str, str]] = st.session_state["voice_history"]

    # Titre
    st.markdown("<h1 class='voice-title'>🎤 Voice Copilot – IT STORM</h1>", unsafe_allow_html=True)
    st.markdown(
        "<p class='voice-subtitle'>Parle, ton copilote écoute. STT → RAG → TTS en local.</p>",
        unsafe_allow_html=True,
    )

    st.markdown("<div class='voice-wrapper'>", unsafe_allow_html=True)

    # Haut (avatar + mode)
    colA, colB = st.columns([1, 2])

    with colA:
        st.markdown("""
<div class="voice-avatar">
  <div class="voice-avatar-inner">AI</div>
</div>
<div class="voice-wave">
  <div class="voice-wave-bar"></div><div class="voice-wave-bar"></div>
  <div class="voice-wave-bar"></div><div class="voice-wave-bar"></div>
  <div class="voice-wave-bar"></div>
</div>
""", unsafe_allow_html=True)

    with colB:
        mode = st.radio(
            "Mode d’interaction",
            ["Question simple", "Conversation continue"],
            horizontal=True
        )

    # Source audio
    col_inA, col_inB = st.columns([2, 1])
    with col_inA:
        st.markdown("### 🎙️ Source audio")
        audio_file = st.file_uploader(
            "Uploader un fichier audio",
            type=["wav", "mp3", "m4a", "ogg", "webm"],
            label_visibility="collapsed"
        )

        mic_bytes = None
        if audio_recorder:
            mic_bytes = audio_recorder(
                text="Appuie pour parler",
                recording_color="#00d0ff",
                neutral_color="#333",
                icon_size="2x",
            )
            if mic_bytes:
                st.success("🎧 Enregistrement micro capturé.")
    with col_inB:
        lang = st.selectbox("Langue de la voix", ["fr", "en"], index=0)

    # Transcription
    st.markdown("### 📝 Transcription")
    transcript = st.text_area(
        "Texte détecté",
        value=st.session_state["voice_transcript"],
        height=120,
    )

    # Buttons
    colB1, colB2, colB3 = st.columns(3)
    stt_btn = colB1.button("🔎 Transcrire l’audio", use_container_width=True)
    rag_btn = colB2.button("🧠 RAG + Voix", use_container_width=True)
    repeat_btn = colB3.button("🔁 Répéter", use_container_width=True)

    # STT logic
    if stt_btn:
        audio_bytes_to_use = None
        filename = "audio.wav"

        if mic_bytes:
            audio_bytes_to_use = mic_bytes
            filename = "micro_input.wav"
        elif audio_file:
            audio_bytes_to_use = audio_file.read()
            filename = audio_file.name

        if not audio_bytes_to_use:
            st.warning("Aucun audio fourni.")
        else:
            with st.spinner("Transcription en cours..."):
                data = _api_post_stt(audio_bytes_to_use, filename, lang)
                if data and "text" in data:
                    st.session_state["voice_transcript"] = data["text"]
                    st.success("Texte extrait avec succès !")

    # RAG + Voix
    if rag_btn:
        question = transcript.strip()
        if question:
            with st.spinner("🔍 RAG en cours..."):
                ans = _call_rag(question)
                st.session_state["voice_answer"] = ans

                # Ajout à l’historique
                if mode == "Conversation continue":
                    voice_history.append({"role": "user", "msg": question})
                    voice_history.append({"role": "ai", "msg": ans})
                    st.session_state["voice_history"] = voice_history[-20:]  # limite

            with st.spinner("🔊 Synthèse vocale..."):
                audio = _api_post_tts(ans, lang)
                st.session_state["voice_last_tts"] = audio

    # Répéter
    if repeat_btn and st.session_state["voice_last_tts"]:
        st.audio(st.session_state["voice_last_tts"], format="audio/mp3")

    # Affichage historique
    if mode == "Conversation continue" and voice_history:
        st.markdown("### 🗂️ Historique conversation")
        for item in voice_history:
            if item["role"] == "user":
                st.markdown(
                    f"<div class='voice-history-msg-user'>{item['msg']}</div>",
                    unsafe_allow_html=True,
                )
            else:
                st.markdown(
                    f"<div class='voice-history-msg-bot'>{item['msg']}</div>",
                    unsafe_allow_html=True,
                )

    st.markdown("</div>", unsafe_allow_html=True)
