# -*- coding: utf-8 -*-
# Path: src/ui/sections/speech_chat.py
# Role: Interface Streamlit "Voice → RAG → Voice" avec :
#   - Upload audio + micro direct
#   - STT (via API /stt/transcribe)
#   - RAG (rag_brain.smart_rag_answer)
#   - TTS (via API /tts/synthesize)
#   - Mode conversation continue
#   - Avatar IA + animations d’ondes
#   - Bouton “Répéter la réponse”
#   - Bouton “Télécharger la transcription” (nom de fichier dynamique)

from __future__ import annotations

import base64
import os
from typing import Any, Dict, Optional, List
from datetime import datetime

import requests
import streamlit as st

# Micro direct (si disponible)
try:
    from audio_recorder_streamlit import audio_recorder  # type: ignore
except Exception:
    audio_recorder = None  # type: ignore

# RAG local
try:
    from src import rag_brain  # type: ignore
except Exception:
    rag_brain = None  # type: ignore

API_BASE = os.getenv("BACKEND_API_BASE_URL", "http://127.0.0.1:8001").rstrip("/")


# =====================================================================
#  HELPERS API
# =====================================================================

def _api_post_stt(file_bytes: bytes, filename: str, lang: str) -> Optional[Dict[str, Any]]:
    """Appel à l’API STT (Whisper) avec timeout long pour tests."""
    try:
        files = {"file": (filename, file_bytes, "audio/wav")}
        params = {"lang": lang}
        r = requests.post(
            f"{API_BASE}/stt/transcribe",
            files=files,
            params=params,
            timeout=1000,  # timeout étendu pour tests longs
        )
        r.raise_for_status()
        return r.json()
    except Exception as e:
        st.error(f"Erreur STT: {e}")
        return None


def _api_post_tts(text: str, lang: str) -> Optional[bytes]:
    """Appel à l’API TTS (gTTS) avec timeout étendu."""
    try:
        payload = {"text": text, "lang": lang}
        r = requests.post(
            f"{API_BASE}/tts/synthesize",
            json=payload,
            timeout=1000,  # idem : large pour éviter les timeouts
        )
        r.raise_for_status()
        data = r.json()
        audio_b64 = data.get("audio_base64")
        if not audio_b64:
            st.error("Réponse TTS invalide (pas de champ 'audio_base64').")
            return None
        return base64.b64decode(audio_b64)
    except Exception as e:
        st.error(f"Erreur TTS: {e}")
        return None


def _call_rag(question: str) -> str:
    """
    Appelle le RAG localement (rag_brain.smart_rag_answer).
    Si smart_rag_answer renvoie un dict, on tente de prendre 'answer'.
    """
    if rag_brain is None:
        return "Le module rag_brain n'est pas disponible."

    fn = getattr(rag_brain, "smart_rag_answer", None)
    if fn is None:
        return "La fonction smart_rag_answer n'est pas définie dans rag_brain."

    try:
        res = fn(question)
        if isinstance(res, dict):
            return str(res.get("answer") or res)
        return str(res)
    except Exception as e:
        return f"Erreur lors de l'appel RAG: {e}"


# =====================================================================
#  CSS / STYLE
# =====================================================================

