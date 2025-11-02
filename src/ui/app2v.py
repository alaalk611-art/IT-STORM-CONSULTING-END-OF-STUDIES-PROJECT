# app2v.py — UI deux-en-un avec transition animée (Client ↔ Employé)
from __future__ import annotations

import base64
import io
import os
import sys
import time
from pathlib import Path
from typing import List, Tuple

# --------- Chemins & Imports de base ----------
ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT))

# Vector DB & Embeddings
import chromadb
import pandas as pd
import streamlit as st
from chromadb.config import Settings
from sentence_transformers import SentenceTransformer

# LLM (optionnel, fallback extractif sinon)
USE_LLM = True
try:
    from transformers import AutoModelForSeq2SeqLM, AutoTokenizer
    from transformers import pipeline as hf_pipeline
except Exception:
    USE_LLM = False

# --------- Constantes ----------
PERSIST_DIR = str((ROOT / "vectors").resolve())
COLLECTION_PUBLIC = "itstorm_public"
COLLECTION_INTERNAL = "itstorm_internal"
EMB_MODEL = "sentence-transformers/all-MiniLM-L6-v2"

# Palettes : Client (bleu) ↔ Employé (violet)
PALETTE_PUBLIC = {
    "bg": "#0b132b",
    "panel": "#1c2541",
    "accent": "#3a86ff",
    "text": "#eef4ff",
    "muted": "#a8b2d1",
}
PALETTE_INTERNAL = {
    "bg": "#120d22",
    "panel": "#1b1530",
    "accent": "#8a5cff",
    "text": "#f2ecff",
    "muted": "#b9aee6",
}

# --------- Page config ----------
st.set_page_config(page_title="StormCopilot — 2 vues", page_icon="✨", layout="wide")


# --------- CSS (transition + look & feel) ----------
def inject_css(palette: dict, mode_label: str):
    css = f"""
    <style>
      html, body, [data-testid="stAppViewContainer"] {{
        background: radial-gradient(1200px 800px at 20% 10%, {palette['panel']} 0%, {palette['bg']} 55%, #060913 100%) !important;
        color: {palette['text']} !important;
        transition: background 600ms ease-in-out, color 300ms ease-in-out;
      }}
      [data-testid="stSidebar"] {{
        background: linear-gradient(160deg, {palette['panel']} 0%, {palette['bg']} 100%) !important;
        border-right: 1px solid rgba(255,255,255,0.06);
      }}
      .mode-badge {{
        display:inline-flex; gap:.5rem; align-items:center;
        padding:.35rem .8rem; border-radius:9999px;
        background: {palette['panel']}; color:{palette['text']};
        border:1px solid rgba(255,255,255,.08);
        box-shadow: 0 10px 30px rgba(0,0,0,.25);
        font-weight:700; letter-spacing:.2px;
      }}
      .pill {{
        padding:.25rem .6rem; border-radius:9999px;
        background: rgba(255,255,255,.06);
        border:1px solid rgba(255,255,255,.10);
        color: {palette['muted']}; font-size:12px;
      }}
      .card {{
        background: {palette['panel']};
        border: 1px solid rgba(255,255,255,.08);
        border-radius: 18px; padding: 14px 16px;
        box-shadow: 0 8px 28px rgba(0,0,0,.25);
      }}
      .btn-accent button {{
        background: {palette['accent']} !important; color: white !important; font-weight:700 !important;
        border-radius:12px !important; border:none !important;
        box-shadow: 0 8px 20px rgba(0,0,0,.25);
      }}

      /* ===== Animations ===== */
      .fadeSlideIn {{
        animation: fadeSlideIn 450ms ease both;
      }}
      @keyframes fadeSlideIn {{
        0% {{ opacity: 0; transform: translateY(12px) scale(.98); }}
        100%{{ opacity: 1; transform: translateY(0)   scale(1);   }}
      }}
      .flip {{
        perspective: 1200px;
      }}
      .flip .pane {{
        transform-style: preserve-3d;
        animation: flipIn 600ms cubic-bezier(.2,.8,.2,1) both;
      }}
      @keyframes flipIn {{
        0% {{ transform: rotateX(-18deg) rotateY(6deg) translateY(12px); opacity:0; }}
        100%{{ transform: rotateX(0)     rotateY(0)    translateY(0);    opacity:1; }}
      }}

      .accent {{
        color: {palette['accent']};
        text-shadow: 0 4px 20px rgba(0,0,0,.4);
      }}
      hr {{ border:none; border-top:1px solid rgba(255,255,255,.08); margin: .6rem 0 1rem; }}
    </style>
    """
    st.markdown(css, unsafe_allow_html=True)
    st.markdown(
        f'<div class="fadeSlideIn" style="margin-bottom:.6rem;"><span class="mode-badge">Mode&nbsp;: <span class="accent">{mode_label}</span></span></div>',
        unsafe_allow_html=True,
    )


