# src/ui/sections/mlops.py
from __future__ import annotations

import os
import glob
from datetime import datetime
import re

import requests
import streamlit as st
import pandas as pd
import mlflow

# ------------------------------------------------------------
# CONFIG
# ------------------------------------------------------------
API_BASE = os.getenv("BACKEND_API_BASE_URL", "http://127.0.0.1:8001").rstrip("/")
N8N_BASE = os.getenv("N8N_BASE_URL", "http://127.0.0.1:5678").rstrip("/")
MLFLOW_URI = os.getenv("MLFLOW_STORE", "sqlite:///mlruns.db")
MLFLOW_UI_URL = os.getenv("MLFLOW_UI_URL", "http://127.0.0.1:5000")


# ------------------------------------------------------------
# CSS – style Dashboard
# ------------------------------------------------------------
def _inject_local_css():
    st.markdown(
        """
        <style>
        .mlops-header {
            padding: 18px 22px;
            border-radius: 20px;
            background: radial-gradient(circle at top left, #4c6fff11, #0f172a05);
            border: 1px solid rgba(148,163,184,0.35);
            box-shadow: 0 18px 40px rgba(15,23,42,0.12);
            margin-bottom: 1.4rem;
        }
        .mlops-header-title {
            font-size: 1.25rem;
            font-weight: 700;
            color: #0f172a;
            display: flex;
            align-items: center;
            gap: 0.6rem;
        }
        .mlops-header-pill {
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
        .mlops-header-sub {
            font-size: 0.85rem;
            color: #64748b;
            margin-top: 0.35rem;
        }

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

        .mlops-kpi-card {
            border-radius: 18px;
            padding: 0.9rem 1.1rem;
            background: rgba(255,255,255,0.96);
            box-shadow: 0 14px 35px rgba(15,23,42,0.08);
            border: 1px solid rgba(148,163,184,0.3);
            position: relative;
            overflow: hidden;
        }
        .mlops-kpi-card::after {
            content: "";
            position: absolute;
            inset: -40%;
            opacity: 0.08;
            background: radial-gradient(circle at top right, #4c6fff, transparent 55%);
            pointer-events: none;
        }
        .mlops-kpi-label {
            font-size: 0.75rem;
            text-transform: uppercase;
            letter-spacing: 0.06em;
            color: #64748b;
            margin-bottom: 0.25rem;
        }
        .mlops-kpi-value {
            font-size: 1.25rem;
            font-weight: 700;
            color: #0f172a;
        }
        .mlops-kpi-sub {
            font-size: 0.75rem;
            color: #94a3b8;
        }
        .mlops-kpi-icon {
            position: absolute;
            right: 12px;
            top: 10px;
            font-size: 1.2rem;
            opacity: 0.35;
        }

        .mlops-panel {
            border-radius: 16px;
            border: 1px solid rgba(148,163,184,0.45);
            padding: 0.9rem 1.1rem;
            background: #f8fafc;
        }
        .mlops-panel-title {
            font-weight: 600;
            font-size: 0.88rem;
            color: #0f172a;
            margin-bottom: 0.35rem;
        }
        .mlops-panel-sub {
            font-size: 0.8rem;
            color: #64748b;
        }
        </style>
        """,
        unsafe_allow_html=True,
    )


# ------------------------------------------------------------
# Helpers généraux
# ------------------------------------------------------------
def _get_champions_summary():
    """Résumé global des champions côté backend."""
    try:
        res = requests.get(f"{API_BASE}/mlops/champions", timeout=8).json()
        if not res:
            return {"count": 0, "best_sil": None, "best_symbol": None}
        count = len(res)
        best_sym = None
        best_sil = None
        for sym, data in res.items():
            metrics = data.get("metrics", {})
            sil = metrics.get("silhouette")
            if sil is None:
                continue
            if best_sil is None or sil > best_sil:
                best_sil = sil
                best_sym = sym
        return {"count": count, "best_sil": best_sil, "best_symbol": best_sym}
    except Exception:
        return {"count": 0, "best_sil": None, "best_symbol": None}


