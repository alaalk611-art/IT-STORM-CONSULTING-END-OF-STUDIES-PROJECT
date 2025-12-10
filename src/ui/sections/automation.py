# -*- coding: utf-8 -*-
# Path: src/ui/sections/automation.py
# Version Premium • StormCopilot Automation Studio

from __future__ import annotations
import os
import json
from datetime import datetime
from typing import Dict, Any, List

import streamlit as st
import requests

from src.automation.engine import run_workflow, get_all_workflows
from src.automation.logs import load_logs

N8N_BASE = os.getenv("N8N_BASE_URL", "http://127.0.0.1:5678").rstrip("/")

# --------------------------------------------------------------------
#  CSS PREMIUM — Glassmorphism, cards animées, boutons pulsés
# --------------------------------------------------------------------
def _inject_css():
    st.markdown(
        """
        <style>

        /* ---- Global fade ---- */
        .fade-in {
            animation: fadeIn 0.6s ease-out;
        }
        @keyframes fadeIn {
            from {opacity: 0; transform: translateY(8px);}
            to   {opacity: 1; transform: translateY(0);}
        }

        /* ---- Dashboard Container ---- */
        .dash-card {
            background: rgba(255,255,255,0.08);
            border: 1px solid rgba(255,255,255,0.18);
            backdrop-filter: blur(14px);
            border-radius: 18px;
            padding: 22px;
            margin-bottom: 1.2rem;
            box-shadow: 0 8px 35px rgba(0,0,0,0.22);
            transition: transform .25s ease, box-shadow .25s ease;
        }
        .dash-card:hover {
            transform: translateY(-3px);
            box-shadow: 0 12px 45px rgba(0,0,0,0.28);
        }

        /* ---- Titles ---- */
        .dash-title {
            font-size: 1.45rem;
            font-weight: 700;
            margin-bottom: 6px;
            background: linear-gradient(90deg,#38bdf8,#818cf8,#a855f7);
            -webkit-background-clip: text;
            color: transparent;
            text-align: center;          /* ✅ centré */


        }

        /* ---- Metrics line ---- */
        .metric-line {
            display: flex;
            gap: 0.7rem;
            flex-wrap: wrap;
            font-size: 0.88rem;
            margin-top: 8px;
        }

        /* ---- Buttons ---- */
        .pulse-btn > button {
            background: linear-gradient(90deg,#1e40af,#3b82f6,#60a5fa);
            border-radius: 999px !important;
            color: white !important;
            font-weight: 600 !important;
            padding: 0.55rem 1.2rem !important;
            border: none !important;
            animation: pulse 2.2s infinite ease-in-out;
            box-shadow: 0 0 0 rgba(30,64,175,0.35);
        }

        @keyframes pulse {
            0% { box-shadow: 0 0 0 0 rgba(59,130,246,0.45); }
            70% { box-shadow: 0 0 0 12px rgba(59,130,246,0); }
            100% { box-shadow: 0 0 0 0 rgba(59,130,246,0); }
        }

        /* Code block styling */
        .json-block {
            background: rgba(15,23,42,0.65);
            padding: 1rem;
            border-radius: 12px;
            font-size: 0.85rem;
            color: #e2e8f0;
            margin-top: 1rem;
        }

        </style>
        """,
        unsafe_allow_html=True,
    )

# --------------------------------------------------------------------
#  Helpers Webhooks
# --------------------------------------------------------------------
def call_n8n(url: str, payload: dict | None = None, timeout: int = 90):
    try:
        r = requests.post(url, json=payload or {}, timeout=timeout)
        r.raise_for_status()
        return r.json()
    except Exception as e:
        return {"status": "error", "error": str(e)}


def _unwrap_n8n(data: Any) -> Dict[str, Any]:
    """
    Normalise les réponses n8n :
    - [ { "json": {...} } ] → {...}
    - [ {...} ] → {...}
    - { "json": {...} } → {...}
    - { ... } → {...}
    """
    # Cas liste (réponse allEntries)
    if isinstance(data, list) and data:
        first = data[0]
        if isinstance(first, dict):
            inner = first.get("json")
            if isinstance(inner, dict):
                return inner
            return first

    # Cas dict simple
    if isinstance(data, dict):
        inner = data.get("json")
        if isinstance(inner, dict):
            return inner
        return data

    # Fallback
    return {}

