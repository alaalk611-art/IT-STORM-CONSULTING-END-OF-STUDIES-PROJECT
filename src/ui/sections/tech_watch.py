# -*- coding: utf-8 -*-
# ============================================================
# Path: src/ui/sections/tech_watch.py
# Onglet Streamlit : Veille technologique IT-STORM
# Style : Dashboard Enterprise / Power BI (ADN MLOps & Automation)
# ============================================================

from __future__ import annotations
import os
import math
from typing import Any, Dict, List
from datetime import datetime, timezone

import requests
import streamlit as st
import streamlit.components.v1 as components
import numpy as np
import plotly.graph_objects as go
from urllib.parse import urljoin

# ------------------------------------------------------------
# CONFIG API & n8n
# ------------------------------------------------------------
API_BASE = os.getenv("BACKEND_API_BASE_URL", "http://127.0.0.1:8001").rstrip("/")
N8N_BASE = os.getenv("N8N_BASE_URL", "http://127.0.0.1:5678").rstrip("/")


# ------------------------------------------------------------
# CSS – Style Dashboard Enterprise / Power BI (header + tabs + KPI)
# ------------------------------------------------------------
_DASHBOARD_CSS = """
<style>
/* Header style "rapport exécutif" (aligné sur MLOps) */
.tw-header {
    padding: 18px 22px;
    border-radius: 20px;
    background: radial-gradient(circle at top left, #4c6fff11, #0f172a05);
    border: 1px solid rgba(148,163,184,0.35);
    box-shadow: 0 18px 40px rgba(15,23,42,0.12);
    margin-bottom: 1.4rem;
}
.tw-header-title {
    font-size: 1.25rem;
    font-weight: 700;
    color: #0f172a;
    display: flex;
    align-items: center;
    gap: 0.6rem;
}
.tw-header-pill {
    display: inline-flex;
    align-items: center;
    gap: 0.35rem;
    padding: 0.15rem 0.6rem;
    border-radius: 999px;
    background: rgba(59,130,246,0.08);
    color: #1d4ed8;
    font-size: 0.7rem;
    font-weight: 600;
    text-transform: uppercase;
    letter-spacing: 0.08em;
}
.tw-header-sub {
    font-size: 0.85rem;
    color: #64748b;
    margin-top: 0.35rem;
}

/* Sous-tabs centrés (même ADN que MLOps) */
.stTabs [data-baseweb="tab-list"] {
    justify-content: center;
    gap: 0.5rem;
}
.stTabs [data-baseweb="tab"] {
    border-radius: 999px !important;
    padding: 0.35rem 1.4rem;
    font-weight: 600;
    font-size: 0.9rem;
    background-color: #f8fafc;
    color: #64748b;
    border: 1px solid transparent;
}
.stTabs [data-baseweb="tab"]:hover {
    border-color: rgba(148,163,184,0.6);
}
.stTabs [aria-selected="true"] {
    background: linear-gradient(135deg, #4c6fff, #c471f5) !important;
    color: white !important;
    box-shadow: 0 10px 30px rgba(59,130,246,0.35);
}

/* KPI cards (alignées sur mlops-kpi-card) */
.tw-kpi-card {
    border-radius: 18px;
    padding: 0.9rem 1.1rem;
    background: rgba(255,255,255,0.96);
    box-shadow: 0 14px 35px rgba(15,23,42,0.08);
    border: 1px solid rgba(148,163,184,0.3);
    position: relative;
    overflow: hidden;
}
.tw-kpi-card::after {
    content: "";
    position: absolute;
    inset: -40%;
    opacity: 0.08;
    background: radial-gradient(circle at top right, #4c6fff, transparent 55%);
    pointer-events: none;
}
.tw-kpi-label {
    font-size: 0.75rem;
    text-transform: uppercase;
    letter-spacing: 0.06em;
    color: #64748b;
    margin-bottom: 0.25rem;
}
.tw-kpi-value {
    font-size: 1.25rem;
    font-weight: 700;
    color: #0f172a;
}
.tw-kpi-sub {
    font-size: 0.75rem;
    color: #94a3b8;
}
.tw-kpi-icon {
    position: absolute;
    right: 12px;
    top: 10px;
    font-size: 1.2rem;
    opacity: 0.35;
}

/* Boutons actions (pillules) */
.stButton>button {
    border-radius: 999px !important;
    font-weight: 600 !important;
    padding: 0.5rem 1.4rem !important;
}
</style>
"""


# ------------------------------------------------------------
# Helpers dates & scoring temporel
# ------------------------------------------------------------
def _parse_dt(dt_str: str) -> datetime | None:
    """Parse un datetime ISO (avec ou sans 'Z') ou format 'YYYY-MM-DD HH:MM:SS'."""
    if not dt_str:
        return None

    try:
        if dt_str.endswith("Z"):
            dt_str = dt_str[:-1]
        if "T" in dt_str:
            dt = datetime.fromisoformat(dt_str)
        else:
            dt = datetime.fromisoformat(dt_str.replace(" ", "T"))
    except Exception:
        return None

    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    else:
        dt = dt.astimezone(timezone.utc)
    return dt


def _time_decay_factor(dt: datetime | None, window_hours: int) -> float:
    """Facteur de décroissance temporelle entre 0.1 et 1.0 sur une fenêtre donnée."""
    if dt is None:
        return 0.4

    now = datetime.now(timezone.utc)
    delta_h = (now - dt).total_seconds() / 3600.0
    if delta_h <= 0:
        return 1.0
    if delta_h >= window_hours:
        return 0.1

    ratio = 1.0 - (delta_h / window_hours)  # 1 → 0
    return max(0.1, 0.1 + 0.9 * max(0.0, ratio))