def _get_last_monitoring_file():
    """Dernier fichier csv dans mlops_metrics/."""
    try:
        files = sorted(glob.glob("mlops_metrics/*.csv"))
        if not files:
            return None, None
        last = files[-1]
        basename = os.path.basename(last)
        date_part = basename.replace("daily_", "").replace(".csv", "")
        return last, date_part
    except Exception:
        return None, None


def _sanitize_name(name: str) -> str:
    """Même logique que côté backend pour les noms de métriques MLflow."""
    return re.sub(r"[^0-9A-Za-z_-]", "_", name)


def _load_mlflow_history_for_symbol(symbol: str, limit: int = 50) -> pd.DataFrame:
    """
    Historique MLflow pour un symbole : silhouette + recon AE.
    Utilise l'expérience 'StormCopilot_Market_MLOps'.
    """
    try:
        mlflow.set_tracking_uri(MLFLOW_URI)
        exp = mlflow.get_experiment_by_name("StormCopilot_Market_MLOps")
        if exp is None:
            return pd.DataFrame()

        runs = mlflow.search_runs(
            experiment_ids=[exp.experiment_id],
            order_by=["start_time DESC"],
            max_results=limit,
        )
        if runs.empty:
            return pd.DataFrame()

        safe_sym = _sanitize_name(symbol)
        sil_col = f"metrics.{safe_sym}_silhouette"
        ae_col = f"metrics.{safe_sym}_ae_recon"

        cols = [
            "run_id",
            "start_time",
            "params.quick_mode",
            "params.symbols",
        ]
        for c in (sil_col, ae_col):
            if c in runs.columns:
                cols.append(c)

        df = runs[cols].copy()
        df["start_time"] = pd.to_datetime(df["start_time"], unit="ms")

        df["silhouette"] = df[sil_col] if sil_col in df.columns else None
        df["ae_reconstruction"] = df[ae_col] if ae_col in df.columns else None

        df.rename(
            columns={
                "params.quick_mode": "quick_mode",
                "params.symbols": "symbols",
            },
            inplace=True,
        )

        return df
    except Exception:
        return pd.DataFrame()


# ------------------------------------------------------------
# RENDU – Résumé d'entraînement
# ------------------------------------------------------------
def _render_train_summary(title: str, payload):
    """Résumé lisible du résultat d’un entraînement MLOps."""
    st.markdown(f"### 🧾 Résumé {title}")

    if payload is None:
        st.info("Aucune donnée retournée par le backend.")
        return

    meta_keys = ["run_id", "timestamp", "experiment", "quick", "quick_mode"]
    meta = {k: payload.get(k) for k in meta_keys if k in payload}

    if meta:
        st.markdown("#### 🔍 Métadonnées du run")
        st.dataframe(pd.DataFrame([meta]), use_container_width=True)

    if "per_symbol" in payload and isinstance(payload["per_symbol"], dict):
        per_symbol = payload["per_symbol"]
        rows = []
        for sym, info in per_symbol.items():
            metrics = info.get("metrics", {})
            sil = metrics.get("silhouette")
            recon = metrics.get("ae_reconstruction")
            version = info.get("version")

            if sil is None:
                sil_emoji = "❔"
            elif sil > 0.35:
                sil_emoji = "👍"
            elif sil > 0.20:
                sil_emoji = "🙂"
            else:
                sil_emoji = "⚠️"

            if recon is None:
                recon_emoji = "❔"
            elif recon < 0.005:
                recon_emoji = "🟢"
            elif recon <= 0.010:
                recon_emoji = "🟡"
            else:
                recon_emoji = "🔴"

            ver_emoji = f"🧬 v{version}" if version is not None else "–"

            rows.append(
                {
                    "Symbole": sym,
                    "Silhouette": f"{sil_emoji} {sil:.3f}" if sil is not None else "❔",
                    "Reconstruction AE": f"{recon_emoji} {recon:.4f}" if recon is not None else "❔",
                    "Version": ver_emoji,
                }
            )

        df = pd.DataFrame(rows)
        st.markdown("#### 📊 Performances par symbole")
        st.dataframe(df, use_container_width=True)
    else:
        try:
            df = pd.json_normalize(payload, sep="_")
            st.dataframe(df.T, use_container_width=True)
        except Exception:
            st.write(payload)

    with st.expander("🔧 Voir le détail brut (JSON)"):
        st.json(payload)