# --------------------------------------------------------------------
# Pretty rendering helpers
# --------------------------------------------------------------------
def _metric(label: str, value: Any, icon: str = "•"):
    return f"<span>{icon} <b>{label}</b> : {value}</span>"

# --------------------------------------------------------------------
#  DASHBOARD TECH RADAR (Premium)
# --------------------------------------------------------------------
# --------------------------------------------------------------------
#  DASHBOARD TECH RADAR (Premium, style onglet Tech)
# --------------------------------------------------------------------
def render_tech_radar() -> None:
    """
    Carte Tech Radar n8n dans Automation Studio.
    - Bouton "Rafraîchir maintenant" qui appelle le webhook /tech-radar
    - Affiche les 4 tuiles Sources / Hot / Trending / Qualité
    - Résumé texte + JSON brut en expander
    """
    state_key = "automation_tech_radar_payload"

    st.markdown('<div class="dash-card fade-in">', unsafe_allow_html=True)
    st.markdown('<div class="dash-title">⚡ Tech Radar — n8n</div>', unsafe_allow_html=True)

    # --- Bouton pour lancer le webhook ---
    with st.container():
        st.markdown('<div class="pulse-btn">', unsafe_allow_html=True)
        if st.button("🔄 Rafraîchir maintenant", key="refresh_tech"):
            with st.spinner("Interrogation du workflow n8n « Tech Radar - IT-STORM »..."):
                raw = call_n8n(
                    f"{N8N_BASE}/webhook/tech-radar",
                    payload={"scope": "tech_only", "timeout": 90},
                    timeout=120,
                )
            st.session_state[state_key] = raw
        st.markdown("</div>", unsafe_allow_html=True)

    raw = st.session_state.get(state_key)
    if not raw:
        st.caption("Clique sur « Rafraîchir maintenant » pour lancer le Tech Radar.")
        st.markdown("</div>", unsafe_allow_html=True)
        return

    # Normalisation de la réponse n8n
    item = _unwrap_n8n(raw)
    if not isinstance(item, dict) or not item:
        st.error("Réponse Tech Radar inattendue.")
        with st.expander("🔍 JSON brut (réponse n8n)", expanded=False):
            st.json(raw)
        st.markdown("</div>", unsafe_allow_html=True)
        return

    status = str(item.get("status") or "unknown")
    quality = str(item.get("quality") or "Inconnu")
    headline = str(item.get("headline") or "Veille technique : statut inconnu.")
    metrics = item.get("metrics") or {}

    sources_total = int(metrics.get("sources_total") or 0)
    sources_ok = int(metrics.get("sources_ok") or 0)
    hot = int(metrics.get("hot") or 0)
    trending = int(metrics.get("trending") or 0)
    fresh = int(metrics.get("fresh") or 0)
    duration_sec = metrics.get("duration_sec")
    truncated = bool(metrics.get("truncated", False))
    fetched_at = item.get("fetched_at")

    # 4 tuiles colorées comme dans l’onglet Tech Radar
    col1, col2, col3, col4 = st.columns(4)

    with col1:
        st.markdown(
            """
            <div style="
                background: linear-gradient(135deg,#2563eb,#38bdf8);
                border-radius: 16px;
                padding: 14px 16px;
                color: white;
                box-shadow: 0 10px 30px rgba(37,99,235,0.45);
            ">
                <div style="font-size:0.75rem;opacity:0.9;">🌐 Sources total</div>
                <div style="font-size:1.6rem;font-weight:700;">{total}</div>
                <div style="font-size:0.8rem;opacity:0.9;">{ok} actives</div>
            </div>
            """.format(total=sources_total, ok=sources_ok),
            unsafe_allow_html=True,
        )

    with col2:
        st.markdown(
            """
            <div style="
                background: linear-gradient(135deg,#f97316,#fb923c);
                border-radius: 16px;
                padding: 14px 16px;
                color: white;
                box-shadow: 0 10px 30px rgba(249,115,22,0.45);
            ">
                <div style="font-size:0.75rem;opacity:0.9;">🔥 Hot</div>
                <div style="font-size:1.6rem;font-weight:700;">{hot}</div>
                <div style="font-size:0.8rem;opacity:0.9;">Sources très prioritaires</div>
            </div>
            """.format(hot=hot),
            unsafe_allow_html=True,
        )

    with col3:
        st.markdown(
            """
            <div style="
                background: linear-gradient(135deg,#eab308,#facc15);
                border-radius: 16px;
                padding: 14px 16px;
                color: #1f2933;
                box-shadow: 0 10px 30px rgba(234,179,8,0.45);
            ">
                <div style="font-size:0.75rem;opacity:0.9;">⭐ Trending</div>
                <div style="font-size:1.6rem;font-weight:700;">{trending}</div>
                <div style="font-size:0.8rem;opacity:0.9;">Sources en montée</div>
            </div>
            """.format(trending=trending),
            unsafe_allow_html=True,
        )

    with col4:
        badge = "✅ Complet" if status == "ok" else "⚠️ À vérifier"
        bg = "linear-gradient(135deg,#16a34a,#22c55e)" if status == "ok" else "linear-gradient(135deg,#b91c1c,#ef4444)"
        st.markdown(
            """
            <div style="
                background: {bg};
                border-radius: 16px;
                padding: 14px 16px;
                color: white;
                box-shadow: 0 10px 30px rgba(22,163,74,0.45);
            ">
                <div style="font-size:0.75rem;opacity:0.9;">📊 Qualité globale</div>
                <div style="font-size:1.3rem;font-weight:700;">{badge}</div>
                <div style="font-size:0.8rem;opacity:0.9;">{quality}</div>
            </div>
            """.format(bg=bg, badge=badge, quality=quality),
            unsafe_allow_html=True,
        )

    # Résumé texte façon onglet Tech
    st.markdown("---")
    st.markdown("#### 🧭 Résumé Tech Radar")

    line = f"➜ Veille chargée : {sources_ok}/{sources_total} sources actives. {hot} Hot · {trending} Trending."
    if truncated:
        line += " (résultat tronqué)."
    st.markdown(f"**{line}**")

    bullets = [
        _metric("Sources actives", f"{sources_ok}/{sources_total}", "📡"),
        _metric("Hot", hot, "🔥"),
        _metric("Trending", trending, "⭐"),
        _metric("Fresh", fresh, "🆕"),
    ]
    if duration_sec is not None:
        bullets.append(_metric("Durée moyenne", f"{duration_sec:.1f}s", "⏱"))
    if fetched_at:
        bullets.append(_metric("Dernier rafraîchissement", fetched_at, "🕒"))

    st.markdown(
        '<div class="metric-line">' + " · ".join(bullets) + "</div>",
        unsafe_allow_html=True,
    )

    # JSON brut pour debug
    with st.expander("🔍 JSON brut (réponse n8n)", expanded=False):
        st.json(raw)

    st.markdown("</div>", unsafe_allow_html=True)

