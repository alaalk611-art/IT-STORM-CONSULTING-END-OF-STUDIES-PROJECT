# -*- coding: utf-8 -*-
# Path: src/ui/sections/home.py

from __future__ import annotations
import streamlit as st


def render_home_tab() -> None:

    # ==========================================================
    # CSS GLOBAL
    # ==========================================================
    st.markdown("""
<style>

.home-hero{position:relative;padding:1.8rem;border-radius:22px;background:
radial-gradient(circle at 0% 0%,rgba(56,189,248,.22),transparent 55%),
radial-gradient(circle at 100% 0%,rgba(129,140,248,.24),transparent 55%),
linear-gradient(135deg,rgba(15,23,42,.96),rgba(15,23,42,.90));
border:1px solid rgba(148,163,184,.55);box-shadow:0 32px 80px rgba(15,23,42,.80);
overflow:hidden;backdrop-filter:blur(22px) saturate(1.25);
transform-origin:center center;
animation:fadeInHero .8s ease-out,heroBreath 14s ease-in-out infinite;
transition:transform .6s ease,box-shadow .6s ease;}
.home-hero:hover{transform:perspective(1100px) rotateX(3deg) rotateY(-3deg) translateY(-4px);
box-shadow:0 40px 95px rgba(15,23,42,.95);}

@keyframes fadeInHero{from{opacity:0;transform:translateY(10px);}to{opacity:1;transform:translateY(0);} }
@keyframes heroBreath{
0%{transform:perspective(1100px) rotateX(0deg) rotateY(0deg) translateY(0);}
50%{transform:perspective(1100px) rotateX(2deg) rotateY(-2deg) translateY(-4px);}
100%{transform:perspective(1100px) rotateX(0deg) rotateY(0deg) translateY(0);}
}

.home-hero-orb{position:absolute;border-radius:999px;filter:blur(18px);opacity:.9;mix-blend-mode:screen;pointer-events:none;}
.home-hero-orb.orb-left{width:140px;height:140px;left:-40px;top:-30px;background:radial-gradient(circle,rgba(56,189,248,.80),transparent 60%);
animation:floatOrb1 11s ease-in-out infinite alternate;}
.home-hero-orb.orb-right{width:220px;height:220px;right:-60px;top:-40px;background:radial-gradient(circle,rgba(129,140,248,.90),transparent 60%);
animation:floatOrb2 15s ease-in-out infinite alternate;}
@keyframes floatOrb1{0%{transform:translate3d(0,0,0) scale(1);}100%{transform:translate3d(15px,22px,0) scale(1.08);}}
@keyframes floatOrb2{0%{transform:translate3d(0,0,0) scale(1);}100%{transform:translate3d(-18px,18px,0) scale(1.04);} }

.home-hero-main{z-index:1;display:flex;flex-direction:row;gap:1.6rem;align-items:flex-start;}
.home-hero-logo-badge{min-width:60px;min-height:60px;border-radius:20px;
background:radial-gradient(circle at 30% 0%,#38bdf8,#4f46e5);
display:flex;align-items:center;justify-content:center;
box-shadow:0 14px 40px rgba(37,99,235,.80);}
.home-hero-logo-badge span{font-size:30px;}

.home-hero-text-title{font-size:1.85rem;font-weight:800;letter-spacing:.02em;margin-bottom:.15rem;
display:inline-flex;flex-wrap:wrap;gap:.35rem;}
.home-hero-text-title span.word{background:linear-gradient(120deg,#e5e7eb,#a5b4fc,#38bdf8);
-webkit-background-clip:text;color:transparent;opacity:0;
transform:translateY(8px);animation:wordRise .6s ease-out forwards;}
.home-hero-text-title span.word:nth-child(1){animation-delay:0s;}
.home-hero-text-title span.word:nth-child(2){animation-delay:.12s;}
.home-hero-text-title span.word:nth-child(3){animation-delay:.24s;}
.home-hero-text-title span.word:nth-child(4){animation-delay:.36s;}
@keyframes wordRise{from{opacity:0;transform:translateY(8px);}to{opacity:1;transform:translateY(0);} }

.home-hero-text-sub{font-size:.95rem;color:#cbd5f5;max-width:620px;}

.home-hero-pill-row{margin-top:.85rem;display:flex;flex-wrap:wrap;gap:.45rem;}
.home-pill{display:inline-flex;align-items:center;gap:.35rem;padding:.22rem .7rem;border-radius:999px;
font-size:.75rem;background:rgba(15,23,42,.85);
border:1px solid rgba(148,163,184,.55);color:#e5e7eb;backdrop-filter:blur(8px);}
.home-pill-dot{width:7px;height:7px;border-radius:999px;background:radial-gradient(circle,#22c55e,#15803d);
box-shadow:0 0 8px rgba(34,197,94,.85);}

.home-hero-mini{margin-left:auto;display:flex;flex-direction:column;align-items:flex-end;gap:.55rem;}
.home-mini-chip{font-size:.72rem;padding:.25rem .65rem;border-radius:999px;
border:1px solid rgba(148,163,184,.55);background:rgba(15,23,42,.92);color:#e5e7eb;}

.home-mini-radar{width:125px;height:125px;border-radius:999px;border:1px solid rgba(148,163,184,.7);
background:radial-gradient(circle at 50% 50%,rgba(59,130,246,.55),transparent 55%),
radial-gradient(circle at 0% 0%,rgba(56,189,248,.30),transparent 60%),
radial-gradient(circle at 100% 100%,rgba(129,140,248,.40),transparent 60%);
box-shadow:0 22px 45px rgba(15,23,42,.9);position:relative;overflow:hidden;}
.home-mini-radar-sweep{position:absolute;width:200%;height:200%;top:-50%;left:-50%;
background:conic-gradient(from 0deg,rgba(59,130,246,0),rgba(56,189,248,.85),rgba(59,130,246,0) 60%);
animation:radarSweep 7.5s linear infinite;}
.home-mini-radar-center{position:absolute;width:12px;height:12px;border-radius:999px;background:#22c55e;
box-shadow:0 0 12px rgba(34,197,94,.95);top:50%;left:50%;transform:translate(-50%,-50%);}
@keyframes radarSweep{0%{transform:rotate(0deg);}100%{transform:rotate(360deg);} }

.home-row{margin-top:1.35rem;}
.home-glow-card{border-radius:18px;padding:.95rem;border:1px solid rgba(148,163,184,.45);
background:radial-gradient(circle at 0% 0%,rgba(56,189,248,.18),transparent 65%),rgba(15,23,42,.96);
box-shadow:0 18px 40px rgba(15,23,42,.85);font-size:.82rem;color:#e5e7eb;}

.home-steps{margin-top:1.8rem;}
.home-steps-title{font-size:1.05rem;font-weight:700;margin-bottom:.5rem;}
.home-step-row{display:flex;flex-wrap:wrap;gap:.7rem;}
.home-step{flex:1 1 180px;display:flex;gap:.55rem;font-size:.78rem;}
.home-step-badge{min-width:24px;height:24px;border-radius:999px;background:radial-gradient(circle,#4f46e5,#1d4ed8);
color:#fff;font-weight:700;font-size:.78rem;display:flex;align-items:center;justify-content:center;
box-shadow:0 10px 22px rgba(79,70,229,.7);}
.home-step-label{font-weight:600;margin-bottom:.05rem;}
.home-step-sub{opacity:.85;}

.home-bottom{margin-top:1.5rem;}
.home-bottom-card{border-radius:18px;border:1px dashed rgba(148,163,184,.6);padding:.95rem;
background:rgba(248,250,252,.92);font-size:.80rem;}
.home-bottom-title{font-weight:700;font-size:.90rem;margin-bottom:.25rem;}
.home-bottom-list{padding-left:1.1rem;margin-bottom:.2rem;}
.home-bottom-list li{margin-bottom:.12rem;}

</style>
""", unsafe_allow_html=True)

    # ==========================================================
    # HERO (3D) — SANS BOUTON AUDIO
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
        "<span class='word'>• Copilote IA</span>"
        "<span class='word'>pour consultants</span>"
        "<span class='word'>IT-STORM</span>"
        "</div>"
        "<div class='home-hero-text-sub'>Un cockpit unique pour connecter vos <b>documents internes</b>, "
        "la <b>veille Cloud / Data / IA</b> et les informations clés du "
        "<span class='spark'>portage salarial</span>.</div>"
        "<div class='home-hero-pill-row'>"
        "<div class='home-pill'><div class='home-pill-dot'></div>IA locale &amp; RAG multi-sources</div>"
        "<div class='home-pill'><div class='home-pill-dot'></div>Portage salarial IT-STORM</div>"
        "<div class='home-pill'><div class='home-pill-dot'></div>Cloud · Data · DevOps · Sécurité</div>"
        "</div>"
        "</div>"
        "<div class='home-hero-mini'>"
        "<div class='home-mini-chip'>Mode consultant : activé</div>"
        "<div class='home-mini-radar'><div class='home-mini-radar-sweep'></div><div class='home-mini-radar-center'></div></div>"
        "<div class='home-mini-chip'>Veille &amp; documents synchronisés</div>"
        "</div>"
        "</div>"
        "</div>"
    )

    st.markdown(hero_html, unsafe_allow_html=True)

    # ==========================================================
    # 3 CARTES
    # ==========================================================
    col1, col2, col3 = st.columns(3)

    col1.markdown(
        "<div class='home-row'><div class='home-glow-card'>"
        "<div class='home-glow-title'><span class='icon'>🤖</span> Mode IA · RAG intelligent</div>"
        "<div class='home-glow-tagline'>Pose tes questions comme à un collègue senior.</div>"
        "<div class='home-glow-bullet'>• Recherche contextuelle dans les documents IT-STORM.<br>"
        "• Synthèses courtes et sources citées automatiquement.<br>"
        "• Génération de slides, notes client, comptes-rendus.</div>"
        "</div></div>",
        unsafe_allow_html=True
    )

    col2.markdown(
        "<div class='home-row'><div class='home-glow-card'>"
        "<div class='home-glow-title'><span class='icon'>🧾</span> Portage salarial &amp; missions</div>"
        "<div class='home-glow-tagline'>Prépare une mission en quelques clics.</div>"
        "<div class='home-glow-bullet'>• Fonctionnement du portage & avantages.<br>"
        "• Messages clients & propositions de valeur.<br>"
        "• Briefing mission prêt à partager.</div>"
        "</div></div>",
        unsafe_allow_html=True
    )

    col3.markdown(
        "<div class='home-row'><div class='home-glow-card'>"
        "<div class='home-glow-title'><span class='icon'>🌐</span> Studio IT-STORM · Cloud / Data / DevOps</div>"
        "<div class='home-glow-tagline'>Vue 360° sur l’écosystème technique.</div>"
        "<div class='home-glow-bullet'>• Veille continue sur les services Cloud, IA &amp; DevOps.<br>"
        "• Suivi des marchés pour les décideurs et product owners.<br>"
        "• Base de connaissances enrichie à chaque mission.</div>"
        "</div></div>",
        unsafe_allow_html=True
    )

    # ==========================================================
    # TIMELINE EN 4 GESTES
    # ==========================================================
    st.markdown(
        "<div class='home-steps'><div class='home-steps-title'>🔁 Votre parcours en 4 gestes</div>"
        "<div class='home-step-row'>"
        "<div class='home-step'><div class='home-step-badge'>1</div>"
        "<div><div class='home-step-label'>Connecter vos contenus</div>"
        "<div class='home-step-sub'>Déposez vos documents dans 📂 Upload &amp; Index.</div></div></div>"
        "<div class='home-step'><div class='home-step-badge'>2</div>"
        "<div><div class='home-step-label'>Activer la mémoire IA</div>"
        "<div class='home-step-sub'>Extraction &amp; chunking → base RAG enrichie.</div></div></div>"
        "<div class='home-step'><div class='home-step-badge'>3</div>"
        "<div><div class='home-step-label'>Lire le marché &amp; la tech</div>"
        "<div class='home-step-sub'>Suivi dans 🌍 Market Watch et 🔎 Veille Techno.</div></div></div>"
        "<div class='home-step'><div class='home-step-badge'>4</div>"
        "<div><div class='home-step-label'>Produire le livrable</div>"
        "<div class='home-step-sub'>Slides & synthèses dans 📝 Generate Docs.</div></div></div>"
        "</div></div>",
        unsafe_allow_html=True
    )

    # ==========================================================
    # BOTTOM : PITCH + CTA
    # ==========================================================
    colL, colR = st.columns([1.2, 1.0])

    colL.markdown(
        "<div class='home-bottom'><div class='home-bottom-card'>"
        "<div class='home-bottom-title'>Pourquoi ce copilote est différent ?</div>"
        "<ul class='home-bottom-list'>"
        "<li>Conçu pour le quotidien des consultants IT-STORM.</li>"
        "<li>Combine documents internes, veille marché et IA.</li>"
        "<li>Prépare directement des livrables utiles.</li>"
        "</ul>"
        "<div>Moins de temps à chercher l’information, plus de temps pour la mission.</div>"
        "</div></div>",
        unsafe_allow_html=True
    )

    colR.markdown(
        "<div class='home-bottom'><div class='home-bottom-card'>"
        "<div class='home-bottom-title'>Et maintenant ?</div>"
        "<ul class='home-bottom-list'>"
        "<li>Ajoute des documents dans 📂 Upload &amp; Index.</li>"
        "<li>Teste une question métier dans 💬 Chat Connaissance.</li>"
        "<li>Observe la veille dans 🔎 Veille Techno.</li>"
        "</ul>"
        "<div>Tu peux revenir ici à tout moment.</div>"
        "</div></div>",
        unsafe_allow_html=True
    )
