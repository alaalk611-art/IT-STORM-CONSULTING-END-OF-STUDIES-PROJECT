# ============================================================
# src/ui/components/floating_chatbot.py
# IRIS — Bulle de chat Streamlit reliée à /chat (FastAPI)
# - Réponse directe si backend renvoie une réponse
# - Sinon : suggestions en chaîne (Oui => répond, Non => nouvelle suggestion)
# - "Une nouvelle Suggestion : ..." à partir de la 2e proposition
# - Jamais "Plus de suggestions." (on boucle au début)
# - + Historique persistant (localStorage)
# - + Typing animation "IRIS est en train d'écrire…"
# - + Bouton "Effacer l'historique"
# - + Alignement façon Messenger (bot gauche / user droite)
# - + Animations d'apparition des messages
# - + Avatar rond pour IRIS
# PATCH 2025 :
#   * "Précision confirmée → ..." affiché seulement après suggestion validée
#     (pas quand l'utilisateur tape déjà la question exacte)
#   * Animation "IRIS est en train d'écrire…" visible AU MAX 3 secondes
# ============================================================

from __future__ import annotations
import sys
import base64
from pathlib import Path
import streamlit as st
import streamlit.components.v1 as components

# --- Setup sys.path (inchangé) ---
ROOT = Path(__file__).resolve().parents[3]
TOOLS = ROOT / "tools"
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))
if TOOLS.exists() and str(TOOLS) not in sys.path:
    sys.path.insert(0, str(TOOLS))