# --------------------------------------------------------------------
#  DASHBOARD MARKET RADAR (Premium)
# --------------------------------------------------------------------

def render_market_radar() -> None:
    """
    Carte Market Radar n8n dans Automation Studio.

    - Bouton "Rafraîchir maintenant"
    - Appelle /webhook/market-radar avec symbols = ^FCHI,... / 1d / 1y
    - Gère 2 formats possibles de n8n :
        • dict avec { status, nb_assets, assets: [...] }
        • liste brute de lignes [{symbol, nb_candles, ...}, ...]
    """
    state_key = "automation_market_radar_payload"

    st.markdown('<div class="dash-card fade-in">', unsafe_allow_html=True)
    st.markdown('<div class="dash-title">📈 Market Radar — n8n</div>', unsafe_allow_html=True)

    payload = {
        "symbols": "^FCHI,BNP.PA,AIR.PA,MC.PA,OR.PA,ORA.PA",
        "interval": "1d",
        "period": "1y",
    }

    # --- Bouton pour lancer le webhook ---
    with st.container():
        st.markdown('<div class="pulse-btn">', unsafe_allow_html=True)
        if st.button("🔄 Rafraîchir maintenant", key="refresh_market"):
            with st.spinner("Interrogation du workflow n8n « Market Radar - IT-STORM »..."):
                raw = call_n8n(f"{N8N_BASE}/webhook/market-radar", payload=payload, timeout=120)
            st.session_state[state_key] = raw
        st.markdown("</div>", unsafe_allow_html=True)

    raw = st.session_state.get(state_key)
    if not raw:
        st.caption("Clique sur « Rafraîchir maintenant » pour lancer le Market Radar.")
        st.markdown("</div>", unsafe_allow_html=True)
        return

    # ----------------------------------------------------------------
    #  Normalisation de la réponse n8n
    # ----------------------------------------------------------------
    assets: List[Dict[str, Any]] = []
    status = "ok"

    # Cas 1 : réponse = liste brute [{...}, {...}, ...]
    if isinstance(raw, list):
        for it in raw:
            if isinstance(it, dict):
                row = it.get("json", it)
                assets.append(row)

    # Cas 2 : réponse = dict (éventuellement avec "assets")
    elif isinstance(raw, dict):
        data = _unwrap_n8n(raw)
        status = str(data.get("status") or "ok")
        tmp_assets = data.get("assets")
        if isinstance(tmp_assets, list):
            assets = tmp_assets
        else:
            # fallback : si jamais le dict lui-même ressemble à une "ligne"
            assets = [data]

    else:
        st.error(f"Format de réponse inattendu depuis n8n : {type(raw)}")
        with st.expander("🔍 JSON brut (réponse n8n)", expanded=False):
            st.json(raw)
        st.markdown("</div>", unsafe_allow_html=True)
        return

    nb_assets = len(assets)
    if nb_assets == 0:
        st.warning("Aucun actif retourné par n8n.")
        with st.expander("🔍 JSON brut (réponse n8n)", expanded=False):
            st.json(raw)
        st.markdown("</div>", unsafe_allow_html=True)
        return

    # Comptage OK / erreur (error_message ou error_status non nuls)
    nb_err = 0
    for a in assets:
        if a.get("error_status") or a.get("error_message"):
            nb_err += 1
    nb_ok = nb_assets - nb_err

    # ----------------------------------------------------------------
    #  Tuiles récap (comme ton onglet Market)
    # ----------------------------------------------------------------
    col1, col2, col3 = st.columns(3)

    with col1:
        st.markdown(
            """
            <div style="
                background: linear-gradient(135deg,#2563eb,#38bdf8);
                border-radius: 16px;
                padding: 14px 16px;
                color: white;
                box-shadow: 0 10px 30px rgba(37,99,235,0.45);
            ">
                <div style="font-size:0.75rem;opacity:0.9;">🌍 Actifs total</div>
                <div style="font-size:1.8rem;font-weight:700;">{n}</div>
                <div style="font-size:0.8rem;opacity:0.9;">1d · 1y</div>
            </div>
            """.format(n=nb_assets),
            unsafe_allow_html=True,
        )

    with col2:
        st.markdown(
            """
            <div style="
                background: linear-gradient(135deg,#16a34a,#22c55e);
                border-radius: 16px;
                padding: 14px 16px;
                color: white;
                box-shadow: 0 10px 30px rgba(22,163,74,0.45);
            ">
                <div style="font-size:0.75rem;opacity:0.9;">✅ OK (avec données)</div>
                <div style="font-size:1.8rem;font-weight:700;">{n_ok}</div>
                <div style="font-size:0.8rem;opacity:0.9;">Sources yfinance valides</div>
            </div>
            """.format(n_ok=nb_ok),
            unsafe_allow_html=True,
        )

    with col3:
        st.markdown(
            """
            <div style="
                background: linear-gradient(135deg,#b91c1c,#ef4444);
                border-radius: 16px;
                padding: 14px 16px;
                color: white;
                box-shadow: 0 10px 30px rgba(185,28,28,0.45);
            ">
                <div style="font-size:0.75rem;opacity:0.9;">⚠️ En erreur / sans données</div>
                <div style="font-size:1.8rem;font-weight:700;">{n_err}</div>
                <div style="font-size:0.8rem;opacity:0.9;">Timeout / symboles KO</div>
            </div>
            """.format(n_err=nb_err),
            unsafe_allow_html=True,
        )

    # ----------------------------------------------------------------
    #  Tableau de détail par symbole (à partir du JSON n8n)
    # ----------------------------------------------------------------
    # ----------------------------------------------------------------