# ------------------------------------------------------------
# TAB 1 – Models & Runs
# ------------------------------------------------------------
def _render_tab_models_and_runs():
    st.subheader("🏆 Models & Runs")


    # =================================================
    # ROW 2 — Tableau des champions + panneau MLflow
    # =================================================
    col_left, col_right = st.columns([2.1, 1])

    # ------- Colonne gauche : tableau des champions -------
    with col_left:
        st.markdown("#### 🏅 Champions par symbole")

        try:
            res = requests.get(f"{API_BASE}/mlops/champions", timeout=8).json()
            if not res:
                st.info(
                    "Aucun champion enregistré pour le moment. "
                    "Lance un entraînement dans l’onglet Training & Automation."
                )
            else:
                rows = []
                for sym, data in res.items():
                    metrics = data.get("metrics", {}) or {}
                    score = data.get("score")

                    sil = metrics.get("silhouette")
                    recon = metrics.get("ae_reconstruction")

                    # Emoji silhouette
                    if sil is None:
                        sil_emoji = "❔"
                    elif sil > 0.35:
                        sil_emoji = "👍"
                    elif sil > 0.20:
                        sil_emoji = "🙂"
                    else:
                        sil_emoji = "⚠️"

                    # Emoji reconstruction
                    if recon is None:
                        recon_emoji = "❔"
                    elif recon < 0.6:
                        recon_emoji = "🟢"
                    elif recon <= 0.8:
                        recon_emoji = "🟡"
                    else:
                        recon_emoji = "🔴"

                    rows.append(
                        {
                            "Symbole": sym,
                            "Silhouette": f"{sil_emoji} {sil:.3f}" if sil is not None else "❔",
                            "Reconstruction AE": f"{recon_emoji} {recon:.4f}" if recon is not None else "❔",
                            "Score global": score,
                            "run_id": data.get("run_id"),
                        }
                    )

                df = pd.DataFrame(rows)

                # Score global : plus proche de 0 = meilleur (scores négatifs chez toi)
                if "Score global" in df.columns:
                    df = df.sort_values("Score global", ascending=True)

                st.dataframe(df, use_container_width=True)
        except Exception as e:
            st.error(f"Erreur lors de la récupération des champions : {e}")

    # ------- Colonne droite : panneau explicatif MLflow -------
    with col_right:
        st.markdown(
            """
            <div class="mlops-panel" style="margin-top: 1.6rem;">
              <div class="mlops-panel-title">🧠 MLflow – Runs & historique</div>
              <div class="mlops-panel-sub">
                Chaque champion correspond à un run MLflow sauvegardé dans l’expérience
                <code>StormCopilot_Market_MLOps</code>.<br/><br/>
                • Entraînements <b>QuickTrain</b> et <b>FullTrain</b> pour chaque symbole.<br/>
                • Suivi de la <b>silhouette</b> (cohésion des régimes de marché) et de
                  l’erreur de <b>reconstruction AutoEncoder</b>.<br/>
                • Analyse de l’évolution dans le temps via l’historique des runs ci-dessous.<br/><br/>
                Tu peux explorer tous les runs (params, métriques détaillées, artefacts)
                directement dans l’UI MLflow :
              </div>
              <div class="mlops-panel-sub" style="margin-top:0.5rem;">
                <code>http://127.0.0.1:5000</code>
              </div>
            </div>
            """,
            unsafe_allow_html=True,
        )

    st.markdown("---")

    # =================================================
    # ROW 3 — Historique des runs par symbole
    # =================================================
    st.markdown("#### 🔎 Historique des runs par symbole")

    default_symbols = ["^FCHI", "BNP.PA", "AIR.PA", "MC.PA", "OR.PA", "ORA.PA"]
    symbol = st.selectbox("Symbole à analyser", default_symbols, index=0)

    mode_filter = st.radio(
        "Type de runs",
        ["Tous", "QuickTrain seulement", "FullTrain seulement"],
        horizontal=True,
    )

    df_hist = _load_mlflow_history_for_symbol(symbol, limit=50)
    if df_hist.empty:
        st.info("Aucun run MLflow trouvé pour ce symbole.")
        return

    if "quick_mode" in df_hist.columns:
        df_hist["mode"] = df_hist["quick_mode"].map(
            {"True": "QuickTrain", "False": "FullTrain"}
        ).fillna(df_hist["quick_mode"])

        if mode_filter == "QuickTrain seulement":
            df_hist = df_hist[df_hist["mode"] == "QuickTrain"]
        elif mode_filter == "FullTrain seulement":
            df_hist = df_hist[df_hist["mode"] == "FullTrain"]

    if df_hist.empty:
        st.info("Aucun run ne correspond à ce filtre.")
        return

    cols = [
        c
        for c in [
            "run_id",
            "start_time",
            "mode",
            "symbols",
            "silhouette",
            "ae_reconstruction",
        ]
        if c in df_hist.columns
    ]

    try:
        st.dataframe(
            df_hist[cols].style.format(
                {"silhouette": "{:.3f}", "ae_reconstruction": "{:.4f}"}
            ),
            use_container_width=True,
        )
    except Exception:
        st.dataframe(df_hist[cols], use_container_width=True)

    if {"silhouette", "ae_reconstruction"}.intersection(df_hist.columns):
        st.markdown("#### 📈 Évolution des métriques")
        chart_df = df_hist.set_index("start_time")[
            [c for c in ["silhouette", "ae_reconstruction"] if c in df_hist.columns]
        ]
        st.line_chart(chart_df)

    st.caption(
        "Pour plus de détails, tu peux retrouver un run dans MLflow UI en utilisant son run_id."
    )

