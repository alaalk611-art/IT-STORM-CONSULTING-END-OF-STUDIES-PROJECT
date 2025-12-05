# -*- coding: utf-8 -*-
# Path: src/ui/sections/upload.py

from __future__ import annotations

from pathlib import Path
from textwrap import dedent
import time
from typing import List, Dict, Tuple

import streamlit as st

# === Backend : on utilise directement tes briques existantes ===
from src.config.settings import RAW_DIR, PROC_DIR
from src.ingestion.chunking import chunk_words
from src.ingestion.extract_text import extract_any
from src.utils.io import write_jsonl

DATA_PROCESSED = PROC_DIR  # pour chunks.jsonl


# ========== STYLES ==========
def _inject_css() -> None:
    """Style simple, clair (white / light) avec un peu d'animation."""
    st.markdown(
        dedent(
            """
            <style>
            .upload-wrapper {
                padding: 0.5rem 0.2rem 0.2rem 0.2rem;
            }

            .upload-header-box {
                background-color: #ffffff;
                border-radius: 16px;
                padding: 1.0rem 1.2rem;
                border: 1px solid #e5e7eb;
                animation: uploadFadeIn 0.35s ease-out;
            }

            .upload-title {
                font-size: 1.25rem;
                font-weight: 600;
                color: #0f172a;
                margin: 0 0 0.25rem 0;
            }

            .upload-subtitle {
                font-size: 0.90rem;
                color: #4b5563;
                margin: 0;
            }

            .upload-steps {
                display: inline-flex;
                align-items: center;
                gap: 0.4rem;
                margin-top: 0.75rem;
                font-size: 0.80rem;
            }

            .upload-step-pill {
                padding: 0.18rem 0.6rem;
                border-radius: 999px;
                border: 1px solid #e5e7eb;
                background-color: #f9fafb;
                color: #4b5563;
            }

            .upload-step-pill.active {
                border-color: #2563eb;
                background-color: #dbeafe;
                color: #1f2937;
                font-weight: 500;
            }

            .upload-grid {
                display: grid;
                grid-template-columns: minmax(0, 1.5fr) minmax(0, 1fr);
                gap: 0.9rem;
                margin-top: 1.0rem;
            }

            @media (max-width: 900px) {
                .upload-grid {
                    grid-template-columns: minmax(0, 1fr);
                }
            }

            .upload-card {
                background-color: #ffffff;
                border-radius: 14px;
                padding: 0.9rem 1.0rem;
                border: 1px solid #e5e7eb;
                box-shadow: 0 8px 16px rgba(15,23,42,0.03);
                transition: box-shadow 0.18s ease-out,
                            transform 0.18s ease-out,
                            border-color 0.18s ease-out;
                animation: uploadFadeInUp 0.40s ease-out;
            }

            .upload-card:hover {
                border-color: #bfdbfe;
                box-shadow: 0 14px 28px rgba(37,99,235,0.10);
                transform: translateY(-1px);
            }

            .upload-card-title {
                font-size: 0.95rem;
                font-weight: 600;
                color: #0f172a;
                margin-bottom: 0.35rem;
                display: flex;
                align-items: center;
                gap: 0.4rem;
            }

            .upload-card-title span.icon {
                font-size: 1.1rem;
            }

            .upload-card-sub {
                font-size: 0.82rem;
                color: #4b5563;
                margin-bottom: 0.6rem;
            }

            .stButton > button {
                border-radius: 999px !important;
                border: 1px solid #e5e7eb;
                background-color: #f9fafb;
                color: #111827;
                font-size: 0.85rem;
                padding: 0.35rem 0.9rem;
            }
            .stButton > button:hover {
                border-color: #2563eb;
                background-color: #eff6ff;
                color: #1d4ed8;
            }

            div[data-testid="stFileUploader"] > label {
                font-size: 0.82rem;
                font-weight: 500;
                color: #374151;
                margin-bottom: 0.25rem;
            }
            div[data-testid="stFileUploader"] {
                background-color: #f9fafb;
                border-radius: 10px;
                padding: 0.6rem 0.6rem 0.7rem 0.6rem;
                border: 1px dashed #d1d5db;
            }

            .upload-chunks-title {
                font-size: 0.90rem;
                font-weight: 500;
                color: #111827;
                margin-top: 0.9rem;
                margin-bottom: 0.2rem;
                display: flex;
                align-items: center;
                gap: 0.35rem;
            }
            .upload-chunks-title span.badge {
                font-size: 0.70rem;
                text-transform: uppercase;
                letter-spacing: 0.08em;
                padding: 0.12rem 0.45rem;
                border-radius: 999px;
                border: 1px solid #e5e7eb;
                color: #4b5563;
                background-color: #f9fafb;
            }

            @keyframes uploadFadeIn {
                0% { opacity: 0; transform: translateY(4px); }
                100% { opacity: 1; transform: translateY(0); }
            }

            @keyframes uploadFadeInUp {
                0% { opacity: 0; transform: translateY(6px); }
                100% { opacity: 1; transform: translateY(0); }
            }
            </style>
            """
        ),
        unsafe_allow_html=True,
    )


