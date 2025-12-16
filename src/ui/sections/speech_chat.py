# -*- coding: utf-8 -*-
# Path: src/ui/sections/speech_chat.py
# Voice Copilot — Micro navigateur → STT → RAG → TTS
# - 0 streamlit-webrtc
# - Stable Windows / Chrome
# - Debug HTTP renforcé (CORS / API down / status + body)
# - TTS auto: joue la réponse RAG

from __future__ import annotations

import os
import streamlit as st
import streamlit.components.v1 as components

# ------------------------------------------------------------
# Config API
# ------------------------------------------------------------
API_BASE = os.getenv("BACKEND_API_BASE_URL", "http://127.0.0.1:8001").rstrip("/")


# ------------------------------------------------------------
# UI — STT + RAG + TTS
# ------------------------------------------------------------
def render_stt_only() -> None:
    st.markdown("## 🎙️ Voice Copilot — STT → RAG → TTS")
    st.caption("Démo stable : micro navigateur → STT → RAG → réponse + lecture audio (sans WebRTC).")

    lang = st.selectbox("Langue", ["fr", "en"], index=0)

    html = f"""
<div style="font-family: system-ui, -apple-system, Segoe UI, Roboto;
            border:1px solid #e5e7eb; border-radius:16px; padding:14px;">

  <div style="display:flex; gap:10px; align-items:center; flex-wrap:wrap;">
    <button id="btnStart"
      style="padding:10px 14px; border-radius:10px; border:1px solid #cbd5e1;
             background:#111827; color:white; font-weight:700;">
      🎤 Start
    </button>

    <button id="btnStop"
      style="padding:10px 14px; border-radius:10px; border:1px solid #cbd5e1;
             background:#ffffff; color:#111827; font-weight:700;">
      ⏹ Stop
    </button>

    <button id="btnSend"
      style="padding:10px 14px; border-radius:10px; border:1px solid #2563eb;
             background:#2563eb; color:white; font-weight:800;">
      🧪 Transcrire
    </button>

    <button id="btnAsk"
      style="padding:10px 14px; border-radius:10px; border:1px solid #16a34a;
             background:#16a34a; color:white; font-weight:800;">
      💬 Interroger Copilot
    </button>

    <span id="status" style="opacity:0.75;">Idle</span>
  </div>

  <div style="margin-top:10px;">
    <audio id="player" controls style="width:100%;"></audio>
  </div>

  <div style="margin-top:12px; padding:12px;
              border-radius:14px; background:#f8fafc;
              border:1px solid #e2e8f0;">
    <div style="font-weight:800; margin-bottom:6px;">📝 Transcription</div>
    <div id="transcript" style="white-space:pre-wrap; line-height:1.35;">(vide)</div>
  </div>

  <div style="margin-top:12px; padding:12px;
              border-radius:14px; background:#f0fdf4;
              border:1px solid #bbf7d0;">
    <div style="font-weight:800; margin-bottom:6px;">🤖 Réponse Copilot (RAG)</div>
    <div id="answer" style="white-space:pre-wrap; line-height:1.35;">(vide)</div>
    <div id="sources" style="margin-top:8px; font-size:12px; opacity:0.85;">Sources: —</div>

    <div style="margin-top:10px;">
      <div style="font-weight:800; margin-bottom:6px;">🔊 Lecture (TTS)</div>
      <audio id="ttsPlayer" controls style="width:100%;"></audio>
      <div style="font-size:12px; opacity:0.7; margin-top:6px;">
        Le TTS se déclenche automatiquement après la réponse RAG.
      </div>
    </div>
  </div>

  <div style="margin-top:10px; padding:10px; border-radius:12px; border:1px dashed #cbd5e1;">
    <div style="font-weight:800; margin-bottom:6px;">🧪 Debug</div>
    <div id="debug" style="font-size:12px; opacity:0.85; white-space:pre-wrap;"></div>
  </div>

  <div style="margin-top:8px; font-size:12px; opacity:0.7;">
    Conseil : parle 2–4 secondes → Stop → Transcrire → Interroger Copilot.
  </div>
</div>

<script>
(function() {{
  const btnStart = document.getElementById("btnStart");
  const btnStop  = document.getElementById("btnStop");
  const btnSend  = document.getElementById("btnSend");
  const btnAsk   = document.getElementById("btnAsk");

  const statusEl = document.getElementById("status");
  const player   = document.getElementById("player");
  const ttsPlayer = document.getElementById("ttsPlayer");

  const transcriptEl = document.getElementById("transcript");
  const answerEl = document.getElementById("answer");
  const sourcesEl = document.getElementById("sources");
  const debugEl  = document.getElementById("debug");

  let mediaRecorder = null;
  let chunks = [];
  let stream = null;
  let lastBlob = null;

  function setStatus(s) {{ statusEl.textContent = s; }}
  function setDebug(s)  {{ debugEl.textContent = s; }}

  function safeText(s) {{
    return (s || "").toString().replace(/\\s+/g, " ").trim();
  }}

  async function start() {{
    chunks = [];
    lastBlob = null;
    transcriptEl.textContent = "(vide)";
    answerEl.textContent = "(vide)";
    sourcesEl.textContent = "Sources: —";
    try {{ ttsPlayer.pause(); ttsPlayer.src = ""; }} catch(e) {{}}
    setDebug("[INFO] Ready. Click Stop then Transcrire.");

    try {{
      stream = await navigator.mediaDevices.getUserMedia({{ audio: true }});
      mediaRecorder = new MediaRecorder(stream, {{ mimeType: "audio/webm" }});

      mediaRecorder.ondataavailable = (e) => {{
        if (e.data && e.data.size > 0) chunks.push(e.data);
      }};

      mediaRecorder.onstart = () => setStatus("Recording...");
      mediaRecorder.onstop = () => {{
        setStatus("Stopped");
        lastBlob = new Blob(chunks, {{ type: "audio/webm" }});
        const url = URL.createObjectURL(lastBlob);
        player.src = url;
        setDebug("[REC] blob bytes=" + lastBlob.size + " | mime=audio/webm");
      }};

      mediaRecorder.start();
      setDebug("[REC] Recording... Speak now.");
    }} catch (err) {{
      console.error(err);
      setStatus("Mic error");
      setDebug("[ERR] Mic denied/error: " + err);
      alert("Micro refusé. Autorise le micro dans Chrome.");
    }}
  }}

  function stop() {{
    try {{
      if (mediaRecorder && mediaRecorder.state !== "inactive") mediaRecorder.stop();
      if (stream) stream.getTracks().forEach(t => t.stop());
    }} catch(e) {{}}
  }}

  async function sendToSTT() {{
    if (!lastBlob) {{
      alert("Aucun audio. Clique Start, parle, puis Stop.");
      return;
    }}
    if (lastBlob.size < 2000) {{
      alert("Audio trop court. Parle au moins 2 secondes.");
      return;
    }}

    const url = "{API_BASE}/stt/transcribe?lang={lang}";
    setStatus("Sending to STT...");
    transcriptEl.textContent = "(transcription en cours...)";
    setDebug("[HTTP STT] sending | url=" + url + " | bytes=" + lastBlob.size);

    try {{
      const form = new FormData();
      form.append("file", lastBlob, "mic.webm");

      const resp = await fetch(url, {{
        method: "POST",
        body: form
      }});

      const body = await resp.text();
      setDebug("[HTTP STT] " + resp.status + " | " + body);

      if (!resp.ok) {{
        transcriptEl.textContent = "❌ STT error: " + body;
        setStatus("Error");
        return;
      }}

      const json = JSON.parse(body);
      const text = safeText(json.text || "");
      transcriptEl.textContent = text || "(texte vide)";
      setStatus("Done ✅");
    }} catch (err) {{
      console.error(err);
      setDebug("[HTTP STT] FETCH FAILED: " + err);
      transcriptEl.textContent = "❌ FETCH FAILED (souvent CORS ou API down): " + err;
      setStatus("Error");
    }}
  }}

  async function speakTTS(text) {{
    const t = (text || "").toString().trim();
    if (!t || t === "(vide)" || t === "(réponse vide)") return;

    // ✅ URL TTS
    // - si ton router est inclus avec prefix="/tts" => /tts/synthesize
    // - sinon, si tu as directement /synthesize => remplace la ligne suivante par:
    //   const url = "{API_BASE}/synthesize";
    const url = "{API_BASE}/tts/synthesize";

    setStatus("TTS...");
    setDebug("[HTTP TTS] sending | url=" + url + " | chars=" + t.length);

    try {{
      const resp = await fetch(url, {{
        method: "POST",
        headers: {{ "Content-Type": "application/json" }},
        body: JSON.stringify({{ text: t, lang: "{lang}" }})
      }});

      const body = await resp.text();
      setDebug("[HTTP TTS] " + resp.status + " | " + body);

      if (!resp.ok) {{
        setStatus("Error");
        return;
      }}

      const json = JSON.parse(body);
      const b64 = (json.audio_base64 || "").trim();
      if (!b64) {{
        setStatus("Done ✅");
        return;
      }}

      // Lecture base64
      ttsPlayer.src = "data:audio/mpeg;base64," + b64;

      try {{
        await ttsPlayer.play();
      }} catch (e) {{
        // Autoplay parfois bloqué : l'utilisateur peut cliquer Play
      }}

      setStatus("Done ✅");
    }} catch (err) {{
      console.error(err);
      setDebug("[HTTP TTS] FETCH FAILED: " + err);
      setStatus("Error");
    }}
  }}

  async function askRAG() {{
    const q = (transcriptEl.textContent || "").trim();
    if (!q || q === "(vide)" || q.includes("transcription en cours")) {{
      alert("D’abord fais la transcription STT.");
      return;
    }}

    const url = "{API_BASE}/rag/ask";
    setStatus("Asking RAG...");
    answerEl.textContent = "(RAG en cours...)";
    sourcesEl.textContent = "Sources: —";
    try {{ ttsPlayer.pause(); ttsPlayer.src = ""; }} catch(e) {{}}
    setDebug("[HTTP RAG] sending | url=" + url + " | q_len=" + q.length);

    try {{
      const resp = await fetch(url, {{
        method: "POST",
        headers: {{ "Content-Type": "application/json" }},
        body: JSON.stringify({{ question: q }})
      }});

      const body = await resp.text();
      setDebug("[HTTP RAG] " + resp.status + " | " + body);

      if (!resp.ok) {{
        answerEl.textContent = "❌ RAG error: " + body;
        setStatus("Error");
        return;
      }}

      const json = JSON.parse(body);
      const ans = (json.answer || "").trim();
      answerEl.textContent = ans || "(réponse vide)";

      const src = Array.isArray(json.sources) ? json.sources : [];
      sourcesEl.textContent = src.length ? ("Sources: " + src.join(" | ")) : "Sources: —";

      // ✅ TTS auto sur la réponse obtenue
      await speakTTS(answerEl.textContent);

      setStatus("Done ✅");
    }} catch (err) {{
      console.error(err);
      setDebug("[HTTP RAG] FETCH FAILED: " + err);
      answerEl.textContent = "❌ FETCH FAILED (souvent CORS ou API down): " + err;
      setStatus("Error");
    }}
  }}

  btnStart.onclick = start;
  btnStop.onclick  = stop;
  btnSend.onclick  = sendToSTT;
  btnAsk.onclick   = askRAG;
}})();
</script>
"""
    components.html(html, height=820, scrolling=False)
