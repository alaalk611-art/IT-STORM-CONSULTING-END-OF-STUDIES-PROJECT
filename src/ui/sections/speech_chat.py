# -*- coding: utf-8 -*-
# Path: src/ui/sections/speech_chat.py
# Voice Copilot — Premium UI (FINAL)
#
# ✅ Fixes included:
# 1) 🎛️ VU-mètre RMS (bar + valeur) + contraintes audio (AGC/NS/EC) => micro “moins faible”
# 2) 🔊 TTS complet (plus de limite ~17s) :
#    - Split en chunks courts
#    - Appels multiples /tts/synthesize (b64)
#    - Concat bytes MP3 => 1 seul Blob audio/mpeg => lecture complète
# 3) 🛡️ Mode anti-hallucination (UI-only): si sources vides => réponse prudente + question

from __future__ import annotations

import os
import streamlit as st
import streamlit.components.v1 as components

API_BASE = os.getenv("BACKEND_API_BASE_URL", "http://127.0.0.1:8001").rstrip("/")


def _inject_page_css() -> None:
    st.markdown(
        """
<style>
/* Page polish (simple, stable) */
.vc-hero{
  padding:1.1rem 1.2rem;
  border-radius:18px;
  background:
    radial-gradient(circle at 0% 0%,rgba(190,18,60,.16),transparent 55%),
    radial-gradient(circle at 100% 0%,rgba(127,29,29,.12),transparent 55%),
    linear-gradient(135deg,rgba(15,23,42,.96),rgba(15,23,42,.90));
  border:1px solid rgba(148,163,184,.35);
  box-shadow:0 24px 60px rgba(15,23,42,.45);
}
.vc-title{
  font-size:1.25rem;
  font-weight:850;
  letter-spacing:.02em;
  background:linear-gradient(120deg,#e5e7eb,#fecdd3,#be123c);
  -webkit-background-clip:text;
  color:transparent;
  margin:0;
}
.vc-sub{color:#cbd5e1; margin-top:.25rem; font-size:.92rem;}
.vc-pills{margin-top:.55rem; display:flex; flex-wrap:wrap; gap:.45rem;}
.vc-pill{
  display:inline-flex; align-items:center; gap:.4rem;
  padding:.22rem .7rem;
  border-radius:999px;
  font-size:.74rem;
  background:rgba(15,23,42,.82);
  border:1px solid rgba(148,163,184,.35);
  color:#e5e7eb;
}
.stTabs [data-baseweb="tab-list"]{justify-content:center; gap:.5rem;}
.stTabs [data-baseweb="tab"]{
  border-radius:999px !important;
  padding:0.35rem 1.0rem !important;
  font-weight:750 !important;
  font-size:.9rem !important;
  background:#f8fafc !important;
  color:#64748b !important;
}
.stTabs [aria-selected="true"]{
  background: linear-gradient(135deg, #7f1d1d, #be123c) !important;
  color: white !important;
  box-shadow: 0 10px 30px rgba(190,18,60,0.18);
}
</style>
""",
        unsafe_allow_html=True,
    )