# --------- Clients / Embeddings / LLM ----------
@st.cache_resource
def get_db():
    return chromadb.Client(Settings(persist_directory=PERSIST_DIR, is_persistent=True))


@st.cache_resource
def get_collection(name: str):
    db = get_db()
    names = [c.name for c in db.list_collections()]
    return db.get_collection(name) if name in names else db.create_collection(name)


@st.cache_resource
def get_embedder():
    return SentenceTransformer(EMB_MODEL)


@st.cache_resource
def get_llm():
    if not USE_LLM:
        return None
    try:
        model = "google/flan-t5-small"
        tok = AutoTokenizer.from_pretrained(model)
        mdl = AutoModelForSeq2SeqLM.from_pretrained(model)
        return hf_pipeline(
            "text2text-generation", model=mdl, tokenizer=tok, max_new_tokens=220
        )
    except Exception:
        return None


def ensure_demo_seed():
    """Crée quelques documents de démo si les collections sont vides, pour tester l’UI immédiatement."""
    db = get_db()
    emb = get_embedder()
    for name, docs in [
        (
            COLLECTION_PUBLIC,
            [
                (
                    "IT Storm en bref",
                    "IT Storm est une société de consulting spécialisée en Cloud, DevOps et IA. Nous aidons nos clients à automatiser et sécuriser leurs déploiements.",
                ),
                (
                    "Offres",
                    "Nos offres couvrent l’adoption du cloud, l’IaC, la mise en place de CI/CD, et l’industrialisation de l’IA (RAG, MLOps).",
                ),
                (
                    "Engagement",
                    "Notre approche met l’accent sur la qualité, la sécurité et la valeur métier, avec des livrables concrets et mesurables.",
                ),
            ],
        ),
        (
            COLLECTION_INTERNAL,
            [
                (
                    "Procédure interne CI/CD",
                    "Pipeline CI/CD GitHub Actions + ArgoCD. Étapes : build, tests, scan SAST, déploiement sur staging, validation, déploiement prod.",
                ),
                (
                    "Guide RAG interne",
                    "Ingestion documents, embeddings all-MiniLM-L6-v2, stockage Chroma. Chaîne LangChain avec top_k=6, réponses sourcées.",
                ),
                (
                    "Veille hebdo",
                    "Scraper les nouveautés cloud/IA, résumer via LLM. Générer un PPT et un mémo PDF pour le comité technique.",
                ),
            ],
        ),
    ]:
        coll = get_collection(name)
        count = coll.count()
        if count == 0:
            texts, metas, ids = [], [], []
            for i, (title, content) in enumerate(docs, start=1):
                texts.append(f"[{title}] {content}")
                metas.append(
                    {"source": f"{name}:{title.replace(' ', '_').lower()}.txt"}
                )
                ids.append(f"{name}_seed_{i}")
            vectors = emb.encode(texts, normalize_embeddings=True).tolist()
            coll.add(documents=texts, embeddings=vectors, metadatas=metas, ids=ids)


def retrieve(query: str, collection: str, k: int = 4):
    coll = get_collection(collection)
    emb = get_embedder()
    qv = emb.encode([query], normalize_embeddings=True).tolist()[0]
    res = coll.query(query_embeddings=[qv], n_results=k)
    docs = res.get("documents", [[]])[0]
    metas = res.get("metadatas", [[]])[0]
    return [(d, (m or {}).get("source", "unknown")) for d, m in zip(docs, metas)]


def generate_answer_public(question: str, contexts: List[str]) -> str:
    # Public : ton marketing concis, pas de sources
    tmpl = (
        "Tu es l’assistant PUBLIC d’IT Storm. Réponds uniquement à partir du contexte, en 5-7 lignes maximum, "
        "ton informatif et accessible. N’évoque jamais de documents internes.\n\n"
        f"Question: {question}\n\nContexte:\n"
        + "\n---\n".join(contexts)
        + "\n\nRéponse concise:"
    )
    llm = get_llm()
    if llm is None:
        # Fallback extractif
        return " ".join(contexts)[:700]
    return llm(tmpl)[0]["generated_text"].strip()


def generate_answer_internal(question: str, ctx_pairs: List[Tuple[str, str]]) -> str:
    # Interne : réponse + puces + sources (noms simples)
    contexts = []
    sources = []
    for text, src in ctx_pairs:
        contexts.append(text)
        sources.append(src.split(":")[-1])
    tmpl = (
        "Tu es un copilote INTERNE. Réponds UNIQUEMENT avec le contexte. Si l’info n’y est pas, réponds 'Je ne sais pas.' "
        "Termine par 3-5 puces opérationnelles.\n\n"
        f"Question: {question}\n\nContexte:\n"
        + "\n---\n".join(contexts)
        + "\n\nRéponse structurée:"
    )
    llm = get_llm()
    if llm is None:
        base = " ".join(contexts)[:900]
        bullets = "\n".join([f"- Point clé {i}" for i in range(1, 4)])
        srcs = ", ".join(sorted(set(sources)))
        return f"{base}\n\n{bullets}\n\nSources: {srcs}"
    out = llm(tmpl)[0]["generated_text"].strip()
    out += f"\n\nSources: {', '.join(sorted(set(sources)))}"
    return out