def _compute_trending_score(it: Dict[str, Any], base_score: float, window_hours: int) -> float:
    dt = _parse_dt(it.get("published_at") or it.get("created_at") or "")
    decay = _time_decay_factor(dt, window_hours)
    return base_score * decay


def _get_base_score(it: Dict[str, Any]) -> float:
    try:
        return float(it.get("score") or 0.0)
    except Exception:
        return 0.0


def _get_effective_score(it: Dict[str, Any], mode: str) -> float:
    base = _get_base_score(it)
    if mode == "Trending 24h":
        return _compute_trending_score(it, base, window_hours=24)
    if mode == "Trending 48h":
        return _compute_trending_score(it, base, window_hours=48)
    return base


# ------------------------------------------------------------
# Helpers API backend
# ------------------------------------------------------------
def _api_get(path: str, params: Dict[str, Any] | None = None) -> Dict[str, Any]:
    try:
        r = requests.get(f"{API_BASE}{path}", params=params or {}, timeout=60)
        r.raise_for_status()
        return r.json()
    except Exception as e:
        st.error(f"Erreur API (GET {path}) : {e}")
        return {"status": "error"}


def _api_post(path: str, params: Dict[str, Any] | None = None) -> Dict[str, Any]:
    try:
        r = requests.post(f"{API_BASE}{path}", params=params or {}, timeout=180)
        r.raise_for_status()
        return r.json()
    except Exception as e:
        st.error(f"Erreur API (POST {path}) : {e}")
        return {"status": "error"}


# ------------------------------------------------------------
# Helper n8n – Tech Radar
# ------------------------------------------------------------
def call_n8n_tech_radar(scope: str = "tech_only", timeout: int = 90):
    """
    Appelle le workflow n8n 'Tech Radar - IT-STORM' via le webhook
    et renvoie un JSON structuré prêt à utiliser dans Streamlit.
    """
    url = f"{N8N_BASE}/webhook/tech-radar"
    payload = {
        "scope": scope,
        "timeout": timeout,
    }

    try:
        resp = requests.post(url, json=payload, timeout=timeout)
        resp.raise_for_status()
    except Exception as e:
        st.error(f"Erreur appel n8n Tech Radar : {e}")
        return None

    try:
        data = resp.json()
    except Exception:
        st.warning("Réponse n8n Tech Radar non-JSON, contenu brut affiché.")
        return resp.text

    return data


# ------------------------------------------------------------
# CSS — Feed / Cartes
# ------------------------------------------------------------
_TW_CSS = """
<style>
.tw-feed {
    display: flex;
    flex-direction: column;
    gap: 0.8rem;
    margin-top: 0.5rem;
}

/* Carte principale */
.tw-card {
    display: grid;
    grid-template-columns: auto 1fr;
    gap: 0.75rem;
    padding: 0.85rem 1rem;
    border-radius: 12px;
    background: #ffffff;
    border: 1px solid rgba(15, 23, 42, 0.06);
    box-shadow: 0 4px 10px rgba(15, 23, 42, 0.05);
}

/* Colonne gauche (favicon / image) */
.tw-left {
    display: flex;
    align-items: flex-start;
    justify-content: center;
    min-width: 44px;
}
.tw-icon {
    width: 32px;
    height: 32px;
    border-radius: 8px;
    object-fit: cover;
    border: 1px solid rgba(148, 163, 184, 0.5);
}

/* Colonne droite */
.tw-right {
    display: flex;
    flex-direction: column;
    gap: 0.25rem;
}

/* Ligne du haut : bloc, statut, score */
.tw-topline {
    display: flex;
    flex-wrap: wrap;
    gap: 0.35rem;
    align-items: center;
    justify-content: space-between;
}

/* Pilules */
.tw-pill-block {
    font-size: 11px;
    border-radius: 999px;
    padding: 2px 9px;
    background: #eef2ff;
    color: #3730a3;
    font-weight: 500;
}
.tw-pill-rank {
    font-size: 11px;
    border-radius: 999px;
    padding: 2px 9px;
    background: #f1f5f9;
    color: #0f172a;
}
.tw-pill-rank.hot {
    background: #fee2e2;
    color: #b91c1c;
}
.tw-pill-rank.trending {
    background: #fef3c7;
    color: #92400e;
}

/* Score */
.tw-score-chip {
    margin-left: auto;
    font-size: 11px;
    font-weight: 500;
    color: #0f172a;
    display: inline-flex;
    align-items: center;
    gap: 0.3rem;
}
.tw-score-bar {
    width: 90px;
    height: 5px;
    border-radius: 999px;
    background: #e2e8f0;
    overflow: hidden;
}
.tw-score-bar-inner {
    display: block;
    height: 100%;
    border-radius: 999px;
    background: linear-gradient(90deg, #22c55e, #16a34a);
}

/* Titre + lien */
.tw-title a {
    font-size: 14px;
    font-weight: 600;
    color: #0f172a;
    text-decoration: none;
}
.tw-title a:hover {
    text-decoration: underline;
}

/* Métadonnées & résumé */
.tw-meta {
    font-size: 11px;
    color: #6b7280;
}
.tw-summary-short {
    font-size: 12px;
    color: #1f2933;
    margin-top: 2px;
}

/* Tags */
.tw-tags {
    margin-top: 4px;
    display: flex;
    flex-wrap: wrap;
    gap: 4px;
}
.tw-tag {
    font-size: 10px;
    padding: 2px 7px;
    border-radius: 999px;
    background: #f3f4f6;
    color: #4b5563;
}

/* Footer lien */
.tw-link {
    margin-top: 4px;
    font-size: 12px;
}
.tw-link a {
    color: #2563eb;
    text-decoration: none;
}
.tw-link a:hover {
    text-decoration: underline;
}

/* Résumé pagination */
.tw-toolbar {
    display: flex;
    justify-content: space-between;
    align-items: center;
    font-size: 11px;
    color: #4b5563;
    margin-top: 0.4rem;
    margin-bottom: 0.2rem;
}
</style>
"""