def _inject_voice_copilot_css() -> None:
    st.markdown(
        """
<style>
.voice-wrapper {
    padding: 24px;
    margin-top: 10px;
    background: radial-gradient(circle at top left, rgba(0, 92, 255, 0.12), transparent 55%),
                radial-gradient(circle at bottom right, rgba(0, 190, 255, 0.12), transparent 55%),
                rgba(15, 18, 30, 0.96);
    border-radius: 24px;
    border: 1px solid rgba(255,255,255,0.10);
    box-shadow: 0 18px 40px rgba(0,0,0,0.45);
}

.voice-title {
    text-align: center;
    font-size: 30px !important;
    font-weight: 700 !important;
    padding-bottom: 4px;
    background: linear-gradient(90deg, #00C2FF, #4C7DFF);
    -webkit-background-clip: text;
    color: transparent;
}

.voice-subtitle {
    text-align: center;
    font-size: 16px;
    opacity: 0.80;
    margin-bottom: 18px;
}

/* Avatar IA circulaire */
.voice-avatar {
    width: 84px;
    height: 84px;
    border-radius: 50%;
    background: radial-gradient(circle at 30% 20%, #ffffff 0, #00E0FF 35%, #0050FF 70%);
    box-shadow: 0 0 22px rgba(0, 192, 255, 0.85);
    display: flex;
    align-items: center;
    justify-content: center;
    margin: 0 auto 10px auto;
    position: relative;
    overflow: hidden;
}

.voice-avatar-inner {
    width: 62px;
    height: 62px;
    border-radius: 50%;
    border: 2px solid rgba(255,255,255,0.7);
    display: flex;
    align-items: center;
    justify-content: center;
    color: #ffffff;
    font-weight: 700;
    font-size: 24px;
}

/* Barres animées type Siri */
.voice-wave {
    position: relative;
    height: 26px;
    margin-top: 4px;
    display: flex;
    align-items: center;
    justify-content: center;
    gap: 6px;
}

.voice-wave-bar {
    width: 4px;
    border-radius: 999px;
    background: linear-gradient(180deg, #00E0FF, #4C7DFF);
    animation: voice-bounce 0.9s infinite ease-in-out;
}

.voice-wave-bar:nth-child(1) { height: 8px; animation-delay: 0s; }
.voice-wave-bar:nth-child(2) { height: 16px; animation-delay: 0.12s; }
.voice-wave-bar:nth-child(3) { height: 24px; animation-delay: 0.24s; }
.voice-wave-bar:nth-child(4) { height: 16px; animation-delay: 0.36s; }
.voice-wave-bar:nth-child(5) { height: 8px;  animation-delay: 0.48s; }

@keyframes voice-bounce {
    0%, 100% { transform: scaleY(0.4); opacity: 0.7; }
    50%      { transform: scaleY(1.2); opacity: 1; }
}

.voice-mode-pill {
    display: inline-flex;
    align-items: center;
    gap: 6px;
    padding: 4px 10px;
    border-radius: 999px;
    background: rgba(255,255,255,0.06);
    font-size: 12px;
    margin-bottom: 8px;
}

.voice-card {
    margin-top: 14px;
    padding: 14px 16px;
    background: rgba(8,10,20,0.9);
    border-radius: 14px;
    border: 1px solid rgba(255,255,255,0.08);
}

.voice-history-msg-user {
    background: rgba(0,150,255,0.1);
    border-radius: 12px;
    padding: 10px 12px;
    margin-bottom: 8px;
    border: 1px solid rgba(0,150,255,0.45);
}

.voice-history-msg-bot {
    background: rgba(255,255,255,0.04);
    border-radius: 12px;
    padding: 10px 12px;
    margin-bottom: 8px;
    border: 1px solid rgba(255,255,255,0.10);
}

.voice-history-label {
    font-size: 11px;
    text-transform: uppercase;
    letter-spacing: 0.08em;
    opacity: 0.6;
    margin-bottom: 2px;
}

/* Boutons */
.stButton > button {
    border-radius: 999px;
    border: 1px solid rgba(255,255,255,0.20);
    font-weight: 600;
}

/* Audio player margin */
.stAudio {
    margin-top: 10px;
}
</style>
""",
        unsafe_allow_html=True,
    )


# =====================================================================
#  RENDER
# =====================================================================