def render_chatbot():
    st.session_state.setdefault("chat_history", [])

    def _b64(p: Path) -> str:
        with open(p, "rb") as f:
            return base64.b64encode(f.read()).decode("utf-8")

    # Logo (si présent)
    logo_path = None
    for p in (
        Path("src/ui/assets/itstorm.png"),
        Path(__file__).resolve().parents[1] / "assets" / "itstorm.png",
    ):
        if p.exists():
            logo_path = p
            break
    logo_html = (
        f'<img src="data:image/png;base64,{_b64(logo_path)}" width="28" '
        f'style="vertical-align:middle;margin-right:6px;"/>'
        if logo_path
        else "🤖"
    )

    # --- URL API ---
    API_URL = "http://127.0.0.1:8001/chat"   # adapte si nécessaire
    BACKUP_URL = ""                           # optionnel (ex: un 2e /chat)

    components.html(
        f"""
<style>
  :root {{
    --sc-blue: #0084ff;
    --sc-blue-dark: #0072db;
    --sc-bot-bg: #f1f3f5;
    --sc-shadow: 0 8px 22px rgba(0,0,0,.25);
  }}

  /* ================= POSITION ================= */

  /* --- Bulle flottante --- */
  #sc-bubble {{
    position: fixed; top: 50%; right: 24px; transform: translateY(-50%);
    width: 64px; height: 64px; border-radius: 50%;
    background: linear-gradient(135deg, #004aad, #0060d4);
    color: #fff; font-size: 28px; line-height: 64px; text-align: center;
    cursor: pointer; box-shadow: 0 6px 14px rgba(0,0,0,.3); z-index: 9999; user-select: none;
  }}

  /* --- Badge Besoin d’aide ? --- */
  #sc-help-badge {{
    position: fixed; top: calc(50% - 80px); right: 24px; transform: translateY(-50%);
    display: none; z-index: 9999;
    background: linear-gradient(135deg, #111827, #1f2937);
    color: #fff; font-size: 12px; padding: 8px 12px; border-radius: 9999px;
    box-shadow: 0 6px 18px rgba(0,0,0,.35);
  }}
  #sc-help-badge::before {{
    content: "❔";
    margin-right: .5rem;
  }}

  /* --- Fenêtre --- */
  #sc-window {{
    position: fixed; top: 50%; right: 96px; transform: translateY(-50%);
    width: 380px; max-height: 560px;
    background: #fff; border-radius: 16px; box-shadow: var(--sc-shadow);
    display: none; z-index: 9999; overflow: hidden;
    font-family: system-ui, -apple-system, Segoe UI, Arial, sans-serif;
  }}
  #sc-header {{
    background: #004aad; color:#fff; padding: 10px 12px;
    display:flex; align-items:center; justify-content:space-between;
  }}
  #sc-title {{ font-weight: 600; }}
  #sc-header-right {{
    display:flex; align-items:center; gap:8px;
  }}
  #sc-close, #sc-clear {{
    cursor:pointer;
    font-size: 14px;
    opacity: 0.9;
  }}
  #sc-close:hover, #sc-clear:hover {{
    opacity: 1;
  }}

  /* --- Zone de messages --- */
  #sc-msgs {{
    padding: 12px; height: 400px; overflow-y: auto; background: #f8fafc;
    display: flex; flex-direction: column; gap: 8px;
  }}

  .sc-row-msg {{
    display:flex;
    width: 100%;
  }}
  .sc-row-bot {{
    justify-content: flex-start;   /* IRIS à gauche */
  }}
  .sc-row-user {{
    justify-content: flex-end;     /* Toi à droite */
  }}

  /* Avatar IRIS */
  .sc-avatar {{
    width: 32px;
    height: 32px;
    border-radius: 9999px;
    overflow: hidden;
    margin-right: 8px;
    flex-shrink: 0;
    display:flex;
    align-items:center;
    justify-content:center;
    background: #e5e7eb;
    box-shadow: 0 0 0 2px #e5e7eb;
  }}
  .sc-avatar img {{
    border-radius: 9999px;
    display:block;
  }}

  .sc-bot, .sc-user, .sc-warn {{
    position: relative;
    transition: transform 0.12s ease-out, box-shadow 0.12s ease-out;
  }}

  .sc-bot {{
    max-width: 80%; align-self: flex-start; color:#111; background: var(--sc-bot-bg);
    padding: 10px 12px; border-radius: 14px; border-top-left-radius: 6px; white-space: pre-wrap;
    animation: sc-msg-left 0.22s ease-out;
  }}
  .sc-user {{
    max-width: 80%; align-self: flex-end; color:#fff; background: var(--sc-blue);
    padding: 10px 12px; border-radius: 14px; border-top-right-radius: 6px; white-space: pre-wrap;
    animation: sc-msg-right 0.22s ease-out;
  }}
  .sc-user a {{ color:#fff; text-decoration: underline; }}

  .sc-warn {{
    max-width: 80%; align-self: center; background: #fff7e6; border:1px solid #ffe58f; color:#8b5e00;
    padding: 10px 12px; border-radius: 10px; white-space: pre-wrap;
    animation: sc-msg-center 0.22s ease-out;
  }}

  .sc-bot:hover, .sc-user:hover, .sc-warn:hover {{
    transform: translateY(-1px);
    box-shadow: 0 4px 10px rgba(15,23,42,0.12);
  }}

  /* Typing indicator */
  .sc-typing {{
    font-style: italic;
    opacity: 0.8;
    animation: sc-pulse 1.2s ease-in-out infinite;
  }}

  /* --- Barre d’entrée --- */
  .sc-input-row {{ display:flex; gap:8px; padding: 10px; border-top: 1px solid #e5e7eb; background: #fff; }}
  #sc-input {{
    flex:1; padding: 10px 12px; border:1px solid #d1d5db; border-radius: 10px; outline:none;
    background:#fff;
  }}
  #sc-send {{
    background: var(--sc-blue); color:#fff; border:none; border-radius:10px; padding:10px 14px; cursor:pointer;
  }}
  #sc-send:hover {{ background: var(--sc-blue-dark); }}

  /* --- Boutons inline (suggestions) --- */
  .sc-inline-actions {{ margin-top:6px; display:flex; gap:8px; }}
  .sc-btn {{
    display:inline-block; border:1px solid #d1d5db; background:#fff; padding:6px 10px; border-radius:8px; cursor:pointer;
  }}
  .sc-btn:hover {{ background:#f3f4f6; }}

  /* === Animations messages === */
  @keyframes sc-msg-left {{
    from {{ opacity:0; transform: translateX(-10px) scale(0.98); }}
    to   {{ opacity:1; transform: translateX(0) scale(1); }}
  }}
  @keyframes sc-msg-right {{
    from {{ opacity:0; transform: translateX(10px) scale(0.98); }}
    to   {{ opacity:1; transform: translateX(0) scale(1); }}
  }}
  @keyframes sc-msg-center {{
    from {{ opacity:0; transform: translateY(4px) scale(0.97); }}
    to   {{ opacity:1; transform: translateY(0) scale(1); }}
  }}
  @keyframes sc-pulse {{
    0%   {{ opacity: 0.5; transform: translateX(0); }}
    50%  {{ opacity: 1.0; transform: translateX(2px); }}
    100% {{ opacity: 0.5; transform: translateX(0); }}
  }}
</style>

<div id="sc-bubble">{logo_html}</div>
<div id="sc-help-badge">Besoin d’aide&nbsp;?</div>

<div id="sc-window" role="dialog" aria-label="IRIS — Assistant IT-Storm">
  <div id="sc-header">
    <div id="sc-title">IRIS — Assistant IT-Storm</div>
    <div id="sc-header-right">
      <div id="sc-clear" title="Effacer l'historique">🧹</div>
      <div id="sc-close" title="Fermer">✖</div>
    </div>
  </div>
  <div id="sc-msgs" aria-live="polite"></div>
  <div class="sc-input-row">
    <input id="sc-input" type="text" placeholder="Pose ta question…" aria-label="Votre question"/>
    <button id="sc-send">Envoyer</button>
  </div>
</div>

<script>
(() => {{
  const API_URL = "{API_URL}";
  const BACKUP_URL = "{BACKUP_URL}";

  const bubble = document.getElementById("sc-bubble");
  const badge  = document.getElementById("sc-help-badge");
  const win    = document.getElementById("sc-window");
  const close  = document.getElementById("sc-close");
  const clearBtn = document.getElementById("sc-clear");
  const msgs   = document.getElementById("sc-msgs");
  const qin    = document.getElementById("sc-input");
  const send   = document.getElementById("sc-send");

  // ====== Historique (localStorage) ======
  const HISTORY_KEY = "iris_chat_history_v1";
  let history = [];

  const esc = (s) => (s || "").replace(/[&<>\"']/g, m => ({{"&":"&amp;","<":"&lt;"," >":"&gt;","\\"":"&quot;","'":"&#039;"}})[m]);

  function saveHistory() {{
    try {{
      localStorage.setItem(HISTORY_KEY, JSON.stringify(history));
    }} catch(e) {{}}
  }}

  function addMsg(text, cls, save=true) {{
    const wrap = document.createElement("div");
    // Alignement façon Messenger : IRIS à gauche, toi à droite
    let rowClass = "sc-row-msg ";
    if (cls === "sc-user") {{
      rowClass += "sc-row-user";
    }} else {{
      rowClass += "sc-row-bot";
    }}
    wrap.className = rowClass;

    // Avatar pour IRIS (bot + typing)
    if (cls === "sc-bot" || cls === "sc-typing") {{
      const avatar = document.createElement("div");
      avatar.className = "sc-avatar";
      avatar.innerHTML = `{logo_html}`;
      wrap.appendChild(avatar);
    }}

    const d = document.createElement("div");
    d.className = cls;
    d.innerHTML = esc(text).replace(/\\n/g, "<br/>");
    wrap.appendChild(d);
    msgs.appendChild(wrap);
    msgs.scrollTop = msgs.scrollHeight;

    if (save) {{
      history.push({{ cls, text }});
      saveHistory();
    }}
    return d;
  }}

  function addBot(text, save=true)  {{ return addMsg(text, "sc-bot", save); }}
  function addUser(text, save=true) {{ return addMsg(text, "sc-user", save); }}
  function addWarn(text, save=true) {{ return addMsg(text, "sc-warn", save); }}

  function restoreHistory() {{
    let raw = null;
    try {{
      raw = localStorage.getItem(HISTORY_KEY);
    }} catch(e) {{}}
    if (!raw) return;
    try {{
      history = JSON.parse(raw) || [];
    }} catch(e) {{
      history = [];
      return;
    }}
    for (const m of history) {{
      if (!m || !m.text || !m.cls) continue;
      addMsg(m.text, m.cls, false);
    }}
    if (history.length > 0) {{
      window.__sc_welcome_once_shown__ = true;
    }}
  }}

  // ====== TYPING INDICATOR : "IRIS est en train d'écrire…" ======
  //          -> visible dès qu'on appelle le backend
  //          -> disparait quand la réponse arrive
  //          -> ou automatiquement au bout de 3 secondes max
  let typingNode = null;
  let typingTimer = null;

  function showTyping() {{
    if (typingNode) return;
    const wrap = document.createElement("div");
    wrap.className = "sc-row-msg sc-row-bot";
    const avatar = document.createElement("div");
    avatar.className = "sc-avatar";
    avatar.innerHTML = `{logo_html}`;
    wrap.appendChild(avatar);
    const d = document.createElement("div");
    d.className = "sc-bot sc-typing";
    d.textContent = "IRIS est en train d'écrire…";   // <=== TEXTE DEMANDÉ
    wrap.appendChild(d);
    msgs.appendChild(wrap);
    msgs.scrollTop = msgs.scrollHeight;
    typingNode = wrap;

    // Auto-hide au bout de 3 secondes MAX
    if (typingTimer) {{
      clearTimeout(typingTimer);
      typingTimer = null;
    }}
    typingTimer = setTimeout(() => {{
      if (typingNode) {{
        try {{ typingNode.remove(); }} catch(e) {{}}
        typingNode = null;
      }}
      typingTimer = null;
    }}, 1000);
  }}

  function hideTyping() {{
    if (typingTimer) {{
      clearTimeout(typingTimer);
      typingTimer = null;
    }}
    if (!typingNode) return;
    try {{
      typingNode.remove();
    }} catch(e) {{}}
    typingNode = null;
  }}

  // Effacer l'historique
  function clearHistory() {{
    history = [];
    try {{
      localStorage.removeItem(HISTORY_KEY);
    }} catch(e) {{}}
    msgs.innerHTML = "";
    window.__sc_welcome_once_shown__ = false;
    addBot("Historique effacé. on commence une nouvelle conversation.", false);
  }}

  // Restaurer l'historique au chargement
  restoreHistory();

  // ---- Helpers UI ----
  function openWin() {{
    win.style.display = "block";
    qin.focus();
    hideHelpBadge();

    if (!window.__sc_welcome_once_shown__) {{
      addBot("Bonjour, je m’appelle IRIS et je suis votre assistant IT-Storm. Posez-moi vos questions sur nos services.");
      window.__sc_welcome_once_shown__ = true;
    }}
  }}
  function closeWin() {{ win.style.display = "none"; showHelpBadge(); }}

  bubble.onclick = () => {{ (win.style.display === "block") ? closeWin() : openWin(); }};
  close.onclick  = () => closeWin();
  clearBtn.onclick = () => clearHistory();

  function showHelpBadge() {{ badge.style.display = "block"; }}
  function hideHelpBadge() {{ badge.style.display = "none"; }}
  document.addEventListener("DOMContentLoaded", () => {{
    if (win.style.display !== "block") showHelpBadge();
  }});
  badge.onclick = () => openWin();

  // ---- Utilitaires texte ----
  function stripSources(text) {{
    if (!text) return "";
    const lines = String(text).split(/\\r?\\n/);
    const kept = [];
    for (const L of lines) {{
      const t = L.trim();
      if (/^source\\s*:/i.test(t)) continue;
      if (/^sources\\s*:/i.test(t)) continue;
      kept.push(L);
    }}
    return kept.join("\\n").replace(/\\n\\s*\\n\\s*$/,"\\n").trim();
  }}

  function normalize(s) {{
    return (s || "")
      .toLowerCase()
      .trim()
      .replace(/[?!.]+$/g, "")
      .replace(/\\s+/g, " ");
  }}

  // ---- Détection hors périmètre (FR/EN) côté front (pas de suggestions) ----
  const SCOPE_KEYWORDS = [
    // IT Storm
    "it storm","itstorm","storm","services","service","prestation",

    // IA / Data / Cloud / DevOps
    "cloud","devops","iac","infra as code","infrastructure as code",
    "kubernetes","k8s","docker","data","donnée","données","pipeline",
    "etl","elt","ia","intelligence artificielle","ml","ai","nlp","rag",
    "consult","conseil",

    // Portage salarial
    "portage","portage salarial","freelance","auto entrepreneur","consultant",
    "indépendant","facturation","tjm","tj","revenu","salaire","mission"
];

  function isOutOfScopeUserQuestion(q) {{
    if (!q) return true;
    const qq = q.toLowerCase();
    return !SCOPE_KEYWORDS.some(k => qq.includes(k));
  }}

  // ---- Protocoles backend ----
  function parseLegacyText(raw) {{
    const mSug = /(^|\\n)SUGGEST:(.*?)(\\n|$)/i.exec(raw);
    const mAns = /(^|\\n)IF_YES_ANSWER:(.*?)(\\n|$)/i.exec(raw);
    if (mSug) {{
      return {{
        type: "suggest",
        normalized_question: (mSug[2] || "").trim(),
        yesAnswer: mAns ? (mAns[2] || "").trim() : "Je ne sais pas."
      }};
    }}
    const clean = stripSources(raw);
    return {{ type:"answer", message:"", answer: clean || "Je ne sais pas." }};
  }}

  function normalizeChatOutJSON(j) {{
    // ChatOut JSON : {{mode, message, normalized_question, answer}}
    if (!j || typeof j !== "object") return null;
    if ("mode" in j) {{
      if (j.mode === "suggest") {{
        return {{ type:"suggest", normalized_question:(j.normalized_question||"").trim() }};
      }} else if (j.mode === "answer") {{
        const msg = j.message ? String(j.message) : "";
        const ans = j.answer  ? String(j.answer)  : "Je ne sais pas.";
        return {{ type:"answer", message: msg, answer: stripSources(ans) }};
      }}
    }}
    if ("answer" in j) {{
      const txt = String(j.answer||"");
      return parseLegacyText(txt);
    }}
    return null;
  }}

  // ---- Appels API (renvoie un objet normalisé suggest|answer) ----
  async function postJSON(url, payload) {{
    const r = await fetch(url, {{
      method: "POST",
      headers: {{ "Content-Type": "application/json" }},
      body: JSON.stringify(payload)
    }});
    if (!r.ok) throw new Error("HTTP " + r.status);
    return await r.json();
  }}

  async function askAPI(message, exclude=[], hop=0) {{
    const payload = {{ message, exclude_suggestions: exclude, hop }};
    try {{
      const j = await postJSON(API_URL, payload);
      const norm = normalizeChatOutJSON(j);
      if (norm) return norm;
      if (typeof j === "string") return parseLegacyText(j);
      return {{ type:"answer", message:"", answer:"Je ne sais pas." }}
    }} catch (e) {{
      if (BACKUP_URL) {{
        try {{
          const j2 = await postJSON(BACKUP_URL, payload);
          const norm2 = normalizeChatOutJSON(j2);
          if (norm2) return norm2;
          if (typeof j2 === "string") return parseLegacyText(j2);
        }} catch(_) {{}}
      }}
      return {{ type:"answer", message:"", answer:"⚠️ Erreur backend." }};
    }}
  }}

  // ---- Chaîne de suggestions (o/n) ----
  function renderSuggestionCard(originalQ, normQ, hop) {{
    const prefix = hop >= 1 ? "Une nouvelle Suggestion : " : "";
    const card = document.createElement("div");
    card.className = "sc-bot";
    card.style.maxWidth = "80%";
    card.innerHTML = prefix + 'Tu veux dire : « ' + esc(normQ) + ' » ?';

    const actions = document.createElement("div");
    actions.className = "sc-inline-actions";
    const bYes = document.createElement("button"); bYes.className = "sc-btn"; bYes.textContent = "Oui (o)";
    const bNo  = document.createElement("button"); bNo.className  = "sc-btn";  bNo.textContent  = "Non (n)";
    actions.appendChild(bYes); actions.appendChild(bNo); card.appendChild(actions);

    const wrap = document.createElement("div");
    wrap.className = "sc-row-msg sc-row-bot";
    const avatar = document.createElement("div");
    avatar.className = "sc-avatar";
    avatar.innerHTML = `{logo_html}`;
    wrap.appendChild(avatar);
    wrap.appendChild(card);
    msgs.appendChild(wrap); msgs.scrollTop = msgs.scrollHeight;

    let keyHandler = null;
    function disable(){{
      bYes.disabled = true; bNo.disabled = true;
      if (keyHandler) window.removeEventListener("keydown", keyHandler);
    }}
    keyHandler = (e) => {{
      if (win.style.display !== "block") return;
      const k = (e.key || "").toLowerCase();
      if (k === "o") onYes();
      if (k === "n") onNo();
    }};
    window.addEventListener("keydown", keyHandler);

    async function onYes(){{
      disable();
      showTyping();
      const j = await askAPI(normQ, [], 0);  // réponse directe avec la formulation validée
      hideTyping();
      if (j.type === "answer"){{
        // Ici, on affiche toujours la précision (cas suggestion validée)
        if (j.message) addBot(j.message);
        addBot(j.answer || "Je ne sais pas.");
      }} else {{
        addBot("Je ne sais pas.");
      }}
    }}

    async function onNo(){{
      disable();
      showTyping();
      let nextHop = hop + 1;
      let j = await askAPI(originalQ, [], nextHop);
      hideTyping();

      // Si plus de suggestion -> reboucle au début (jamais "Plus de suggestions.")
      if (j.type !== "suggest"){{
        j = await askAPI(originalQ, [], 0);
        nextHop = 0;
      }}

      if (j.type === "suggest"){{
        renderSuggestionCard(originalQ, j.normalized_question || originalQ, nextHop);
      }} else if (j.type === "answer"){{
        if (j.message) addBot(j.message);
        addBot(j.answer || "Je ne sais pas.");
      }} else {{
        const j2 = await askAPI(originalQ, [], 0);
        if (j2.type === "suggest"){{
          renderSuggestionCard(originalQ, j2.normalized_question || originalQ, 0);
        }} else {{
          addBot(j2.answer || "Je ne sais pas.");
        }}
      }}
    }}

    bYes.onclick = onYes;
    bNo.onclick  = onNo;
  }}

  // ---- Orchestration principale ----
  function outOfScopeMessage(){{
    return "Ce système répond uniquement aux questions liées à IT Storm, Merci de reformuler votre question dans ce périmètre.";
  }}

  async function startAsk(userQ){{
    // 1) Filtre hors périmètre : pas de suggestions, on s'arrête
    if (isOutOfScopeUserQuestion(userQ)) {{
      addBot(outOfScopeMessage());
      return;
    }}

    // 2) Appel backend (hop=0) + TYPING
    showTyping();
    let j = await askAPI(userQ, [], 0);
    hideTyping();

    if (j.type === "answer"){{
      // Réponse directe -> pas de suggestions
      const msg = j.message || "";
      let showMsg = true;

      // Si le backend renvoie "Précision confirmée → ..."
      // ET que l'utilisateur a déjà tapé exactement cette question,
      // on n'affiche PAS ce message (on garde seulement la réponse).
      if (msg.startsWith("Précision confirmée")) {{
        const m = msg.match(/«(.*)»/);
        if (m && m[1]) {{
          const nUser  = normalize(userQ);
          const nInside = normalize(m[1]);
          if (nUser && nInside && nUser === nInside) {{
            showMsg = false;
          }}
        }}
      }}

      if (showMsg && msg) {{
        addBot(msg);
      }}
      addBot(j.answer || "Je ne sais pas.");
      return;
    }}

    if (j.type === "suggest"){{
      // 3) Si la suggestion == question saisie (normalisées)
      const nUser = normalize(userQ);
      const nNorm = normalize(j.normalized_question || "");
      if (nUser && nUser === nNorm) {{
        // court-circuit : on demande la réponse directe sans passer par Oui/Non
        showTyping();
        const j2 = await askAPI(j.normalized_question || userQ, [], 0);
        hideTyping();
        if (j2.type === "answer") {{
          const msg2 = j2.message || "";
          let showMsg2 = true;

          if (msg2.startsWith("Précision confirmée")) {{
            const m2 = msg2.match(/«(.*)»/);
            if (m2 && m2[1]) {{
              const nInside2 = normalize(m2[1]);
              if (nUser && nInside2 && nUser === nInside2) {{
                showMsg2 = false;
              }}
            }}
          }}

          if (showMsg2 && msg2) {{
            addBot(msg2);
          }}
          addBot(j2.answer || "Je ne sais pas.");
        }} else {{
          // si malgré tout ce n'est pas une answer, on retombe sur le flux suggestion
          renderSuggestionCard(userQ, j.normalized_question || userQ, 0);
        }}
        return;
      }}

      // 4) Sinon : démarrer la chaîne Oui/Non
      renderSuggestionCard(userQ, j.normalized_question || userQ, 0);
      return;
    }}

    // Fallback doux
    showTyping();
    const j2 = await askAPI(userQ, [], 0);
    hideTyping();
    if (j2.type === "answer"){{
      const msg3 = j2.message || "";
      let showMsg3 = true;

      if (msg3.startsWith("Précision confirmée")) {{
        const m3 = msg3.match(/«(.*)»/);
        if (m3 && m3[1]) {{
          const nUser3  = normalize(userQ);
          const nInside3 = normalize(m3[1]);
          if (nUser3 && nInside3 && nUser3 === nInside3) {{
            showMsg3 = false;
          }}
        }}
      }}

      if (showMsg3 && msg3) {{
        addBot(msg3);
      }}
      addBot(j2.answer || "Je ne sais pas.");
    }} else if (j2.type === "suggest"){{
      renderSuggestionCard(userQ, j2.normalized_question || userQ, 0);
    }} else {{
      addBot("Je ne sais pas.");
    }}
  }}

  // Envoi
  function sendQ(){{
    const q = (qin.value || "").trim();
    if (!q) return;
    addUser(q);
    qin.value = "";
    startAsk(q);
  }}
  send.onclick = sendQ;
  qin.addEventListener("keydown", (e) => {{ if (e.key === "Enter") sendQ(); }});
}})();
</script>
        """,
        height=600,
    )