# ------------------------------------------------------------
# TAB 2 – Monitoring (marché)
# ------------------------------------------------------------
def _render_tab_monitoring():
    st.subheader("📉 Market Monitoring")

    last_metrics_file, metrics_date = _get_last_monitoring_file()

    col_btn, col_info = st.columns([1, 2])
    with col_btn:
        if st.button("🔄 Rafraîchir monitoring via n8n"):
            try:
                resp = requests.post(
                    f"{N8N_BASE}/webhook/market-monitoring", timeout=15
                )
                st.success("Monitoring déclenché via n8n.")
                with st.expander("Voir la réponse JSON brute"):
                    st.json(resp.json())
            except Exception as e:
                st.error(f"Erreur lors de l’appel n8n : {e}")

    with col_info:
        st.markdown(
            """
            <div class="mlops-panel">
              <div class="mlops-panel-title">Dernier snapshot de monitoring</div>
            """,
            unsafe_allow_html=True,
        )
        if last_metrics_file:
            st.markdown(
                f"<div class='mlops-panel-sub'>Fichier : <code>{last_metrics_file}</code></div>",
                unsafe_allow_html=True,
            )
            if metrics_date:
                st.markdown(
                    f"<div class='mlops-panel-sub'>Date : <b>{metrics_date}</b></div>",
                    unsafe_allow_html=True,
                )
        else:
            st.markdown(
                "<div class='mlops-panel-sub'>Aucun fichier trouvé dans <code>mlops_metrics/</code>.</div>",
                unsafe_allow_html=True,
            )
        st.markdown("</div>", unsafe_allow_html=True)

    st.markdown("")

    if last_metrics_file and os.path.exists(last_metrics_file):
        try:
            df = pd.read_csv(last_metrics_file)
            st.dataframe(df, use_container_width=True)
        except Exception as e:
            st.error(f"Impossible de lire le fichier de monitoring : {e}")