# ------------------------------------------------------------
# CSS — TrendRadar™
# ------------------------------------------------------------
_TREND_CSS = """
<style>
.tr-title {
    font-size: 22px;
    font-weight: 800;
    padding-top: 20px;
    padding-bottom: 4px;
    color: #0f172a;
}
.tr-subtitle {
    font-size: 14px;
    color: #475569;
    margin-top: -4px;
    margin-bottom: 16px;
}
.tr-corr-legend {
    font-size: 11px;
    color: #6b7280;
    margin-top: 4px;
}
</style>
"""

# ------------------------------------------------------------
# CSS — Panneau de filtres (plus beau)
# ------------------------------------------------------------
_FILTERS_CSS = """
<style>
.tw-filters-panel {
    padding: 0.75rem 1rem 1rem;
    border-radius: 18px;
    background:
        radial-gradient(circle at 0% 0%, rgba(56,189,248,0.18), transparent 55%),
        radial-gradient(circle at 100% 0%, rgba(129,140,248,0.20), transparent 55%),
        #f8fafc;
    border: 1px solid rgba(148,163,184,0.45);
    box-shadow: 0 14px 40px rgba(15,23,42,0.08);
}

.tw-filters-row {
    display: flex;
    gap: 1.25rem;
    align-items: flex-start;
    flex-wrap: wrap;
    margin-bottom: 0.75rem;
}

.tw-filters-col {
    flex: 1 1 0;
    min-width: 260px;
}

.tw-filters-label {
    font-size: 0.72rem;
    font-weight: 600;
    letter-spacing: 0.08em;
    text-transform: uppercase;
    color: #64748b;
    margin-bottom: 0.15rem;
}

.tw-filters-help {
    font-size: 0.70rem;
    color: #94a3b8;
    margin-top: 0.15rem;
}

.tw-filters-footer {
    display: flex;
    justify-content: space-between;
    gap: 1rem;
    margin-top: 0.75rem;
    flex-wrap: wrap;
}

.tw-filters-footer > div {
    flex: 1 1 0;
    min-width: 240px;
}
</style>
"""

# ------------------------------------------------------------
# Thématiques pour la matrice de corrélation
# ------------------------------------------------------------
_THEME_DEFS: Dict[str, List[str]] = {
    "Cloud & Infrastructure": ["cloud", "cloud_infra", "kubernetes", "docker"],
    "Data & Big Data": ["data_bigdata", "apache-spark", "apache-kafka", "apache-airflow"],
    "DevOps & CI/CD": ["devops", "cicd"],
    "IA / ML / GenAI / RAG": ["ai_genai", "genai", "rag", "hugging-face", "llama", "mistral-ai"],
    "Portage salarial & Freelancing": ["freelance", "portage-salarial", "portage_consulting"],
    "Sécurité / Cloud Security": ["security", "cloud_security", "owasp", "mitre"],
}


# ------------------------------------------------------------
# TrendRadar™ helpers
# ------------------------------------------------------------
def _compute_trends(items: List[Dict[str, Any]]):
    from collections import Counter

    freq = Counter()
    bucket: Dict[str, List[float]] = {}

    for it in items:
        cat = it.get("block_label") or it.get("block") or "Divers"

        if "communautaire" in cat.lower():
            continue

        try:
            s = float(it.get("score") or 0.0)
        except Exception:
            s = 0.0

        freq[cat] += 1
        bucket.setdefault(cat, []).append(s)

    score_mean = {k: (sum(v) / len(v) if v else 0.0) for k, v in bucket.items()}
    return freq, score_mean


def _render_radar_plotly(freq: Dict[str, int], intensity: Dict[str, float]) -> None:
    if not freq:
        st.info("Pas assez de données pour le radar.")
        return

    labels = list(freq.keys())
    values = [max(0.0, min(1.0, float(intensity.get(k, 0.0)))) * 100 for k in labels]

    r = values + [values[0]]
    theta = labels + [labels[0]]

    fig = go.Figure(
        data=go.Scatterpolar(
            r=r,
            theta=theta,
            fill="toself",
            name="Intensité (%)",
            hovertemplate="<b>%{theta}</b><br>Intensité : %{r:.0f}%<extra></extra>",
        )
    )

    fig.update_layout(
        polar=dict(
            radialaxis=dict(visible=True, range=[0, 100], tickfont=dict(size=9)),
            angularaxis=dict(tickfont=dict(size=11)),
        ),
        showlegend=True,
        legend=dict(orientation="h", y=-0.15, x=0.5, xanchor="center"),
        margin=dict(l=40, r=40, t=40, b=80),
        height=420,
    )

    st.plotly_chart(fig, use_container_width=False)