# --------- Sidebar (switch dynamique) ----------
mode = st.sidebar.toggle(
    "Basculer Employé ↔ Client",
    value=False,
    help="OFF = Client (public), ON = Employé (interne)",
)
is_internal = bool(mode)
palette = PALETTE_INTERNAL if is_internal else PALETTE_PUBLIC
inject_css(palette, "Employé (Interne)" if is_internal else "Client (Public)")

# --------- Header animé ----------
st.markdown(
    f"""
    <div class="flip"><div class="pane">
      <h1 style="margin:.3rem 0 0;">StormCopilot <span class="accent">2&nbsp;vues</span></h1>
      <div style="opacity:.8">Une seule app — deux expériences complémentaires.</div>
      <div style="margin-top:.4rem;">
        <span class="pill">RAG</span> <span class="pill">ChromaDB</span> <span class="pill">Sentence-Transformers</span> <span class="pill">LLM local (optionnel)</span>
      </div>
    </div></div>
    """,
    unsafe_allow_html=True,
)

st.markdown("<hr/>", unsafe_allow_html=True)

# --------- Barre d’actions hautes ----------
cA, cB, cC = st.columns([0.38, 0.32, 0.30])
with cA:
    st.markdown(
        '<div class="card fadeSlideIn"><b>🎯 But</b><br />Client: info claire & vitrine.<br />Employé: réponses sourcées & productivité.</div>',
        unsafe_allow_html=True,
    )
with cB:
    if st.button("▶ Seed demo data", use_container_width=True, type="primary"):
        ensure_demo_seed()
        st.success("Collections remplies avec quelques documents de démo.")
with cC:
    st.markdown(
        f'<div class="card fadeSlideIn"><b>🎨 Palette</b><br/>Accent actuel : <span class="accent">{palette["accent"]}</span></div>',
        unsafe_allow_html=True,
    )

st.markdown("<hr/>", unsafe_allow_html=True)

# --------- Corps principal (2 modes) ----------
if not is_internal:
    # =================== MODE CLIENT (PUBLIC) ===================
    st.markdown("### 💬 Chat Public — FAQ / Présentation", unsafe_allow_html=True)
    q = st.text_input("Posez votre question (contenus publics)")
    topk = st.slider("Top-K (public)", 2, 8, 3, 1)
    if st.button("Répondre (Public)", use_container_width=True):
        ensure_demo_seed()
        with st.spinner("Recherche publique + génération…"):
            pairs = retrieve(q, COLLECTION_PUBLIC, k=topk)
            contexts = [p[0] for p in pairs]
            ans = generate_answer_public(q, contexts)
        st.markdown('<div class="card fadeSlideIn">', unsafe_allow_html=True)
        st.subheader("Réponse")
        st.write(ans)
        st.caption("Ce chatbot public ne cite pas de chemins ni de documents internes.")
        st.markdown("</div>", unsafe_allow_html=True)

else:
    # =================== MODE EMPLOYÉ (INTERNE) ===================
    tabs = st.tabs(["💬 Knowledge Chat", "📂 Aperçu & Upload (démo)"])
    with tabs[0]:
        st.markdown("### 💬 Knowledge Q/A — Interne (réponses sourcées)")
        q = st.text_input("Question (documents internes)")
        topk = st.slider("Top-K (interne)", 2, 12, 6, 1, key="k_internal")
        if st.button("Répondre (Interne)", use_container_width=True):
            ensure_demo_seed()
            with st.spinner("Récupération interne + génération…"):
                pairs = retrieve(q, COLLECTION_INTERNAL, k=topk)
                ans = generate_answer_internal(q, pairs)
            st.markdown('<div class="card fadeSlideIn">', unsafe_allow_html=True)
            st.subheader("Réponse")
            st.write(ans)
            with st.expander("📚 Contextes (chunks)"):
                for i, (txt, src) in enumerate(pairs, 1):
                    st.markdown(f"**Chunk #{i}** — *{src}*")
                    st.write((txt[:1000] + "…") if len(txt) > 1000 else txt)
            st.markdown("</div>", unsafe_allow_html=True)

    with tabs[1]:
        st.markdown("### 📂 Démo — Aperçu des collections")
        ensure_demo_seed()
        db = get_db()
        cols = st.columns(2)
        for j, name in enumerate([COLLECTION_PUBLIC, COLLECTION_INTERNAL]):
            with cols[j]:
                try:
                    count = db.get_collection(name).count()
                except Exception:
                    count = 0
                st.markdown(
                    f'<div class="card"><b>{name}</b><br/>Documents indexés : {count}</div>',
                    unsafe_allow_html=True,
                )
        st.caption(
            "Cette section est une démo visuelle (pas d’upload réel ici pour rester simple)."
        )