#  Tableau de détail par symbole (à partir du JSON n8n)
# ----------------------------------------------------------------
    st.markdown("---")
    st.markdown("#### 📊 Détail par symbole (réponse n8n)")

    import pandas as pd
    rows = []
    for row in assets:
        rows.append(
            {
                "symbol": row.get("symbol"),
                "nb_candles": row.get("nb_candles"),
                "source": row.get("source"),
                "interval": row.get("interval"),
                "period": row.get("period"),
                "signal": row.get("signal"),
                "trend": row.get("trend"),
                "pct_change": row.get("pct_change"),
                "volatility": row.get("volatility"),
                "error_message": row.get("error_message"),
                "error_status": row.get("error_status"),
                "fetched_at": row.get("fetched_at"),
            }
        )
    df = pd.DataFrame(rows)

    # 👉 Rendre l’index humain (1, 2, 3…)
    df.index = df.index + 1

    # 👉 Affichage plus moderne que st.table()
    st.dataframe(df, use_container_width=True)

    # JSON brut pour debug
    with st.expander("🔍 JSON brut (réponse n8n)", expanded=False):
        st.json(raw)

    st.markdown("</div>", unsafe_allow_html=True)


# --------------------------------------------------------------------
#  DASHBOARD DAILY FULL (Premium, Tech + Market)
# --------------------------------------------------------------------

