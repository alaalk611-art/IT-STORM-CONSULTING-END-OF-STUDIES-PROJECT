# -*- coding: utf-8 -*-
# Path: src/ui/sections/upload.py

from __future__ import annotations

from pathlib import Path
from textwrap import dedent
import time
from typing import List, Dict, Tuple

import streamlit as st

from src.config.settings import RAW_DIR, PROC_DIR
from src.ingestion.chunking import chunk_words
from src.ingestion.extract_text import extract_any
from src.utils.io import write_jsonl

DATA_PROCESSED = PROC_DIR


# ============================================================
# ======================= STYLES GLOBAUX =====================
# ============================================================
def _inject_css() -> None:
    st.markdown(
        dedent(
            """
            <style>
            .upload-wrapper {
                padding: 0.75rem 0.2rem 0.2rem 0.2rem;
            }

            .upload-header-box {
                background: linear-gradient(135deg,#eff6ff,#e0f2fe);
                border-radius: 18px;
                padding: 1.0rem 1.2rem 1.0rem 1.2rem;
                border: 1px solid #bae6fd;
                box-shadow: 0 10px 25px rgba(15,23,42,0.06);
                margin-bottom: 1.0rem;
            }

            .upload-title {
                font-size: 1.32rem;
                font-weight: 750;
                color: #0369a1;
                margin: 0.10rem 0 0.18rem 0;
            }

            .upload-subtitle {
                font-size: 0.92rem;
                color: #1f2937;
                margin: 0;
            }

            /* ================= PIPELINE ================= */

            .pipeline-row-wrapper {
                margin-top: 1.0rem;
                margin-bottom: 0.3rem;
            }

            .pipeline-card {
                border-radius: 14px;
                padding: 0.90rem 1.0rem;
                border: 1px solid #e5e7eb;
                background: #f9fafb;
                box-shadow: 0 4px 10px rgba(15,23,42,0.03);
                height: 100%;
                transition:
                    background-color 0.25s ease,
                    border-color 0.25s ease,
                    box-shadow 0.25s ease,
                    transform 0.20s ease,
                    opacity 0.25s ease;
            }

            .pipeline-card.status-active {
                border-color: #bae6fd;
                background: #f0f9ff;
                box-shadow: 0 6px 14px rgba(59,130,246,0.12);
                opacity: 1.0;
            }

            .pipeline-card.status-done {
                border-color: #bbf7d0;
                background: #f0fdf4;
                box-shadow: 0 6px 14px rgba(34,197,94,0.10);
                opacity: 1.0;
            }

            .pipeline-card.status-locked {
                border-style: dashed;
                background: #f9fafb;
                opacity: 0.60;
            }

            .pipeline-card-header {
                display: flex;
                align-items: flex-start;
                gap: 0.6rem;
                margin-bottom: 0.35rem;
            }

            .pipeline-circle {
                width: 28px;
                height: 28px;
                border-radius: 999px;
                display: flex;
                align-items: center;
                justify-content: center;
                font-size: 0.82rem;
                font-weight: 600;
                border: 1px solid #d1d5db;
                background: #ffffff;
                color: #374151;
                flex-shrink: 0;
            }

            .pipeline-circle.done {
                background: #22c55e;
                border-color: #16a34a;
                color: #f9fafb;
            }

            .pipeline-circle.active {
                background: #0ea5e9;
                border-color: #0284c7;
                color: #f9fafb;
            }

            .pipeline-circle.locked {
                background: #f3f4f6;
                color: #9ca3af;
                border-style: dashed;
            }

            .pipeline-title-block {
                display: flex;
                flex-direction: column;
                align-items: flex-start;
                gap: 0.20rem;
            }

            .pipeline-title {
                font-size: 0.92rem;
                font-weight: 600;
                color: #111827;
            }

            .pipeline-status {
                font-size: 0.70rem;
                padding: 0.10rem 0.60rem;
                border-radius: 999px;
                border: 1px solid #e5e7eb;
                background: #ffffff;
                color: #6b7280;
            }

            .pipeline-status.done {
                background: #dcfce7;
                border-color: #22c55e;
                color: #166534;
            }

            .pipeline-status.active {
                background: #e0f2fe;
                border-color: #0ea5e9;
                color: #0369a1;
            }

            .pipeline-status.locked {
                background: #f3f4f6;
                color: #9ca3af;
                border-style: dashed;
            }

            .pipeline-desc {
                font-size: 0.80rem;
                color: #6b7280;
                margin-top: 0.15rem;
            }

            .pipeline-arrow {
                text-align: center;
                font-size: 1.6rem;
                color: #cbd5f5;
                padding-top: 1.7rem;
                opacity: 0.8;
            }

            @media (max-width: 900px) {
                .pipeline-arrow {
                    display: none;
                }
            }

            /* ================= NAVIGATION D'ÉTAPES ================= */

            .upload-steps-label {
                font-size: 0.80rem;
                color: #6b7280;
                margin: 0.4rem 0 0.1rem 0;
                text-align: center;
            }

            div[role="radiogroup"] {
                justify-content: center !important;
                gap: 0.4rem !important;
            }

            div[role="radiogroup"] > label > div:first-child {
                display: none;
            }

            div[role="radiogroup"] > label {
                border-radius: 999px;
                border: 1px solid #e5e7eb;
                background: #f9fafb;
                padding: 0.20rem 0.9rem;
                font-size: 0.82rem;
                color: #4b5563;
                cursor: pointer;
                text-align: center;
            }

            div[role="radiogroup"] > label[data-checked="true"] {
                border-color: #0ea5e9;
                background: #e0f2fe;
                color: #0369a1;
                box-shadow: 0 4px 10px rgba(14,165,233,0.22);
                transform: translateY(-1px);
            }

            div[role="radiogroup"] > label[data-checked="false"] {
                display: none;
            }

            /* ================= AUTRES ================= */

            .upload-card-hint {
                font-size: 0.76rem;
                color: #6b7280;
                margin-top: 0.6rem;
            }

            div[data-testid="stFileUploader"] > label {
                font-size: 0.80rem;
                font-weight: 500;
                color: #374151;
                margin-bottom: 0.25rem;
            }
            div[data-testid="stFileUploader"] {
                background: #f9fafb;
                border-radius: 10px;
                padding: 0.7rem;
                border: 1px dashed #d1d5db;
            }

            .stButton > button {
                border-radius: 999px !important;
                border: 1px solid #d1d5db;
                background: linear-gradient(90deg,#eff6ff,#dbeafe);
                color: #1f2937;
                font-size: 0.85rem;
                padding: 0.35rem 0.9rem;
                font-weight: 500;
            }
            .stButton > button:hover {
                border-color: #2563eb;
                background: linear-gradient(90deg,#dbeafe,#bfdbfe);
                color: #1d4ed8;
                box-shadow: 0 6px 14px rgba(37,99,235,0.20);
            }
            .stButton > button:disabled {
                opacity: 0.45;
                cursor: not-allowed;
                box-shadow: none;
            }

            .upload-summary {
                margin-top: 0.55rem;
                font-size: 0.78rem;
                color: #374151;
            }
            .upload-summary h3 {
                font-size: 0.86rem;
                margin-bottom: 0.35rem;
            }
            </style>
            """
        ),
        unsafe_allow_html=True,
    )


