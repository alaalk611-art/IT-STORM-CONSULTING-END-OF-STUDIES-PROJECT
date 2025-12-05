# -*- coding: utf-8 -*-
# Path: src/ui/sections/automation.py

from __future__ import annotations
from typing import List, Dict, Any
import json

import streamlit as st
from textwrap import dedent

from src.automation.engine import (
    get_all_workflows,
    save_all_workflows,
    run_workflow,
)
from src.automation.logs import load_logs


STATE_KEY = "automation_workflows"
RESULT_KEY = "automation_last_result"


def _init_state() -> None:
    """
    Initialise les workflows en mémoire (st.session_state) à partir du stockage.
    """
    if STATE_KEY not in st.session_state:
        st.session_state[STATE_KEY] = get_all_workflows()
    if RESULT_KEY not in st.session_state:
        st.session_state[RESULT_KEY] = None


def _get_workflows() -> List[Dict[str, Any]]:
    return st.session_state.get(STATE_KEY, [])


def _set_workflows(workflows: List[Dict[str, Any]]) -> None:
    st.session_state[STATE_KEY] = workflows
    save_all_workflows(workflows)


def render_automation_tab() -> None:
    """
    Tab principal "⚙️ Automation Studio".
    Appelé depuis app.py :
        from src.ui.sections import automation
        ...
        with tab_automation:
            automation.render_automation_tab()
    """
    _init_state()
    workflows = _get_workflows()

    # ============================================================
    # CSS — LOOK & FEEL "STUDIO" FAÇON n8n
    # ============================================================
    st.markdown(
        dedent(
            """
        <style>
        /* === WRAPPER GLOBAL === */
        .auto-studio-wrapper {
            position: relative;
            padding-top: 0.5rem;
        }

        /* Barre gradient animée sous le titre */
        .auto-studio-header-bar {
            height: 4px;
            border-radius: 999px;
            background: linear-gradient(90deg,
                #22c55e,
                #0ea5e9,
                #6366f1,
                #ec4899
            );
            background-size: 300% 100%;
            animation: auto-bar-move 12s linear infinite;
            margin: 0.4rem 0 1.5rem 0;
            opacity: 0.9;
        }

        @keyframes auto-bar-move {
            0% { background-position: 0% 50%; }
            50% { background-position: 100% 50%; }
            100% { background-position: 0% 50%; }
        }

        /* Petit badge “Studio” à la n8n */
        .auto-badge {
            display: inline-flex;
            align-items: center;
            gap: 0.35rem;
            padding: 0.18rem 0.65rem;
            border-radius: 999px;
            font-size: 0.78rem;
            letter-spacing: 0.03em;
            text-transform: uppercase;
            border: 1px solid rgba(148,163,184,0.45);
            background: radial-gradient(circle at 0 0, rgba(45,212,191,0.15), transparent 55%),
                        rgba(15,23,42,0.02);
            backdrop-filter: blur(10px);
        }

        .auto-badge-dot {
            width: 7px;
            height: 7px;
            border-radius: 999px;
            background: #22c55e;
            box-shadow: 0 0 0 0 rgba(34,197,94,0.9);
            animation: auto-pulse 2.2s infinite;
        }

        @keyframes auto-pulse {
            0%   { box-shadow: 0 0 0 0 rgba(34,197,94,0.7); }
            70%  { box-shadow: 0 0 0 10px rgba(34,197,94,0); }
            100% { box-shadow: 0 0 0 0 rgba(34,197,94,0); }
        }

        /* Cartes panels */
        .auto-panel {
            border-radius: 18px;
            padding: 1.2rem 1.2rem 1rem;
            background: rgba(255,255,255,0.85);
            box-shadow: 0 14px 40px rgba(15,23,42,0.06);
            border: 1px solid rgba(226,232,240,0.9);
        }

        [data-theme="dark"] .auto-panel {
            background: radial-gradient(circle at 0 0, rgba(56,189,248,0.08), transparent 60%),
                        rgba(15,23,42,0.96);
            border-color: rgba(51,65,85,0.9);
            box-shadow: 0 18px 55px rgba(15,23,42,0.9);
        }

        /* Cartes workflow individuelles */
        .auto-workflow-card {
            border-radius: 16px;
            padding: 0.75rem 0.85rem 0.7rem;
            margin-bottom: 0.6rem;
            background: linear-gradient(120deg, rgba(248,250,252,0.9), rgba(241,245,249,0.85));
            border: 1px solid rgba(226,232,240,0.95);
            position: relative;
            overflow: hidden;
            transition: transform 0.16s ease-out, box-shadow 0.16s ease-out,
                        border-color 0.16s ease-out, background 0.16s ease-out;
        }
        [data-theme="dark"] .auto-workflow-card {
            background: radial-gradient(circle at 0 0, rgba(56,189,248,0.12), transparent 65%),
                        rgba(15,23,42,0.96);
            border-color: rgba(51,65,85,0.95);
        }
        .auto-workflow-card::before {
            content: "";
            position: absolute;
            inset: 0;
            background-image: radial-gradient(circle at 0 0, rgba(59,130,246,0.18), transparent 58%);
            opacity: 0;
            transition: opacity 0.18s ease-out;
            pointer-events: none;
        }
        .auto-workflow-card:hover {
            transform: translateY(-2px);
            box-shadow: 0 18px 45px rgba(15,23,42,0.15);
            border-color: rgba(59,130,246,0.5);
            background: linear-gradient(120deg, rgba(239,246,255,0.98), rgba(219,234,254,0.96));
        }
        .auto-workflow-card:hover::before {
            opacity: 1;
        }

        .auto-workflow-header {
            display: flex;
            align-items: center;
            justify-content: space-between;
            gap: 0.4rem;
            margin-bottom: 0.15rem;
        }

        .auto-workflow-title {
            display: flex;
            align-items: center;
            gap: 0.35rem;
            font-weight: 600;
            font-size: 0.96rem;
        }

        .auto-pill {
            padding: 0.05rem 0.55rem;
            border-radius: 999px;
            font-size: 0.72rem;
            border: 1px solid rgba(148,163,184,0.7);
            background: rgba(248,250,252,0.8);
        }
        [data-theme="dark"] .auto-pill {
            background: rgba(15,23,42,0.9);
            border-color: rgba(148,163,184,0.7);
        }

        /* Boutons RUN / DELETE custom */
        .auto-btn-row {
            display: flex;
            gap: 0.35rem;
        }

        .auto-run-btn > button {
            border-radius: 999px !important;
            padding-inline: 0.85rem !important;
            font-size: 0.82rem !important;
            font-weight: 600 !important;
        }
        .auto-run-btn > button:hover {
            box-shadow: 0 0 0 2px rgba(34,197,94,0.35);
        }

        .auto-del-btn > button {
            border-radius: 999px !important;
            padding-inline: 0.8rem !important;
            font-size: 0.8rem !important;
        }

        /* Panneau formulaire à droite */
        .auto-panel-form {
            position: sticky;
            top: 0.6rem;
        }

        /* Légère animation d’apparition */
        .auto-fade-in {
            animation: auto-fade 0.45s ease-out;
        }

        @keyframes auto-fade {
            from { opacity: 0; transform: translateY(6px); }
            to   { opacity: 1; transform: translateY(0); }
        }

        /* === FORM STYLE – champs façon Studio / n8n === */
        .auto-form-block {
            display: flex;
            flex-direction: column;
            gap: 0.4rem;
            margin-top: 0.4rem;
        }

        .auto-field-label {
            font-size: 0.83rem;
            font-weight: 600;
            letter-spacing: 0.02em;
            text-transform: uppercase;
            color: rgba(100,116,139,0.95);
            margin-bottom: 0.15rem;
            display: flex;
            align-items: center;
            gap: 0.3rem;
        }

        .auto-field-label span.auto-chip {
            font-size: 0.7rem;
            padding: 0.05rem 0.45rem;
            border-radius: 999px;
            border: 1px solid rgba(148,163,184,0.7);
            background: rgba(248,250,252,0.95);
        }

        .auto-field-helper {
            font-size: 0.78rem;
            color: rgba(148,163,184,0.95);
            margin-top: 0.05rem;
            margin-bottom: 0.25rem;
        }

        /* Inputs / selects / textarea – style global Studio */
        .stTextInput input,
        .stSelectbox > div > div,
        .stTextArea textarea {
            border-radius: 999px !important;
            border: 1px solid rgba(203,213,225,0.95) !important;
            background: linear-gradient(135deg, rgba(248,250,252,0.98),
                                                 rgba(241,245,249,0.98)) !important;
            box-shadow: 0 4px 10px rgba(148,163,184,0.18) !important;
            transition: box-shadow 0.16s ease-out, border-color 0.16s ease-out,
                        transform 0.12s ease-out;
        }

        .stTextArea textarea {
            border-radius: 18px !important;
        }

        .stTextInput input:focus,
        .stSelectbox > div > div:focus-within,
        .stTextArea textarea:focus {
            border-color: rgba(59,130,246,0.85) !important;
            box-shadow:
                0 0 0 1px rgba(59,130,246,0.35),
                0 10px 25px rgba(37,99,235,0.25) !important;
            transform: translateY(-1px);
        }

        /* Bouton submit – look plus “primary” */
        .auto-submit-btn > button {
            width: 100%;
            border-radius: 999px !important;
            font-weight: 600 !important;
            letter-spacing: 0.02em;
            padding-block: 0.5rem !important;
            box-shadow: 0 10px 25px rgba(79,70,229,0.28) !important;
            transition: transform 0.08s ease-out, box-shadow 0.12s ease-out;
        }

        .auto-submit-btn > button:hover {
            transform: translateY(-1px);
            box-shadow: 0 14px 35px rgba(79,70,229,0.38) !important;
        }
        </style>
        """
        ),
        unsafe_allow_html=True,
    )

    # ============================================================
    # HEADER
    # ============================================================
    st.markdown('<div class="auto-studio-wrapper">', unsafe_allow_html=True)

    col_icon, col_title = st.columns([0.12, 0.88])

    with col_icon:
        st.markdown(
            """
            <div style="font-size:2.5rem;display:flex;align-items:center;justify-content:center;">
                ⚙️
            </div>
            """,
            unsafe_allow_html=True,
        )

    with col_title:
        st.markdown(
            """
            <div style="display:flex;align-items:center;gap:0.6rem;flex-wrap:wrap;">
                <h1 style="margin-bottom:0;">Automation Studio</h1>
                <span class="auto-badge">
                    <span class="auto-badge-dot"></span>
                    Workflow Orchestrator
                </span>
            </div>
            <p style="margin-top:0.25rem;margin-bottom:0.3rem;font-size:0.94rem;color:rgba(71,85,105,0.95);">
                Définissez des workflows visuels (inspirés de n8n) pour enchaîner RAG, veille et génération de livrables dans StormCopilot.
            </p>
            """,
            unsafe_allow_html=True,
        )

    st.markdown('<div class="auto-studio-header-bar"></div>', unsafe_allow_html=True)

    # ============================================================
    # LAYOUT 2 COLONNES
    # ============================================================
    col_left, col_right = st.columns([2, 1])

    # ------------------------- GAUCHE ---------------------------------
    with col_left:
        st.markdown('<div class="auto-panel auto-fade-in">', unsafe_allow_html=True)

        st.markdown(
            """
            <h3 style="display:flex;align-items:center;gap:0.45rem;margin-top:0;">
                <span style="font-size:1.2rem;">📜</span>
                <span>Workflows existants</span>
            </h3>
            """,
            unsafe_allow_html=True,
        )

        if not workflows:
            st.info("Aucun workflow pour le moment. Créez-en un à droite.")
        else:
            for idx, wf in enumerate(workflows):
                st.markdown('<div class="auto-workflow-card">', unsafe_allow_html=True)

                name = wf.get("name", "Sans nom")
                trigger = wf.get("trigger", "manual")
                steps = wf.get("steps", []) or []

                st.markdown(
                    f"""
                    <div class="auto-workflow-header">
                        <div class="auto-workflow-title">
                            <span>🧩</span>
                            <span>{name}</span>
                        </div>
                        <div class="auto-pill">
                            Trigger : <strong>{trigger}</strong> • Steps : {len(steps)}
                        </div>
                    </div>
                    """,
                    unsafe_allow_html=True,
                )

                btn_c1, btn_c2 = st.columns([1, 1])
                with btn_c1:
                    st.markdown(
                        '<div class="auto-run-btn auto-btn-row">', unsafe_allow_html=True
                    )
                    if st.button("▶️ Lancer", key=f"run_{idx}"):
                        result = run_workflow(wf)
                        st.session_state[RESULT_KEY] = result
                        st.success("Workflow exécuté.")
                    st.markdown("</div>", unsafe_allow_html=True)

                with btn_c2:
                    st.markdown(
                        '<div class="auto-del-btn auto-btn-row">', unsafe_allow_html=True
                    )
                    if st.button("🗑 Supprimer", key=f"delete_{idx}"):
                        new_list = [w for i, w in enumerate(workflows) if i != idx]
                        _set_workflows(new_list)
                        st.rerun()
                    st.markdown("</div>", unsafe_allow_html=True)

                st.markdown("</div>", unsafe_allow_html=True)  # auto-workflow-card

        st.markdown("<hr/>", unsafe_allow_html=True)

        st.markdown(
            """
            <h3 style="display:flex;align-items:center;gap:0.45rem;margin-top:0.2rem;">
                <span style="font-size:1.1rem;">📊</span>
                <span>Dernier résultat d'exécution</span>
            </h3>
            """,
            unsafe_allow_html=True,
        )

        last_result = st.session_state.get(RESULT_KEY)
        if last_result is None:
            st.caption("Aucun workflow exécuté pour le moment.")
        else:
            st.json(last_result)

        # -------------------- HISTORIQUE DES LOGS --------------------
        st.markdown(
            "<hr style='margin-top:0.8rem;margin-bottom:0.5rem;'/>",
            unsafe_allow_html=True,
        )

        with st.expander("🕒 Historique des exécutions (logs)", expanded=False):
            logs = load_logs(limit=50)
            st.caption(f"{len(logs)} log(s) trouvé(s).")

            if not logs:
                st.caption("Aucun log enregistré pour le moment.")
            else:
                workflow_names = sorted(
                    {log.get("workflow_name", "Sans nom") for log in logs}
                )
                selected = st.selectbox(
                    "Filtrer par workflow",
                    options=["(Tous)"] + workflow_names,
                    index=0,
                    key="auto_logs_filter",
                )

                if selected != "(Tous)":
                    logs_to_show = [
                        log for log in logs if log.get("workflow_name") == selected
                    ]
                else:
                    logs_to_show = logs

                for log in logs_to_show[:10]:
                    wf_name = log.get("workflow_name", "Sans nom")
                    executed_at = log.get("executed_at") or log.get("logged_at") or "?"
                    st.markdown(f"**{wf_name}** · _{executed_at}_")
                    st.json(log.get("logs"))
                    st.markdown("---")

        st.markdown("</div>", unsafe_allow_html=True)  # auto-panel gauche

    # ------------------------- DROITE ---------------------------------
    with col_right:
        st.markdown(
            '<div class="auto-panel auto-panel-form auto-fade-in">',
            unsafe_allow_html=True,
        )

        st.markdown(
            """
            <h3 style="display:flex;align-items:center;gap:0.45rem;margin-top:0;">
                <span style="font-size:1.2rem;">➕</span>
                <span>Nouveau workflow</span>
            </h3>
            <p style="margin-top:0;font-size:0.86rem;color:rgba(100,116,139,0.95);">
                Commencez simple : un trigger manuel et une seule action (rafraîchir, résumer, générer un livrable).
            </p>
            """,
            unsafe_allow_html=True,
        )

        with st.form("automation_new_workflow"):
            st.markdown('<div class="auto-form-block">', unsafe_allow_html=True)

            # -------- Nom du workflow --------
            st.markdown(
                """
                <div class="auto-field-label">
                    <span>Nom du workflow</span>
                    <span class="auto-chip">Label</span>
                </div>
                """,
                unsafe_allow_html=True,
            )
            name = st.text_input(
                "Nom du workflow",
                placeholder="Daily Tech Radar",
                label_visibility="collapsed",
            )
            st.markdown(
                '<div class="auto-field-helper">Choisissez un nom court et explicite, facile à retrouver dans la liste.</div>',
                unsafe_allow_html=True,
            )

            # -------- Trigger --------
            st.markdown(
                """
                <div class="auto-field-label" style="margin-top:0.4rem;">
                    <span>Trigger</span>
                    <span class="auto-chip">Entrée</span>
                </div>
                """,
                unsafe_allow_html=True,
            )
            trigger = st.selectbox(
                " ",
                options=["manual"],
                index=0,
                label_visibility="collapsed",
            )
            st.markdown(
                '<div class="auto-field-helper">Pour l’instant, seul le déclenchement manuel est disponible.</div>',
                unsafe_allow_html=True,
            )

            # -------- Action principale --------
            st.markdown(
                """
                <div class="auto-field-label" style="margin-top:0.4rem;">
                    <span>Action principale</span>
                    <span class="auto-chip">Node</span>
                </div>
                """,
                unsafe_allow_html=True,
            )
            action = st.selectbox(
                " ",
                options=[
                    ("refresh_tech_watch", "Rafraîchir Tech Watch"),
                    ("refresh_market", "Rafraîchir Market Watch"),
                    ("generate_rag_summary", "Générer un résumé RAG"),
                ],
                format_func=lambda x: x[1],
                label_visibility="collapsed",
            )
            st.markdown(
                '<div class="auto-field-helper">Sélectionnez le premier “node” de votre workflow (veille, marché, résumé...).</div>',
                unsafe_allow_html=True,
            )

            # -------- Paramètres --------
            st.markdown(
                """
                <div class="auto-field-label" style="margin-top:0.4rem;">
                    <span>Paramètres</span>
                    <span class="auto-chip">JSON</span>
                </div>
                """,
                unsafe_allow_html=True,
            )
            params_json = st.text_area(
                "Paramètres JSON",
                value='{"target": "tech"}',
                height=110,
                label_visibility="collapsed",
            )
            st.markdown(
                '<div class="auto-field-helper">Optionnel. Utilisez du JSON simple pour préciser la cible (par ex. <code>{"target": "tech"}</code>).</div>',
                unsafe_allow_html=True,
            )

            st.markdown("</div>", unsafe_allow_html=True)  # auto-form-block

            # Bouton submit
            st.markdown('<div class="auto-submit-btn">', unsafe_allow_html=True)
            submitted = st.form_submit_button("💾 Créer le workflow")
            st.markdown("</div>", unsafe_allow_html=True)

        # Traitement du submit
        if submitted:
            if not name.strip():
                st.error("Merci de donner un nom au workflow.")
            else:
                action_type = action[0]
                try:
                    params = json.loads(params_json) if params_json.strip() else {}
                    if not isinstance(params, dict):
                        raise ValueError("Les paramètres JSON doivent être un objet (dict).")
                except Exception as e:
                    st.error(f"JSON invalide pour les paramètres : {e}")
                else:
                    new_workflow = {
                        "name": name.strip(),
                        "trigger": trigger,
                        "steps": [
                            {
                                "type": action_type,
                                "params": params,
                            }
                        ],
                    }
                    workflows = _get_workflows()
                    workflows.append(new_workflow)
                    _set_workflows(workflows)
                    st.success("Workflow créé avec succès ✅")
                    st.rerun()

        st.markdown("</div>", unsafe_allow_html=True)  # auto-panel droite

    st.markdown("</div>", unsafe_allow_html=True)  # auto-studio-wrapper