def _component_single_question(lang: str) -> str:
    return f"""
<div style="font-family: system-ui, -apple-system, Segoe UI, Roboto, Arial;
            border:1px solid rgba(148,163,184,.35);
            border-radius:18px; padding:14px;
            background: rgba(255,255,255,0.92);
            box-shadow:0 14px 35px rgba(15,23,42,.08);">

  <style>
    :root{{
      --bd-1:#7f1d1d;
      --bd-2:#991b1b;
      --bd-3:#be123c;
      --ok:#16a34a;
      --run:#be123c;
      --err:#ef4444;
    }}

    .rowtop {{
      display:flex; gap:10px; align-items:center; flex-wrap:wrap;
      padding:10px; border-radius:16px;
      border:1px solid rgba(148,163,184,.35);
      background: #f8fafc;
    }}
    .btn {{
      padding:10px 14px; border-radius:999px; cursor:pointer;
      border:1px solid rgba(148,163,184,.55);
      font-weight:850;
      transition: transform .12s ease, box-shadow .12s ease, opacity .12s ease;
    }}
    .btn:hover {{ transform: translateY(-1px); box-shadow:0 10px 25px rgba(15,23,42,.10); }}
    .btn:disabled {{ opacity:.5; cursor:not-allowed; transform:none; box-shadow:none; }}
    .b-dark {{
      background: linear-gradient(135deg, #0f172a, #111827);
      color:white;
      border-color: rgba(148,163,184,.55);
    }}
    .b-bordeaux {{
      background: linear-gradient(135deg, var(--bd-1), var(--bd-2), var(--bd-3));
      color:white;
      border-color: rgba(190,18,60,.65);
      box-shadow: 0 14px 35px rgba(127,29,29,.20);
    }}
    .b-white {{
      background:#ffffff; color:#0f172a;
      border-color: rgba(148,163,184,.55);
    }}

    .toggle {{
      display:inline-flex; align-items:center; gap:8px;
      padding:8px 10px;
      border-radius:999px;
      border:1px solid rgba(148,163,184,.45);
      background:#ffffff;
      font-size:12px;
      font-weight:900;
      color:#0f172a;
      cursor:pointer;
      user-select:none;
    }}

    .status {{
      margin-left:auto; font-weight:900; font-size:12px; color:#0f172a;
      padding:6px 10px; border-radius:999px; background:#ffffff;
      border:1px solid rgba(148,163,184,.45);
      display:flex; align-items:center; gap:8px;
    }}
    .dot {{
      width:8px; height:8px; border-radius:999px; background:#94a3b8;
      box-shadow:0 0 0 0 rgba(190,18,60,.0);
    }}
    .dot.ok  {{ background: var(--ok); }}
    .dot.run {{
      background: var(--run);
      animation:pulse 1.6s infinite ease-in-out;
      box-shadow:0 0 0 0 rgba(190,18,60,.35);
    }}
    .dot.err {{ background: var(--err); }}
    @keyframes pulse {{
      0%   {{ box-shadow:0 0 0 0 rgba(190,18,60,.40); }}
      70%  {{ box-shadow:0 0 0 10px rgba(190,18,60,0); }}
      100% {{ box-shadow:0 0 0 0 rgba(190,18,60,0); }}
    }}

    .grid {{
      display:grid;
      grid-template-columns: 1fr 1fr;
      gap:12px;
      margin-top:12px;
    }}
    @media (max-width: 900px) {{
      .grid {{ grid-template-columns: 1fr; }}
    }}
    .panel {{
      border-radius:16px;
      border:1px solid rgba(148,163,184,.35);
      background:#ffffff;
      padding:12px;
    }}
    .title {{
      font-weight:950; font-size:13px; color:#0f172a;
      display:flex; align-items:center; gap:8px; margin-bottom:8px;
    }}
    .box {{
      white-space:pre-wrap; line-height:1.45;
      border-radius:14px;
      background:#f8fafc;
      border:1px solid rgba(148,163,184,.25);
      padding:10px;
      min-height:92px;
      color:#0f172a;
      font-size:13px;
    }}
    .mini {{
      font-size:12px; color:#64748b; margin-top:8px;
    }}

    .trace {{
      margin-top:12px;
      border-radius:16px;
      border:1px solid rgba(148,163,184,.35);
      background: linear-gradient(135deg, rgba(190,18,60,.08), rgba(199,210,254,.10));
      padding:12px;
    }}
    .trace-row {{
      display:flex; flex-wrap:wrap; gap:8px; margin-top:10px;
    }}
    .step {{
      display:inline-flex; align-items:center; gap:8px;
      padding:8px 10px;
      border-radius:999px;
      border:1px solid rgba(148,163,184,.45);
      background:#ffffff;
      font-size:12px;
      color:#0f172a;
      font-weight:900;
    }}
    .badge {{
      font-size:11px;
      padding:3px 8px;
      border-radius:999px;
      border:1px solid rgba(148,163,184,.35);
      background:#f8fafc;
      font-weight:950;
      color:#0f172a;
    }}
    .badge.ok   {{ background: rgba(22,163,74,.14); border-color: rgba(22,163,74,.35); }}
    .badge.err  {{ background: rgba(239,68,68,.12); border-color: rgba(239,68,68,.35); }}
    .badge.wait {{ background: rgba(190,18,60,.08); border-color: rgba(190,18,60,.25); }}
    .badge.run  {{ background: rgba(190,18,60,.12); border-color: rgba(190,18,60,.35); }}

    .meta {{
      margin-top:8px;
      font-size:12px;
      color:#475569;
      display:flex; flex-wrap:wrap; gap:10px;
    }}
    .chip {{
      border:1px solid rgba(148,163,184,.35);
      background:#ffffff;
      padding:6px 10px;
      border-radius:999px;
      font-weight:800;
    }}
  </style>

  <div class="rowtop">
    <label class="toggle" title="Si pas de sources, réponse prudente + question de précision">
      <input id="antiHall" type="checkbox" checked style="margin-right:6px;" />
      🛡️ Anti-hallucination
    </label>

    <button id="btnStart" class="btn b-dark">🎤 Start</button>
    <button id="btnStop"  class="btn b-white">⏹ Stop</button>
    <button id="btnSend"  class="btn b-bordeaux">🧪 Transcrire</button>
    <button id="btnAsk"   class="btn b-bordeaux">💬 Interroger</button>

    <div class="status">
      <div id="dot" class="dot"></div>
      <span id="status">Idle</span>
    </div>
  </div>

  <!-- 🎛️ VU Meter -->
  <div style="margin-top:8px; display:flex; align-items:center; gap:10px;">
    <div style="font-weight:900; font-size:12px;">VU</div>
    <div style="flex:1; height:10px; background:#e2e8f0; border-radius:999px; overflow:hidden;">
      <div id="vuBar" style="width:0%; height:100%; background:linear-gradient(90deg,#16a34a,#f59e0b,#ef4444);"></div>
    </div>
    <div id="vuTxt" style="font-weight:900; font-size:12px; width:110px; text-align:right;">RMS=0.0000</div>
  </div>

  <div style="margin-top:10px;">
    <div class="title">🎧 Pré-écoute (micro)</div>
    <audio id="player" controls style="width:100%;"></audio>
  </div>

  <div class="grid">
    <div class="panel">
      <div class="title">📝 Transcription (STT)</div>
      <div id="transcript" class="box">(vide)</div>
      <div class="mini">Endpoint : <code>{API_BASE}/stt/transcribe?lang={lang}</code></div>
    </div>

    <div class="panel">
      <div class="title">🤖 Réponse documentée (RAG)</div>
      <div id="answer" class="box">(vide)</div>
      <div id="sources" class="mini">Sources: —</div>

      <div style="margin-top:10px;">
        <div class="title">🔊 Lecture (TTS)</div>
        <audio id="ttsPlayer" controls style="width:100%;"></audio>
        <div class="mini">Endpoint : <code>{API_BASE}/tts/synthesize</code></div>
      </div>
    </div>
  </div>

  <div class="trace">
    <div class="title">🧾 Trace d’exécution</div>
    <div class="trace-row">
      <div class="step">🎤 Record <span class="badge wait" id="bRecord">WAIT</span></div>
      <div class="step">🧪 STT <span class="badge wait" id="bSTT">WAIT</span></div>
      <div class="step">💬 RAG <span class="badge wait" id="bRAG">WAIT</span></div>
      <div class="step">🔊 TTS <span class="badge wait" id="bTTS">WAIT</span></div>
    </div>
    <div class="meta">
      <div class="chip">⏱ total: <b id="tTotal">—</b></div>
      <div class="chip">🧪 stt: <b id="tStt">—</b></div>
      <div class="chip">💬 rag: <b id="tRag">—</b></div>
      <div class="chip">🔊 tts: <b id="tTts">—</b></div>
    </div>
  </div>

</div>

<script>
(function() {{
  const btnStart = document.getElementById("btnStart");
  const btnStop  = document.getElementById("btnStop");
  const btnSend  = document.getElementById("btnSend");
  const btnAsk   = document.getElementById("btnAsk");

  const antiHallEl = document.getElementById("antiHall");

  const statusEl = document.getElementById("status");
  const dotEl    = document.getElementById("dot");

  const player    = document.getElementById("player");
  const ttsPlayer = document.getElementById("ttsPlayer");

  const transcriptEl = document.getElementById("transcript");
  const answerEl     = document.getElementById("answer");
  const sourcesEl    = document.getElementById("sources");

  const bRecord = document.getElementById("bRecord");
  const bSTT    = document.getElementById("bSTT");
  const bRAG    = document.getElementById("bRAG");
  const bTTS    = document.getElementById("bTTS");

  const tTotal = document.getElementById("tTotal");
  const tStt   = document.getElementById("tStt");
  const tRag   = document.getElementById("tRag");
  const tTts   = document.getElementById("tTts");

  const vuBar = document.getElementById("vuBar");
  const vuTxt = document.getElementById("vuTxt");

  let mediaRecorder = null;
  let chunks = [];
  let stream = null;
  let lastBlob = null;

  let lastObjectUrl = null;
  let t0 = null;
  let tick = {{ stt: null, rag: null, tts: null, total: null }};

  // VU-meter state
  let audioCtx = null;
  let analyser = null;
  let data = null;
  let vuTimer = null;

  function msToStr(ms) {{
    if (ms === null || ms === undefined) return "—";
    const v = Math.max(0, Math.round(ms));
    return v < 1000 ? (v + "ms") : ((v/1000).toFixed(2) + "s");
  }}

  function setStatus(s, mode) {{
    statusEl.textContent = s;
    dotEl.className = "dot";
    if (mode === "run") dotEl.classList.add("run");
    if (mode === "ok")  dotEl.classList.add("ok");
    if (mode === "err") dotEl.classList.add("err");
  }}

  function setBadge(el, state) {{
    el.textContent = state;
    el.className = "badge";
    if (state === "OK")   el.classList.add("ok");
    if (state === "ERR")  el.classList.add("err");
    if (state === "WAIT") el.classList.add("wait");
    if (state === "RUN")  el.classList.add("run");
  }}

  function resetTrace() {{
    setBadge(bRecord, "WAIT");
    setBadge(bSTT, "WAIT");
    setBadge(bRAG, "WAIT");
    setBadge(bTTS, "WAIT");
    tick = {{ stt: null, rag: null, tts: null, total: null }};
    tTotal.textContent = "—";
    tStt.textContent = "—";
    tRag.textContent = "—";
    tTts.textContent = "—";
  }}

  function safeText(s) {{
    return (s || "").toString().replace(/\\s+/g, " ").trim();
  }}

  function cleanAnswer(text) {{
    let t = (text || "").toString();
    t = t.replace(/\\r/g, "");
    t = t.replace(/\\n{{3,}}/g, "\\n\\n").trim();

    const parts = t.split(/(?<=[\\.!\\?])\\s+/).map(x => x.trim()).filter(Boolean);
    const seen = new Set();
    const out = [];
    for (const p of parts) {{
      const key = p.toLowerCase().replace(/[^a-z0-9àâçéèêëîïôùûüÿñæœ\\s]/gi, "").replace(/\\s+/g, " ").trim();
      if (!key) continue;
      if (seen.has(key)) continue;
      seen.add(key);
      out.push(p);
    }}
    t = out.join(" ").trim();

    const maxChars = 2000;
    if (t.length > maxChars) t = t.slice(0, maxChars).trim() + "…";
    return t;
  }}

  function buildRagPrompt(userQuestion, antiHall) {{
    const base = [
      "Règles de réponse :",
      "- Réponds comme un humain à l’oral",
      "- Une seule réponse claire et utile",
      "- Pas de répétition, pas de blabla",
      "- Phrases courtes",
      "- Maximum 6 phrases",
    ];
    if (antiHall) {{
      base.push(
        "",
        "Anti-hallucination :",
        "- Si tu n’es pas sûr, dis-le clairement.",
        "- Ne devine pas.",
        "- Pose UNE question courte pour préciser."
      );
    }}
    base.push("", "Question :", userQuestion);
    return base.join("\\n");
  }}

  function antiHallFallback(originalQ) {{
    const q = (originalQ || "").trim();
    if (!q) return "Je n’ai pas assez d’éléments pour répondre avec certitude. Tu peux préciser ta question ?";
    return "Je n’ai pas trouvé d’éléments fiables dans ma base pour répondre avec certitude. " +
           "Tu peux préciser (ex: le point exact, ou le document concerné) ?";
  }}

  // ----------------------------
  // 🎛️ VU-meter
  // ----------------------------
  function startVu(s) {{
    if (!vuBar || !vuTxt) return;
    try {{
      audioCtx = new (window.AudioContext || window.webkitAudioContext)();
      const src = audioCtx.createMediaStreamSource(s);
      analyser = audioCtx.createAnalyser();
      analyser.fftSize = 2048;
      data = new Float32Array(analyser.fftSize);
      src.connect(analyser);

      if (vuTimer) clearInterval(vuTimer);
      vuTimer = setInterval(() => {{
        analyser.getFloatTimeDomainData(data);
        let sum = 0;
        for (let i = 0; i < data.length; i++) sum += data[i] * data[i];
        const rms = Math.sqrt(sum / data.length);
        const pct = Math.min(100, Math.max(0, rms * 220)); // scaling
        vuBar.style.width = pct + "%";
        vuTxt.textContent = "RMS=" + rms.toFixed(4);
      }}, 80);
    }} catch (e) {{
      // ignore
    }}
  }}

  function stopVu() {{
    if (vuTimer) clearInterval(vuTimer);
    vuTimer = null;
    try {{ if (audioCtx) audioCtx.close(); }} catch(e) {{}}
    audioCtx = null; analyser = null; data = null;
    if (vuBar) vuBar.style.width = "0%";
    if (vuTxt) vuTxt.textContent = "RMS=0.0000";
  }}

  // ----------------------------
  // 🔊 TTS: split => multi-call => concat mp3 => 1 Blob
  // ----------------------------
  function splitForTts(text, maxLen) {{
    const t = (text || "").toString().trim();
    if (!t) return [];
    const maxL = Math.max(80, maxLen || 140);

    const sentences = t
      .replace(/\\s+/g, " ")
      .split(/(?<=[\\.!\\?])\\s+/)
      .map(x => x.trim())
      .filter(Boolean);

    const chunks = [];
    let cur = "";
    for (const s of sentences) {{
      if (!cur) {{ cur = s; continue; }}
      if ((cur.length + 1 + s.length) <= maxL) cur += " " + s;
      else {{ chunks.push(cur); cur = s; }}
    }}
    if (cur) chunks.push(cur);

    const final = [];
    for (const c of chunks) {{
      if (c.length <= maxL) final.push(c);
      else for (let i=0;i<c.length;i+=maxL) final.push(c.slice(i,i+maxL));
    }}
    return final.filter(Boolean);
  }}

  function b64ToBytes(b64) {{
    const bin = atob(b64);
    const arr = new Uint8Array(bin.length);
    for (let i = 0; i < bin.length; i++) arr[i] = bin.charCodeAt(i);
    return arr;
  }}

  async function ttsSynthesizeB64(text) {{
    const url = "{API_BASE}/tts/synthesize";
    const resp = await fetch(url, {{
      method: "POST",
      headers: {{ "Content-Type": "application/json" }},
      body: JSON.stringify({{ text: text, lang: "{lang}" }})
    }});
    const body = await resp.text();
    if (!resp.ok) throw new Error(body || "TTS error");
    const json = JSON.parse(body);
    const b64 = (json.audio_base64 || "").trim();
    if (!b64) throw new Error("Empty audio");
    return b64;
  }}

  async function speakTTSLong(text) {{
    const t = (text || "").toString().trim();
    if (!t || t === "(vide)" || t === "(réponse vide)") return;

    setBadge(bTTS, "RUN");
    setStatus("TTS…", "run");

    const tStart = performance.now();

    // Chunks plus petits => pas de coupe ~17s côté TTS
    const parts = splitForTts(t, 140);

    const byteParts = [];
    for (const part of parts) {{
      const b64 = await ttsSynthesizeB64(part);
      byteParts.push(b64ToBytes(b64));
    }}

    let totalLen = 0;
    for (const a of byteParts) totalLen += a.length;
    const merged = new Uint8Array(totalLen);
    let off = 0;
    for (const a of byteParts) {{ merged.set(a, off); off += a.length; }}

    const blob = new Blob([merged], {{ type: "audio/mpeg" }});
    const url = URL.createObjectURL(blob);

    try {{ ttsPlayer.pause(); ttsPlayer.currentTime = 0; }} catch(e) {{}}
    ttsPlayer.src = url;

    try {{ await ttsPlayer.play(); }} catch(e) {{ /* user can press play */ }}

    tick.tts = performance.now() - tStart;
    tTts.textContent = msToStr(tick.tts);

    setBadge(bTTS, "OK");
    setStatus("Done ✅", "ok");
  }}

  // ----------------------------
  // Record / STT / RAG
  // ----------------------------
  async function start() {{
    chunks = [];
    lastBlob = null;

    transcriptEl.textContent = "(vide)";
    answerEl.textContent = "(vide)";
    sourcesEl.textContent = "Sources: —";
    try {{ ttsPlayer.pause(); ttsPlayer.src = ""; }} catch(e) {{}}

    resetTrace();
    setBadge(bRecord, "RUN");
    setStatus("Recording…", "run");

    try {{
      stream = await navigator.mediaDevices.getUserMedia({{
        audio: {{
          echoCancellation: true,
          noiseSuppression: true,
          autoGainControl: true,
          channelCount: 1,
          sampleRate: 48000
        }}
      }});

      startVu(stream);

      mediaRecorder = new MediaRecorder(stream, {{ mimeType: "audio/webm" }});

      mediaRecorder.ondataavailable = (e) => {{
        if (e.data && e.data.size > 0) chunks.push(e.data);
      }};

      mediaRecorder.onstop = () => {{
        lastBlob = new Blob(chunks, {{ type: "audio/webm" }});

        if (lastObjectUrl) {{
          try {{ URL.revokeObjectURL(lastObjectUrl); }} catch(e) {{}}
        }}
        lastObjectUrl = URL.createObjectURL(lastBlob);
        player.src = lastObjectUrl;

        setBadge(bRecord, "OK");
        setStatus("Stopped", "ok");
      }};

      t0 = performance.now();
      mediaRecorder.start();
    }} catch (err) {{
      setBadge(bRecord, "ERR");
      setStatus("Mic error", "err");
      alert("Micro refusé. Autorise le micro dans Chrome.");
    }}
  }}

  function stop() {{
    try {{
      if (mediaRecorder && mediaRecorder.state !== "inactive") mediaRecorder.stop();
      if (stream) stream.getTracks().forEach(t => t.stop());
    }} catch(e) {{}}
    stopVu();
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

    setBadge(bSTT, "RUN");
    setStatus("STT…", "run");
    transcriptEl.textContent = "(transcription en cours.)";

    const url = "{API_BASE}/stt/transcribe?lang={lang}";
    const tStart = performance.now();

    try {{
      const form = new FormData();
      form.append("file", lastBlob, "mic.webm");

      const resp = await fetch(url, {{ method: "POST", body: form }});
      const body = await resp.text();

      if (!resp.ok) {{
        transcriptEl.textContent = "❌ STT error: " + body;
        setBadge(bSTT, "ERR");
        setStatus("Error", "err");
        return;
      }}

      const json = JSON.parse(body);
      const text = safeText(json.text || "");
      transcriptEl.textContent = text || "(texte vide)";

      tick.stt = performance.now() - tStart;
      tStt.textContent = msToStr(tick.stt);

      setBadge(bSTT, "OK");
      setStatus("STT done", "ok");
    }} catch (err) {{
      transcriptEl.textContent = "❌ STT fetch failed: " + err;
      setBadge(bSTT, "ERR");
      setStatus("Error", "err");
    }}
  }}

  async function askRAG() {{
    const qRaw = (transcriptEl.textContent || "").trim();
    if (!qRaw || qRaw === "(vide)" || qRaw.includes("transcription en cours")) {{
      alert("D’abord fais la transcription STT.");
      return;
    }}

    setBadge(bRAG, "RUN");
    setStatus("RAG…", "run");

    answerEl.textContent = "(RAG en cours.)";
    sourcesEl.textContent = "Sources: —";
    try {{ ttsPlayer.pause(); ttsPlayer.src = ""; }} catch(e) {{}}

    const url = "{API_BASE}/rag/ask";
    const tStart = performance.now();

    const antiHall = antiHallEl ? !!antiHallEl.checked : true;
    const enriched = buildRagPrompt(qRaw, antiHall);

    try {{
      const resp = await fetch(url, {{
        method: "POST",
        headers: {{ "Content-Type": "application/json" }},
        body: JSON.stringify({{ question: enriched }})
      }});

      const body = await resp.text();
      if (!resp.ok) {{
        answerEl.textContent = "❌ RAG error: " + body;
        setBadge(bRAG, "ERR");
        setStatus("Error", "err");
        return;
      }}

      const json = JSON.parse(body);
      const src = Array.isArray(json.sources) ? json.sources : [];
      sourcesEl.textContent = src.length ? ("Sources: " + src.join(" | ")) : "Sources: —";

      let ans = cleanAnswer((json.answer || "").trim());
      if (antiHall && src.length === 0) {{
        ans = antiHallFallback(qRaw);
      }}

      answerEl.textContent = ans || "(réponse vide)";

      tick.rag = performance.now() - tStart;
      tRag.textContent = msToStr(tick.rag);

      setBadge(bRAG, "OK");

      // 🔊 TTS complet (concat blob)
      await speakTTSLong(answerEl.textContent);

      tick.total = (t0 ? (performance.now() - t0) : null);
      tTotal.textContent = msToStr(tick.total);

      setStatus("Done ✅", "ok");
    }} catch (err) {{
      answerEl.textContent = "❌ RAG fetch failed: " + err;
      setBadge(bRAG, "ERR");
      setStatus("Error", "err");
    }}
  }}

  btnStart.onclick = start;
  btnStop.onclick  = stop;
  btnSend.onclick  = sendToSTT;
  btnAsk.onclick   = askRAG;
}})();
</script>
"""