# ------------------------------------------------------------
# TAB 3 – Training & Automation
# ------------------------------------------------------------
def _render_tab_training():
    st.subheader("⚙️ Training & Automation")

    col_fastapi, col_n8n = st.columns(2)

    # --- Entraînement direct FastAPI ---
    with col_fastapi:
        st.markdown("#### 🚀 Entraînement via FastAPI")
        st.caption(
            "QuickTrain : config légère pour itérer rapidement.\n"
            "FullTrain : recalibrage complet des modèles de marché."
        )

        if st.button("⚡ QuickTrain (rapide)"):
            try:
                res = requests.post(
                    f"{API_BASE}/mlops/train/market",
                    params={"quick": True},
                    timeout=180,
                ).json()
                st.success("QuickTrain terminé.")
                _render_train_summary("QuickTrain", res)
            except Exception as e:
                st.error(f"Erreur lors du QuickTrain via FastAPI : {e}")

        if st.button("🧪 FullTrain (complet)"):
            try:
                res = requests.post(
                    f"{API_BASE}/mlops/train/market",
                    timeout=600,
                ).json()
                st.success("FullTrain terminé.")
                _render_train_summary("FullTrain", res)
            except Exception as e:
                st.error(f"Erreur lors du FullTrain via FastAPI : {e}")

    # --- Orchestration n8n ---
    with col_n8n:
        st.markdown("### 🚀 Daily Full MLOps – orchestré par n8n")
        st.caption(
            "Lance le scénario complet : QuickTrain → Metrics → Champions, "
            "via le workflow n8n `mlops-daily-full`."
        )

        if st.button("▶️ Exécuter mlops-daily-full (n8n)"):
            try:
                resp = requests.post(
                    f"{N8N_BASE}/webhook/mlops-daily-full",
                    timeout=120,
                )
                resp.raise_for_status()
                data = resp.json()

                st.success("Workflow `mlops-daily-full` exécuté avec succès via n8n.")
                render_champions_synthesis_card()
                # Petit résumé lisible
                if isinstance(data, dict) and data:
                    st.markdown("#### Synthèse des champions mis à jour")
                    st.write(f"Nombre de symboles : **{len(data)}**")

                    # Champion silhouette max
                    try:
                        best_sil_sym, best_sil = None, None
                        for sym, info in data.items():
                            m = info.get("metrics", {}) or {}
                            sil = m.get("silhouette")
                            if sil is None:
                                continue
                            if best_sil is None or sil > best_sil:
                                best_sil_sym, best_sil = sym, float(sil)

                        if best_sil_sym is not None:
                            st.info(
                                f"Meilleur score silhouette : **{best_sil_sym}** "
                                f"avec **{best_sil:.3f}**"
                            )
                    except Exception:
                        pass

                    with st.expander("Voir la réponse JSON complète"):
                        st.json(data)
                else:
                    st.warning("Réponse inattendue du workflow n8n (format non dict).")

            except Exception as e:
                st.error(f"Erreur lors de l’appel du workflow n8n `mlops-daily-full` : {e}")


    st.markdown("---")
    st.info(f"UI MLflow disponible sur : {MLFLOW_UI_URL}")


# ------------------------------------------------------------
# RENDER principal
# ------------------------------------------------------------
def render():
    _inject_local_css()

    # Header
    with st.container():
        st.markdown(
            """
            <div class="mlops-header">
              <div class="mlops-header-title">
                <span>🧠 MLOps Cockpit – StormCopilot</span>
                <span class="mlops-header-pill">Market · MLflow · n8n</span>
              </div>
              <div class="mlops-header-sub">
                Pilotage des modèles de marché (KMeans + AutoEncoder), suivi des métriques
                et orchestration des entraînements.
              </div>
            </div>
            """,
            unsafe_allow_html=True,
        )

    # KPI bandeau
    champs_summary = _get_champions_summary()
    last_metrics_file, metrics_date = _get_last_monitoring_file()

    col1, col2, col3 = st.columns([1.1, 1.1, 1])
    with col1:
        st.markdown(
            f"""
            <div class="mlops-kpi-card">
              <div class="mlops-kpi-icon">🏆</div>
              <div class="mlops-kpi-label">Modèles champions</div>
              <div class="mlops-kpi-value">{champs_summary["count"]}</div>
              <div class="mlops-kpi-sub">KMeans + AutoEncoder par symbole</div>
            </div>
            """,
            unsafe_allow_html=True,
        )

    with col2:
        best_sil = champs_summary["best_sil"]
        best_sym = champs_summary["best_symbol"]
        txt = f"{best_sil:.3f} ({best_sym})" if best_sil is not None else "–"
        st.markdown(
            f"""
            <div class="mlops-kpi-card">
              <div class="mlops-kpi-icon">📈</div>
              <div class="mlops-kpi-label">Meilleur score silhouette</div>
              <div class="mlops-kpi-value">{txt}</div>
              <div class="mlops-kpi-sub">Cohésion des régimes de marché détectés</div>
            </div>
            """,
            unsafe_allow_html=True,
        )

    with col3:
        title = metrics_date if metrics_date else "N/A"
        sub = "Dernier monitoring quotidien" if metrics_date else "Aucun fichier détecté"
        st.markdown(
            f"""
            <div class="mlops-kpi-card">
              <div class="mlops-kpi-icon">🛰️</div>
              <div class="mlops-kpi-label">Monitoring marché</div>
              <div class="mlops-kpi-value">{title}</div>
              <div class="mlops-kpi-sub">{sub}</div>
            </div>
            """,
            unsafe_allow_html=True,
        )

    st.markdown("")

    # 3 tabs simplifiés
    tab1, tab2, tab3 = st.tabs(
        ["🏆 Models & Runs", "📉 Monitoring", "⚙️ Training & Automation"]
    )

    with tab1:
        _render_tab_models_and_runs()
    with tab2:
        _render_tab_monitoring()
    with tab3:
        _render_tab_training()