def _render_heatmap(freq: Dict[str, int], intensity: Dict[str, float]) -> None:
    st.markdown("#### 🔥 Heatmap Activité / Intensité")

    if not freq:
        st.info("Pas encore de données pour la heatmap.")
        return

    labels = list(freq.keys())
    z_values = [freq[l] for l in labels]
    texts = [
        f"{l}<br>{freq[l]} posts<br>score moyen {int(intensity.get(l, 0.0) * 100)} %"
        for l in labels
    ]

    fig = go.Figure(
        data=go.Heatmap(
            z=[z_values],
            x=labels,
            y=["Activité"],
            text=[texts],
            texttemplate="%{text}",
            textfont={"size": 10},
            colorscale="Reds",
            showscale=True,
            hovertemplate="%{text}<extra></extra>",
        )
    )
    fig.update_layout(height=260, margin=dict(l=40, r=40, t=10, b=40))
    st.plotly_chart(fig, use_container_width=True)


def _compute_thematic_matrix(items: List[Dict[str, Any]]):
    names = list(_THEME_DEFS.keys())
    n = len(names)
    mat = [[0 for _ in range(n)] for _ in range(n)]

    for it in items:
        tags = set(it.get("tags", []))
        block = (it.get("block_label") or it.get("block") or "").strip()

        present = [False] * n
        for idx, name in enumerate(names):
            kw = _THEME_DEFS[name]
            if block == name:
                present[idx] = True
            elif any(k in tags for k in kw):
                present[idx] = True

        if sum(present) < 2:
            continue

        for i in range(n):
            if present[i]:
                for j in range(n):
                    if present[j]:
                        mat[i][j] += 1

    return names, mat


def _render_thematic_correlation(items: List[Dict[str, Any]]) -> None:
    names, mat = _compute_thematic_matrix(items)
    mat_arr = np.array(mat, dtype=float)

    if not mat_arr.any():
        st.markdown("#### 🔗 Corrélation entre thématiques")
        st.info("Pas encore de co-occurrence significative entre les thématiques.")
        return

    np.fill_diagonal(mat_arr, 0)

    text = []
    for i in range(len(names)):
        row = []
        for j in range(len(names)):
            if i == j:
                row.append("—")
            else:
                row.append(str(int(mat[i][j])))
        text.append(row)

    fig = go.Figure(
        data=go.Heatmap(
            z=mat_arr,
            x=names,
            y=names,
            text=text,
            texttemplate="%{text}",
            textfont={"size": 10},
            colorscale="Blues",
            hovertemplate="(%{y}, %{x})<br>co-occurrences : %{z:.0f}<extra></extra>",
            zmin=0,
        )
    )
    fig.update_layout(
        title="🔗 Corrélation entre thématiques",
        xaxis={"side": "top"},
        yaxis_autorange="reversed",
        height=420,
        margin=dict(l=80, r=40, t=60, b=80),
    )

    st.plotly_chart(fig, use_container_width=True)
    st.markdown(
        "<div class='tr-corr-legend'>Plus la cellule est foncée, plus les deux thématiques co-apparaissent dans les mêmes sources. "
        "La diagonale (même thématique) est affichée comme « — ».</div>",
        unsafe_allow_html=True,
    )


def _render_trend_radar(items: List[Dict[str, Any]]) -> None:
    st.markdown(_TREND_CSS, unsafe_allow_html=True)
    st.markdown("### 📊 TrendRadar™ Premium")
    st.markdown(
        "Radar circulaire, heatmap et corrélation des tendances Cloud, Data, IA, DevOps et Portage salarial."
    )

    if not items:
        st.warning("Aucune donnée disponible pour le TrendRadar.")
        return

    freq, intensity = _compute_trends(items)

    st.markdown("#### 🧭 Radar circulaire")
    _render_radar_plotly(freq, intensity)

    _render_heatmap(freq, intensity)
    _render_thematic_correlation(items)

    st.markdown("#### 🏆 Top catégories actives")
    for k, v in freq.most_common(5):
        st.markdown(f"- **{k}** — {v} nouvelles publications")

    st.markdown("#### ⚡ Intensité technique")
    sorted_int = sorted(intensity.items(), key=lambda x: x[1], reverse=True)
    for k, v in sorted_int[:5]:
        pct = int(max(0.0, min(1.0, float(v))) * 100)
        st.markdown(f"- **{k}** : {pct} %")

    st.divider()


# ------------------------------------------------------------
# Logos Top Trending 24h
# ------------------------------------------------------------
def _render_trending_logos(items: List[Dict[str, Any]], top_n: int = 8) -> None:
    """Affiche les logos des sources les plus trending sur 24h."""
    if not items:
        return

    scored: List[Dict[str, Any]] = []

    for it in items:
        raw_favicon = it.get("og_image") or it.get("favicon_url") or ""
        page_url = it.get("url") or ""

        favicon = None

        if isinstance(raw_favicon, str):
            raw_favicon = raw_favicon.strip()

            # Cas 1 : déjà une URL absolue http(s)
            if raw_favicon.startswith(("http://", "https://")):
                favicon = raw_favicon

            # Cas 2 : chemin relatif ("/images/..." ou "images/...")
            elif raw_favicon.startswith("/") or raw_favicon.startswith("images/"):
                if page_url.startswith(("http://", "https://")):
                    favicon = urljoin(page_url, raw_favicon)

        # Si on n'a toujours rien de propre → on skip
        if not favicon:
            continue

        score_24h = _get_effective_score(it, "Trending 24h")
        if score_24h <= 0:
            continue

        scored.append(
            {
                "item": it,
                "favicon": favicon,
                "score_24h": score_24h,
            }
        )

    if not scored:
        return

    scored.sort(key=lambda x: x["score_24h"], reverse=True)
    top = scored[:top_n]

    st.markdown("### 🔥 Top sources Trending 24h")

    cols = st.columns(min(4, len(top)))
    for idx, entry in enumerate(top):
        it = entry["item"]
        favicon = entry["favicon"]
        score_24h = entry["score_24h"]

        col = cols[idx % len(cols)]
        source_name = it.get("source_name") or it.get("block_label") or "Source"
        score_pct = int(max(0.0, min(1.0, score_24h)) * 100)

        with col:
            try:
                st.image(favicon, width=40)
            except Exception:
                st.write("🧩")
            st.caption(f"{source_name}\n{score_pct}/100")