def _component_call_mode(lang: str) -> str:
    return f"""
<div style="font-family: system-ui, -apple-system, Segoe UI, Roboto, Arial;
            border:1px solid rgba(148,163,184,.35);
            border-radius:18px; padding:14px;
            background: rgba(255,255,255,0.92);
            box-shadow:0 14px 35px rgba(15,23,42,.08);">

  <style>
    :root{{
      --bd-1:#7f1d1d;
      --bd-2:#991b1b;
      --bd-3:#be123c;
      --ok:#16a34a;
      --run:#be123c;
      --err:#ef4444;
    }}

    .rowtop {{
      display:flex; gap:10px; align-items:center; flex-wrap:wrap;
      padding:10px; border-radius:16px;
      border:1px solid rgba(148,163,184,.35);
      background: #f8fafc;
    }}
    .btn {{
      padding:10px 14px; border-radius:999px; cursor:pointer;
      border:1px solid rgba(148,163,184,.55);
      font-weight:850;
      transition: transform .12s ease, box-shadow .12s ease, opacity .12s ease;
    }}
    .btn:hover {{ transform: translateY(-1px); box-shadow:0 10px 25px rgba(15,23,42,.10); }}
    .btn:disabled {{ opacity:.5; cursor:not-allowed; transform:none; box-shadow:none; }}
    .b-dark {{
      background: linear-gradient(135deg, #0f172a, #111827);
      color:white;
      border-color: rgba(148,163,184,.55);
    }}
    .b-bordeaux {{
      background: linear-gradient(135deg, var(--bd-1), var(--bd-2), var(--bd-3));
      color:white;
      border-color: rgba(190,18,60,.65);
      box-shadow: 0 14px 35px rgba(127,29,29,.20);
    }}
    .b-white {{
      background:#ffffff; color:#0f172a;
      border-color: rgba(148,163,184,.55);
    }}

    .toggle {{
      display:inline-flex; align-items:center; gap:8px;
      padding:8px 10px;
      border-radius:999px;
      border:1px solid rgba(148,163,184,.45);
      background:#ffffff;
      font-size:12px;
      font-weight:900;
      color:#0f172a;
      cursor:pointer;
      user-select:none;
    }}

    .status {{
      margin-left:auto; font-weight:900; font-size:12px; color:#0f172a;
      padding:6px 10px; border-radius:999px; background:#ffffff;
      border:1px solid rgba(148,163,184,.45);
      display:flex; align-items:center; gap:8px;
    }}
    .dot {{
      width:8px; height:8px; border-radius:999px; background:#94a3b8;
      box-shadow:0 0 0 0 rgba(190,18,60,.0);
    }}
    .dot.ok  {{ background: var(--ok); }}
    .dot.run {{
      background: var(--run);
      animation:pulse 1.6s infinite ease-in-out;
      box-shadow:0 0 0 0 rgba(190,18,60,.35);
    }}
    .dot.err {{ background: var(--err); }}
    @keyframes pulse {{
      0%   {{ box-shadow:0 0 0 0 rgba(190,18,60,.40); }}
      70%  {{ box-shadow:0 0 0 10px rgba(190,18,60,0); }}
      100% {{ box-shadow:0 0 0 0 rgba(190,18,60,0); }}
    }}

    .grid {{
      display:grid;
      grid-template-columns: 1fr 1fr;
      gap:12px;
      margin-top:12px;
    }}
    @media (max-width: 900px) {{
      .grid {{ grid-template-columns: 1fr; }}
    }}
    .panel {{
      border-radius:16px;
      border:1px solid rgba(148,163,184,.35);
      background:#ffffff;
      padding:12px;
    }}
    .title {{
      font-weight:950; font-size:13px; color:#0f172a;
      display:flex; align-items:center; gap:8px; margin-bottom:8px;
    }}
    .box {{
      white-space:pre-wrap; line-height:1.45;
      border-radius:14px;
      background:#f8fafc;
      border:1px solid rgba(148,163,184,.25);
      padding:10px;
      min-height:92px;
      color:#0f172a;
      font-size:13px;
    }}
    .mini {{
      font-size:12px; color:#64748b; margin-top:8px;
    }}

    .callbar {{
      display:none;
      margin-left:auto;
      padding:8px 12px; border-radius:999px;
      border:1px solid rgba(190,18,60,.35);
      background: rgba(190,18,60,.08);
      font-weight:950; font-size:12px; color:#0f172a;
      align-items:center;
      gap:8px;
    }}

    .trace {{
      margin-top:12px;
      border-radius:16px;
      border:1px solid rgba(148,163,184,.35);
      background: linear-gradient(135deg, rgba(190,18,60,.08), rgba(199,210,254,.10));
      padding:12px;
    }}
    .trace-row {{
      display:flex; flex-wrap:wrap; gap:8px; margin-top:10px;
    }}
    .step {{
      display:inline-flex; align-items:center; gap:8px;
      padding:8px 10px;
      border-radius:999px;
      border:1px solid rgba(148,163,184,.45);
      background:#ffffff;
      font-size:12px;
      color:#0f172a;
      font-weight:900;
    }}
    .badge {{
      font-size:11px;
      padding:3px 8px;
      border-radius:999px;
      border:1px solid rgba(148,163,184,.35);
      background:#f8fafc;
      font-weight:950;
      color:#0f172a;
    }}
    .badge.ok   {{ background: rgba(22,163,74,.14); border-color: rgba(22,163,74,.35); }}
    .badge.err  {{ background: rgba(239,68,68,.12); border-color: rgba(239,68,68,.35); }}
    .badge.wait {{ background: rgba(190,18,60,.08); border-color: rgba(190,18,60,.25); }}
    .badge.run  {{ background: rgba(190,18,60,.12); border-color: rgba(190,18,60,.35); }}

    .meta {{
      margin-top:8px;
      font-size:12px;
      color:#475569;
      display:flex; flex-wrap:wrap; gap:10px;
    }}
    .chip {{
      border:1px solid rgba(148,163,184,.35);
      background:#ffffff;
      padding:6px 10px;
      border-radius:999px;
      font-weight:800;
    }}

    .chat {{
      background:#ffffff;
      min-height:160px;
      max-height:240px;
      overflow:auto;
    }}
    .hint {{
      margin-top:8px;
      padding:8px 10px;
      border-radius:14px;
      border:1px dashed rgba(148,163,184,.55);
      color:#475569;
      background: rgba(248,250,252,.7);
      font-size:12px;
    }}
  </style>

  <div class="rowtop" style="gap:8px;">
    <label class="toggle">
      <input id="callMode" type="checkbox" style="margin-right:6px;" />
      📞 Mode appel
    </label>

    <button id="btnScenario" class="btn b-white" style="padding:8px 12px;">
      🎬 Scénario support
    </button>

    <label class="toggle">
      <input id="useContext" type="checkbox" checked style="margin-right:6px;" />
      Multi-tours (3)
    </label>

    <label class="toggle" title="L’agent accuse réception et enchaîne naturellement">
      <input id="activeListen" type="checkbox" checked style="margin-right:6px;" />
      Écoute active
    </label>

    <label class="toggle" title="Si pas de sources, réponse prudente + question de précision">
      <input id="antiHall" type="checkbox" checked style="margin-right:6px;" />
      🛡️ Anti-hallucination
    </label>

    <button id="btnResetCtx" class="btn b-white" style="padding:8px 12px;">
      ♻️ Reset
    </button>

    <div id="callBar" class="callbar">
      📞 <span id="callTimer">00:00</span> • <span id="callState">Idle</span>
    </div>
  </div>

  <div class="hint">
    Astuce: parle en 1 phrase, puis “Transcrire” → “Interroger”. Le TTS lit toute la réponse, même longue.
  </div>

  <!-- 🎛️ VU Meter -->
  <div style="margin-top:10px; display:flex; align-items:center; gap:10px;">
    <div style="font-weight:900; font-size:12px;">VU</div>
    <div style="flex:1; height:10px; background:#e2e8f0; border-radius:999px; overflow:hidden;">
      <div id="vuBar" style="width:0%; height:100%; background:linear-gradient(90deg,#16a34a,#f59e0b,#ef4444);"></div>
    </div>
    <div id="vuTxt" style="font-weight:900; font-size:12px; width:110px; text-align:right;">RMS=0.0000</div>
  </div>

  <div class="rowtop" style="margin-top:10px;">
    <button id="btnStart" class="btn b-dark">🎤 Start</button>
    <button id="btnStop"  class="btn b-white">⏹ Stop</button>
    <button id="btnSend"  class="btn b-bordeaux">🧪 Transcrire</button>
    <button id="btnAsk"   class="btn b-bordeaux">💬 Interroger</button>

    <div class="status">
      <div id="dot" class="dot"></div>
      <span id="status">Idle</span>
    </div>
  </div>

  <div style="margin-top:10px;">
    <div class="title">🎧 Pré-écoute (micro)</div>
    <audio id="player" controls style="width:100%;"></audio>
  </div>

  <div class="grid">
    <div class="panel">
      <div class="title">🗣️ Conversation (appel)</div>
      <div id="chat" class="box chat"><div style="color:#94a3b8;">(Conversation vide)</div></div>
      <div class="mini" id="ctxHint">Contexte actif: 0 tour</div>
    </div>

    <div class="panel">
      <div class="title">📝 Transcription (STT)</div>
      <div id="transcript" class="box">(vide)</div>
      <div class="mini">Endpoint : <code>{API_BASE}/stt/transcribe?lang={lang}</code></div>

      <div style="margin-top:10px;">
        <div class="title">🤖 Réponse + 🔊 TTS</div>
        <div id="answer" class="box">(vide)</div>
        <div id="sources" class="mini">Sources: —</div>
        <audio id="ttsPlayer" controls style="width:100%; margin-top:10px;"></audio>
      </div>
    </div>
  </div>

  <div class="trace">
    <div class="title">🧾 Trace d’exécution</div>
    <div class="trace-row">
      <div class="step">🎤 Record <span class="badge wait" id="bRecord">WAIT</span></div>
      <div class="step">🧪 STT <span class="badge wait" id="bSTT">WAIT</span></div>
      <div class="step">💬 RAG <span class="badge wait" id="bRAG">WAIT</span></div>
      <div class="step">🔊 TTS <span class="badge wait" id="bTTS">WAIT</span></div>
    </div>
    <div class="meta">
      <div class="chip">⏱ total: <b id="tTotal">—</b></div>
      <div class="chip">🧪 stt: <b id="tStt">—</b></div>
      <div class="chip">💬 rag: <b id="tRag">—</b></div>
      <div class="chip">🔊 tts: <b id="tTts">—</b></div>
    </div>
  </div>

</div>

<script>
(function() {{
  const btnStart = document.getElementById("btnStart");
  const btnStop  = document.getElementById("btnStop");
  const btnSend  = document.getElementById("btnSend");
  const btnAsk   = document.getElementById("btnAsk");

  const statusEl = document.getElementById("status");
  const dotEl    = document.getElementById("dot");

  const player    = document.getElementById("player");
  const ttsPlayer = document.getElementById("ttsPlayer");

  const transcriptEl = document.getElementById("transcript");
  const answerEl     = document.getElementById("answer");
  const sourcesEl    = document.getElementById("sources");

  const bRecord = document.getElementById("bRecord");
  const bSTT    = document.getElementById("bSTT");
  const bRAG    = document.getElementById("bRAG");
  const bTTS    = document.getElementById("bTTS");

  const tTotal = document.getElementById("tTotal");
  const tStt   = document.getElementById("tStt");
  const tRag   = document.getElementById("tRag");
  const tTts   = document.getElementById("tTts");

  const chatEl = document.getElementById("chat");
  const useContextEl = document.getElementById("useContext");
  const activeListenEl = document.getElementById("activeListen");
  const antiHallEl = document.getElementById("antiHall");
  const btnResetCtx = document.getElementById("btnResetCtx");
  const ctxHintEl = document.getElementById("ctxHint");

  const callModeEl = document.getElementById("callMode");
  const btnScenario = document.getElementById("btnScenario");
  const callBar = document.getElementById("callBar");
  const callTimerEl = document.getElementById("callTimer");
  const callStateEl = document.getElementById("callState");

  const vuBar = document.getElementById("vuBar");
  const vuTxt = document.getElementById("vuTxt");

  let mediaRecorder = null;
  let chunks = [];
  let stream = null;
  let lastBlob = null;

  let lastObjectUrl = null;
  let t0 = null;
  let tick = {{ stt: null, rag: null, tts: null, total: null }};

  // VU-meter state
  let audioCtx = null;
  let analyser = null;
  let data = null;
  let vuTimer = null;

  let callOn = false;
  let callStartedAt = null;
  let callTimer = null;

  let HISTORY = [];
  const MAX_TURNS = 3;

  function msToStr(ms) {{
    if (ms === null || ms === undefined) return "—";
    const v = Math.max(0, Math.round(ms));
    return v < 1000 ? (v + "ms") : ((v/1000).toFixed(2) + "s");
  }}

  function setStatus(s, mode) {{
    statusEl.textContent = s;
    dotEl.className = "dot";
    if (mode === "run") dotEl.classList.add("run");
    if (mode === "ok")  dotEl.classList.add("ok");
    if (mode === "err") dotEl.classList.add("err");
  }}

  function setBadge(el, state) {{
    el.textContent = state;
    el.className = "badge";
    if (state === "OK")   el.classList.add("ok");
    if (state === "ERR")  el.classList.add("err");
    if (state === "WAIT") el.classList.add("wait");
    if (state === "RUN")  el.classList.add("run");
  }}

  function resetTrace() {{
    setBadge(bRecord, "WAIT");
    setBadge(bSTT, "WAIT");
    setBadge(bRAG, "WAIT");
    setBadge(bTTS, "WAIT");
    tick = {{ stt: null, rag: null, tts: null, total: null }};
    tTotal.textContent = "—";
    tStt.textContent = "—";
    tRag.textContent = "—";
    tTts.textContent = "—";
  }}

  function safeText(s) {{
    return (s || "").toString().replace(/\\s+/g, " ").trim();
  }}

  function esc(s) {{
    return (s || "").toString()
      .replaceAll("&", "&amp;")
      .replaceAll("<", "&lt;")
      .replaceAll(">", "&gt;");
  }}

  function cleanAnswer(text) {{
    let t = (text || "").toString();
    t = t.replace(/\\r/g, "");
    t = t.replace(/\\n{{3,}}/g, "\\n\\n").trim();

    const parts = t.split(/(?<=[\\.!\\?])\\s+/).map(x => x.trim()).filter(Boolean);
    const seen = new Set();
    const out = [];
    for (const p of parts) {{
      const key = p.toLowerCase().replace(/[^a-z0-9àâçéèêëîïôùûüÿñæœ\\s]/gi, "").replace(/\\s+/g, " ").trim();
      if (!key) continue;
      if (seen.has(key)) continue;
      seen.add(key);
      out.push(p);
    }}
    t = out.join(" ").trim();

    const maxChars = 2200;
    if (t.length > maxChars) t = t.slice(0, maxChars).trim() + "…";
    return t;
  }}

  function antiHallFallback(originalQ) {{
    const q = (originalQ || "").trim();
    if (!q) return "Je n’ai pas assez d’éléments pour répondre avec certitude. Tu peux préciser ta question ?";
    return "Je n’ai pas trouvé d’éléments fiables dans ma base pour répondre avec certitude. " +
           "Tu peux préciser (ex: le point exact, ou le document concerné) ?";
  }}

  // ----------------------------
  // 🎛️ VU-meter
  // ----------------------------
  function startVu(s) {{
    if (!vuBar || !vuTxt) return;
    try {{
      audioCtx = new (window.AudioContext || window.webkitAudioContext)();
      const src = audioCtx.createMediaStreamSource(s);
      analyser = audioCtx.createAnalyser();
      analyser.fftSize = 2048;
      data = new Float32Array(analyser.fftSize);
      src.connect(analyser);

      if (vuTimer) clearInterval(vuTimer);
      vuTimer = setInterval(() => {{
        analyser.getFloatTimeDomainData(data);
        let sum = 0;
        for (let i = 0; i < data.length; i++) sum += data[i] * data[i];
        const rms = Math.sqrt(sum / data.length);
        const pct = Math.min(100, Math.max(0, rms * 220));
        vuBar.style.width = pct + "%";
        vuTxt.textContent = "RMS=" + rms.toFixed(4);
      }}, 80);
    }} catch (e) {{}}
  }}

  function stopVu() {{
    if (vuTimer) clearInterval(vuTimer);
    vuTimer = null;
    try {{ if (audioCtx) audioCtx.close(); }} catch(e) {{}}
    audioCtx = null; analyser = null; data = null;
    if (vuBar) vuBar.style.width = "0%";
    if (vuTxt) vuTxt.textContent = "RMS=0.0000";
  }}

  // ----------------------------
  // 🔊 TTS: split => multi-call => concat mp3 => 1 Blob
  // ----------------------------
  function splitForTts(text, maxLen) {{
    const t = (text || "").toString().trim();
    if (!t) return [];
    const maxL = Math.max(80, maxLen || 140);

    const sentences = t
      .replace(/\\s+/g, " ")
      .split(/(?<=[\\.!\\?])\\s+/)
      .map(x => x.trim())
      .filter(Boolean);

    const chunks = [];
    let cur = "";
    for (const s of sentences) {{
      if (!cur) {{ cur = s; continue; }}
      if ((cur.length + 1 + s.length) <= maxL) cur += " " + s;
      else {{ chunks.push(cur); cur = s; }}
    }}
    if (cur) chunks.push(cur);

    const final = [];
    for (const c of chunks) {{
      if (c.length <= maxL) final.push(c);
      else for (let i=0;i<c.length;i+=maxL) final.push(c.slice(i,i+maxL));
    }}
    return final.filter(Boolean);
  }}

  function b64ToBytes(b64) {{
    const bin = atob(b64);
    const arr = new Uint8Array(bin.length);
    for (let i = 0; i < bin.length; i++) arr[i] = bin.charCodeAt(i);
    return arr;
  }}

  async function ttsSynthesizeB64(text) {{
    const url = "{API_BASE}/tts/synthesize";
    const resp = await fetch(url, {{
      method: "POST",
      headers: {{ "Content-Type": "application/json" }},
      body: JSON.stringify({{ text: text, lang: "{lang}" }})
    }});
    const body = await resp.text();
    if (!resp.ok) throw new Error(body || "TTS error");
    const json = JSON.parse(body);
    const b64 = (json.audio_base64 || "").trim();
    if (!b64) throw new Error("Empty audio");
    return b64;
  }}

  async function speakTTSLong(text) {{
    const t = (text || "").toString().trim();
    if (!t || t === "(vide)" || t === "(réponse vide)") return;

    setBadge(bTTS, "RUN");
    setStatus("TTS…", "run");
    if (callOn) callUi(true, "Speaking");

    const tStart = performance.now();

    const parts = splitForTts(t, 140);
    const byteParts = [];
    for (const part of parts) {{
      const b64 = await ttsSynthesizeB64(part);
      byteParts.push(b64ToBytes(b64));
    }}

    let totalLen = 0;
    for (const a of byteParts) totalLen += a.length;
    const merged = new Uint8Array(totalLen);
    let off = 0;
    for (const a of byteParts) {{ merged.set(a, off); off += a.length; }}

    const blob = new Blob([merged], {{ type: "audio/mpeg" }});
    const url = URL.createObjectURL(blob);

    try {{ ttsPlayer.pause(); ttsPlayer.currentTime = 0; }} catch(e) {{}}
    ttsPlayer.src = url;

    try {{ await ttsPlayer.play(); }} catch(e) {{}}

    tick.tts = performance.now() - tStart;
    tTts.textContent = msToStr(tick.tts);

    setBadge(bTTS, "OK");
    setStatus("Done ✅", "ok");
    if (callOn) callUi(true, "Connected");
  }}

  // ----------------------------
  // Call mode UI + Memory
  // ----------------------------
  function renderChat() {{
    if (!chatEl) return;

    if (!HISTORY.length) {{
      chatEl.innerHTML = '<div style="color:#94a3b8;">(Conversation vide)</div>';
      if (ctxHintEl) ctxHintEl.textContent = "Contexte actif: 0 tour";
      return;
    }}

    let html = "";
    for (const m of HISTORY) {{
      const isUser = m.role === "user";
      html += `
        <div style="display:flex; justify-content:${{isUser ? "flex-end" : "flex-start"}}; margin:6px 0;">
          <div style="
            max-width:92%;
            padding:8px 10px;
            border-radius:14px;
            border:1px solid ${{isUser ? "rgba(190,18,60,0.35)" : "rgba(148,163,184,.35)"}};
            background:${{isUser ? "rgba(190,18,60,0.12)" : "#f8fafc"}};
            color:#0f172a;
            font-size:13px;
            line-height:1.35;">
            <div style="font-weight:950; font-size:11px; opacity:.7; margin-bottom:4px;">
              ${{isUser ? "YOU" : "COPILOT"}}
            </div>
            <div>${{esc(m.text)}}</div>
          </div>
        </div>
      `;
    }}

    chatEl.innerHTML = html;
    chatEl.scrollTop = chatEl.scrollHeight;

    const turns = HISTORY.filter(x => x.role === "assistant").length;
    if (ctxHintEl) ctxHintEl.textContent = `Contexte actif: ${{turns}} tour(s)`;
  }}

  function pushHistory(role, text) {{
    const t = (text || "").toString().trim();
    if (!t) return;
    HISTORY.push({{ role, text: t }});

    const maxMsgs = MAX_TURNS * 2;
    if (HISTORY.length > maxMsgs) HISTORY = HISTORY.slice(HISTORY.length - maxMsgs);
    renderChat();
  }}

  function resetHistory() {{
    HISTORY = [];
    renderChat();
  }}

  function fmtMMSS(ms) {{
    const s = Math.max(0, Math.floor(ms / 1000));
    const mm = String(Math.floor(s / 60)).padStart(2, "0");
    const ss = String(s % 60).padStart(2, "0");
    return `${{mm}}:${{ss}}`;
  }}

  function callUi(show, state) {{
    if (!callBar) return;
    callBar.style.display = show ? "inline-flex" : "none";
    if (callStateEl) callStateEl.textContent = state || "Idle";
  }}

  function startCall() {{
    callOn = true;
    callStartedAt = performance.now();
    callUi(true, "Connected");
    if (callTimer) clearInterval(callTimer);
    callTimer = setInterval(() => {{
      if (callTimerEl && callStartedAt) callTimerEl.textContent = fmtMMSS(performance.now() - callStartedAt);
    }}, 250);
  }}

  function stopCall() {{
    callOn = false;
    callStartedAt = null;
    callUi(false, "Idle");
    if (callTimer) clearInterval(callTimer);
    callTimer = null;
  }}

  if (btnResetCtx) {{
    btnResetCtx.onclick = () => {{
      resetTrace();
      resetHistory();
      setStatus("Context reset", "ok");
      if (callOn) callUi(true, "Connected");
    }};
  }}

  if (callModeEl) {{
    callModeEl.onchange = () => {{
      if (callModeEl.checked) {{
        startCall();
        resetHistory();
        pushHistory("assistant", "Bonjour, vous êtes en ligne avec le support StormCopilot. Je vous écoute.");
      }} else {{
        stopCall();
      }}
    }};
  }}

  if (btnScenario) {{
    btnScenario.onclick = () => {{
      if (!callModeEl || !callModeEl.checked) {{
        alert("Active d’abord le mode 📞 appel.");
        return;
      }}
      resetHistory();
      pushHistory("assistant", "Bonjour, support StormCopilot à l’appareil. Je vous écoute.");
      pushHistory("assistant", "Contexte: appel au sujet d’IT STORM (consulting / portage salarial).");
      pushHistory("assistant", "Dites-moi votre question en une phrase, je vous réponds avec des éléments documentés.");
    }};
  }}

  // ----------------------------
  // Record / STT / RAG
  // ----------------------------
  async function start() {{
    chunks = [];
    lastBlob = null;

    transcriptEl.textContent = "(vide)";
    answerEl.textContent = "(vide)";
    sourcesEl.textContent = "Sources: —";
    try {{ ttsPlayer.pause(); ttsPlayer.src = ""; }} catch(e) {{}}

    resetTrace();
    setBadge(bRecord, "RUN");
    setStatus("Recording…", "run");
    if (callOn) callUi(true, "Recording");

    try {{
      stream = await navigator.mediaDevices.getUserMedia({{
        audio: {{
          echoCancellation: true,
          noiseSuppression: true,
          autoGainControl: true,
          channelCount: 1,
          sampleRate: 48000
        }}
      }});

      startVu(stream);

      mediaRecorder = new MediaRecorder(stream, {{ mimeType: "audio/webm" }});

      mediaRecorder.ondataavailable = (e) => {{
        if (e.data && e.data.size > 0) chunks.push(e.data);
      }};

      mediaRecorder.onstop = () => {{
        lastBlob = new Blob(chunks, {{ type: "audio/webm" }});

        if (lastObjectUrl) {{
          try {{ URL.revokeObjectURL(lastObjectUrl); }} catch(e) {{}}
        }}
        lastObjectUrl = URL.createObjectURL(lastBlob);
        player.src = lastObjectUrl;

        setBadge(bRecord, "OK");
        setStatus("Stopped", "ok");
        if (callOn) callUi(true, "Connected");
      }};

      t0 = performance.now();
      mediaRecorder.start();
    }} catch (err) {{
      setBadge(bRecord, "ERR");
      setStatus("Mic error", "err");
      if (callOn) callUi(true, "Mic error");
      alert("Micro refusé. Autorise le micro dans Chrome.");
    }}
  }}

  function stop() {{
    try {{
      if (mediaRecorder && mediaRecorder.state !== "inactive") mediaRecorder.stop();
      if (stream) stream.getTracks().forEach(t => t.stop());
    }} catch(e) {{}}
    stopVu();
    if (callOn) callUi(true, "Connected");
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

    setBadge(bSTT, "RUN");
    setStatus("STT…", "run");
    transcriptEl.textContent = "(transcription en cours.)";
    if (callOn) callUi(true, "Transcribing");

    const url = "{API_BASE}/stt/transcribe?lang={lang}";
    const tStart = performance.now();

    try {{
      const form = new FormData();
      form.append("file", lastBlob, "mic.webm");

      const resp = await fetch(url, {{ method: "POST", body: form }});
      const body = await resp.text();

      if (!resp.ok) {{
        transcriptEl.textContent = "❌ STT error: " + body;
        setBadge(bSTT, "ERR");
        setStatus("Error", "err");
        if (callOn) callUi(true, "STT error");
        return;
      }}

      const json = JSON.parse(body);
      const text = safeText(json.text || "");
      transcriptEl.textContent = text || "(texte vide)";

      tick.stt = performance.now() - tStart;
      tStt.textContent = msToStr(tick.stt);

      setBadge(bSTT, "OK");
      setStatus("STT done", "ok");
      if (callOn) callUi(true, "Connected");
    }} catch (err) {{
      transcriptEl.textContent = "❌ STT fetch failed: " + err;
      setBadge(bSTT, "ERR");
      setStatus("Error", "err");
      if (callOn) callUi(true, "STT error");
    }}
  }}

  function buildCallPrompt(q, ctxText, useCtx, activeListen, antiHall) {{
    const rules = [
      "Tu es un agent vocal en conversation téléphonique (ton naturel).",
      "Réponds comme un humain à l’oral.",
      "Une seule réponse claire et utile.",
      "Pas de répétition, pas de blabla.",
      "Phrases courtes. Maximum 6 phrases.",
      "Si la question est ambiguë, pose UNE question courte de clarification.",
    ];
    if (antiHall) rules.push("Anti-hallucination : si tu n’es pas sûr, dis-le clairement. Ne devine pas.");
    const listen = activeListen
      ? "Écoute active: commence par une courte phrase de réception puis répond."
      : "Écoute active: désactivée.";

    let prompt = rules.join("\\n") + "\\n\\n" + listen + "\\n";
    if (useCtx && ctxText) prompt += "\\nHistorique récent :\\n" + ctxText + "\\n";
    prompt += "\\nUtilisateur :\\n" + q;
    return prompt;
  }}

  async function askRAG() {{
    const q = (transcriptEl.textContent || "").trim();
    if (!q || q === "(vide)" || q.includes("transcription en cours")) {{
      alert("D’abord fais la transcription STT.");
      return;
    }}

    setBadge(bRAG, "RUN");
    setStatus("RAG…", "run");
    if (callOn) callUi(true, "Answering");

    answerEl.textContent = "(RAG en cours.)";
    sourcesEl.textContent = "Sources: —";
    try {{ ttsPlayer.pause(); ttsPlayer.src = ""; }} catch(e) {{}}

    const url = "{API_BASE}/rag/ask";
    const tStart = performance.now();

    const useCtx = useContextEl ? !!useContextEl.checked : true;
    const activeListen = activeListenEl ? !!activeListenEl.checked : true;
    const antiHall = antiHallEl ? !!antiHallEl.checked : true;

    let ctxText = "";
    if (useCtx && HISTORY.length) {{
      ctxText = HISTORY.map(m => (m.role === "user" ? "User: " : "Assistant: ") + m.text).join("\\n");
    }}

    const enriched = buildCallPrompt(q, ctxText, useCtx, activeListen, antiHall);

    try {{
      const resp = await fetch(url, {{
        method: "POST",
        headers: {{ "Content-Type": "application/json" }},
        body: JSON.stringify({{ question: enriched }})
      }});

      const body = await resp.text();
      if (!resp.ok) {{
        answerEl.textContent = "❌ RAG error: " + body;
        setBadge(bRAG, "ERR");
        setStatus("Error", "err");
        if (callOn) callUi(true, "RAG error");
        return;
      }}

      const json = JSON.parse(body);
      const src = Array.isArray(json.sources) ? json.sources : [];
      sourcesEl.textContent = src.length ? ("Sources: " + src.join(" | ")) : "Sources: —";

      let ans = cleanAnswer((json.answer || "").trim());
      if (antiHall && src.length === 0) ans = antiHallFallback(q);

      answerEl.textContent = ans || "(réponse vide)";

      tick.rag = performance.now() - tStart;
      tRag.textContent = msToStr(tick.rag);

      setBadge(bRAG, "OK");

      // Memory (call-mode)
      if (callOn) {{
        pushHistory("user", q);
        pushHistory("assistant", ans);
      }}

      await speakTTSLong(answerEl.textContent);

      tick.total = (t0 ? (performance.now() - t0) : null);
      tTotal.textContent = msToStr(tick.total);

      setStatus("Done ✅", "ok");
      if (callOn) callUi(true, "Connected");
    }} catch (err) {{
      answerEl.textContent = "❌ RAG fetch failed: " + err;
      setBadge(bRAG, "ERR");
      setStatus("Error", "err");
      if (callOn) callUi(true, "RAG error");
    }}
  }}

  btnStart.onclick = start;
  btnStop.onclick  = stop;
  btnSend.onclick  = sendToSTT;
  btnAsk.onclick   = askRAG;

  renderChat();
}})();
</script>
"""


