# -*- coding: utf-8 -*-
# Path: src/ui/sections/home.py

from __future__ import annotations

import os
from pathlib import Path
import streamlit as st


def render_home_tab() -> None:
    # ==========================================================
    # Helpers (métriques dynamiques, robustes)
    # ==========================================================
    def _count_files(folder: str, exts: tuple[str, ...] | None = None) -> str:
        try:
            p = Path(folder)
            if not p.exists():
                return "—"
            if exts:
                return str(sum(1 for f in p.rglob("*") if f.is_file() and f.suffix.lower() in exts))
            return str(sum(1 for f in p.rglob("*") if f.is_file()))
        except Exception:
            return "—"

    def _file_exists(fp: str) -> bool:
        try:
            return Path(fp).exists()
        except Exception:
            return False

    # Dossiers “classiques” du projet (fallback si différents → affiche —)
    RAW_DIR = os.getenv("SC_RAW_DIR", "data/raw")
    PROC_DIR = os.getenv("SC_PROC_DIR", "data/processed")
    CHUNKS_FP = os.getenv("SC_CHUNKS_FILE", str(Path(PROC_DIR) / "chunks.jsonl"))

    docs_raw = _count_files(RAW_DIR, exts=(".pdf", ".docx", ".txt", ".md", ".pptx", ".csv", ".xlsx", ".xls", ".html", ".htm", ".json"))
    chunks_ready = "OK" if _file_exists(CHUNKS_FP) else "—"
    proc_files = _count_files(PROC_DIR)  # indicateur simple (fichiers process)

    # ==========================================================
    # CSS GLOBAL (inchangé : même thème / même style)
    # ==========================================================
    st.markdown(
        """
<style>

/* ================= HERO CARD ================= */

.home-hero{
position:relative;
padding:1.8rem;
border-radius:22px;
background:
radial-gradient(circle at 0% 0%,rgba(56,189,248,.22),transparent 55%),
radial-gradient(circle at 100% 0%,rgba(129,140,248,.24),transparent 55%),
linear-gradient(135deg,rgba(15,23,42,.96),rgba(15,23,42,.90));
border:1px solid rgba(148,163,184,.55);
box-shadow:0 32px 80px rgba(15,23,42,.80);
overflow:hidden;
backdrop-filter:blur(22px) saturate(1.25);
transform-origin:center center;
animation:fadeInHero .8s ease-out,heroBreath 14s ease-in-out infinite;
transition:transform .6s ease,box-shadow .6s ease;
}

/* background animé soft (radial waves) */
.home-hero::before{
content:"";
position:absolute;
inset:-40%;
background:
radial-gradient(circle at 10% 0%,rgba(56,189,248,.14),transparent 60%),
radial-gradient(circle at 90% 10%,rgba(129,140,248,.12),transparent 60%),
linear-gradient(120deg,rgba(56,189,248,.18),rgba(129,140,248,.05),rgba(56,189,248,.18));
opacity:.55;
mix-blend-mode:soft-light;
pointer-events:none;
animation:heroWaves 22s ease-in-out infinite alternate;
z-index:0;
}

/* halo pulsant derrière le logo */
.home-hero::after{
content:"";
position:absolute;
width:210px;
height:210px;
left:-40px;
top:-40px;
border-radius:999px;
background:radial-gradient(circle,rgba(56,189,248,.55),transparent 65%);
opacity:.65;
filter:blur(6px);
mix-blend-mode:screen;
animation:haloPulse 12s ease-in-out infinite;
pointer-events:none;
z-index:0;
}

.home-hero:hover{
transform:perspective(1100px) rotateX(3deg) rotateY(-3deg) translateY(-4px);
box-shadow:0 40px 95px rgba(15,23,42,.95);
}

/* orbes parallax */
.home-hero-orb{
position:absolute;
border-radius:999px;
filter:blur(18px);
opacity:.9;
mix-blend-mode:screen;
pointer-events:none;
transition:transform .9s ease;
z-index:0;
}
.home-hero-orb.orb-left{
width:140px;
height:140px;
left:-40px;
top:-30px;
background:radial-gradient(circle,rgba(56,189,248,.80),transparent 60%);
animation:floatOrb1 11s ease-in-out infinite alternate;
}
.home-hero-orb.orb-right{
width:220px;
height:220px;
right:-60px;
top:-40px;
background:radial-gradient(circle,rgba(129,140,248,.90),transparent 60%);
animation:floatOrb2 15s ease-in-out infinite alternate;
}
.home-hero:hover .home-hero-orb.orb-left{
transform:translate3d(12px,10px,0) scale(1.05);
}
.home-hero:hover .home-hero-orb.orb-right{
transform:translate3d(-14px,6px,0) scale(1.04);
}

/* bloc principal */
.home-hero-main{
z-index:2;
position:relative;
display:flex;
flex-direction:row;
gap:1.6rem;
align-items:flex-start;
}

/* logo */
.home-hero-logo-badge{
min-width:60px;
min-height:60px;
border-radius:20px;
background:radial-gradient(circle at 30% 0%,#38bdf8,#4f46e5);
display:flex;
align-items:center;
justify-content:center;
box-shadow:0 14px 40px rgba(37,99,235,.80);
position:relative;
overflow:hidden;
}
.home-hero-logo-badge span{
font-size:30px;
color:#e5e7eb;
}

/* titre */
.home-hero-text-title{
position:relative;
font-size:1.85rem;
font-weight:800;
letter-spacing:.02em;
margin-bottom:.15rem;
display:inline-flex;
flex-wrap:wrap;
gap:.35rem;
overflow:hidden;
}
.home-hero-text-title span.word{
background:linear-gradient(120deg,#e5e7eb,#a5b4fc,#38bdf8);
-webkit-background-clip:text;
color:transparent;
opacity:0;
transform:translateY(8px);
animation:wordRise .6s ease-out forwards;
}
.home-hero-text-title span.word:nth-child(1){animation-delay:0s;}
.home-hero-text-title span.word:nth-child(2){animation-delay:.12s;}
.home-hero-text-title span.word:nth-child(3){animation-delay:.24s;}
.home-hero-text-title span.word:nth-child(4){animation-delay:.36s;}

/* effet "sheen" qui balaye le titre */
.home-hero-text-title::after{
content:"";
position:absolute;
top:-20%;
left:-30%;
width:40%;
height:150%;
background:linear-gradient(110deg,transparent,rgba(248,250,252,.85),transparent);
opacity:0;
transform:translateX(-120%);
animation:titleSheen 7s ease-in-out 1.4s infinite;
}

/* sous-titre */
.home-hero-text-sub{
font-size:.95rem;
color:#cbd5f5;
max-width:650px;
}

/* mot "portage salarial" mis en avant */
.spark{
color:#fde68a;
font-weight:600;
text-shadow:0 0 10px rgba(250,204,21,.4);
}

/* pills */
.home-hero-pill-row{
margin-top:.85rem;
display:flex;
flex-wrap:wrap;
gap:.45rem;
}
.home-pill{
display:inline-flex;
align-items:center;
gap:.35rem;
padding:.22rem .7rem;
border-radius:999px;
font-size:.75rem;
background:rgba(15,23,42,.85);
border:1px solid rgba(148,163,184,.55);
color:#e5e7eb;
backdrop-filter:blur(8px);
}
.home-pill-dot{
width:7px;
height:7px;
border-radius:999px;
background:radial-gradient(circle,#22c55e,#15803d);
box-shadow:0 0 8px rgba(34,197,94,.85);
}

/* mini dashboard dans le hero */
.home-metrics-row{
margin-top:.9rem;
display:flex;
flex-wrap:wrap;
gap:.45rem;
}
.home-metric-chip{
display:inline-flex;
flex-direction:column;
justify-content:center;
gap:.08rem;
padding:.35rem .7rem;
border-radius:14px;
border:1px solid rgba(148,163,184,.55);
background:rgba(15,23,42,.88);
backdrop-filter:blur(10px);
min-width:140px;
}
.home-metric-label{
font-size:.7rem;
color:#9ca3af;
}
.home-metric-value{
font-size:.86rem;
font-weight:600;
color:#e5e7eb;
}

/* bloc mini radar / statut */
.home-hero-mini{
margin-left:auto;
display:flex;
flex-direction:column;
align-items:flex-end;
gap:.55rem;
}
.home-mini-chip{
font-size:.72rem;
padding:.25rem .65rem;
border-radius:999px;
border:1px solid rgba(148,163,184,.55);
background:rgba(15,23,42,.92);
color:#e5e7eb;
}

/* radar */
.home-mini-radar{
width:125px;
height:125px;
border-radius:999px;
border:1px solid rgba(148,163,184,.7);
background:
radial-gradient(circle at 50% 50%,rgba(59,130,246,.55),transparent 55%),
radial-gradient(circle at 0% 0%,rgba(56,189,248,.30),transparent 60%),
radial-gradient(circle at 100% 100%,rgba(129,140,248,.40),transparent 60%);
box-shadow:0 22px 45px rgba(15,23,42,.9);
position:relative;
overflow:hidden;
}
.home-mini-radar-sweep{
position:absolute;
width:200%;
height:200%;
top:-50%;
left:-50%;
background:conic-gradient(from 0deg,rgba(59,130,246,0),rgba(56,189,248,.85),rgba(59,130,246,0) 60%);
animation:radarSweep 7.5s linear infinite;
}
.home-mini-radar-center{
position:absolute;
width:12px;
height:12px;
border-radius:999px;
background:#22c55e;
box-shadow:0 0 12px rgba(34,197,94,.95);
top:50%;
left:50%;
transform:translate(-50%,-50%);
}

/* ============= AUTRES BLOCS ================= */

.home-row{margin-top:1.35rem;}
.home-glow-card{
border-radius:18px;
padding:.95rem;
border:1px solid rgba(148,163,184,.45);
background:radial-gradient(circle at 0% 0%,rgba(56,189,248,.18),transparent 65%),rgba(15,23,42,.96);
box-shadow:0 18px 40px rgba(15,23,42,.85);
font-size:.82rem;
color:#e5e7eb;
opacity:0;
transform:translateY(18px);
}
.home-glow-card.card-1{animation:cardFadeUp .6s ease-out .20s forwards;}
.home-glow-card.card-2{animation:cardFadeUp .6s ease-out .35s forwards;}
.home-glow-card.card-3{animation:cardFadeUp .6s ease-out .50s forwards;}

.home-steps{
margin-top:1.8rem;
opacity:0;
transform:translateY(14px);
animation:sectionFadeUp .6s ease-out .65s forwards;
}
.home-steps-title{font-size:1.05rem;font-weight:700;margin-bottom:.5rem;}
.home-step-row{display:flex;flex-wrap:wrap;gap:.7rem;}
.home-step{flex:1 1 210px;display:flex;gap:.55rem;font-size:.78rem;}
.home-step-badge{
min-width:24px;
height:24px;
border-radius:999px;
background:radial-gradient(circle,#4f46e5,#1d4ed8);
color:#fff;
font-weight:700;
font-size:.78rem;
display:flex;
align-items:center;
justify-content:center;
box-shadow:0 10px 22px rgba(79,70,229,.7);
}
.home-step-label{font-weight:600;margin-bottom:.05rem;}
.home-step-sub{opacity:.85;}

.home-bottom{margin-top:1.5rem;}
.home-bottom-card{
border-radius:18px;
border:1px dashed rgba(148,163,184,.6);
padding:.95rem;
background:rgba(248,250,252,.92);
font-size:.80rem;
opacity:0;
transform:translateY(14px);
animation:sectionFadeUp .6s ease-out .85s forwards;
}
.home-bottom-title{font-weight:700;font-size:.90rem;margin-bottom:.25rem;}
.home-bottom-list{padding-left:1.1rem;margin-bottom:.2rem;}
.home-bottom-list li{margin-bottom:.12rem;}

/* ================== ANIMATIONS KEYFRAMES ================== */
@keyframes fadeInHero{from{opacity:0;transform:translateY(10px);}to{opacity:1;transform:translateY(0);}}
@keyframes heroBreath{
0%{transform:perspective(1100px) rotateX(0deg) rotateY(0deg) translateY(0);}
50%{transform:perspective(1100px) rotateX(2deg) rotateY(-2deg) translateY(-4px);}
100%{transform:perspective(1100px) rotateX(0deg) rotateY(0deg) translateY(0);}
}
@keyframes heroWaves{
0%{transform:translate3d(0,0,0) scale(1);}
50%{transform:translate3d(-12px,6px,0) scale(1.05);}
100%{transform:translate3d(10px,-8px,0) scale(1.04);}
}
@keyframes haloPulse{
0%{opacity:.4;transform:scale(1);}
50%{opacity:.9;transform:scale(1.08);}
100%{opacity:.45;transform:scale(1);}
}
@keyframes floatOrb1{0%{transform:translate3d(0,0,0) scale(1);}100%{transform:translate3d(15px,22px,0) scale(1.08);}}
@keyframes floatOrb2{0%{transform:translate3d(0,0,0) scale(1);}100%{transform:translate3d(-18px,18px,0) scale(1.04);}}
@keyframes wordRise{from{opacity:0;transform:translateY(8px);}to{opacity:1;transform:translateY(0);}}
@keyframes titleSheen{
0%{opacity:0;transform:translateX(-120%);}
10%{opacity:.9;}
50%{opacity:.6;}
100%{opacity:0;transform:translateX(120%);}
}
@keyframes radarSweep{0%{transform:rotate(0deg);}100%{transform:rotate(360deg);}}
@keyframes cardFadeUp{from{opacity:0;transform:translateY(18px);}to{opacity:1;transform:translateY(0);}}
@keyframes sectionFadeUp{from{opacity:0;transform:translateY(14px);}to{opacity:1;transform:translateY(0);}}

</style>
""",
        unsafe_allow_html=True,
    )

    # ==========================================================
    # HERO (3D) — MAJ “projet final”
    # ==========================================================
    hero_html = (
        "<div class='home-hero'>"
        "<div class='home-hero-orb orb-left'></div>"
        "<div class='home-hero-orb orb-right'></div>"
        "<div class='home-hero-main'>"
        "<div class='home-hero-logo-badge'><span>⚡</span></div>"
        "<div>"
        "<div class='home-hero-text-title'>"
        "<span class='word'>StormCopilot</span>"
        "<span class='word'>• Plateforme IA</span>"
        "<span class='word'>+ Automation</span>"
        "<span class='word'>IT-STORM</span>"
        "</div>"
        "<div class='home-hero-text-sub'>"
        "Une plateforme unifiée pour <b>ingérer</b> vos documents, "
        "<b>interroger</b> la base RAG, <b>générer</b> des livrables consulting-ready, "
        "orchestrer des radars via <b>n8n</b>, et piloter <b>Market / Tech / MLOps</b> "
        "autour des besoins <span class='spark'>portage salarial</span> &amp; missions."
        "</div>"
        "<div class='home-hero-pill-row'>"
        "<div class='home-pill'><div class='home-pill-dot'></div>RAG + Jury multi-modèles (local)</div>"
        "<div class='home-pill'><div class='home-pill-dot'></div>Automation Studio (n8n)</div>"
        "<div class='home-pill'><div class='home-pill-dot'></div>Voice Copilot (STT → RAG → TTS)</div>"
        "</div>"
        
        "</div>"
        "<div class='home-hero-mini'>"
        
        "<div class='home-mini-radar'><div class='home-mini-radar-sweep'></div><div class='home-mini-radar-center'></div></div>"
        
        "</div>"
        "</div>"
        "</div>"
    )
    st.markdown(hero_html, unsafe_allow_html=True)

    # ==========================================================
    # 3 CARTES — MAJ : modules finaux
    # ==========================================================
    col1, col2, col3 = st.columns(3)

    col1.markdown(
        "<div class='home-row'><div class='home-glow-card card-1'>"
        "<div class='home-glow-title'><span class='icon'>🧠</span> Generate Docs · RAG + Jury</div>"
        "<div class='home-glow-tagline'>Question, résumé, et génération de livrables prêts client.</div>"
        "<div class='home-glow-bullet'>"
        "• RAG multi-sources + réduction d’hallucinations.<br>"
        "• Résumé long + mode “question” + citations.<br>"
        "• Export DOCX consulting-ready."
        "</div>"
        "</div></div>",
        unsafe_allow_html=True,
    )

    col2.markdown(
        "<div class='home-row'><div class='home-glow-card card-2'>"
        "<div class='home-glow-title'><span class='icon'>🎙️</span> Voice Copilot · STT → RAG → TTS</div>"
        "<div class='home-glow-tagline'>Démo “assistant vocal” : parler, comprendre, répondre.</div>"
        "<div class='home-glow-bullet'>"
        "• Transcription locale (audio → texte).<br>"
        "• Réponse ancrée sur la base IT-STORM.<br>"
        "• Restitution vocale + UX demo-friendly."
        "</div>"
        "</div></div>",
        unsafe_allow_html=True,
    )

    col3.markdown(
        "<div class='home-row'><div class='home-glow-card card-3'>"
        "<div class='home-glow-title'><span class='icon'>⚙️</span> Automation + Radars + MLOps</div>"
        "<div class='home-glow-tagline'>Orchestration n8n et pilotage de pipelines.</div>"
        "<div class='home-glow-bullet'>"
        "• Tech Radar & Market Radar (webhooks n8n).<br>"
        "• Daily Full : scénario complet automatisé.<br>"
        "• MLOps : training, monitoring, champions."
        "</div>"
        "</div></div>",
        unsafe_allow_html=True,
    )

    # ==========================================================
    # TIMELINE — MAJ : parcours final (avec tous les modules)
    # ==========================================================
    st.markdown(
        "<div class='home-steps'><div class='home-steps-title'>🔁 Parcours complet (projet final)</div>"
        "<div class='home-step-row'>"
        "<div class='home-step'><div class='home-step-badge'>1</div>"
        "<div><div class='home-step-label'>Sécuriser l’accès</div>"
        "<div class='home-step-sub'>Authentification multi-étapes dans 🔐 Auth.</div></div></div>"
        "<div class='home-step'><div class='home-step-badge'>2</div>"
        "<div><div class='home-step-label'>Ingestion documentaire</div>"
        "<div class='home-step-sub'>Upload → Chunking → Index dans 📂 Upload.</div></div></div>"
        "<div class='home-step'><div class='home-step-badge'>3</div>"
        "<div><div class='home-step-label'>Comprendre & produire</div>"
        "<div class='home-step-sub'>Q/R, résumé, DOCX dans 📝 Generate Docs.</div></div></div>"
        "<div class='home-step'><div class='home-step-badge'>4</div>"
        "<div><div class='home-step-label'>Observer & automatiser</div>"
        "<div class='home-step-sub'>Market / Tech / Automation Studio (n8n) + 🧪 MLOps.</div></div></div>"
        "</div></div>",
        unsafe_allow_html=True,
    )

    # ==========================================================
    # BOTTOM : pitch final + CTA final
    # ==========================================================
    colL, colR = st.columns([1.2, 1.0])

    colL.markdown(
        "<div class='home-bottom'><div class='home-bottom-card'>"
        "<div class='home-bottom-title'>Ce que StormCopilot apporte (version finale)</div>"
        "<ul class='home-bottom-list'>"
        "<li>Un point d’entrée unique pour la connaissance IT-STORM (docs + RAG).</li>"
        "<li>Génération de livrables directement exploitables (résumés + DOCX).</li>"
        "<li>Automatisation par workflows (n8n) + radars Tech & Marché.</li>"
        "<li>Pipeline MLOps : entraînement, monitoring, synthèse champions.</li>"
        "</ul>"
        "<div>Objectif : transformer l’information en action, sans perte de temps.</div>"
        "</div></div>",
        unsafe_allow_html=True,
    )

    colR.markdown(
        "<div class='home-bottom'><div class='home-bottom-card'>"
        "<div class='home-bottom-title'>Par où commencer ?</div>"
        "<ul class='home-bottom-list'>"
        "<li>1) Ajoute des documents dans 📂 Upload.</li>"
        "<li>2) Pose une question IT-STORM dans 📝 Generate Docs.</li>"
        "<li>3) Lance un radar dans ⚙️ Automation Studio.</li>"
        "<li>4) Vérifie le monitoring dans 🧪 MLOps.</li>"
        "</ul>"
        "<div>Astuce : IRIS (bulle) peut t’accompagner à tout moment.</div>"
        "</div></div>",
        unsafe_allow_html=True,
    )