def render() -> None:
    _inject_voice_copilot_css()

    # --------- STATE INIT ---------
    if "voice_transcript" not in st.session_state:
        st.session_state["voice_transcript"] = ""
    if "voice_answer" not in st.session_state:
        st.session_state["voice_answer"] = ""
    if "voice_last_tts" not in st.session_state:
        st.session_state["voice_last_tts"] = None  # type: ignore
    if "voice_history" not in st.session_state:
        st.session_state["voice_history"] = []

    # Variable locale typée (optionnel, utile pour mypy/IDE)
    voice_history: List[Dict[str, str]] = st.session_state["voice_history"]

    # --------- HEADER ---------
    st.markdown("<h1 class='voice-title'>🎤 Voice Copilot – IT STORM</h1>", unsafe_allow_html=True)
    st.markdown(
        "<p class='voice-subtitle'>Parle, ton copilote écoute. Transcription instantanée, réponse ancrée dans le RAG IT STORM, voix de synthèse claire.</p>",
        unsafe_allow_html=True,
    )

    with st.container():
        st.markdown("<div class='voice-wrapper'>", unsafe_allow_html=True)

        top_col1, top_col2 = st.columns([1, 2])

        with top_col1:
            st.markdown(
                """
<div class="voice-avatar">
  <div class="voice-avatar-inner">AI</div>
</div>
<div class="voice-wave">
  <div class="voice-wave-bar"></div>
  <div class="voice-wave-bar"></div>
  <div class="voice-wave-bar"></div>
  <div class="voice-wave-bar"></div>
  <div class="voice-wave-bar"></div>
</div>
""",
                unsafe_allow_html=True,
            )

        with top_col2:
            mode = st.radio(
                "Mode d’interaction",
                options=["Question simple", "Conversation continue"],
                horizontal=True,
            )
            st.caption("💡 En mode conversation, chaque échange est ajouté à l’historique (chat vocal).")

        # --------- INPUT ZONE ---------
        col_input_left, col_input_right = st.columns([2, 1])

        with col_input_left:
            st.markdown("#### 🎙️ Source audio")

            audio_file = st.file_uploader(
                "Upload un fichier audio (wav/mp3/m4a/ogg/webm)",
                type=["wav", "mp3", "m4a", "ogg", "webm"],
                label_visibility="collapsed",
            )

            mic_bytes: Optional[bytes] = None
            if audio_recorder is not None:
                st.markdown("##### ou enregistre avec le micro")
                mic_bytes = audio_recorder(
                    text="Appuie pour parler",
                    recording_color="#00d0ff",
                    neutral_color="#333333",
                    icon_size="2x",
                )
                if mic_bytes:
                    st.success("🎧 Enregistrement micro capturé.")
            else:
                st.info("ℹ️ Composant micro non disponible (audio-recorder-streamlit non installé).")

        with col_input_right:
            st.markdown("#### 🌐 Paramètres")
            lang = st.selectbox("Langue de la voix", ["fr", "en"], index=0)
            st.markdown("<div class='voice-mode-pill'>🧠 RAG IT STORM activé</div>", unsafe_allow_html=True)

        # --------- TRANSCRIPT ---------
        st.markdown("### 📝 Transcription")
        transcript = st.text_area(
            "Texte détecté (modifie si besoin avant d’envoyer au RAG) :",
            value=st.session_state["voice_transcript"],
            height=120,
        )

        # Bouton de téléchargement de la transcription (nom dynamique)
        if st.session_state["voice_transcript"].strip():
            model_name = os.getenv("WHISPER_MODEL_SIZE", "small")
            dt_str = datetime.now().strftime("%Y-%m-%d_%Hh%M")
            dynamic_filename = f"transcription_{dt_str}_{model_name}.txt"

            st.download_button(
                label="💾 Télécharger la transcription",
                data=st.session_state["voice_transcript"],
                file_name=dynamic_filename,
                mime="text/plain",
                use_container_width=True,
            )

        # --------- BUTTONS ---------
        col_btn1, col_btn2, col_btn3 = st.columns([1, 1, 1])

        with col_btn1:
            stt_btn = st.button("🔎 Transcrire l’audio", use_container_width=True)
        with col_btn2:
            rag_btn = st.button("🧠 RAG + Voix", use_container_width=True)
        with col_btn3:
            repeat_btn = st.button("🔁 Répéter la réponse audio", use_container_width=True)

        # --------- LOGIQUE STT ---------
        if stt_btn:
            # priorité au micro si disponible
            audio_bytes_to_use: Optional[bytes] = None
            filename_for_stt = "micro.wav"

            if mic_bytes:
                audio_bytes_to_use = mic_bytes
            elif audio_file is not None:
                audio_bytes_to_use = audio_file.read()
                filename_for_stt = audio_file.name

            if not audio_bytes_to_use:
                st.warning("Merci d’enregistrer ou d’uploader un fichier audio avant la transcription.")
            else:
                with st.spinner("Transcription de l’audio (STT)…"):
                    data = _api_post_stt(audio_bytes_to_use, filename_for_stt, lang)
                if data and "text" in data:
                    st.session_state["voice_transcript"] = data["text"]
                    st.success("✅ Transcription terminée.")
                    st.rerun()

        # synchro textarea → state
        if transcript != st.session_state["voice_transcript"]:
            st.session_state["voice_transcript"] = transcript

        # --------- LOGIQUE RAG + TTS ---------
        if rag_btn:
            question = st.session_state["voice_transcript"].strip()
            if not question:
                st.warning("Le texte est vide. Transcris l’audio ou écris ta question.")
            else:
                # Historique conversationnel (affichage uniquement)
                if mode == "Conversation continue":
                    voice_history.append({"role": "user", "text": question})
                    st.session_state["voice_history"] = voice_history

                with st.spinner("Interrogation du RAG IT STORM…"):
                    answer = _call_rag(question)

                st.session_state["voice_answer"] = answer
                if mode == "Conversation continue":
                    voice_history.append({"role": "assistant", "text": answer})
                    st.session_state["voice_history"] = voice_history

                st.markdown("### 🧠 Réponse du copilote")
                st.markdown("<div class='voice-card'>", unsafe_allow_html=True)
                st.write(answer)
                st.markdown("</div>", unsafe_allow_html=True)

                with st.spinner("Génération de la réponse audio (TTS)…"):
                    audio_bytes = _api_post_tts(answer, lang)

                if audio_bytes:
                    st.session_state["voice_last_tts"] = audio_bytes
                    st.markdown("### 🔊 Lecture de la réponse")
                    st.audio(audio_bytes, format="audio/mp3")
                    st.download_button(
                        label="💾 Télécharger la réponse audio",
                        data=audio_bytes,
                        file_name="itstorm_voice_answer.mp3",
                        mime="audio/mpeg",
                    )

        # --------- BOUTON REPEAT ---------
        if repeat_btn:
            last = st.session_state.get("voice_last_tts")
            if last:
                st.markdown("### 🔁 Répétition de la réponse")
                st.audio(last, format="audio/mp3")
            else:
                st.info("Aucune réponse audio précédente à répéter pour l’instant.")

        # --------- MODE CONVERSATION : HISTORIQUE ---------
        if mode == "Conversation continue" and st.session_state["voice_history"]:
            st.markdown("### 💬 Historique de la conversation")
            for msg in st.session_state["voice_history"]:
                if msg["role"] == "user":
                    st.markdown("<div class='voice-history-msg-user'>", unsafe_allow_html=True)
                    st.markdown("<div class='voice-history-label'>Vous</div>", unsafe_allow_html=True)
                    st.write(msg["text"])
                    st.markdown("</div>", unsafe_allow_html=True)
                else:
                    st.markdown("<div class='voice-history-msg-bot'>", unsafe_allow_html=True)
                    st.markdown("<div class='voice-history-label'>Copilote</div>", unsafe_allow_html=True)
                    st.write(msg["text"])
                    st.markdown("</div>", unsafe_allow_html=True)

        st.markdown("</div>", unsafe_allow_html=True)
# --------------------------------------------------------------------------------------
# END OF FILE