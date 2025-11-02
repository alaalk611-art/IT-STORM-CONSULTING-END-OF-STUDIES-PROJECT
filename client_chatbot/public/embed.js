// public/embed.js — clean & animated
(() => {
        "use strict";

        // ===== Helpers =====
        const uid = () => Math.random().toString(36).slice(2) + Date.now().toString(36);
        const escapeHTML = (s = "") =>
            String(s).replaceAll("&", "&amp;").replaceAll("<", "&lt;").replaceAll(">", "&gt;");
        const nl2br = (s = "") => String(s).replace(/\n/g, "<br>");

        // ===== Options via <script ... data-*> =====
        const currentScript =
            document.currentScript ||
            (() => {
                const scripts = document.getElementsByTagName("script");
                return scripts[scripts.length - 1] || null;
            })();

        const getAttr = (name, def) => {
            const v = currentScript && currentScript.getAttribute ? currentScript.getAttribute(name) : null;
            return v == null ? def : v;
        };

        const API_ENDPOINT = getAttr("data-endpoint", "/api/chat");
        const WIDGET_TITLE = getAttr("data-title", "StormCopilot");
        const WIDGET_POS =
            String(getAttr("data-position", "right")).toLowerCase() === "left" ? "left" : "right";
        const WELCOME = getAttr("data-welcome", "Bonjour 👋 Comment puis-je vous aider ?");

        // ===== Inject CSS once =====
        const cssId = "stormcopilot-widget-css";
        if (!document.getElementById(cssId)) {
            const link = document.createElement("link");
            link.id = cssId;
            link.rel = "stylesheet";
            link.href = "/client-chat/widget.css"; // adapte ce chemin si besoin
            document.head.appendChild(link);
        }

        // ===== Session simple =====
        const SESSION_KEY = "sc_session_id";
        let sessionId = null;
        try {
            sessionId = localStorage.getItem(SESSION_KEY);
            if (!sessionId) {
                sessionId = uid();
                localStorage.setItem(SESSION_KEY, sessionId);
            }
        } catch {
            // localStorage indisponible (mode privé, etc.)
            sessionId = uid();
        }

        // ===== Anti-spam =====
        let lastSendAt = 0;
        const RATE_MS = 500;

        // ===== UI =====
        const bubble = document.createElement("button");
        bubble.className = `sc-bubble ${WIDGET_POS === "left" ? "sc-left" : "sc-right"}`;
        bubble.setAttribute("aria-label", "Ouvrir le chat");
        bubble.setAttribute("type", "button");
        bubble.innerHTML = `<span class="sc-bubble-dot" aria-hidden="true"></span>`;

        const panel = document.createElement("div");
        panel.className = `sc-panel sc-hidden ${WIDGET_POS === "left" ? "sc-left" : "sc-right"}`;
        panel.setAttribute("role", "dialog");
        panel.setAttribute("aria-modal", "false");
        panel.setAttribute("aria-hidden", "true");
        panel.innerHTML = `
    <div class="sc-header">
      <div class="sc-title">${escapeHTML(WIDGET_TITLE)}</div>
      <div class="sc-actions">
        <button class="sc-minimize" aria-label="Réduire" type="button">—</button>
        <button class="sc-close" aria-label="Fermer" type="button">×</button>
      </div>
    </div>
    <div class="sc-messages" id="sc-messages" role="log" aria-live="polite"></div>
    <form class="sc-input" id="sc-form">
      <textarea id="sc-text" rows="1" placeholder="Écrivez votre message… (Shift+Entrée pour ligne)" autocomplete="off"></textarea>
      <button type="submit" class="sc-send" title="Envoyer" aria-label="Envoyer">➤</button>
    </form>
  `;

        document.body.appendChild(bubble);
        document.body.appendChild(panel);

        // Refs
        const messagesEl = panel.querySelector("#sc-messages");
        const form = panel.querySelector("#sc-form");
        const input = panel.querySelector("#sc-text");
        const closeBtn = panel.querySelector(".sc-close");
        const minimizeBtn = panel.querySelector(".sc-minimize");

        // ===== UI helpers =====
        function scrollToBottom() {
            messagesEl.scrollTop = messagesEl.scrollHeight;
        }

        function addMsg(html, role) {
            const msg = document.createElement("div");
            msg.className = `sc-msg sc-${role} sc-in`;
            msg.innerHTML = html;
            messagesEl.appendChild(msg);
            msg.addEventListener(
                "animationend",
                () => {
                    msg.classList.remove("sc-in");
                }, { once: true }
            );
            scrollToBottom();
            return msg;
        }

        function addUser(text) {
            addMsg(nl2br(escapeHTML(text)), "user");
        }

        function addAssistant(text, sources) {
            const safe = nl2br(escapeHTML(text));
            const srcs = Array.isArray(sources) ? sources : [];
            const srcHtml =
                srcs.length > 0 ?
                `<div class="sc-sources">${srcs
            .map((s, i) => `<span class="sc-source">[${i + 1}] ${escapeHTML(String(s))}</span>`)
            .join("")}</div>`
        : "";
    addMsg(`${safe}${srcHtml}`, "assistant");
  }

  function addTyping() {
    const el = document.createElement("div");
    el.className = "sc-msg sc-assistant sc-typing";
    el.innerHTML = `<span class="sc-dot"></span><span class="sc-dot"></span><span class="sc-dot"></span>`;
    messagesEl.appendChild(el);
    scrollToBottom();
    return el;
  }

  function autosize() {
    input.style.height = "auto";
    input.style.height = Math.min(input.scrollHeight, 160) + "px";
  }

  function pingBubble() {
    bubble.classList.add("sc-ripple");
    setTimeout(() => bubble.classList.remove("sc-ripple"), 350);
  }

  function togglePanel(show) {
    if (show) {
      panel.classList.remove("sc-hidden");
      panel.classList.add("sc-open");
      panel.setAttribute("aria-hidden", "false");
      bubble.setAttribute("aria-expanded", "true");
      setTimeout(() => {
        if (input) input.focus();
      }, 0);
      if (navigator.vibrate) {
        try {
          navigator.vibrate(8);
        } catch {}
      }
    } else {
      panel.classList.remove("sc-open");
      panel.classList.add("sc-hidden");
      panel.setAttribute("aria-hidden", "true");
      bubble.setAttribute("aria-expanded", "false");
    }
  }

  // ===== Events =====
  input.addEventListener("input", autosize);
  autosize();

  bubble.addEventListener("click", () => {
    pingBubble();
    togglePanel(true);
  });

  closeBtn.addEventListener("click", () => togglePanel(false));
  minimizeBtn.addEventListener("click", () => togglePanel(false));

  window.addEventListener("keydown", (e) => {
    if (e.ctrlKey && e.key === "/") {
      e.preventDefault();
      togglePanel(!panel.classList.contains("sc-open"));
    }
  });

  input.addEventListener("keydown", (e) => {
    if (e.key === "Enter" && !e.shiftKey) {
      e.preventDefault();
      form.requestSubmit();
    }
  });

  // ===== Backend =====
  async function sendMessage(text) {
    const now = Date.now();
    if (now - lastSendAt < RATE_MS) return;
    lastSendAt = now;

    addUser(text);
    input.value = "";
    autosize();

    const typing = addTyping();

    try {
      const res = await fetch(API_ENDPOINT, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ message: text, session_id: sessionId }),
        keepalive: true
      });

      if (!res.ok) {
        typing.remove();
        addAssistant(`Erreur ${res.status} — impossible de joindre le service. Réessayez.`);
        return;
      }

      let data = {};
      try {
        data = await res.json();
      } catch {
        data = {};
      }

      typing.remove();

      const answer =
        typeof data.answer === "string"
          ? data.answer
          : typeof data.message === "string"
          ? data.message
          : "(réponse vide)";
      const sources = Array.isArray(data.sources) ? data.sources : [];
      addAssistant(answer, sources);
    } catch (err) {
      typing.remove();
      // eslint-disable-next-line no-console
      console.error("[StormCopilot] Network error:", err);
      addAssistant("Erreur réseau. Vérifiez votre connexion et réessayez.");
    }
  }

  form.addEventListener("submit", (e) => {
    e.preventDefault();
    const text = input.value.trim();
    if (!text) return;
    sendMessage(text);
  });

  // ===== Message de bienvenue =====
  addAssistant(WELCOME);
})();