# ========== BACKEND HELPERS (local, sans pipeline.py) ==========

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
    """
    Lit les fichiers dans RAW_DIR, extrait le texte, chunk,
    et écrit data/processed/chunks.jsonl (via PROC_DIR).
    """
    in_dir = Path(RAW_DIR)
    out_path = Path(PROC_DIR) / "chunks.jsonl"
    PROC_DIR.mkdir(parents=True, exist_ok=True)

    records = []
    stats: Dict = {"seen": 0, "processed": 0, "ignored": 0, "by_ext": {}}

    for p in in_dir.glob("*"):
        if not p.is_file():
            continue

        stats["seen"] += 1
        ext = p.suffix.lower() or "<no_ext>"
        stats["by_ext"].setdefault(ext, 0)
        stats["by_ext"][ext] += 1

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
    """
    Implémentation minimale :
    - lit chunks.jsonl
    - retourne le nombre de lignes
    (Tu pourras plus tard brancher ici ton vrai build_index / Chroma.)
    """
    chunks_path = DATA_PROCESSED / "chunks.jsonl"
    if not chunks_path.exists():
        return 0

    total = 0
    with open(chunks_path, "r", encoding="utf-8") as f:
        for _ in f:
            total += 1
    return total


def _animate_progress(label: str = "Traitement en cours...", duration: float = 0.45) -> None:
    """
    Petite barre de progression animée (cosmétique) après une opération lourde.
    """
    progress = st.progress(0, text=label)
    steps = 8
    for i in range(steps + 1):
        pct = int((i / steps) * 100)
        progress.progress(pct, text=label)
        time.sleep(duration / steps)
    progress.empty()


# ========== RENDER ==========
def render_upload_tab() -> None:
    """
    Tab 2 : 📂 Upload & Index — version claire, simple, avec progress bar et résumé.
    """
    _inject_css()

    st.markdown('<div class="upload-wrapper">', unsafe_allow_html=True)

    # En-tête
    st.markdown(
        dedent(
            """
            <div class="upload-header-box">
              <div class="upload-title">📂 Upload & Index</div>
              <p class="upload-subtitle">
                Uploade tes documents, lance l’extraction en chunks puis reconstruis l’index RAG.
              </p>
              <div class="upload-steps">
                <span class="upload-step-pill active">1. Upload</span>
                <span class="upload-step-pill">2. Chunk</span>
                <span class="upload-step-pill">3. Index</span>
              </div>
            </div>
            """
        ),
        unsafe_allow_html=True,
    )

    # Grille : gauche = upload/chunk, droite = index
    st.markdown('<div class="upload-grid">', unsafe_allow_html=True)

    # --------- Colonne gauche : Upload & Chunk ----------
    with st.container():
        st.markdown('<div class="upload-card">', unsafe_allow_html=True)
        st.markdown(
            """
            <div class="upload-card-title">
              <span class="icon">📁</span>
              <span>Étape 1 & 2 · Upload & Chunk</span>
            </div>
            <div class="upload-card-sub">
              Sélectionne tes fichiers, sauvegarde-les puis déclenche l’extraction & le découpage en chunks.
            </div>
            """,
            unsafe_allow_html=True,
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

        col_save, col_chunk = st.columns(2)

        # Save uploads
        if col_save.button("⬆️  Save uploads"):
            if not files:
                st.warning("Aucun fichier sélectionné.")
            else:
                saved = _save_uploaded_files(files)
                st.success(f"{len(saved)} fichier(s) sauvegardé(s) dans `{RAW_DIR}`.")

        # Extract & Chunk
        if col_chunk.button("⚙️  Extract & Chunk"):
            with st.spinner("Extraction & découpage en chunks..."):
                n, outp, stats = _extract_and_chunk()
            _animate_progress("Finalisation de l’extraction & du chunking...")

            st.success(f"{n} chunks générés → {outp}")

            # Petit résumé automatique
            seen = stats.get("seen", 0)
            processed = stats.get("processed", 0)
            ignored = stats.get("ignored", 0)
            by_ext = stats.get("by_ext", {})

            summary_lines = [
                "### 🧾 Résumé de l’extraction",
                f"- 📄 Documents détectés : **{seen}**",
                f"- ✅ Documents traités : **{processed}**",
                f"- 🚫 Ignorés : **{ignored}**",
                f"- 🧩 Chunks générés : **{n}**",
            ]

            if by_ext:
                exts_str = ", ".join(
                    f"`{ext}`: {count}" for ext, count in by_ext.items()
                )
                summary_lines.append(f"- 📂 Répartition par extension : {exts_str}")

            st.markdown("\n".join(summary_lines))

        st.markdown("</div>", unsafe_allow_html=True)

    # --------- Colonne droite : Index ----------
    with st.container():
        st.markdown('<div class="upload-card">', unsafe_allow_html=True)
        st.markdown(
            """
            <div class="upload-card-title">
              <span class="icon">🧠</span>
              <span>Étape 3 · Index vectoriel</span>
            </div>
            <div class="upload-card-sub">
              Recrée l’index (compte des chunks) à partir du fichier généré.
              Tu pourras plus tard brancher ici ton vrai index Chroma.
            </div>
            """,
            unsafe_allow_html=True,
        )

        if st.button("🧠  Rebuild Vector Index"):
            with st.spinner("Reconstruction de l’index..."):
                total = _rebuild_index()
            _animate_progress("Mise à jour de l’index...")

            st.success(f"{total} chunks détectés dans `chunks.jsonl`.")

        # Statut chunks.jsonl
        chunks_file = DATA_PROCESSED / "chunks.jsonl"
        if chunks_file.exists():
            st.info(f"Fichier de chunks détecté : `{chunks_file.as_posix()}`", icon="✅")
        else:
            st.warning("Aucun fichier `chunks.jsonl` détecté pour l’instant.", icon="ℹ️")

        st.markdown("</div>", unsafe_allow_html=True)

    st.markdown("</div>", unsafe_allow_html=True)  # fin upload-grid
    st.markdown("</div>", unsafe_allow_html=True)  # fin upload-wrapper
