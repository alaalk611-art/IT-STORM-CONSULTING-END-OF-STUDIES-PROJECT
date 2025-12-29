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
/* ================================
   Voice Copilot – UI polish (blue)
   ================================ */

/* Hero */
.vc-hero{
  text-align:center;
  padding:1.2rem 1.4rem;
  border-radius:22px;
  background: linear-gradient(
    135deg,
    #f0f9ff,   /* sky-50 */
    #e0f2fe    /* sky-100 */
  );
  border:1px solid #bae6fd;
  box-shadow:0 14px 35px rgba(14,165,233,.18);
  margin-bottom: 0.6rem;
}

.vc-title{
  font-size:1.25rem;
  font-weight:850;
  letter-spacing:.02em;
  background:linear-gradient(
    120deg,
    #0f172a,   /* slate-900 */
    #0369a1    /* sky-700 */
  );
  -webkit-background-clip:text;
  color:transparent;
  margin:0;
}

.vc-sub{
  color:#334155;            /* slate-700 */
  margin:.45rem auto 0 auto;
  font-size:.95rem;
  line-height:1.35;
  max-width:920px;
  opacity:.95;
}

/* Pills (si jamais réutilisées plus tard) */
.vc-pills{
  margin-top:.55rem;
  display:flex;
  flex-wrap:wrap;
  gap:.45rem;
  justify-content:center;
}

.vc-pill{
  display:inline-flex;
  align-items:center;
  gap:.4rem;
  padding:.22rem .7rem;
  border-radius:999px;
  font-size:.74rem;
  background:#f0f9ff;
  border:1px solid #bae6fd;
  color:#0369a1;
}

/* Tabs (Question unique / Appel téléphonique) */
.stTabs [data-baseweb="tab-list"]{
  justify-content:center;
  gap:.5rem;
  margin-bottom: 0.8rem;

}

.stTabs [data-baseweb="tab"]{
  border-radius:999px !important;
  padding:0.35rem 1.0rem !important;
  font-weight:750 !important;
  font-size:.9rem !important;
  background:#f8fafc !important;
  color:#64748b !important;
  border:1px solid #e2e8f0 !important;
  
}