# ============================================================
# ==================== PIPELINE (3 ÉTAPES) ===================
# ============================================================
def _render_pipeline(step1_done: bool, step2_done: bool, step3_done: bool) -> None:
    def status(idx: int) -> str:
        if idx == 1:
            return "done" if step1_done else "active"
        if idx == 2:
            if step2_done:
                return "done"
            return "active" if step1_done else "locked"
        if idx == 3:
            if step3_done:
                return "done"
            return "active" if step2_done else "locked"
        return "locked"

    def label(sts: str) -> str:
        return {"done": "Validée", "active": "En cours", "locked": "Verrouillée"}[sts]

    st.markdown('<div class="pipeline-row-wrapper">', unsafe_allow_html=True)

    col1, col_arrow1, col2, col_arrow2, col3 = st.columns([4, 1, 4, 1, 4])

    s1 = status(1)
    col1.markdown(
        f"""
        <div class="pipeline-card status-{s1}">
          <div class="pipeline-card-header">
            <div class="pipeline-circle {s1}">1</div>
            <div class="pipeline-title-block">
              <div class="pipeline-title">Upload des documents</div>
              <span class="pipeline-status {s1}">{label(s1)}</span>
            </div>
          </div>
          <div class="pipeline-desc">
            Ajoute tes fichiers bruts dans le dossier RAW (PDF, DOCX, TXT, ...).
          </div>
        </div>
        """,
        unsafe_allow_html=True,
    )

    col_arrow1.markdown('<div class="pipeline-arrow">➜</div>', unsafe_allow_html=True)

    s2 = status(2)
    col2.markdown(
        f"""
        <div class="pipeline-card status-{s2}">
          <div class="pipeline-card-header">
            <div class="pipeline-circle {s2}">2</div>
            <div class="pipeline-title-block">
              <div class="pipeline-title">Extraction & Chunking</div>
              <span class="pipeline-status {s2}">{label(s2)}</span>
            </div>
          </div>
          <div class="pipeline-desc">
            Extraction du texte et découpage en petits segments pour le RAG.
          </div>
        </div>
        """,
        unsafe_allow_html=True,
    )

    col_arrow2.markdown('<div class="pipeline-arrow">➜</div>', unsafe_allow_html=True)

    s3 = status(3)
    col3.markdown(
        f"""
        <div class="pipeline-card status-{s3}">
          <div class="pipeline-card-header">
            <div class="pipeline-circle {s3}">3</div>
            <div class="pipeline-title-block">
              <div class="pipeline-title">Index vectoriel</div>
              <span class="pipeline-status {s3}">{label(s3)}</span>
            </div>
          </div>
          <div class="pipeline-desc">
            Construction / mise à jour de l’index exploité par StormCopilot.
          </div>
        </div>
        """,
        unsafe_allow_html=True,
    )

    st.markdown("</div>", unsafe_allow_html=True)