def render_daily_full() -> None:
    """
    Carte Daily Full (workflow combiné Tech + Market).
    - Bouton "Exécuter Daily Full" qui appelle /webhook/daily-full
    - 4 tuiles : Quality, Hot, Trending, Actifs marché
    - Résumé texte + JSON brut
    """
    state_key = "automation_daily_full_payload"

    st.markdown('<div class="dash-card fade-in">', unsafe_allow_html=True)
    st.markdown('<div class="dash-title">🛰 Daily Full — Tech + Market</div>', unsafe_allow_html=True)

    # --- Bouton ---
    with st.container():
        st.markdown('<div class="pulse-btn">', unsafe_allow_html=True)
        if st.button("🔄 Exécuter Daily Full", key="refresh_full"):
            with st.spinner("Lancement du workflow n8n « StormCopilot Daily Full »..."):
                raw = call_n8n(f"{N8N_BASE}/webhook/daily-full", payload={}, timeout=160)
            st.session_state[state_key] = raw
        st.markdown("</div>", unsafe_allow_html=True)

    raw = st.session_state.get(state_key)
    if not raw:
        st.caption("Clique sur « Exécuter Daily Full » pour lancer le workflow combiné.")
        st.markdown("</div>", unsafe_allow_html=True)
        return

    data = _unwrap_n8n(raw)
    if not isinstance(data, dict) or not data:
        st.error("Réponse Daily Full inattendue.")
        with st.expander("🔍 JSON brut (réponse n8n)", expanded=False):
            st.json(raw)
        st.markdown("</div>", unsafe_allow_html=True)
        return

    tech = data.get("tech_radar", {}) or {}
    market = data.get("market_radar", {}) or {}
    if isinstance(market, list) and market:
        market = market[0]

    gen = data.get("generated_at", "")
    if gen:
        st.caption(f"Généré : {gen}")

    # --- métriques Tech ---
    t_quality = str(tech.get("quality") or "Inconnu")
    t_metrics = tech.get("metrics", {}) or {}
    hot = int(t_metrics.get("hot") or 0)
    trending = int(t_metrics.get("trending") or 0)
    fresh = int(t_metrics.get("fresh") or 0)

    # --- métriques Market ---
    m_assets = int(market.get("nb_assets") or 0)

    # ----------------------------------------------------------------
    #  4 tuiles colorées, comme Tech / Market
    # ----------------------------------------------------------------
    c1, c2, c3, c4 = st.columns(4)

    with c1:
        bg = "linear-gradient(135deg,#16a34a,#22c55e)" if "omplet" in t_quality else "linear-gradient(135deg,#eab308,#facc15)"
        label = "✅ Complet" if "omplet" in t_quality else t_quality
        st.markdown(
            """
            <div style="
                background: {bg};
                border-radius: 16px;
                padding: 14px 16px;
                color: white;
                box-shadow: 0 10px 30px rgba(22,163,74,0.45);
            ">
                <div style="font-size:0.75rem;opacity:0.9;">⚙️ Tech Quality</div>
                <div style="font-size:1.4rem;font-weight:700;">{label}</div>
                <div style="font-size:0.8rem;opacity:0.9;">Synthèse n8n</div>
            </div>
            """.format(bg=bg, label=label),
            unsafe_allow_html=True,
        )

    with c2:
        st.markdown(
            """
            <div style="
                background: linear-gradient(135deg,#f97316,#fb923c);
                border-radius: 16px;
                padding: 14px 16px;
                color: white;
                box-shadow: 0 10px 30px rgba(249,115,22,0.45);
            ">
                <div style="font-size:0.75rem;opacity:0.9;">🔥 Hot</div>
                <div style="font-size:1.8rem;font-weight:700;">{hot}</div>
                <div style="font-size:0.8rem;opacity:0.9;">Sources Tech très prioritaires</div>
            </div>
            """.format(hot=hot),
            unsafe_allow_html=True,
        )

    with c3:
        st.markdown(
            """
            <div style="
                background: linear-gradient(135deg,#eab308,#facc15);
                border-radius: 16px;
                padding: 14px 16px;
                color: #1f2933;
                box-shadow: 0 10px 30px rgba(234,179,8,0.45);
            ">
                <div style="font-size:0.75rem;opacity:0.9;">⭐ Trending</div>
                <div style="font-size:1.8rem;font-weight:700;">{tr}</div>
                <div style="font-size:0.8rem;opacity:0.9;">Sources en montée</div>
            </div>
            """.format(tr=trending),
            unsafe_allow_html=True,
        )

    with c4:
        st.markdown(
            """
            <div style="
                background: linear-gradient(135deg,#2563eb,#38bdf8);
                border-radius: 16px;
                padding: 14px 16px;
                color: white;
                box-shadow: 0 10px 30px rgba(37,99,235,0.45);
            ">
                <div style="font-size:0.75rem;opacity:0.9;">📊 Actifs marché</div>
                <div style="font-size:1.8rem;font-weight:700;">{assets}</div>
                <div style="font-size:0.8rem;opacity:0.9;">Couverture Daily Full</div>
            </div>
            """.format(assets=m_assets),
            unsafe_allow_html=True,
        )

    # ----------------------------------------------------------------
    #  Résumé texte
    # ----------------------------------------------------------------
    st.markdown("---")
    st.markdown("#### 🧭 Résumé Daily Full")

    st.markdown(
        f"• **Tech** : {hot} Hot · {trending} Trending · Fresh {fresh}.  \n"
        f"• **Marché** : {m_assets} actifs couverts sur l’univers configuré.",
    )

    # JSON brut
    with st.expander("🔍 JSON brut (réponse n8n)", expanded=False):
        st.json(raw)

    st.markdown("</div>", unsafe_allow_html=True)

