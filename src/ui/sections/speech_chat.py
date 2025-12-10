# -*- coding: utf-8 -*-
# Path: src/ui/sections/speech_chat.py
# Version: WebRTC — Mode appel téléphonique (STT → RAG → TTS)

from __future__ import annotations

import base64
import mimetypes
import os
import re
import io
import wave
from typing import Any, Dict, Optional, List
import requests
import streamlit as st

# WebRTC audio continu
try:
    from streamlit_webrtc import webrtc_streamer, WebRtcMode, RTCConfiguration
    import av
    import numpy as np
    WEBRTC_AVAILABLE = True
except Exception:
    webrtc_streamer = None
    WebRtcMode = None
    RTCConfiguration = None
    av = None
    np = None
    WEBRTC_AVAILABLE = False

# RAG local
try:
    from src import rag_brain
except Exception:
    rag_brain = None

API_BASE = os.getenv("BACKEND_API_BASE_URL", "http://127.0.0.1:8001").rstrip("/")

RTC_CONFIG = (
    RTCConfiguration(
        {
            "iceServers": [
                {"urls": ["stun:stun.l.google.com:19302"]},
            ]
        }
    )
    if WEBRTC_AVAILABLE
    else None
)


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


# --------------------------------------------------------------
#  NORMALISATION STT → RAG (portage salarial / IT STORM / bruit)
# --------------------------------------------------------------

def _normalize_query_for_rag(text: str) -> str:
    """
    Nettoie légèrement la transcription STT avant RAG.
    - enlève les salutations ("bonjour", "bonsoir", "salut")
    - corrige les variantes autour de "portage salarial"
    - corrige les variantes autour de "IT STORM"
    - retire "Sous-titres réalisés par la communauté d'Amara.org"
    """
    if not text:
        return ""

    t = text.strip()
    low = t.lower().lstrip()

    # 1) Enlever les salutations
    for hello in ("bonjour", "bonsoir", "salut"):
        if low.startswith(hello):
            cut = len(hello)
            low = low[cut:].lstrip(" ,.!?;:-")
            break

    # 2) Corrections "portage salarial"
    low = re.sub(r"\bportage\s+salariage\b", "portage salarial", low)
    low = re.sub(r"\bportage\s+salaria[lm]?\b", "portage salarial", low)
    low = re.sub(r"\bportage\s+salairal\b", "portage salarial", low)

    # 3) Corrections "IT STORM"
    low = re.sub(r"\bit[-\s]*storm\b", "it storm", low)
    low = re.sub(r"\bit\s*storum\b", "it storm", low)
    low = re.sub(r"\bitstorm\b", "it storm", low)

    # 4) Supprimer la phrase parasite Amara.org
    low = re.sub(
        r"sous[-\s]*titres\s*r[ée]alis[ée]s?\s*par\s*la\s*communaut[ée]\s*d['’]amara\.org",
        "",
        low,
        flags=re.IGNORECASE,
    )

    # 5) Nettoyage espaces
    low = re.sub(r"\s{2,}", " ", low).strip()

    # 6) Remettre IT STORM en majuscules
    low = low.replace("it storm", "IT STORM")

    return low


def _call_rag(question: str) -> str:
    """Appel RAG → rag_brain.smart_rag_answer avec normalisation STT."""
    if rag_brain is None:
        return "Module rag_brain indisponible."

    fn = getattr(rag_brain, "smart_rag_answer", None)
    if fn is None:
        return "Fonction smart_rag_answer absente."

    try:
        normalized = _normalize_query_for_rag(question)
        res = fn(normalized)
        if isinstance(res, dict):
            return str(res.get("answer") or res)
        return str(res)
    except Exception as e:
        return f"Erreur RAG: {e}"


# --------------------------------------------------------------
#  WEBRTC → WAV BYTES
# --------------------------------------------------------------

from typing import Any

def _frames_to_wav_bytes(frames: List[Any]) -> bytes:
    """
    Convertit une liste de frames audio WebRTC (av.AudioFrame)
    en un flux WAV mono 16 bits.
    """
    if not frames:
        return b""

    if np is None or av is None:
        return b""

    # On suppose un sample_rate constant sur les frames
    sample_rate = frames[0].sample_rate or 48000

    from typing import List, Any
    samples_all: List[Any] = []
    for f in frames:
        arr = f.to_ndarray()  # shape (channels, samples)
        arr = arr.astype("float32")

        if arr.ndim == 2 and arr.shape[0] > 1:
            mono = arr.mean(axis=0)  # moyenne des canaux
        elif arr.ndim == 2:
            mono = arr[0]
        else:
            mono = arr

        samples_all.append(mono)

    if not samples_all:
        return b""

    samples = np.concatenate(samples_all).astype("float32")

    # Normalisation douce pour éviter la saturation
    max_amp = float(np.max(np.abs(samples))) if samples.size else 1.0
    if max_amp < 1e-9:
        max_amp = 1.0
    samples = samples / max_amp

    int16 = (samples * 32767).astype("int16")

    buf = io.BytesIO()
    wf = wave.open(buf, "wb")
    wf.setnchannels(1)
    wf.setsampwidth(2)  # int16
    wf.setframerate(sample_rate)
    wf.writeframes(int16.tobytes())
    wf.close()
    return buf.getvalue()