def render_stt_only() -> None:
    _inject_page_css()

    st.markdown(
        """
<div class="vc-hero">
  <div class="vc-title">Voice Copilot</div>
  <div class="vc-sub">
    Démo PFE stable : tu parles → transcription (Whisper) → question RAG → réponse documentée + lecture audio.
  </div>

  <div class="vc-pills">
    <div class="vc-pill">🎛️ VU-mètre RMS</div>
    <div class="vc-pill">🛡️ Anti-hallucination</div>
    <div class="vc-pill">🔊 TTS complet (concat blob)</div>
    <div class="vc-pill">🎙 Micro navigateur</div>
    <div class="vc-pill">🧪 STT</div>
    <div class="vc-pill">💬 RAG</div>
    <div class="vc-pill">📞 Call-mode</div>
  </div>
</div>
""",
        unsafe_allow_html=True,
    )
    st.markdown("")

    (tab_live,) = st.tabs(["🎙 Live"])

    with tab_live:
        sub1, sub2 = st.tabs(["✅ Question unique", "📞 Appel téléphonique"])

        with sub1:
            lang = st.selectbox("Langue STT/TTS", ["fr", "en"], index=0, key="vc_lang_single")
            components.html(_component_single_question(lang), height=950, scrolling=False)

        with sub2:
            lang = st.selectbox("Langue STT/TTS", ["fr", "en"], index=0, key="vc_lang_call")
            components.html(_component_call_mode(lang), height=1120, scrolling=False)