# --------------------------------------------------------------------
#  RÉSULTAT D’UN WORKFLOW (Premium)
# --------------------------------------------------------------------
def render_execution_result(result: Dict[str, Any] | None):
    st.markdown('<div class="dash-card fade-in">', unsafe_allow_html=True)
    st.markdown('<div class="dash-title">📊 Résultat d’exécution</div>', unsafe_allow_html=True)

    if not result:
        st.caption("Aucun workflow exécuté pour le moment.")
        st.markdown("</div>", unsafe_allow_html=True)
        return

    wf_name = result.get("workflow_name", "Sans nom")
    executed_at = result.get("executed_at", "?")

    st.markdown(f"**Workflow :** {wf_name}")
    st.caption(f"📅 Exécuté à : `{executed_at}`")

    logs = result.get("logs", [])

    rows = []
    for step in logs:
        step_type = step.get("step_type", "?")
        status = step.get("result", {}).get("status", "unknown")
        rows.append(f"• **{step_type}** → `{status}`")

    if rows:
        st.markdown("<br>".join(rows), unsafe_allow_html=True)
    else:
        st.caption("Aucune étape détectée.")

    with st.expander("🔍 Voir les logs détaillés (JSON)", expanded=False):
        st.markdown('<div class="json-block">', unsafe_allow_html=True)
        st.json(result)
        st.markdown("</div>", unsafe_allow_html=True)

    st.markdown("</div>", unsafe_allow_html=True)

