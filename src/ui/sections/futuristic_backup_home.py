# -*- coding: utf-8 -*-
# Path: src/ui/sections/home.py
# Tab 1 — Accueil futuriste StormCopilot (IA x Portage salarial IT-STORM)

from __future__ import annotations

import streamlit as st
from textwrap import dedent

def render_home_tab() -> None:
    """
    Rend l’onglet d’accueil futuriste de StormCopilot.
    À appeler depuis app.py à l’intérieur de `with tab_home:`.
    """

    # =========================
    # CSS GLOBAL DU HOME
    # =========================
    st.markdown(
        """
<style>
/* === ACCUEIL — STORMCOPILOT FUTURISTIC === */
.home-hero {
    position: relative;
    padding: 1.8rem 1.8rem 1.4rem;
    border-radius: 22px;
    background:
        radial-gradient(circle at 0% 0%, rgba(56,189,248,0.22), transparent 55%),
        radial-gradient(circle at 100% 0%, rgba(129,140,248,0.24), transparent 55%),
        linear-gradient(135deg, rgba(15,23,42,0.92), rgba(15,23,42,0.88));
    border: 1px solid rgba(148,163,184,0.55);
    box-shadow: 0 32px 80px rgba(15,23,42,0.65);
    overflow: hidden;
    backdrop-filter: blur(22px) saturate(1.25);
    animation: fadeInHero 0.9s ease-out;
}

/* Animation d’apparition futuriste */
@keyframes fadeInHero {
    from { opacity: 0; transform: translateY(8px); }
    to   { opacity: 1; transform: translateY(0); }
}

/* Orbes animées en arrière-plan */
.home-hero-orb {
    position: absolute;
    border-radius: 999px;
    filter: blur(18px);
    opacity: 0.9;
    mix-blend-mode: screen;
    /* important : ne pas bloquer les clics */
    pointer-events: none;
}
.home-hero-orb.orb-left {
    width: 140px;
    height: 140px;
    left: -40px;
    top: -30px;
    background: radial-gradient(circle, rgba(56,189,248,0.80), transparent 60%);
    animation: floatOrb1 11s ease-in-out infinite alternate;
}
.home-hero-orb.orb-right {
    width: 220px;
    height: 220px;
    right: -60px;
    top: -40px;
    background: radial-gradient(circle, rgba(129,140,248,0.90), transparent 60%);
    animation: floatOrb2 15s ease-in-out infinite alternate;
}
@keyframes floatOrb1 {
    0% { transform: translate3d(0,0,0) scale(1); }
    100% { transform: translate3d(15px,25px,0) scale(1.08); }
}
@keyframes floatOrb2 {
    0% { transform: translate3d(0,0,0) scale(1); }
    100% { transform: translate3d(-18px,18px,0) scale(1.04); }
}

/* Titre principal avec animation mot par mot */
.home-hero-main {
    position: relative;
    z-index: 1;
    display: flex;
    flex-direction: row;
    gap: 1.6rem;
    align-items: flex-start;
}
.home-hero-logo-badge {
    min-width: 60px;
    min-height: 60px;
    border-radius: 20px;
    background: radial-gradient(circle at 30% 0%, #38bdf8, #4f46e5);
    display: flex;
    align-items: center;
    justify-content: center;
    box-shadow: 0 14px 40px rgba(37,99,235,0.65);
}
.home-hero-logo-badge span {
    font-size: 30px;
}

/* Container du titre */
.home-hero-text-title {
    font-size: 1.85rem;
    font-weight: 800;
    letter-spacing: 0.02em;
    margin-bottom: 0.15rem;
    display: inline-flex;
    flex-wrap: wrap;
    gap: 0.35rem;
}
.home-hero-text-title span.word {
    background: linear-gradient(120deg, #e5e7eb, #a5b4fc, #38bdf8);
    -webkit-background-clip: text;
    color: transparent;
    opacity: 0;
    transform: translateY(8px);
    animation: wordRise 0.6s ease-out forwards;
}
.home-hero-text-title span.word:nth-child(1) { animation-delay: 0.00s; }
.home-hero-text-title span.word:nth-child(2) { animation-delay: 0.12s; }
.home-hero-text-title span.word:nth-child(3) { animation-delay: 0.24s; }
.home-hero-text-title span.word:nth-child(4) { animation-delay: 0.36s; }

@keyframes wordRise {
    from { opacity: 0; transform: translateY(8px); }
    to   { opacity: 1; transform: translateY(0); }
}

.home-hero-text-sub {
    font-size: 0.95rem;
    color: #cbd5f5;
    max-width: 620px;
}

/* Bandeau “IA x Portage salarial” */
.home-hero-pill-row {
    margin-top: 0.85rem;
    display: flex;
    flex-wrap: wrap;
    gap: 0.45rem;
}
.home-pill {
    display: inline-flex;
    align-items: center;
    gap: 0.35rem;
    padding: 0.22rem 0.7rem;
    border-radius: 999px;
    font-size: 0.75rem;
    background: rgba(15,23,42,0.85);
    border: 1px solid rgba(148,163,184,0.55);
    color: #e5e7eb;
    backdrop-filter: blur(8px);
}
.home-pill-dot {
    width: 7px;
    height: 7px;
    border-radius: 999px;
    background: radial-gradient(circle, #22c55e, #15803d);
    box-shadow: 0 0 8px rgba(34,197,94,0.85);
}

/* Petit radar à droite */
.home-hero-mini {
    position: relative;
    z-index: 1;
    margin-left: auto;
    display: flex;
    flex-direction: column;
    align-items: flex-end;
    gap: 0.55rem;
}
.home-mini-chip {
    font-size: 0.72rem;
    padding: 0.25rem 0.65rem;
    border-radius: 999px;
    border: 1px solid rgba(148,163,184,0.55);
    background: rgba(15,23,42,0.85);
    color: #e5e7eb;
}
.home-mini-radar {
    width: 125px;
    height: 125px;
    border-radius: 999px;
    border: 1px solid rgba(148,163,184,0.7);
    background:
        radial-gradient(circle at 50% 50%, rgba(59,130,246,0.55), transparent 55%),
        radial-gradient(circle at 0% 0%, rgba(56,189,248,0.30), transparent 60%),
        radial-gradient(circle at 100% 100%, rgba(129,140,248,0.40), transparent 60%);
    box-shadow: 0 22px 45px rgba(15,23,42,0.8);
    position: relative;
    overflow: hidden;
}
.home-mini-radar-sweep {
    position: absolute;
    width: 200%;
    height: 200%;
    top: -50%;
    left: -50%;
    background: conic-gradient(from 0deg, rgba(59,130,246,0.0),
                               rgba(56,189,248,0.85),
                               rgba(59,130,246,0.0) 60%);
    animation: radarSweep 7.5s linear infinite;
}
.home-mini-radar-center {
    position: absolute;
    width: 12px;
    height: 12px;
    border-radius: 999px;
    background: #22c55e;
    box-shadow: 0 0 12px rgba(34,197,94,0.95);
    top: 50%;
    left: 50%;
    transform: translate(-50%, -50%);
}
@keyframes radarSweep {
    0% { transform: rotate(0deg); }
    100% { transform: rotate(360deg); }
}

/* Cartes 3 colonnes */
.home-row {
    margin-top: 1.35rem;
}
.home-glow-card {
    position: relative;
    border-radius: 18px;
    padding: 0.95rem 0.95rem 0.9rem;
    border: 1px solid rgba(148,163,184,0.45);
    background: radial-gradient(circle at 0% 0%, rgba(56,189,248,0.18), transparent 65%),
                rgba(15,23,42,0.96);
    box-shadow: 0 18px 40px rgba(15,23,42,0.70);
    font-size: 0.82rem;
    color: #e5e7eb;
}
.home-glow-title {
    font-size: 0.86rem;
    font-weight: 700;
    margin-bottom: 0.18rem;
    display: flex;
    align-items: center;
    gap: 0.3rem;
}
.home-glow-title span.icon {
    font-size: 1rem;
}
.home-glow-tagline {
    font-size: 0.75rem;
    opacity: 0.88;
    margin-bottom: 0.25rem;
}
.home-glow-bullet {
    font-size: 0.78rem;
    opacity: 0.9;
}

/* Timeline “4 gestes” */
.home-steps {
    margin-top: 1.8rem;
}
.home-steps-title {
    font-size: 1.05rem;
    font-weight: 700;
    color: #0f172a;
    margin-bottom: 0.5rem;
}
[data-theme="dark"] .home-steps-title {
    color: #e5e7eb;
}
.home-step-row {
    display: flex;
    flex-wrap: wrap;
    gap: 0.7rem;
}
.home-step {
    flex: 1 1 180px;
    display: flex;
    align-items: flex-start;
    gap: 0.55rem;
    font-size: 0.78rem;
}
.home-step-badge {
    min-width: 24px;
    height: 24px;
    border-radius: 999px;
    background: radial-gradient(circle, #4f46e5, #1d4ed8);
    color: white;
    font-weight: 700;
    font-size: 0.78rem;
    display: flex;
    align-items: center;
    justify-content: center;
    box-shadow: 0 10px 22px rgba(79,70,229,0.7);
}
.home-step-main {
    display: flex;
    flex-direction: column;
}
.home-step-label {
    font-weight: 600;
    margin-bottom: 0.05rem;
}
.home-step-sub {
    opacity: 0.85;
}

/* Dernier bloc : pitch + call to action */
.home-bottom {
    margin-top: 1.5rem;
}
.home-bottom-card {
    border-radius: 18px;
    border: 1px dashed rgba(148,163,184,0.6);
    padding: 0.95rem 1.0rem;
    background: rgba(248,250,252,0.85);
    font-size: 0.80rem;
}
[data-theme="dark"] .home-bottom-card {
    background: rgba(15,23,42,0.95);
}
.home-bottom-title {
    font-weight: 700;
    font-size: 0.90rem;
    margin-bottom: 0.25rem;
}
.home-bottom-list {
    padding-left: 1.1rem;
    margin-bottom: 0.2rem;
}
.home-bottom-list li {
    margin-bottom: 0.12rem;
}

/* Effet spark subtil */
.spark {
    position: relative;
}
.spark::after {
    content: "";
    position: absolute;
    left: -5%;
    right: -5%;
    bottom: -2px;
    height: 1px;
    background: linear-gradient(90deg, transparent, rgba(96,165,250,0.7), transparent);
    opacity: 0.0;
    animation: sparkPulse 4.5s ease-in-out infinite;
}
@keyframes sparkPulse {
    0%, 35% { opacity: 0; }
    45%, 60% { opacity: 1; }
    100% { opacity: 0; }
}

/* Bouton audio dans le hero */
.hero-sound-btn {
    position: absolute;
    top: 14px;
    right: 16px;
    border-radius: 999px;
    border: 1px solid rgba(148,163,184,0.7);
    background: rgba(15,23,42,0.92);
    color: #e5e7eb;
    font-size: 0.78rem;
    padding: 0.25rem 0.75rem;
    display: inline-flex;
    align-items: center;
    gap: 0.35rem;
    cursor: pointer;
    backdrop-filter: blur(10px);
    box-shadow: 0 10px 26px rgba(15,23,42,0.7);
    transition: background 0.18s ease, transform 0.18s ease,
                box-shadow 0.18s ease, border-color 0.18s ease;
    z-index: 10;  /* pour rester cliquable */
}
.hero-sound-btn:hover {
    background: rgba(37,99,235,0.95);
    border-color: rgba(191,219,254,0.9);
    transform: translateY(-1px);
    box-shadow: 0 14px 34px rgba(37,99,235,0.75);
}
.hero-sound-btn span.icon {
    font-size: 0.9rem;
}
</style>
        """,
        unsafe_allow_html=True,
    )

    # =========================
    # HERO + SON + BOUTON
    # =========================
    st.markdown(
        """
<audio id="home-hero-sound">
  <source src="/static/sounds/chicken_song_geco_remix.mp3" type="audio/mp3">
</audio>

<div class="home-hero">
  <!-- Clic direct sur l'audio -->
  <button id="hero-sound-btn" class="hero-sound-btn"
          onclick="try { const a = document.getElementById('home-hero-sound'); if(a){ a.volume = 0.15; a.play(); } } catch(e) {}">
    <span class="icon">🔊</span>
    <span>Activer l’intro</span>
  </button>

  <div class="home-hero-orb orb-left"></div>
  <div class="home-hero-orb orb-right"></div>

  <div class="home-hero-main">
    <div class="home-hero-logo-badge">
      <span>⚡</span>
    </div>

    <div>
      <div class="home-hero-text-title">
        <span class="word">StormCopilot</span>
        <span class="word">• Copilote IA</span>
        <span class="word">pour consultants</span>
        <span class="word">IT-STORM</span>
      </div>
      <div class="home-hero-text-sub">
        Un cockpit unique pour connecter vos <b>documents internes</b>, la
        <b>veille Cloud / Data / IA</b> et les informations clés du
        <span class="spark">portage salarial</span> — afin de préparer
        une mission ou un rendez-vous client en quelques minutes.
      </div>

      <div class="home-hero-pill-row">
        <div class="home-pill">
          <div class="home-pill-dot"></div>
          <span>IA locale & RAG multi-sources</span>
        </div>
        <div class="home-pill">
          <div class="home-pill-dot"></div>
          <span>Portage salarial IT-STORM & missions freelance</span>
        </div>
        <div class="home-pill">
          <div class="home-pill-dot"></div>
          <span>Cloud · Data · DevOps · Sécurité</span>
        </div>
      </div>
    </div>

    <div class="home-hero-mini">
      <div class="home-mini-chip">
        Mode consultant : activé ✅
      </div>
      <div class="home-mini-radar">
        <div class="home-mini-radar-sweep"></div>
        <div class="home-mini-radar-center"></div>
      </div>
      <div class="home-mini-chip">
        Veille & documents synchronisés
      </div>
    </div>
  </div>
</div>
        """,
        unsafe_allow_html=True,
    )

    # =========================
    # 3 BLOCS (IA, PORTAGE, STUDIO)
    # =========================
    c1, c2, c3 = st.columns(3)

    with c1:
        st.markdown(
            """
<div class="home-row">
  <div class="home-glow-card">
    <div class="home-glow-title">
      <span class="icon">🤖</span><span>Mode IA · RAG intelligent</span>
    </div>
    <div class="home-glow-tagline">
      Pose tes questions comme à un collègue senior.
    </div>
    <div class="home-glow-bullet">
      • Recherche contextuelle dans les documents IT-STORM.<br>
      • Synthèses courtes et sources citées automatiquement.<br>
      • Génération de <b>slides, notes client, comptes-rendus</b>.
    </div>
  </div>
</div>
            """,
            unsafe_allow_html=True,
        )

    with c2:
        st.markdown(
            """
<div class="home-row">
  <div class="home-glow-card">
    <div class="home-glow-title">
      <span class="icon">🧾</span><span>Portage salarial & missions</span>
    </div>
    <div class="home-glow-tagline">
      Prépare une mission de consultant porté en quelques clics.
    </div>
    <div class="home-glow-bullet">
      • Rappels sur le <b>fonctionnement du portage</b> et les avantages.<br>
      • Aide à formuler des <b>messages clients</b> et propositions de valeur.<br>
      • Génération de fiches “mission briefing” prêtes à partager.
    </div>
  </div>
</div>
            """,
            unsafe_allow_html=True,
        )

    with c3:
        st.markdown(
            """
<div class="home-row">
  <div class="home-glow-card">
    <div class="home-glow-title">
      <span class="icon">🌐</span><span>Studio IT-STORM · Cloud / Data / DevOps</span>
    </div>
    <div class="home-glow-tagline">
      Une vue 360° sur l’écosystème technique.
    </div>
    <div class="home-glow-bullet">
      • Veille continue sur les <b>services Cloud, IA & DevOps</b>.<br>
      • Suivi des marchés pour les décideurs et product owners.<br>
      • Base de connaissances enrichie à chaque nouvelle mission.
    </div>
  </div>
</div>
            """,
            unsafe_allow_html=True,
        )

    # =========================
    # TIMELINE — 4 GESTES
    # =========================
    st.markdown(
        """
<div class="home-steps">
  <div class="home-steps-title">🔁 Votre parcours en 4 gestes</div>
  <div class="home-step-row">

    <div class="home-step">
      <div class="home-step-badge">1</div>
      <div class="home-step-main">
        <div class="home-step-label">Connecter vos contenus</div>
        <div class="home-step-sub">
          Onglet <b>📂 Upload & Index</b> : déposez contrats, présentations,
          offres de mission, modèles de livrables…
        </div>
      </div>
    </div>

    <div class="home-step">
      <div class="home-step-badge">2</div>
      <div class="home-step-main">
        <div class="home-step-label">Activer la mémoire IA</div>
        <div class="home-step-sub">
          Lancez l’extraction & le chunking pour alimenter la base RAG
          avec vos documents IT-STORM.
        </div>
      </div>
    </div>

    <div class="home-step">
      <div class="home-step-badge">3</div>
      <div class="home-step-main">
        <div class="home-step-label">Lire le marché & la tech</div>
        <div class="home-step-sub">
          Suivez <b>🌍 Market Watch</b> et <b>🔎 Veille Techno</b> :
          signaux marchés, tendances Cloud, IA, portage salarial…
        </div>
      </div>
    </div>

    <div class="home-step">
      <div class="home-step-badge">4</div>
      <div class="home-step-main">
        <div class="home-step-label">Produire le livrable final</div>
        <div class="home-step-sub">
          Dans <b>📝 Generate Docs</b>, transformez ces infos en slides,
          notes de cadrage, synthèses pour vos clients ou partenaires.
        </div>
      </div>
    </div>

  </div>
</div>
        """,
        unsafe_allow_html=True,
    )

    # =========================
    # BOTTOM : POURQUOI + CTA
    # =========================
    col_left, col_right = st.columns([1.2, 1.0])

    with col_left:
        st.markdown(
            """
<div class="home-bottom">
  <div class="home-bottom-card">
    <div class="home-bottom-title">Pourquoi ce copilote est différent&nbsp;?</div>
    <ul class="home-bottom-list">
      <li>Il est pensé pour le <b>quotidien des consultants IT-STORM</b>, pas comme une démo technique.</li>
      <li>Il combine <b>documents internes</b>, <b>veille marché</b> et <b>infos portage salarial</b> dans un même cockpit.</li>
      <li>Il prépare directement les <b>livrables utiles</b> : slides, notes client, briefs de mission.</li>
    </ul>
    <div>
      En résumé : moins de temps à chercher l’information, plus de temps à préparer la mission
      et à créer de la valeur pour le client.
    </div>
  </div>
</div>
            """,
            unsafe_allow_html=True,
        )

    with col_right:
        # petit texte simple ; tu pourras ajouter des boutons plus tard
        st.markdown(
            """
<div class="home-bottom">
  <div class="home-bottom-card">
    <div class="home-bottom-title">Et maintenant&nbsp;?</div>
    <ul class="home-bottom-list">
      <li>Commence par déposer quelques documents clés dans <b>📂 Upload & Index</b>.</li>
      <li>Teste une première question métier dans <b>💬 Chat Connaissance</b>.</li>
      <li>Observe la veille Cloud / IA dans <b>🔎 Veille Techno</b>.</li>
    </ul>
    <div>
      Tu peux revenir sur cet écran à tout moment pour retrouver le fil conducteur de StormCopilot.
    </div>
  </div>
</div>
            """,
            unsafe_allow_html=True,
        )