# ============================================================
# ======================= BACKEND HELPERS ====================
# ============================================================
def _save_uploaded_files(files) -> List[Path]:
    RAW_DIR.mkdir(parents=True, exist_ok=True)
    saved: List[Path] = []
    for f in files:
        dest = RAW_DIR / f.name
        with open(dest, "wb") as out:
            out.write(f.read())
        saved.append(dest)
    return saved


def _extract_and_chunk() -> Tuple[int, Path, Dict]:
    in_dir = Path(RAW_DIR)
    out_path = Path(PROC_DIR) / "chunks.jsonl"
    PROC_DIR.mkdir(parents=True, exist_ok=True)

    records = []
    stats: Dict = {"seen": 0, "processed": 0, "ignored": 0}

    for p in in_dir.glob("*"):
        if not p.is_file():
            continue

        stats["seen"] += 1
        text = extract_any(p)
        if not text:
            stats["ignored"] += 1
            continue

        processed_for_doc = False
        for i, ch in enumerate(chunk_words(text)):
            records.append({"id": f"{p.name}:{i}", "source": str(p), "text": ch})
            processed_for_doc = True

        if processed_for_doc:
            stats["processed"] += 1

    write_jsonl(records, out_path)
    return len(records), out_path, stats


def _rebuild_index() -> int:
    chunks_path = DATA_PROCESSED / "chunks.jsonl"
    if not chunks_path.exists():
        return 0

    total = 0
    with open(chunks_path, "r", encoding="utf-8") as f:
        for _ in f:
            total += 1
    return total


def _animate_progress(label: str, duration: float = 0.45) -> None:
    progress = st.progress(0, text=label)
    steps = 8
    for i in range(steps + 1):
        pct = int((i / steps) * 100)
        progress.progress(pct, text=label)
        time.sleep(duration / steps)
    progress.empty()