# --------------------------------------------------------------------
#  HISTORIQUE DES EXÉCUTIONS (Premium)
# --------------------------------------------------------------------
def render_logs_history():
    logs = load_logs()

    st.markdown('<div class="dash-card fade-in">', unsafe_allow_html=True)
    st.markdown('<div class="dash-title">📚 Historique des exécutions</div>', unsafe_allow_html=True)

    if not logs:
        st.caption("Aucun log disponible.")
        st.markdown("</div>", unsafe_allow_html=True)
        return

    names = sorted({log.get("workflow_name", "Sans nom") for log in logs})
    selected = st.selectbox(
        "Filtrer par workflow",
        options=["(Tous)"] + names,
        key="logs_filter",
    )

    if selected != "(Tous)":
        logs = [l for l in logs if l.get("workflow_name") == selected]

    for log in logs[:10]:
        wf = log.get("workflow_name", "Sans nom")
        t = log.get("executed_at", "?")

        st.markdown(f"### 🧩 {wf}")
        st.caption(f"⏱ {t}")

        with st.expander("Voir le détail", expanded=False):
            st.markdown('<div class="json-block">', unsafe_allow_html=True)
            st.json(log.get("logs"))
            st.markdown("</div>", unsafe_allow_html=True)

        st.markdown("---")

    st.markdown("</div>", unsafe_allow_html=True)

# --------------------------------------------------------------------
#  WORKFLOWS PAR DÉFAUT (fallback in-memory)
# --------------------------------------------------------------------
RESULT_KEY = "automation_last_result"


# --------------------------------------------------------------------
#  WORKFLOWS PAR DÉFAUT (si aucun workflow stocké)
# --------------------------------------------------------------------
def _default_workflows() -> List[Dict[str, Any]]:
    return [
        {
            "name": "Backend · Tech + Market",
            "trigger": "manual",
            "steps": [
                {
                    "type": "refresh_tech_watch",
                    "params": {"timeout": 120},
                },
                {
                    "type": "refresh_market",
                    "params": {
                        "symbols": "^FCHI,BNP.PA,AIR.PA,MC.PA,OR.PA,ORA.PA",
                        "interval": "1d",
                        "period": "1y",   # 👉 1y
                        "timeout": 30,
                    },
                },
            ],
        },
        {
            "name": "Tech Radar (n8n)",
            "trigger": "manual",
            "steps": [
                {
                    "type": "n8n_webhook",
                    "params": {
                        "url": f"{N8N_BASE}/webhook/tech-radar",
                        "timeout": 120,
                        "payload": {"scope": "tech_only", "timeout": 90},
                    },
                }
            ],
        },
        {
            "name": "Market Radar (n8n)",
            "trigger": "manual",
            "steps": [
                {
                    "type": "n8n_webhook",
                    "params": {
                        "url": f"{N8N_BASE}/webhook/market-radar",
                        "timeout": 120,
                        "payload": {
                            "symbols": "^FCHI,BNP.PA,AIR.PA,MC.PA,OR.PA,ORA.PA",
                            "interval": "1d",
                            "period": "1y",   # 👉 1y
                        },
                    },
                }
            ],
        },
        {
            "name": "Daily Full · Tech + Market (via n8n)",
            "trigger": "manual",
            "steps": [
                {
                    "type": "n8n_webhook",
                    "params": {
                        "url": f"{N8N_BASE}/webhook/daily-full",
                        "timeout": 160,
                        "payload": {},
                    },
                }
            ],
        },
    ]

# --------------------------------------------------------------------
#  TAB PRINCIPAL : Automation Studio Premium
# --------------------------------------------------------------------
def render_automation_tab() -> None:
    _inject_css()

    st.markdown(
        """
        <div class="fade-in" style="margin-bottom: 1.5rem;">
            <h1 style="margin-bottom:0.2rem;">⚙️ StormCopilot · Automation Studio</h1>
            <p style="margin-top:0.2rem;color:rgba(100,116,139,0.95);font-size:0.92rem;">
                Orchestration temps réel entre FastAPI, n8n et les radars Tech & Marché.
            </p>
        </div>
        """,
        unsafe_allow_html=True,
    )

        # ---------------- DASHBOARDS n8n ----------------
    st.markdown("### 🎯 Dashboards n8n en temps réel")

    # 👉 chacun sur sa propre ligne
    render_tech_radar()
    render_market_radar()
    render_daily_full()


    # ---------------- WORKFLOW EXECUTION ----------------