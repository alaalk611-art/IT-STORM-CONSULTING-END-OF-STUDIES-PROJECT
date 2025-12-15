# -*- coding: utf-8 -*-
# Path: src/ui/sections/speech_chat.py
# STT ONLY — Micro navigateur (MediaRecorder) → /stt/transcribe → texte
# - 0 streamlit-webrtc
# - Stable Windows / Chrome
# - Debug HTTP renforcé (CORS / API down / status + body)

from __future__ import annotations

import os
import streamlit as st
import streamlit.components.v1 as components

# ------------------------------------------------------------
# Config API
# ------------------------------------------------------------
API_BASE = os.getenv("BACKEND_API_BASE_URL", "http://127.0.0.1:8001").rstrip("/")


# ------------------------------------------------------------
# UI — STT ONLY
# ------------------------------------------------------------
def render_stt_only() -> None:
    st.markdown("## 🎙️ STT — Micro → Transcription")
    st.caption("Démo STT simple : enregistrement micro navigateur → API STT → texte (sans WebRTC).")

    lang = st.selectbox("Langue STT", ["fr", "en"], index=0)

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

  <div style="margin-top:10px; padding:10px; border-radius:12px; border:1px dashed #cbd5e1;">
    <div style="font-weight:800; margin-bottom:6px;">🧪 Debug</div>
    <div id="debug" style="font-size:12px; opacity:0.85; white-space:pre-wrap;"></div>
  </div>

  <div style="margin-top:8px; font-size:12px; opacity:0.7;">
    Conseil : parle 2–4 secondes → Stop → Transcrire.
  </div>
</div>

<script>
(function() {{
  const btnStart = document.getElementById("btnStart");
  const btnStop  = document.getElementById("btnStop");
  const btnSend  = document.getElementById("btnSend");
  const statusEl = document.getElementById("status");
  const player   = document.getElementById("player");
  const transcriptEl = document.getElementById("transcript");
  const debugEl  = document.getElementById("debug");

  let mediaRecorder = null;
  let chunks = [];
  let stream = null;
  let lastBlob = null;

  function setStatus(s) {{ statusEl.textContent = s; }}
  function setDebug(s)  {{ debugEl.textContent = s; }}

  async function start() {{
    chunks = [];
    lastBlob = null;
    transcriptEl.textContent = "(vide)";
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

        // ✅ Important: ne plus écraser un debug HTTP, on met juste l'info REC
        setDebug("[REC] blob bytes = " + lastBlob.size + " | mime = audio/webm");
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

    // ✅ Debug immédiat pour prouver que le bouton déclenche
    setDebug("[HTTP] sending... url=" + url + " | bytes=" + lastBlob.size);

    try {{
      const form = new FormData();
      form.append("file", lastBlob, "mic.webm");

      const resp = await fetch(url, {{
        method: "POST",
        body: form
      }});

      const body = await resp.text();
      setDebug("[HTTP] " + resp.status + " | " + body);

      if (!resp.ok) {{
        transcriptEl.textContent = "❌ STT error: " + body;
        setStatus("Error");
        return;
      }}

      const json = JSON.parse(body);
      transcriptEl.textContent = (json.text || "").trim() || "(texte vide)";
      setStatus("Done ✅");
    }} catch (err) {{
      console.error(err);
      // ✅ Ici tu verras clairement CORS / API down (Failed to fetch)
      setDebug("[HTTP] FETCH FAILED: " + err);
      transcriptEl.textContent = "❌ FETCH FAILED (souvent CORS ou API down): " + err;
      setStatus("Error");
    }}
  }}

  btnStart.onclick = start;
  btnStop.onclick  = stop;
  btnSend.onclick  = sendToSTT;
}})();
</script>
"""
    components.html(html, height=520, scrolling=False)