# ============================================================
# =========================== RENDER =========================
# ============================================================
def render_upload_tab() -> None:
    _inject_css()

    if "upload_done_step1" not in st.session_state:
        st.session_state["upload_done_step1"] = False
    if "upload_done_step2" not in st.session_state:
        st.session_state["upload_done_step2"] = False
    if "upload_done_step3" not in st.session_state:
        st.session_state["upload_done_step3"] = False
    if "upload_active_step_idx" not in st.session_state:
        st.session_state["upload_active_step_idx"] = 0

    step1_done = bool(st.session_state["upload_done_step1"])
    step2_done = bool(st.session_state["upload_done_step2"])
    step3_done = bool(st.session_state["upload_done_step3"])

    st.markdown('<div class="upload-wrapper">', unsafe_allow_html=True)

    # Nouveau titre / sous-titre
    st.markdown(
        """
        <div class="upload-header-box">
          <h2 class="upload-title">Organise ton corpus en 3 étapes</h2>
          <p class="upload-subtitle">
            Importe les fichiers, crée les chunks nécessaires puis mets à jour l’index utilisé par le copilot.
          </p>
        </div>
        """,
        unsafe_allow_html=True,
    )

    _render_pipeline(step1_done, step2_done, step3_done)

    st.markdown(
        '<p class="upload-steps-label">Étape en cours :</p>',
        unsafe_allow_html=True,
    )

    labels = [
        "① Étape 1 · Upload",
        "② Étape 2 · Chunking",
        "③ Étape 3 · Index",
    ]

    current_idx = st.session_state["upload_active_step_idx"]

    # centrer la radio dans la page
    col_left, col_center, col_right = st.columns([1, 2, 1])
    with col_center:
        selected_label = st.radio(
            "",
            labels,
            index=current_idx,
            horizontal=True,
            key="upload_steps_radio",
        )

    selected_idx = labels.index(selected_label)
    st.session_state["upload_active_step_idx"] = selected_idx

    st.markdown("---")

    if selected_idx == 0:
        st.markdown("### 📁 Étape 1 · Upload des documents")
        st.caption(
            "Sélectionne tes fichiers et enregistre-les dans le dossier brut RAW pour qu’ils "
            "puissent être analysés."
        )

        files = st.file_uploader(
            "Upload PDF/DOCX/TXT/MD/PPTX/CSV/XLSX/HTML/JSON",
            type=[
                "pdf",
                "docx",
                "txt",
                "md",
                "pptx",
                "csv",
                "xlsx",
                "xls",
                "html",
                "htm",
                "json",
            ],
            accept_multiple_files=True,
        )

        if st.button("⬆️ Enregistrer les fichiers dans RAW"):
            if not files:
                st.warning("Aucun fichier sélectionné.")
            else:
                saved = _save_uploaded_files(files)
                st.success(
                    f"Étape 1 validée : {len(saved)} fichier(s) sauvegardé(s) dans `{RAW_DIR}`."
                )
                st.session_state["upload_done_step1"] = True

        st.markdown(
            """
            <p class="upload-card-hint">
              Astuce : évite les fichiers protégés par mot de passe ou trop volumineux.
            </p>
            """,
            unsafe_allow_html=True,
        )

    elif selected_idx == 1:
        st.markdown("### ✂️ Étape 2 · Extraction & Chunking")
        st.caption(
            "À partir des fichiers présents dans RAW, le système extrait le texte et le découpe "
            "en segments (chunks) pour le RAG."
        )

        if not st.session_state["upload_done_step1"]:
            st.info(
                "L’étape 2 sera disponible une fois que l’étape 1 aura été validée."
            )
            st.button("⚙️ Lancer l’extraction & le chunking", disabled=True)
        else:
            if st.button("⚙️ Lancer l’extraction & le chunking"):
                with st.spinner("Extraction du texte & découpage en chunks..."):
                    n, outp, stats = _extract_and_chunk()
                _animate_progress("Finalisation de l’extraction & du chunking...")

                st.success(f"Étape 2 validée : {n} chunks générés → {outp}")
                st.session_state["upload_done_step2"] = True

                seen = stats.get("seen", 0)
                processed = stats.get("processed", 0)
                ignored = stats.get("ignored", 0)

                st.markdown(
                    f"""
                    <div class="upload-summary">
                      <h3>🧾 Résumé de l’extraction</h3>
                      <ul>
                        <li>Documents détectés : <b>{seen}</b></li>
                        <li>Documents traités : <b>{processed}</b></li>
                        <li>Ignorés (vides / non lisibles) : <b>{ignored}</b></li>
                        <li>Chunks générés : <b>{n}</b></li>
                      </ul>
                    </div>
                    """,
                    unsafe_allow_html=True,
                )

    else:
        st.markdown("### 🧠 Étape 3 · Index vectoriel")
        st.caption(
            "Reconstruis l’index à partir des chunks générés. Cet index sera ensuite utilisé "
            "par le moteur RAG du copilot."
        )

        if not st.session_state["upload_done_step2"]:
            st.info(
                "L’étape 3 sera disponible une fois que l’étape 2 aura été validée."
            )
            st.button("🧠 Reconstruire l’index vectoriel", disabled=True)
        else:
            if st.button("🧠 Reconstruire l’index vectoriel"):
                with st.spinner("Reconstruction de l’index (lecture chunks.jsonl)..."):
                    total = _rebuild_index()
                _animate_progress("Mise à jour de l’index...")
                st.success(
                    f"Étape 3 validée : {total} chunks détectés dans `chunks.jsonl`."
                )
                st.session_state["upload_done_step3"] = True

        st.markdown(
            """
            <p class="upload-card-hint">
              Conseil : reconstruis l’index après un gros import de documents ou un changement
              de modèle d’embedding.
            </p>
            """,
            unsafe_allow_html=True,
        )

    st.markdown("</div>", unsafe_allow_html=True)