# ------------------------------------------------------------
# Tech Radar (via n8n) — sous-onglet dédié
# ------------------------------------------------------------
def _render_tech_radar_panel() -> None:
    """Sous-onglet complet pour le Tech Radar via n8n."""
    st.markdown("### 🛰️ Tech Radar (via n8n)")
    st.caption(
        "Pilotage de la veille via le workflow n8n « Tech Radar - IT-STORM » "
        "(webhook `/webhook/tech-radar`)."
    )

    col_ctrl1, col_ctrl2 = st.columns([3, 1])
    with col_ctrl1:
        scope = st.selectbox(
            "Scope de la veille",
            ["tech_only", "full"],
            format_func=lambda x: (
                "Veille technique uniquement (Cloud, Data, IA, DevOps)"
                if x == "tech_only"
                else "Tous les contenus (tech + marché / portage)"
            ),
            key="tech_radar_scope",
        )
    with col_ctrl2:
        timeout = st.slider(
            "Timeout n8n (secondes)",
            min_value=30,
            max_value=240,
            value=90,
            step=10,
            key="tech_radar_timeout",
        )

    if not st.button("🚀 Lancer Tech Radar (n8n)", key="btn_tech_radar_n8n"):
        st.info("Configure le scope puis lance le Tech Radar pour voir la synthèse.")
        return

    with st.spinner("Interrogation du workflow n8n et consolidation des métriques…"):
        data = call_n8n_tech_radar(scope=scope, timeout=int(timeout))

    if not data:
        st.info("Tech Radar (via n8n) non disponible pour le moment.")
        return

    # n8n peut renvoyer une liste ou un dict
    item: Dict[str, Any] | None = None
    if isinstance(data, list):
        if data and isinstance(data[0], dict) and "json" in data[0]:
            item = data[0]["json"]
        elif data and isinstance(data[0], dict):
            item = data[0]
    elif isinstance(data, dict):
        item = data

    if not item:
        st.info("Réponse Tech Radar inattendue.")
        st.json(data)
        return

    status = str(item.get("status") or "unknown")
    quality = str(item.get("quality") or "Inconnu")
    headline = str(item.get("headline") or "Etat de la veille inconnu.")
    metrics = item.get("metrics") or {}

    nb_ok = int(metrics.get("nb_ok") or 0)
    nb_err = int(metrics.get("nb_err") or 0)
    sources_total = int(metrics.get("sources_total") or 0)
    sources_ok = int(metrics.get("sources_ok") or nb_ok)
    sources_error = int(metrics.get("sources_error") or nb_err)
    duration_sec = metrics.get("duration_sec")
    truncated = bool(metrics.get("truncated", False))
    hot = int(metrics.get("hot") or 0)
    trending = int(metrics.get("trending") or 0)
    # On garde fresh uniquement pour information interne (JSON debug)
    fresh = int(metrics.get("fresh") or max(0, sources_ok - hot - trending))

    fetched_at = item.get("fetched_at")

    # ----------------- Cartes de synthèse jolies -----------------
    col_a, col_b, col_c, col_d = st.columns(4)

    # Total / actives
    with col_a:
        st.markdown(
            f"""
            <div style="
                background: linear-gradient(135deg,#0d6efd,#4dabf7);
                padding: 18px;
                border-radius: 18px;
                color: white;
                text-align: center;
                box-shadow: 0 10px 30px rgba(13,110,253,0.30);
            ">
                <div style="font-size:0.9rem;opacity:0.9;">🌍 Sources total</div>
                <div style="font-size:2.2rem;font-weight:700;margin-top:4px;">{sources_total}</div>
                <div style="font-size:0.8rem;opacity:0.9;">{sources_ok} actives</div>
            </div>
            """,
            unsafe_allow_html=True,
        )

    # Hot
    with col_b:
        st.markdown(
            f"""
            <div style="
                background: linear-gradient(135deg,#b91c1c,#f97316);
                padding: 18px;
                border-radius: 18px;
                color: white;
                text-align: center;
                box-shadow: 0 10px 30px rgba(248,113,113,0.30);
            ">
                <div style="font-size:0.9rem;opacity:0.9;">🔥 Hot</div>
                <div style="font-size:2.2rem;font-weight:700;margin-top:4px;">{hot}</div>
                <div style="font-size:0.8rem;opacity:0.9;">Sources très prioritaires</div>
            </div>
            """,
            unsafe_allow_html=True,
        )

    # Trending
    with col_c:
        st.markdown(
            f"""
            <div style="
                background: linear-gradient(135deg,#92400e,#facc15);
                padding: 18px;
                border-radius: 18px;
                color: white;
                text-align: center;
                box-shadow: 0 10px 30px rgba(250,204,21,0.30);
            ">
                <div style="font-size:0.9rem;opacity:0.9;">⭐ Trending</div>
                <div style="font-size:2.2rem;font-weight:700;margin-top:4px;">{trending}</div>
                <div style="font-size:0.8rem;opacity:0.9;">Sources en montée</div>
            </div>
            """,
            unsafe_allow_html=True,
        )

    # Qualité / statut
    with col_d:
        if "Complet" in quality:
            bg = "linear-gradient(135deg, #0f5132, #198754)"
            icon = "🟢"
        elif "Vide" in quality:
            bg = "linear-gradient(135deg, #664d03, #ffc107)"
            icon = "🟡"
        else:
            bg = "linear-gradient(135deg, #842029, #dc3545)"
            icon = "🔴"

        st.markdown(
            f"""
            <div style="
                background: {bg};
                padding: 18px;
                border-radius: 18px;
                color: white;
                text-align: center;
                box-shadow: 0 10px 30px rgba(0,0,0,0.25);
            ">
                <div style="font-size:0.9rem;opacity:0.9;">{icon} Qualité globale</div>
                <div style="font-size:1.4rem;font-weight:700;margin-top:4px;">{quality}</div>
                <div style="font-size:0.75rem;opacity:0.9;">Statut API : {status}</div>
            </div>
            """,
            unsafe_allow_html=True,
        )

    st.markdown("---")

    # ----------------- Résumé lisible -----------------
    st.markdown("#### 🧭 Résumé Tech Radar")
    st.markdown(f"**➜ {headline}**")

    bullets = [
        f"- **Sources actives :** {sources_ok}/{sources_total} (erreurs : {sources_error})",
        f"- **Répartition :** {hot} Hot · {trending} Trending",
    ]

    if truncated:
        bullets.append("- ⚠️ Couverture tronquée (limite de sources atteinte).")
    else:
        bullets.append("- ✅ Couverture complète des sources configurées.")
    st.markdown("\n".join(bullets))

    if isinstance(duration_sec, (int, float)):
        st.caption(f"⏱ Durée d'exécution n8n + backend : {duration_sec:.1f} s")

    if fetched_at:
        st.caption(f"🕒 Dernier rafraîchissement consolidé : {fetched_at}")

    # JSON brut pour debug si besoin
    with st.expander("🔍 Détail JSON complet (debug)"):
        st.json(item)


