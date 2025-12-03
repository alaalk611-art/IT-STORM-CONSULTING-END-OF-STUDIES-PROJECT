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
    st.markdown(
        """
<style>
/* ==========================
   LAYOUT GLOBAL
   ========================== */

.voice-page {
    width: 100%;
}

.voice-header {
    text-align: center;
    padding: 16px 20px 10px;
    border-radius: 26px;
    background: linear-gradient(90deg, #f1fbff 0%, #e8f2ff 50%, #f4fbff 100%);
    box-shadow: 0 12px 32px rgba(34, 83, 150, 0.16);
    margin-bottom: 8px;
}

.voice-title {
    font-size: 32px !important;
    font-weight: 800 !important;
    margin-bottom: 4px;
    background: linear-gradient(90deg, #31D2FF, #5F76FF);
    -webkit-background-clip: text;
    color: transparent;
}

.voice-subtitle {
    font-size: 15px !important;
    opacity: 0.8;
    margin-top: -2px;
    margin-bottom: 0;
}

/* Ligne fine animée sous le header */
.voice-top-banner {
    height: 5px;
    width: 100%;
    max-width: 720px;
    border-radius: 999px;
    margin: 12px auto 26px;
    background: linear-gradient(90deg, #31D2FF, #5F76FF, #31D2FF);
    background-size: 220% 100%;
    box-shadow: 0 0 14px rgba(49,210,255,0.55);
    animation: voiceBannerGlow 4s linear infinite;
}

@keyframes voiceBannerGlow {
    0%   { background-position:   0% 0%; box-shadow: 0 0 4px  rgba(49,210,255,0.4); }
    50%  { background-position: 100% 0%; box-shadow: 0 0 18px rgba(95,118,255,0.9); }
    100% { background-position:   0% 0%; box-shadow: 0 0 4px  rgba(49,210,255,0.4); }
}

.voice-layout {
    max-width: 1100px;
    margin: 0 auto 40px;
}

/* Wrapper principal autour de la zone audio */
.voice-wrapper {
    padding: 26px 26px 30px;
    border-radius: 26px;
    background: rgba(255,255,255,0.78);
    backdrop-filter: blur(22px) saturate(180%);
    border: 1px solid rgba(255,255,255,0.6);
    box-shadow: 0 18px 46px rgba(9, 42, 92, 0.16);
}

/* ==========================
   AVATAR IA + MODE
   ========================== */

.voice-avatar {
    width: 100px;
    height: 100px;
    border-radius: 50%;
    margin: 0 auto 4px;
    background: radial-gradient(circle at 30% 30%, #FFFFFF, #00D7FF, #0061FF);
    box-shadow: 0 0 32px rgba(0,200,255,0.90);
    position: relative;
    display: flex;
    align-items: center;
    justify-content: center;
}

.voice-avatar::after {
    content: "";
    position: absolute;
    width: 150px;
    height: 150px;
    border-radius: 50%;
    background: radial-gradient(circle, rgba(0,221,255,0.25), transparent);
    animation: pulse 2.6s infinite ease-in-out;
}

@keyframes pulse {
    0%   { transform: scale(0.86); opacity: 0.35; }
    50%  { transform: scale(1.06); opacity: 0.82; }
    100% { transform: scale(0.86); opacity: 0.35; }
}

.voice-avatar-inner {
    width: 72px;
    height: 72px;
    border-radius: 50%;
    border: 2px solid rgba(255,255,255,0.75);
    display: flex;
    align-items: center;
    justify-content: center;
    font-size: 28px;
    color: white;
    font-weight: 700;
}

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

/* Carte "mode d'interaction" */
.voice-mode-card {
    padding: 14px 18px 10px;
    border-radius: 18px;
    background: rgba(255,255,255,0.96);
    box-shadow: 0 10px 26px rgba(14, 54, 104, 0.10);
    margin-bottom: 18px;
}

.voice-section-label {
    font-size: 12px;
    text-transform: uppercase;
    letter-spacing: .08em;
    font-weight: 700;
    color: #7b88a6;
    margin-bottom: 4px;
}

/* ==========================
   CARTES SECTIONS
   ========================== */

.voice-section-card {
    padding: 18px 18px 14px;
    border-radius: 20px;
    background: rgba(255,255,255,0.98);
    box-shadow: 0 8px 30px rgba(11, 44, 93, 0.06);
    margin-bottom: 20px;
}

.voice-section-title {
    font-size: 18px;
    font-weight: 700;
    margin-bottom: 8px;
    color: #1b2b4a;
}

.voice-section-subtitle {
    font-size: 13px;
    color: #7c8aa7;
    margin-bottom: 12px;
}

/* Historiques / badges */

.voice-badges-row span.badge {
    display: inline-flex;
    align-items: center;
    padding: 3px 10px;
    border-radius: 999px;
    font-size: 11px;
    background: rgba(49,210,255,0.12);
    border: 1px solid rgba(49,210,255,0.45);
    color: #144064;
    margin-right: 6px;
}

/* ==========================
   HISTORIQUE CONVERSATION
   ========================== */

.voice-history-card {
    margin-top: 8px;
    padding: 12px 14px 6px;
    border-radius: 18px;
    background: rgba(246,249,255,0.98);
    max-height: 260px;
    overflow-y: auto;
}

.voice-history-title {
    font-size: 14px;
    font-weight: 700;
    margin-bottom: 8px;
    color: #22355b;
}

.voice-history-msg-user {
    background: rgba(0,150,255,0.18);
    border: 1px solid rgba(0,150,255,0.45);
    padding: 8px 11px;
    border-radius: 14px;
    margin-bottom: 6px;
    font-size: 13px;
}

.voice-history-msg-bot {
    background: rgba(255,255,255,0.9);
    border: 1px solid rgba(170,186,215,0.6);
    padding: 8px 11px;
    border-radius: 14px;
    margin-bottom: 6px;
    font-size: 13px;
}

/* ==========================
   BOUTONS
   ========================== */

.voice-actions-row {
    margin-top: 14px;
}

.voice-actions-row .stButton > button {
    border-radius: 999px;
    padding: 10px 18px;
    background: linear-gradient(90deg,#2FBFFF,#587DFF);
    border: none;
    color: white;
    font-weight: 600;
}

.voice-actions-row .stButton > button:hover {
    filter: brightness(1.08);
}

/* ==========================
   DIVERS
   ========================== */

/* Suppression de la barre noire par défaut de Streamlit */
div[data-testid="stDecoration"] {
    display: none !important;
}
</style>
""",
        unsafe_allow_html=True,
    )


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

    # Header + bandeau
    st.markdown(
        """
<div class="voice-page">
  <div class="voice-header">
    <h1 class="voice-title">🎤 Voice Copilot – IT STORM</h1>
    <p class="voice-subtitle">Parle, ton copilote écoute. STT → RAG → TTS en local.</p>
  </div>
  <div class="voice-top-banner"></div>
  <div class="voice-layout">
    <div class="voice-wrapper">
""",
        unsafe_allow_html=True,
    )

    # Haut (avatar + mode)
    colA, colB = st.columns([1, 2])

    with colA:
        st.markdown(
            """
<div class="voice-avatar">
  <div class="voice-avatar-inner">AI</div>
</div>
<div class="voice-wave">
  <div class="voice-wave-bar"></div><div class="voice-wave-bar"></div>
  <div class="voice-wave-bar"></div><div class="voice-wave-bar"></div>
  <div class="voice-wave-bar"></div>
</div>
""",
            unsafe_allow_html=True,
        )

    with colB:
        st.markdown(
            """
<div class="voice-mode-card">
  <div class="voice-section-label">Mode d'interaction</div>
""",
            unsafe_allow_html=True,
        )
        mode = st.radio(
            "Mode d’interaction",
            ["Question simple", "Conversation continue"],
            horizontal=True,
            label_visibility="collapsed",
        )
        st.markdown("</div>", unsafe_allow_html=True)

    # ==============================
    #  SOURCE AUDIO
    # ==============================
    st.markdown(
        """
<div class="voice-section-card">
  <div class="voice-section-label">Entrée</div>
  <div class="voice-section-title">🎙️ Source audio</div>
  <div class="voice-section-subtitle">Charge un fichier audio ou parle directement au micro.</div>
""",
        unsafe_allow_html=True,
    )

    col_inA, col_inB = st.columns([2, 1])

    with col_inA:
        audio_file = st.file_uploader(
            "Drag and drop file here",
            type=["wav", "mp3", "m4a", "ogg", "webm"],
            help="Limite 200MB par fichier.",
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

    st.markdown("</div>", unsafe_allow_html=True)  # fin carte source audio

    # ==============================
    #  TRANSCRIPTION
    # ==============================
    st.markdown(
        """
<div class="voice-section-card">
  <div class="voice-section-label">Texte</div>
  <div class="voice-section-title">📝 Transcription</div>
""",
        unsafe_allow_html=True,
    )

    transcript = st.text_area(
        "Texte détecté",
        value=st.session_state["voice_transcript"],
        height=140,
    )

    st.markdown("</div>", unsafe_allow_html=True)  # fin carte transcription

    # ==============================
    #  BOUTONS D'ACTION
    # ==============================
    st.markdown("<div class='voice-actions-row'>", unsafe_allow_html=True)
    colB1, colB2, colB3 = st.columns(3)
    stt_btn = colB1.button("🔎 Transcrire l’audio", use_container_width=True)
    rag_btn = colB2.button("🧠 RAG + Voix", use_container_width=True)
    repeat_btn = colB3.button("🔁 Répéter", use_container_width=True)
    st.markdown("</div>", unsafe_allow_html=True)

    # ==============================
    #  LOGIQUE STT
    # ==============================
    if stt_btn:
        audio_bytes_to_use = None
        filename = "audio.wav"

        if "mic_bytes" in locals() and mic_bytes:
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

    # ==============================
    #  RAG + VOIX
    # ==============================
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
                    st.session_state["voice_history"] = voice_history[-20:]

            with st.spinner("🔊 Synthèse vocale..."):
                audio = _api_post_tts(ans, lang)
                st.session_state["voice_last_tts"] = audio

    # ==============================
    #  REPETER
    # ==============================
    if repeat_btn and st.session_state["voice_last_tts"]:
        st.audio(st.session_state["voice_last_tts"], format="audio/mp3")

    # ==============================
    #  HISTORIQUE CONVERSATION
    # ==============================
    if mode == "Conversation continue" and voice_history:
        st.markdown(
            """
<div class="voice-history-card">
  <div class="voice-history-title">🗂️ Historique conversation</div>
""",
            unsafe_allow_html=True,
        )
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

    # Fermeture des conteneurs HTML ouverts au début
    st.markdown("</div></div></div>", unsafe_allow_html=True)