# --------------------------------------------------------------
#  CSS
# --------------------------------------------------------------
def _inject_css():
    st.markdown(
        """
<style>
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
.voice-wrapper {
    padding: 26px 26px 30px;
    border-radius: 26px;
    background: rgba(255,255,255,0.78);
    backdrop-filter: blur(22px) saturate(180%);
    border: 1px solid rgba(255,255,255,0.6);
    box-shadow: 0 18px 46px rgba(9, 42, 92, 0.16);
}
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
.voice-section-card {
    margin-top: 16px;
    padding: 16px 18px 14px;
    border-radius: 20px;
    background: rgba(248,250,255,0.98);
    border: 1px solid rgba(209,220,250,0.9);
}
.voice-section-label {
    font-size: 11px;
    text-transform: uppercase;
    letter-spacing: 0.08em;
    font-weight: 600;
    color: #4a6fa8;
    opacity: 0.9;
    margin-bottom: 4px;
}
.voice-section-title {
    font-size: 18px;
    font-weight: 700;
    margin-bottom: 2px;
    color: #1f3253;
}
.voice-section-subtitle {
    font-size: 13px;
    color: #5b6b87;
    margin-bottom: 8px;
}
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

    st.markdown(
        """
<div class="voice-page">
  <div class="voice-header">
    <h1 class="voice-title">🎤 Voice Copilot – IT STORM</h1>
    <p class="voice-subtitle">Mode appel : tu parles, le copilot écoute (WebRTC) puis répond via RAG + TTS.</p>
  </div>
  <div class="voice-top-banner"></div>
  <div class="voice-layout">
    <div class="voice-wrapper">
""",
        unsafe_allow_html=True,
    )

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
<div class="voice-section-card">
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
    #  SOURCE AUDIO (WebRTC + Upload)
    # ==============================
    st.markdown(
        """
<div class="voice-section-card">
  <div class="voice-section-label">Entrée</div>
  <div class="voice-section-title">🎙️ Source audio</div>
  <div class="voice-section-subtitle">
    Soit parle en continu via le micro (START / STOP), soit charge un fichier audio.
  </div>
""",
        unsafe_allow_html=True,
    )

    col_inA, col_inB = st.columns([2, 1])

    webrtc_ctx = None
    with col_inA:
        if WEBRTC_AVAILABLE:
            webrtc_ctx = webrtc_streamer(
                key="voice_call_webrtc",
                mode=WebRtcMode.SENDONLY,
                rtc_configuration=RTC_CONFIG,
                media_stream_constraints={"audio": True, "video": False},
                async_processing=True,
            )
            st.caption("▶️ Clique sur START pour ouvrir le micro, parle, puis utilise « Transcrire l’audio ».")
        else:
            st.error("streamlit-webrtc / av / numpy non installés. WebRTC désactivé.")

    with col_inB:
        audio_file = st.file_uploader(
            "Ou bien charge un fichier audio",
            type=["wav", "mp3", "m4a", "ogg", "webm"],
        )
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
    #  LOGIQUE STT (WebRTC ou fichier)
    # ==============================
    if stt_btn:
        audio_bytes_to_use: Optional[bytes] = None
        filename = "audio.wav"

        # 1) Priorité au fichier uploadé
        if audio_file is not None:
            audio_bytes_to_use = audio_file.read()
            filename = audio_file.name
        # 2) Sinon, on récupère les frames WebRTC
        elif webrtc_ctx and webrtc_ctx.audio_receiver:
            frames = webrtc_ctx.audio_receiver.get_frames(timeout=1)
            if frames:
                audio_bytes_to_use = _frames_to_wav_bytes(frames)
                filename = "webrtc_audio.wav"

        if not audio_bytes_to_use:
            st.warning("Aucun audio à transcrire. Parle au micro (START), puis clique rapidement sur « Transcrire l’audio » ou upload un fichier.")
        else:
            with st.spinner("Transcription en cours..."):
                data = _api_post_stt(audio_bytes_to_use, filename, lang)
                if data and "text" in data:
                    st.session_state["voice_transcript"] = data["text"]
                    transcript = data["text"]
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
    #  RÉPONSE TEXTE DU COPILOT
    # ==============================
    answer_text = (st.session_state.get("voice_answer") or "").strip()

    st.markdown(
        """
<div class="voice-section-card">
  <div class="voice-section-label">Réponse</div>
  <div class="voice-section-title">🧠 Réponse du copilot</div>
  <div class="voice-section-subtitle">
    Résultat textuel renvoyé par le moteur RAG à partir de ta question (portage salarial, IT STORM…).
  </div>
""",
        unsafe_allow_html=True,
    )

    if answer_text:
        st.markdown(
            f"<div class='voice-history-msg-bot'>{answer_text}</div>",
            unsafe_allow_html=True,
        )
    else:
        st.markdown(
            "<div class='voice-history-msg-bot'>"
            "Aucune réponse pour l’instant. Parle au micro, lance la transcription puis clique sur "
            "<b>🧠 RAG + Voix</b>."
            "</div>",
            unsafe_allow_html=True,
        )

    st.markdown("</div>", unsafe_allow_html=True)  # fin carte réponse

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

    st.markdown("</div></div></div>", unsafe_allow_html=True)