# ------------------------------------------------------------
# RENDER TAB (Dashboard Power BI harmonisé)
# ------------------------------------------------------------
def render() -> None:
    # CSS global dashboard (header + tabs + KPI) + CSS spécifique feed/filters
    st.markdown(_DASHBOARD_CSS, unsafe_allow_html=True)
    st.markdown(_TW_CSS, unsafe_allow_html=True)
    st.markdown(_FILTERS_CSS, unsafe_allow_html=True)

    # Header harmonisé avec MLOps / Automation
    st.markdown(
        """
        <div class="tw-header">
          <div class="tw-header-title">
            <span>🔎 Veille technologique IT-STORM</span>
            <span class="tw-header-pill">Cloud · Data · IA · DevOps · Portage salarial</span>
          </div>
          <div class="tw-header-sub">
            Radar des tendances techniques et du marché du portage salarial pour les consultants IT-STORM,
            avec agrégation automatique des sources, scoring et n8n pour l’orchestration.
          </div>
        </div>
        """,
        unsafe_allow_html=True,
    )

    # Sous-tabs : vue locale + vue n8n (style pillule Power BI)
    tab_local, tab_n8n = st.tabs(
        [
            "📡 TrendRadar & Feed",
            "🛰️ Tech Watch · n8n",
        ]
    )

    # =========================
    # TAB 1 : TrendRadar & Feed
    # =========================
    with tab_local:
        # Ligne d'action + explication
        col1, col2 = st.columns([1, 2])
        with col1:
            if st.button("🔄 Rafraîchir la veille maintenant"):
                with st.spinner("Collecte des sources et génération des résumés."):
                    res_refresh = _api_post("/tech/watch/refresh")

                if res_refresh.get("status") == "ok":
                    nb_ok = int(res_refresh.get("nb_ok", 0) or 0)
                    plural_ok = "source" if nb_ok == 1 else "sources"
                    st.success(f"✅ {nb_ok} {plural_ok} à jour")
                else:
                    st.error("Impossible de rafraîchir la veille. Vérifie le backend.")

        with col2:
            st.info(
                "Ce module agrège automatiquement les nouveautés Cloud, Data, IA, DevOps "
                "et les informations sur le marché du portage salarial pour les consultants IT-STORM."
            )

        # Données détaillées pour TrendRadar, KPI et feed
        res = _api_get("/tech/watch/latest", params={"limit": 120})
        if res.get("status") != "ok":
            st.error("Impossible de charger la veille. Vérifie l'API backend.")
            return

        items: List[Dict[str, Any]] = res.get("items") or []
        if not items:
            st.warning("Aucun résultat disponible. Lance un rafraîchissement pour initialiser la veille.")
            return

        # ----------- KPI Dashboard (Power BI style) -----------
        # Calcul des indicateurs globaux sur la veille
        distinct_sources = {
            (it.get("source_name") or it.get("url") or "").strip()
            for it in items
            if (it.get("source_name") or it.get("url"))
        }
        total_sources = len(distinct_sources)
        total_items = len(items)

        hot_count = sum(
            1 for it in items
            if str(it.get("rank_label", "")).startswith("🔥")
        )
        trending_count = sum(
            1 for it in items
            if str(it.get("rank_label", "")).startswith("⭐")
        )
        fresh_count = sum(
            1 for it in items
            if "Fresh" in str(it.get("rank_label", "🆕 Fresh"))
        )

        generated_at = res.get("generated_at") or res.get("fetched_at") or ""

        k1, k2, k3 = st.columns([1.1, 1.1, 1])
        with k1:
            st.markdown(
                f"""
                <div class="tw-kpi-card">
                  <div class="tw-kpi-icon">🌐</div>
                  <div class="tw-kpi-label">Sources distinctes</div>
                  <div class="tw-kpi-value">{total_sources}</div>
                  <div class="tw-kpi-sub">Sur {total_items} contenus agrégés</div>
                </div>
                """,
                unsafe_allow_html=True,
            )

        with k2:
            st.markdown(
                f"""
                <div class="tw-kpi-card">
                  <div class="tw-kpi-icon">🔥</div>
                  <div class="tw-kpi-label">Hot & Trending</div>
                  <div class="tw-kpi-value">{hot_count} Hot · {trending_count} Trend</div>
                  <div class="tw-kpi-sub">Contenus les plus prioritaires (24–48h)</div>
                </div>
                """,
                unsafe_allow_html=True,
            )

            # ------- KPI 3 : Articles récents 24h --------

            # Calcul du nombre d’items publiés dans les 24 dernières heures
            now = datetime.now(timezone.utc)
            recent_24h = sum(
                1
                for it in items
                if (dt := _parse_dt(it.get("published_at") or it.get("created_at")))
                and (now - dt).total_seconds() <= 24*3600
            )

            with k3:
                st.markdown(
                    f"""
                    <div class="tw-kpi-card">
                    <div class="tw-kpi-icon">🕒</div>
                    <div class="tw-kpi-label">Articles récents (24h)</div>
                    <div class="tw-kpi-value">{recent_24h}</div>
                    <div class="tw-kpi-sub">Nouveautés techniques détectées</div>
                    </div>
                    """,
                    unsafe_allow_html=True,
                )

        st.markdown("")

        # TrendRadar global (radar/heatmap/corrélation)
        _render_trend_radar(items)

        # Logos Trending 24h
        _render_trending_logos(items)

        # ---------------------------- Filtres ----------------------------
        blocks = sorted({it.get("block_label") or it.get("block") or "Autre" for it in items})
        all_tags = sorted({tag for it in items for tag in it.get("tags", [])})
        all_status = sorted({it.get("rank_label", "🆕 Fresh") for it in items})
        default_blocks = [b for b in blocks if "communautaire" not in b.lower()] or blocks

        with st.expander("🧩 Filtres & affichage", expanded=True):
            st.markdown("<div class='tw-filters-panel'>", unsafe_allow_html=True)

            # Ligne principale (thématiques + tags / tri)
            st.markdown("<div class='tw-filters-row'>", unsafe_allow_html=True)
            col_left, col_right = st.columns(2)

            with col_left:
                st.markdown(
                    "<div class='tw-filters-label'>Thématiques à afficher</div>",
                    unsafe_allow_html=True,
                )
                selected_blocks = st.multiselect(
                    " ",
                    options=blocks,
                    default=default_blocks,
                )

                st.markdown(
                    "<div class='tw-filters-label' style='margin-top:0.6rem;'>Statut</div>",
                    unsafe_allow_html=True,
                )
                selected_status = st.multiselect(
                    "  ",
                    options=all_status,
                    default=all_status,
                    help="Filtre sur Hot / Trending / Fresh.",
                )

            with col_right:
                st.markdown(
                    "<div class='tw-filters-label'>Tags</div>",
                    unsafe_allow_html=True,
                )
                selected_tags = st.multiselect(
                    "   ",
                    options=all_tags,
                    default=[],
                    help="Laisse vide pour ne pas filtrer par tag.",
                )

                st.markdown(
                    "<div class='tw-filters-label' style='margin-top:0.6rem;'>Trier par</div>",
                    unsafe_allow_html=True,
                )
                sort_mode = st.selectbox(
                    "    ",
                    [
                        "Trending 24h",
                        "Score décroissant",
                        "Trending 48h",
                        "Plus récents",
                        "Thématique A→Z",
                    ],
                    index=0,  # Trending 24h par défaut
                )

            st.markdown("</div>", unsafe_allow_html=True)  # fin .tw-filters-row

            # Footer : résultats par page + recherche
            st.markdown("<div class='tw-filters-footer'>", unsafe_allow_html=True)
            col_fp, col_fq = st.columns(2)

            with col_fp:
                st.markdown(
                    "<div class='tw-filters-label'>Résultats par page</div>",
                    unsafe_allow_html=True,
                )
                per_page = st.radio(
                    "     ",
                    options=[20, 40, 60],
                    horizontal=True,
                    index=0,
                )

            with col_fq:
                st.markdown(
                    "<div class='tw-filters-label'>Rechercher dans les titres / résumés</div>",
                    unsafe_allow_html=True,
                )
                query = st.text_input(
                    "      ",
                    placeholder="kubernetes, mistral, freelance, spark…",
                )

            st.markdown("</div>", unsafe_allow_html=True)  # fin .tw-filters-footer
            st.markdown("</div>", unsafe_allow_html=True)  # fin .tw-filters-panel

        # ------------------------- Filtrage & tri -------------------------
        def _match(it: Dict[str, Any]) -> bool:
            if selected_blocks:
                if (it.get("block_label") or it.get("block")) not in selected_blocks:
                    return False

            if selected_status:
                if it.get("rank_label", "🆕 Fresh") not in selected_status:
                    return False

            tags = set(it.get("tags", []))
            if selected_tags:
                if not tags.intersection(selected_tags):
                    return False

            if query:
                q = query.lower()
                haystack = " ".join(
                    [
                        str(it.get("source_name") or ""),
                        str(it.get("summary") or ""),
                        str(it.get("short_summary") or ""),
                        str(it.get("block_label") or ""),
                        str(it.get("url") or ""),
                        " ".join(it.get("tags", [])),
                    ]
                ).lower()
                if q not in haystack:
                    return False

            return True

        filtered_items = [it for it in items if _match(it)]
        if not filtered_items:
            st.warning("Aucun résultat ne correspond aux filtres actuels.")
            return

        if sort_mode == "Score décroissant":
            filtered_items.sort(
                key=lambda x: (_get_base_score(x), x.get("created_at", "")),
                reverse=True,
            )
        elif sort_mode == "Plus récents":
            filtered_items.sort(
                key=lambda x: x.get("created_at", ""),
                reverse=True,
            )
        elif sort_mode == "Thématique A→Z":
            filtered_items.sort(
                key=lambda x: (
                    (x.get("block_label") or x.get("block") or ""),
                    -_get_base_score(x),
                )
            )
        elif sort_mode in {"Trending 24h", "Trending 48h"}:
            filtered_items.sort(
                key=lambda x: (
                    _get_effective_score(x, sort_mode),
                    x.get("created_at", ""),
                ),
                reverse=True,
            )

        # ------------------------- Pagination -------------------------
        total = len(filtered_items)
        max_page = max(1, (total + per_page - 1) // per_page)

        key_page = "tech_watch_page"
        if key_page not in st.session_state:
            st.session_state[key_page] = 1
        st.session_state[key_page] = min(st.session_state[key_page], max_page)

        page = st.number_input(
            "Page",
            min_value=1,
            max_value=max_page,
            value=st.session_state[key_page],
            step=1,
        )
        st.session_state[key_page] = page

        start = (page - 1) * per_page
        end = start + per_page
        page_items = filtered_items[start:end]

        st.markdown(
            "<div class='tw-toolbar'>"
            f"<span>{total} résultats · page {int(page)}/{max_page}</span>"
            "</div>",
            unsafe_allow_html=True,
        )

        # ------------------------- Cartes -------------------------
        st.markdown("<div class='tw-feed'>", unsafe_allow_html=True)

        for it in page_items:
            title = it.get("source_name") or it.get("url") or "Source"
            url = it.get("url") or "#"
            block_label = it.get("block_label") or it.get("block") or "Divers"
            created_at = (it.get("created_at") or "")[:19].replace("T", " ")
            tags = it.get("tags", []) or []

            short_summary = (
                it.get("short_summary")
                or ((it.get("summary") or "")[:280] + "…") if it.get("summary") else ""
            )

            base_score = _get_base_score(it)
            score_pct = int(max(0.0, min(1.0, base_score)) * 100)

            rank_label = it.get("rank_label") or "🆕 Fresh"
            risk_login = bool(it.get("risk_login"))
            favicon = it.get("og_image") or it.get("favicon_url") or ""

            rank_class = ""
            if str(rank_label).startswith("🔥"):
                rank_class = "hot"
            elif str(rank_label).startswith("⭐"):
                rank_class = "trending"

            if tags:
                chips = " ".join(f"<span class='tw-tag'>{t}</span>" for t in tags)
                tags_html = f"<div class='tw-tags'>{chips}</div>"
            else:
                tags_html = ""

            risk_html = ""
            if risk_login:
                risk_html = (
                    "<span style='font-size:11px;padding:2px 8px;border-radius:999px;"
                    "background:#fee2e2;color:#b91c1c;font-weight:500;margin-left:6px;'>"
                    "⚠ login/cookies</span>"
                )

            img_html = f'<img src="{favicon}" class="tw-icon" />' if favicon else ""

            card_html = (
                '<div class="tw-card">'
                '<div class="tw-left">'
                f"{img_html}"
                "</div>"
                '<div class="tw-right">'
                '<div class="tw-topline">'
                f'<span class="tw-pill-block">{block_label}</span>'
                f'<span class="tw-pill-rank {rank_class}">{rank_label}</span>'
                f"{risk_html}"
                '<span class="tw-score-chip">'
                f"Score {score_pct}/100"
                '<span class="tw-score-bar">'
                f'<span class="tw-score-bar-inner" style="width:{score_pct}%;"></span>'
                "</span>"
                "</span>"
                "</div>"
                '<div class="tw-title">'
                f'<a href="{url}" target="_blank">🔹 {title}</a>'
                "</div>"
                f'<div class="tw-meta">🕒 {created_at} UTC</div>'
                f'<div class="tw-summary-short">{short_summary}</div>'
                f"{tags_html}"
                '<div class="tw-link">'
                f'<a href="{url}" target="_blank">🔗 Ouvrir la source</a>'
                "</div>"
                "</div>"
                "</div>"
            )

            st.markdown(card_html, unsafe_allow_html=True)

        st.markdown("</div>", unsafe_allow_html=True)

    # =========================
    # TAB 2 : Tech Watch · n8n
    # =========================
    with tab_n8n:
        _render_tech_radar_panel()