def render_champions_synthesis_card(title: str = "🏅 Synthèse des champions mis à jour"):
    """
    Carte récap des champions MLOps (nombre de symboles + meilleur silhouette).
    Style inspiré de la carte Market Radar n8n.
    """
    try:
        res = requests.get(f"{API_BASE}/mlops/champions", timeout=8).json()
    except Exception as e:
        st.error(f"Impossible de récupérer les champions : {e}")
        return

    if not res:
        st.warning("Aucun champion disponible pour le moment.")
        return

    nb_symbols = len(res)

    # Recherche du meilleur score silhouette
    best_sym = None
    best_sil = None
    for sym, data in res.items():
        metrics = (data or {}).get("metrics") or {}
        sil = metrics.get("silhouette")
        if sil is None:
            continue
        if best_sil is None or sil > best_sil:
            best_sil = sil
            best_sym = sym

    # Fallback
    if best_sym is None:
        best_sym = "N/A"
    if best_sil is None:
        best_sil_txt = "–"
    else:
        best_sil_txt = f"{best_sil:.3f}"

    # ---- Carte style "dash-card" ----
    st.markdown(
        '<div class="dash-card fade-in" style="margin-bottom: 1rem;">',
        unsafe_allow_html=True,
    )
    st.markdown(
        f'<div class="dash-title">{title}</div>',
        unsafe_allow_html=True,
    )

    col1, col2 = st.columns(2)

    with col1:
        st.markdown(
            f"""
            <div style="
                background: linear-gradient(135deg,#2563eb,#38bdf8);
                border-radius: 16px;
                padding: 14px 16px;
                color: white;
                box-shadow: 0 10px 30px rgba(37,99,235,0.45);
            ">
                <div style="font-size:0.75rem;opacity:0.9;">📊 Nombre de symboles</div>
                <div style="font-size:1.9rem;font-weight:700;">{nb_symbols}</div>
                <div style="font-size:0.8rem;opacity:0.9;">Champions enregistrés</div>
            </div>
            """,
            unsafe_allow_html=True,
        )

    with col2:
        st.markdown(
            f"""
            <div style="
                background: linear-gradient(135deg,#16a34a,#22c55e);
                border-radius: 16px;
                padding: 14px 16px;
                color: white;
                box-shadow: 0 10px 30px rgba(22,163,74,0.45);
            ">
                <div style="font-size:0.75rem;opacity:0.9;">🏆 Meilleur score silhouette</div>
                <div style="font-size:1.4rem;font-weight:700;display:flex;align-items:baseline;gap:0.35rem;">
                    <span>{best_sil_txt}</span>
                    <span style="font-size:0.9rem;opacity:0.9;">({best_sym})</span>
                </div>
                <div style="font-size:0.8rem;opacity:0.9;">Régime de marché le plus cohérent</div>
            </div>
            """,
            unsafe_allow_html=True,
        )

    st.markdown("</div>", unsafe_allow_html=True)


def render_mlops_tab():
    """Wrapper appelé par app.py."""
    render()