.stTabs [aria-selected="true"]{
  background: linear-gradient(135deg, #38bdf8, #0ea5e9) !important;
  color: white !important;
  border:none !important;
  box-shadow: 0 10px 30px rgba(56,189,248,0.35);
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

    const url = "{API_BASE}/rag/hybrid";
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
<div style="font-family: system-ui, -apple-system, Segoe UI, Roboto, Arial;">
  <style>
    :root{{
      --bg:#0b1220;
      --panel:rgba(255,255,255,.06);
      --stroke:rgba(148,163,184,.22);
      --text:#e5e7eb;
      --muted:#94a3b8;
      --ok:#22c55e;
      --err:#ef4444;
      --accent1:#7f1d1d;
      --accent2:#be123c;
      --glass:rgba(255,255,255,.07);
    }}

    .wrap {{
      border:1px solid var(--stroke);
      border-radius:22px;
      padding:14px;
      background:
        radial-gradient(circle at 15% 0%, rgba(190,18,60,.18), transparent 55%),
        radial-gradient(circle at 85% 10%, rgba(59,130,246,.12), transparent 55%),
        linear-gradient(180deg, rgba(2,6,23,.92), rgba(2,6,23,.88));
      box-shadow: 0 28px 80px rgba(2,6,23,.55);
      color: var(--text);
      overflow:hidden;
    }}

    .call-header {{
      display:flex; align-items:center; justify-content:space-between; gap:12px;
      padding:14px; border-radius:18px;
      border:1px solid var(--stroke); background: var(--glass);
      backdrop-filter: blur(10px);
    }}
    .callee {{ display:flex; align-items:center; gap:12px; }}
    .avatar {{
      width:44px; height:44px; border-radius:16px;
      background: linear-gradient(135deg, rgba(190,18,60,.95), rgba(15,23,42,.95));
      border:1px solid rgba(190,18,60,.35);
      box-shadow:0 14px 35px rgba(190,18,60,.18);
      display:flex; align-items:center; justify-content:center;
      font-weight:950;
      letter-spacing:.02em;
    }}
    .callee-meta {{ display:flex; flex-direction:column; gap:2px; }}
    .callee-name {{ font-weight:950; font-size:14px; letter-spacing:.02em; }}
    .callee-sub {{ font-size:12px; color: var(--muted); display:flex; gap:10px; flex-wrap:wrap; }}

    .chip {{
      display:inline-flex; align-items:center; gap:8px;
      padding:6px 10px; border-radius:999px;
      border:1px solid var(--stroke);
      background: rgba(255,255,255,.06);
      font-size:12px; font-weight:850; color: var(--text);
      user-select:none;
      white-space:nowrap;
    }}
    .dot {{ width:8px; height:8px; border-radius:999px; background:#64748b; }}
    .dot.live {{
      background: var(--ok);
      box-shadow: 0 0 0 0 rgba(34,197,94,.35);
      animation: pulse 1.6s infinite ease-in-out;
    }}
    @keyframes pulse {{
      0% {{ box-shadow:0 0 0 0 rgba(34,197,94,.35); }}
      70% {{ box-shadow:0 0 0 10px rgba(34,197,94,0); }}
      100% {{ box-shadow:0 0 0 0 rgba(34,197,94,0); }}
    }}

    .controls {{ display:flex; align-items:center; gap:10px; flex-wrap:wrap; justify-content:flex-end; }}
    .btn {{
      padding:10px 14px; border-radius:999px;
      cursor:pointer;
      border:1px solid var(--stroke);
      background: rgba(255,255,255,.06);
      color: var(--text);
      font-weight:950;
      transition: transform .12s ease, box-shadow .12s ease, opacity .12s ease;
    }}
    .btn:hover {{ transform: translateY(-1px); box-shadow:0 14px 35px rgba(2,6,23,.35); }}
    .btn-danger {{
      background: linear-gradient(135deg, rgba(239,68,68,.95), rgba(127,29,29,.95));
      border-color: rgba(239,68,68,.35);
      box-shadow: 0 14px 35px rgba(239,68,68,.16);
    }}

    .vu-wrap {{
      margin-top:12px; display:flex; align-items:center; gap:10px;
      padding:10px 12px; border-radius:16px;
      border:1px solid var(--stroke);
      background: rgba(255,255,255,.04);
    }}
    .vu-bar {{
      flex:1; height:10px; background: rgba(148,163,184,.18);
      border-radius:999px; overflow:hidden;
    }}
    .vu-fill {{
      width:0%; height:100%;
      background: linear-gradient(90deg,#22c55e,#f59e0b,#ef4444);
    }}
    .vu-txt {{
      font-weight:950; font-size:12px; width:170px; text-align:right;
      color: var(--text);
    }}

    .grid {{ display:grid; grid-template-columns: 1fr; gap:14px; margin-top:14px; }}
    .card {{
      border-radius:18px; border:1px solid var(--stroke);
      background: rgba(255,255,255,.05);
      padding:12px; backdrop-filter: blur(10px);
    }}
    .card-title {{
      display:flex; align-items:center; justify-content:space-between;
      gap:10px; font-weight:950; font-size:13px; margin-bottom:10px;
    }}

    .chat {{
      height: 420px; overflow:auto; padding:10px;
      border-radius:16px;
      border:1px solid rgba(148,163,184,.18);
      background: rgba(2,6,23,.35);
    }}
    .bubble-row {{ display:flex; margin:10px 0; }}
    .bubble {{
      max-width: 92%;
      padding:10px 12px;
      border-radius:16px;
      border:1px solid rgba(148,163,184,.22);
      background: rgba(255,255,255,.06);
      color: var(--text);
      line-height:1.35;
      font-size:13px;
      box-shadow:0 14px 35px rgba(2,6,23,.25);
    }}
    .bubble.you {{
      margin-left:auto;
      border-color: rgba(190,18,60,.30);
      background: rgba(190,18,60,.10);
    }}
    .bubble .who {{
      font-size:11px; font-weight:950; opacity:.75; margin-bottom:6px;
      letter-spacing:.02em;
    }}

    .mini {{
      margin-top:10px;
      color: var(--muted);
      font-size:12px;
      display:flex;
      gap:10px;
      flex-wrap:wrap;
      align-items:center;
      justify-content:space-between;
    }}
    .audio {{
      width:100%; margin-top:10px;
      filter: invert(0.92) hue-rotate(180deg) saturate(1.0);
      border-radius:14px;
    }}

    .hidden {{ display:none !important; }}
  </style>

  <div class="wrap">
    <div class="call-header">
      <div class="callee">
        <div class="avatar">IT</div>
        <div class="callee-meta">
          <div class="callee-name">Service client IT-STORM · StormCopilot</div>
          <div class="callee-sub">
            <span class="chip"><span class="dot" id="liveDot"></span> <span id="callState">Boot</span></span>
            <span class="chip">⏱ <span id="callTimer">00:00</span></span>
            <span class="chip">🎙 <span id="micState">Init</span></span>
          </div>
        </div>
      </div>

      <div class="controls">
        <button id="btnHang" class="btn btn-danger">📴 Raccrocher</button>
      </div>
    </div>

    <div class="vu-wrap">
      <div style="font-weight:950; font-size:12px;">VU</div>
      <div class="vu-bar"><div id="vuBar" class="vu-fill"></div></div>
      <div id="vuTxt" class="vu-txt">RMS=0.0000</div>
    </div>

    <div class="grid">
      <div class="card">
        <div class="card-title">
          <span>📞 Appel en cours</span>
          <span id="ctxHint" style="color:var(--muted); font-size:12px; font-weight:850;">Contexte: 0 tour</span>
        </div>

        <div id="chat" class="chat"></div>

        <div class="mini">
          <span>Parlez normalement. Le système transcrit et répond automatiquement.</span>
          <span style="opacity:.9;">Mode IA (écoute → STT → RAG → TTS)</span>
        </div>

        <audio id="player" class="audio" controls></audio>
        <audio id="ttsPlayer" class="audio" controls></audio>

        <div class="hidden">
          <div id="transcript"></div>
          <div id="answer"></div>
          <div id="sources"></div>
        </div>
      </div>
    </div>
  </div>
</div>

<script>
(function() {{
  const autoModeEl = {{ checked: true }};
  const useContextEl = {{ checked: true }};
  const antiHallEl = {{ checked: true }};

  const btnHang = document.getElementById("btnHang");

  const liveDot = document.getElementById("liveDot");
  const callStateEl = document.getElementById("callState");
  const callTimerEl = document.getElementById("callTimer");
  const micStateEl  = document.getElementById("micState");

  const chatEl = document.getElementById("chat");
  const ctxHintEl = document.getElementById("ctxHint");

  const transcriptEl = document.getElementById("transcript");
  const answerEl     = document.getElementById("answer");
  const sourcesEl    = document.getElementById("sources");

  const player    = document.getElementById("player");
  const ttsPlayer = document.getElementById("ttsPlayer");

  const vuBar = document.getElementById("vuBar");
  const vuTxt = document.getElementById("vuTxt");

  // --- state
  let callOn = true;
  let callStartedAt = performance.now();
  let callTimer = null;

  let mediaRecorder = null;
  let stream = null;
  let chunks = [];
  let lastBlob = null;
  let lastObjectUrl = null;

  let audioCtx = null;
  let analyser = null;
  let data = null;
  let vuTimer = null;

  let HISTORY = [];
  const MAX_TURNS = 3;

  let isBusy = false;
  let isSpeaking = false;
  let silenceCount = 0;
  let recStartedAt = 0;

  let cooldownUntil = 0;
  let lastAssistantMsg = "";
  let hasSpeech = false;

  // ✅ adaptive thresholds (will be tuned from noise floor)
  let RMS_START_THRESHOLD = 0.010;
  let RMS_SILENCE_THRESHOLD = 0.006;
  const SILENCE_MS_TO_STOP = 900;
  const MIN_RECORD_MS = 900;

  // ✅ noise floor calibration
  let noiseFloor = 0.002;
  let calibrated = false;

  function updateThresholdsFromNoise(rms) {{
    noiseFloor = 0.92 * noiseFloor + 0.08 * rms;
    RMS_SILENCE_THRESHOLD = Math.max(0.004, noiseFloor * 1.6);
    RMS_START_THRESHOLD   = Math.max(0.008, noiseFloor * 2.6);
  }}

  function esc(s) {{
    return (s || "").toString().replaceAll("&","&amp;").replaceAll("<","&lt;").replaceAll(">","&gt;");
  }}
  function fmtMMSS(ms) {{
    const s = Math.max(0, Math.floor(ms/1000));
    const mm = String(Math.floor(s/60)).padStart(2,"0");
    const ss = String(s%60).padStart(2,"0");
    return `${{mm}}:${{ss}}`;
  }}
  function callUi(state) {{
    callStateEl.textContent = state;
    liveDot.className = "dot" + (callOn ? " live" : "");
  }}
  function pushHistory(role, text) {{
    const t = (text || "").toString().trim();
    if (!t) return;

    HISTORY.push({{role, text:t}});
    const maxMsgs = MAX_TURNS * 2;
    if (HISTORY.length > maxMsgs) HISTORY = HISTORY.slice(HISTORY.length - maxMsgs);

    renderChat();
  }}
  function renderChat() {{
    if (!HISTORY.length) {{
      chatEl.innerHTML = '<div style="color: var(--muted); font-size:13px;">(Conversation vide)</div>';
      ctxHintEl.textContent = "Contexte: 0 tour";
      return;
    }}
    let html = "";
    for (const m of HISTORY) {{
      const isUser = m.role === "user";
      html += `
        <div class="bubble-row" style="justify-content:${{isUser?"flex-end":"flex-start"}};">
          <div class="bubble ${{isUser?"you":""}}">
            <div class="who">${{isUser?"VOUS":"COPILOT"}}</div>
            <div>${{esc(m.text)}}</div>
          </div>
        </div>`;
    }}
    chatEl.innerHTML = html;
    chatEl.scrollTop = chatEl.scrollHeight;

    const turns = HISTORY.filter(x => x.role === "assistant").length;
    ctxHintEl.textContent = `Contexte: ${{turns}} tour(s)`;
  }}

  function safeText(s) {{
    return (s || "").toString().replace(/\\s+/g, " ").trim();
  }}
  function cleanAnswer(text) {{
    let t = (text || "").toString().replace(/\\r/g,"").replace(/\\n{{3,}}/g,"\\n\\n").trim();
    const parts = t.split(/(?<=[\\.!\\?])\\s+/).map(x=>x.trim()).filter(Boolean);
    const seen=new Set(); const out=[];
    for (const p of parts) {{
      const k = p.toLowerCase().replace(/[^a-z0-9àâçéèêëîïôùûüÿñæœ\\s]/gi,"").replace(/\\s+/g," ").trim();
      if (!k) continue;
      if (seen.has(k)) continue;
      seen.add(k);
      out.push(p);
    }}
    t = out.join(" ").trim();
    if (t.length > 2200) t = t.slice(0,2200).trim() + "…";
    return t;
  }}
  function antiHallFallback(originalQ) {{
    const q = (originalQ||"").trim();
    if (!q) return "Je n’ai pas assez d’éléments pour répondre avec certitude. Tu peux préciser ?";
    return "Je n’ai pas trouvé d’éléments fiables dans ma base pour répondre avec certitude. Tu peux préciser ?";
  }}
  function isNoIntent(text) {{
    const t = (text||"").toLowerCase().trim();
    const no = ["non", "non merci", "c'est tout", "cest tout", "merci c'est tout", "ça ira", "ca ira", "rien", "rien d'autre", "pas d'autre", "pas dautre"];
    return no.some(x => t === x || t.startsWith(x + " "));
  }}

  // ---- VU + RMS + auto record trigger
  function startVu(s) {{
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
        for (let i=0;i<data.length;i++) sum += data[i]*data[i];
        const rms = Math.sqrt(sum/data.length);

        updateThresholdsFromNoise(rms);
        if (!calibrated && performance.now() - callStartedAt > 1200) calibrated = true;

        const pct = Math.min(100, Math.max(0, rms*220));
        vuBar.style.width = pct + "%";
        vuTxt.textContent = "RMS=" + rms.toFixed(4) + " | NF=" + noiseFloor.toFixed(4);

        if (rms >= RMS_START_THRESHOLD) hasSpeech = true;

        const ttsPlaying = (ttsPlayer && !ttsPlayer.paused && !ttsPlayer.ended && ttsPlayer.currentTime > 0);

        if (autoModeEl.checked && callOn && !isBusy && !isSpeaking && !ttsPlaying &&
            (!mediaRecorder || mediaRecorder.state === "inactive")) {{
          if (performance.now() < cooldownUntil) return;
          if (rms >= RMS_START_THRESHOLD) {{
            autoStartRecording();
          }}
        }}

        if (mediaRecorder && mediaRecorder.state === "recording") {{
          if (rms < RMS_SILENCE_THRESHOLD) silenceCount += 80;
          else silenceCount = 0;

          const recMs = performance.now() - recStartedAt;
          if (hasSpeech && recMs > MIN_RECORD_MS && silenceCount >= SILENCE_MS_TO_STOP) {{
            autoStopRecording();
          }}
        }}
      }}, 80);
    }} catch(e) {{}}
  }}

  function stopVu() {{
    if (vuTimer) clearInterval(vuTimer);
    vuTimer=null;
    try {{ if(audioCtx) audioCtx.close(); }} catch(e) {{}}
    audioCtx=null; analyser=null; data=null;
    vuBar.style.width="0%";
    vuTxt.textContent="RMS=0.0000";
  }}

  // ---- TTS
  function splitForTts(text, maxLen) {{
    const t=(text||"").toString().trim();
    if(!t) return [];
    const maxL = Math.max(80, maxLen||140);
    const sentences = t.replace(/\\s+/g," ").split(/(?<=[\\.!\\?])\\s+/).map(x=>x.trim()).filter(Boolean);
    const chunks=[]; let cur="";
    for (const s of sentences) {{
      if(!cur) {{ cur=s; continue; }}
      if((cur.length+1+s.length) <= maxL) cur += " " + s;
      else {{ chunks.push(cur); cur=s; }}
    }}
    if(cur) chunks.push(cur);
    const final=[];
    for (const c of chunks) {{
      if(c.length<=maxL) final.push(c);
      else for (let i=0;i<c.length;i+=maxL) final.push(c.slice(i,i+maxL));
    }}
    return final.filter(Boolean);
  }}
  function b64ToBytes(b64) {{
    const bin = atob(b64);
    const arr = new Uint8Array(bin.length);
    for (let i=0;i<bin.length;i++) arr[i] = bin.charCodeAt(i);
    return arr;
  }}
  async function ttsSynthesizeB64(text) {{
    const url = "{API_BASE}/tts/synthesize";
    const resp = await fetch(url, {{
      method:"POST",
      headers:{{"Content-Type":"application/json"}},
      body: JSON.stringify({{text:text, lang:"{lang}"}})
    }});
    const body = await resp.text();
    if(!resp.ok) throw new Error(body||"TTS error");
    const json = JSON.parse(body);
    const b64 = (json.audio_base64||"").trim();
    if(!b64) throw new Error("Empty audio");
    return b64;
  }}

  async function speak(text) {{
    const t=(text||"").toString().trim();
    if(!t) return;

    isSpeaking = true;
    cooldownUntil = performance.now() + 600;

    micStateEl.textContent = "Speaking";
    callUi("Speaking");

    // ✅ PATCH: chunks plus longs (moins d’appels TTS)
    const parts = splitForTts(t, 220);

    const byteParts=[];
    for (const part of parts) {{
      const b64 = await ttsSynthesizeB64(part);
      byteParts.push(b64ToBytes(b64));
    }}
    let totalLen=0;
    for (const a of byteParts) totalLen += a.length;
    const merged = new Uint8Array(totalLen);
    let off=0;
    for (const a of byteParts) {{ merged.set(a, off); off += a.length; }}

    const blob = new Blob([merged], {{type:"audio/mpeg"}});
    const url = URL.createObjectURL(blob);

    try {{ ttsPlayer.pause(); ttsPlayer.currentTime=0; }} catch(e) {{}}
    ttsPlayer.src=url;

    ttsPlayer.onplaying = () => {{ isSpeaking = true; }};
    ttsPlayer.onended = () => {{
      isSpeaking = false;
      cooldownUntil = performance.now() + 900;
      micStateEl.textContent = "Ready";
      callUi("Connected");
    }};

    try {{ await ttsPlayer.play(); }} catch(e) {{
      isSpeaking = false;
      cooldownUntil = performance.now() + 900;
      micStateEl.textContent = "Ready";
      callUi("Connected");
    }}
  }}

  // ---- Auto record
  async function autoStartRecording() {{
    if (isBusy) return;
    if (!autoModeEl.checked || !callOn) return;
    if (!stream) return;

    chunks=[]; lastBlob=null;
    silenceCount=0;
    hasSpeech=false;

    micStateEl.textContent = "Recording";
    callUi("Listening");

    try {{
      const mime =
        (window.MediaRecorder && MediaRecorder.isTypeSupported && MediaRecorder.isTypeSupported("audio/webm;codecs=opus")) ? "audio/webm;codecs=opus" :
        (window.MediaRecorder && MediaRecorder.isTypeSupported && MediaRecorder.isTypeSupported("audio/webm")) ? "audio/webm" :
        "";

      mediaRecorder = mime ? new MediaRecorder(stream, {{ mimeType: mime }}) : new MediaRecorder(stream);

      mediaRecorder.ondataavailable = (e) => {{
        if (e.data && e.data.size > 0) chunks.push(e.data);
      }};
      mediaRecorder.onstop = () => {{
        lastBlob = new Blob(chunks, {{type:"audio/webm"}});
        if (lastObjectUrl) {{ try{{URL.revokeObjectURL(lastObjectUrl)}}catch(e){{}} }}
        lastObjectUrl = URL.createObjectURL(lastBlob);
        player.src = lastObjectUrl;

        micStateEl.textContent = "Processing";

        if (autoModeEl.checked && callOn) {{
          autoPipeline().catch(()=>{{}});
        }}
      }};

      recStartedAt = performance.now();
      mediaRecorder.start();

      setTimeout(() => {{
        try {{
          if (mediaRecorder && mediaRecorder.state === "recording") {{
            autoStopRecording();
          }}
        }} catch(e) {{}}
      }}, 6000);

    }} catch(e) {{
      micStateEl.textContent = "Recorder error";
      callUi("Recorder error");
    }}
  }}

  function autoStopRecording() {{
    try {{
      if (mediaRecorder && mediaRecorder.state !== "inactive") mediaRecorder.stop();
    }} catch(e) {{}}
    micStateEl.textContent = "Processing";
    callUi("Processing");
  }}

  // ✅ PATCH: prompt téléphone ultra-court
  function buildCallPrompt(q, ctxText, useCtx, antiHall) {{
    let prompt =
      "Tu es un agent vocal IT-STORM. " +
      "Réponds en 2 à 4 phrases, naturel et direct. " +
      "Termine par : 'Avez-vous d'autres questions ?' ";
    if (antiHall) prompt += "Si tu n'es pas sûr, dis : 'Je ne sais pas.' ";
    if (useCtx && ctxText) prompt += "\\nContexte: " + ctxText + "\\n";
    prompt += "\\nQuestion: " + q;
    return prompt;
  }}

  // ---- pipeline: STT -> RAG -> TTS
  async function autoPipeline() {{
    if (isBusy) return;
    if (!lastBlob) return;
    isBusy = true;

    callUi("Transcribing");
    micStateEl.textContent = "Transcribing";

    try {{
      if (lastBlob.size < 1200) {{
        cooldownUntil = performance.now() + 900;
        const msg = "Je n’ai pas bien entendu. Peux-tu répéter ?";
        transcriptEl.textContent = "(trop court)";
        answerEl.textContent = msg;
        if (lastAssistantMsg !== msg) {{
          pushHistory("assistant", msg);
          lastAssistantMsg = msg;
        }}
        try {{ await speak(msg); }} catch(e) {{}}
        isBusy = false;
        return;
      }}

      const form = new FormData();
      form.append("file", lastBlob, "mic.webm");

      const sttUrl = "{API_BASE}/stt/transcribe?lang={lang}";
      const sttResp = await fetch(sttUrl, {{ method:"POST", body: form }});
      const sttBody = await sttResp.text();
      if (!sttResp.ok) throw new Error(sttBody || "STT error");
      const sttJson = JSON.parse(sttBody);

      const q = safeText(sttJson.text || "");
      transcriptEl.textContent = q || "(texte vide)";

      if (!q) {{
        cooldownUntil = performance.now() + 900;
        const msg = "Je n’ai pas bien entendu. Peux-tu répéter ?";
        answerEl.textContent = msg;
        if (lastAssistantMsg !== msg) {{
          pushHistory("assistant", msg);
          lastAssistantMsg = msg;
        }}
        await speak(msg);
        isBusy = false;
        return;
      }}

      if (isNoIntent(q)) {{
        const bye = "Très bien. Je vous souhaite une excellente journée Monsieur.";
        pushHistory("user", q);
        pushHistory("assistant", bye);
        await speak(bye);
        callOn = false;
        callUi("Ended");
        liveDot.className = "dot";
        micStateEl.textContent = "Ended";
        isBusy = false;
        return;
      }}

      pushHistory("user", q);

      callUi("Answering");
      micStateEl.textContent = "Answering";

      const useCtx = useContextEl ? !!useContextEl.checked : true;
      const antiHall = antiHallEl ? !!antiHallEl.checked : true;

      // ✅ PATCH: contexte 1 tour (2 messages max)
      let ctxText = "";
      if (useCtx && HISTORY.length) {{
        const last = HISTORY.slice(-2);
        ctxText = last.map(m => (m.role==="user" ? "U: " : "A: ") + m.text).join(" | ");
      }}

      const enriched = buildCallPrompt(q, ctxText, useCtx, antiHall);

      // ✅ PATCH: call-mode -> /rag/fast + top_k réduit
      const ragUrl = "{API_BASE}/rag/fast";
      const ragResp = await fetch(ragUrl, {{
        method:"POST",
        headers:{{"Content-Type":"application/json"}},
        body: JSON.stringify({{ question: enriched, top_k: 2 }})
      }});
      const ragBody = await ragResp.text();
      if (!ragResp.ok) throw new Error(ragBody || "RAG error");
      const ragJson = JSON.parse(ragBody);

      const src = Array.isArray(ragJson.sources) ? ragJson.sources : [];
      sourcesEl.textContent = src.length ? ("Sources: " + src.join(" | ")) : "Sources: —";

      let ans = cleanAnswer((ragJson.answer || "").trim());
      if (antiHall && src.length === 0) ans = antiHallFallback(q);

      if (!/avez[- ]vous d['’]autres questions\\s*\\?\\s*$/i.test(ans)) {{
        ans = ans.trim() + "\\n\\nAvez-vous d'autres questions ?";
      }}

      answerEl.textContent = ans || "(réponse vide)";
      pushHistory("assistant", ans);
      lastAssistantMsg = ans;

      // ✅ PATCH: lire seulement les 2 premières phrases en audio
      const shortAns = (ans || "").split(/(?<=[\\.!\\?])\\s+/).slice(0,2).join(" ");
      await speak(shortAns || ans);

      isBusy = false;
      return;

    }} catch(err) {{
      cooldownUntil = performance.now() + 1800;
      const msg = "Désolé, j’ai eu un souci technique. Peux-tu répéter ?";
      answerEl.textContent = msg;
      if (lastAssistantMsg !== msg) {{
        pushHistory("assistant", msg);
        lastAssistantMsg = msg;
      }}
      try {{ await speak(msg); }} catch(e) {{}}
      isBusy = false;
      micStateEl.textContent = "Ready";
      callUi("Connected");
    }}
  }}

  function startCall() {{
    callOn = true;
    callStartedAt = performance.now();
    callUi("Connected");
    liveDot.className = "dot live";
    micStateEl.textContent = "Ready";

    if (callTimer) clearInterval(callTimer);
    callTimer = setInterval(() => {{
      if (callTimerEl && callStartedAt) callTimerEl.textContent = fmtMMSS(performance.now() - callStartedAt);
    }}, 250);
  }}

  async function greet() {{
    const greetText = "Bonjour, vous êtes bien sur le service client IT-STORM. Je vous écoute. Quelle est votre question ?";
    pushHistory("assistant", greetText);
    await speak(greetText);
  }}

  btnHang.onclick = () => {{
    callOn = false;
    liveDot.className = "dot";
    callUi("Ended");
    micStateEl.textContent = "Ended";

    try {{
      if (mediaRecorder && mediaRecorder.state !== "inactive") mediaRecorder.stop();
    }} catch(e) {{}}

    try {{
      if (stream) stream.getTracks().forEach(t => t.stop());
    }} catch(e) {{}}

    stopVu();
    try {{ ttsPlayer.pause(); }} catch(e) {{}}

    pushHistory("assistant", "Appel terminé. Je vous souhaite une excellente journée Monsieur.");
  }};

  renderChat();
  startCall();

  navigator.mediaDevices.getUserMedia({{
    audio: {{
      echoCancellation:true,
      noiseSuppression:true,
      autoGainControl:true,
      channelCount:1,
      sampleRate:48000
    }}
  }}).then(s => {{
    stream = s;
    startVu(stream);
    greet().catch(()=>{{}});
  }}).catch(err => {{
    callUi("Mic denied");
    micStateEl.textContent = "Mic denied";
    alert("Micro refusé. Autorise le micro dans Chrome.");
  }});

}})();
</script>
"""

def render_stt_only() -> None:
    _inject_page_css()

    st.markdown(
    """
<div class="vc-hero vc-hero--center">
  <div class="vc-title">Voice Copilot</div>
  <div class="vc-sub">
    Une interaction vocale naturelle : parlez librement, StormCopilot comprend, recherche dans vos documents et vous répond instantanément, à l’oral.
  </div>
</div>
""",
    unsafe_allow_html=True,
)

    (tab_live,) = st.tabs(["🎙 Live"])

    with tab_live:
        sub1, sub2 = st.tabs(["✅ Question unique", "📞 Appel téléphonique"])

        with sub1:
          components.html(_component_single_question("fr"), height=950, scrolling=False)

        with sub2:
          components.html(_component_call_mode("fr"), height=1120, scrolling=False)