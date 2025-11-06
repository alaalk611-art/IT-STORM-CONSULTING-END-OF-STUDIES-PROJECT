# -*- coding: utf-8 -*-
# ============================================================
# Path: src/ui/tabs/generate_docs_rag.py
# Role: Streamlit tab for grounded doc generation & QA.
# Focus: ambiguity handling → strict retrieval → grounded answers (0-hallucination)
#        Uses src.rag_brain.smart_rag_answer + optional ask_multi_ollama jury.
# ============================================================

from __future__ import annotations
import os, re, io, textwrap, uuid
from dataclasses import dataclass
from pathlib import Path
from typing import List, Tuple, Dict, Any

import streamlit as st
# --- RAG strict engine (imports robustes) ---
try:
    import src.rag_brain as _rb
    smart_rag_answer = getattr(_rb, 'smart_rag_answer', None)
    ask_multi_ollama = getattr(_rb, 'ask_multi_ollama', None)
    _IMPORT_ERR = None if smart_rag_answer else RuntimeError('smart_rag_answer introuvable dans src.rag_brain')
except Exception as e:
    smart_rag_answer = None
    ask_multi_ollama = None
    _IMPORT_ERR = e

# Optional: Ollama model listing (robuste)
try:
    from src.llm.ollama_client import list_models as _ollama_list, ping as _ollama_ping
except Exception:
    _ollama_list = None
    _ollama_ping = None
except Exception as e:
    smart_rag_answer = None
    ask_multi_ollama = None
    _IMPORT_ERR = e

# ---- Optional deps for exports / PDF read (handled gracefully) ----
_HAS_DOCX = False
_HAS_PPTX = False
_HAS_PDF  = False

try:
    from docx import Document
    _HAS_DOCX = True
except Exception:
    pass

try:
    from pptx import Presentation
    from pptx.util import Inches  # noqa
    _HAS_PPTX = True
except Exception:
    pass

try:
    from PyPDF2 import PdfReader
    _HAS_PDF = True
except Exception:
    pass

# ---- ENV & Defaults ----
ROOT = Path(__file__).resolve().parents[3]
OUTPUT_DIR = os.getenv("OUTPUT_DIR", str(ROOT / "out"))

SUPPORTED = {"Français": "fr", "English": "en"}

# ============================================================
# Utilities (UI helpers)
# ============================================================

def _clean(x: str) -> str:
    return re.sub(r"\s+", " ", (x or "").strip())

def _safe_filename(x: str) -> str:
    return re.sub(r"[^A-Za-z0-9_\- ]+", "", x).strip().replace(" ", "_") or f"export_{uuid.uuid4().hex[:8]}"



def _get_ollama_models(defaults=None):
    """Retourne la liste des modèles Ollama disponibles (robuste)."""
    defaults = defaults or ['mistral:7b-instruct','llama3.2:3b','qwen2.5:7b']
    try:
        if _ollama_ping and _ollama_ping():
            ms = _ollama_list() if _ollama_list else []
            # Normaliser en liste simple
            if isinstance(ms, dict) and 'models' in ms:
                names = [m.get('name') for m in ms.get('models', [])]
            elif isinstance(ms, (list, tuple)):
                names = [str(m) for m in ms]
            else:
                names = []
            names = [m for m in names if isinstance(m, str) and m.strip()]
            return names or defaults
    except Exception:
        pass
    # Fallbacks
    if ask_multi_ollama is not None:
        return defaults
    return []
def _badge_conf(conf: float) -> str:
    try:
        c = float(conf)
    except Exception:
        c = 0.0
    if c >= 0.80: return f"🟢 Confiance: **{c:.2f}**"
    if c >= 0.65: return f"🟡 Confiance: **{c:.2f}**"
    return f"🟠 Confiance: **{c:.2f}**"

def _q_to_paragraph(q: str) -> str:
    q = _clean(q)
    if not q:
        return q
    if not q.lower().startswith(("en un paragraphe", "in one paragraph")):
        return f"En un paragraphe : {q}"
    return q

# ============================================================
# Exports
# ============================================================

def export_docx(title: str, sections: List[Tuple[str, str]]) -> str:
    if not _HAS_DOCX:
        return "(python-docx manquant)"
    os.makedirs(OUTPUT_DIR, exist_ok=True)
    path = os.path.join(OUTPUT_DIR, _safe_filename(title) + ".docx")
    doc = Document()
    doc.add_heading(title, 0)
    for name, content in sections:
        doc.add_heading(name, level=1)
        for para in str(content).split("\n"):
            doc.add_paragraph(para)
    doc.save(path)
    return path

def export_pptx(title: str, sections: List[Tuple[str, str]]) -> str:
    if not _HAS_PPTX:
        return "(python-pptx manquant)"
    os.makedirs(OUTPUT_DIR, exist_ok=True)
    path = os.path.join(OUTPUT_DIR, _safe_filename(title) + ".pptx")
    prs = Presentation()
    slide = prs.slides.add_slide(prs.slide_layouts[0])
    slide.shapes.title.text = title
    slide.placeholders[1].text = "IT-STORM · RAG local (réponses ancrées)"
    layout = prs.slide_layouts[1]
    for name, content in sections:
        s = prs.slides.add_slide(layout)
        s.shapes.title.text = name
        tf = s.placeholders[1].text_frame
        tf.clear()
        text = _clean(str(content))
        # Max ~14 lignes pour lisibilité
        for line in textwrap.wrap(text, width=110)[:14]:
            p = tf.add_paragraph(); p.text = line; p.level = 0
    prs.save(path)
    return path

# ============================================================
# Core wrappers (use smart_rag_answer from rag_brain)
# ============================================================

@dataclass
class QAResult:
    answer: str
    sources: List[str]
    quotes: List[Dict[str, str]]
    confidence: float
    quality: Dict[str, float]
    dbg: Dict[str, Any]

def _ask_strict_grounded(question: str) -> QAResult:
    """
    Ask the strict RAG engine. 'smart_rag_answer' ignore lang/mode,
    et renvoie une réponse en 1 paragraphe si RAG_SINGLE_PARAGRAPH=1.
    """
    if smart_rag_answer is None:
        raise RuntimeError(f"Moteur RAG indisponible: {_IMPORT_ERR}")
    res = smart_rag_answer(question=_q_to_paragraph(str(question)))
    # Robust defaults to avoid KeyErrors / ZeroDivisionError visuals
    return QAResult(
        answer = res.get("answer", "Je ne sais pas."),
        sources = res.get("sources", []) or [],
        quotes = res.get("quotes", []) or [],
        confidence = float(res.get("confidence", 0.0) or 0.0),
        quality = res.get("quality", {}) or {},
        dbg = res.get("dbg", {}) or {},
    )

# ============================================================
# Streamlit UI
# ============================================================

def render_generate_docs_tab():
    st.header("🧠 Génération automatique de documents RAG (local, 0-hallucination)")
    st.caption("Moteur strict ancré sur vos documents (smart_rag_answer) · Jury Ollama en option")

    if _IMPORT_ERR is not None:
        st.error(f"Erreur d’import du moteur RAG: {_IMPORT_ERR}")
        st.stop()

    lang_lbl = st.selectbox("Langue / Language", list(SUPPORTED.keys()), index=0)
    lang = SUPPORTED[lang_lbl]

    mode = st.radio(
        "Mode",
        ["Question libre (RAG)", "Question + Jury (choix modèles)", "Complet (8 sections)", "Résumé de document (PDF/TXT)"],
        horizontal=True,
    )

    st.divider()

    # === Mode 1: Question libre (RAG strict, 1 paragraphe) ===
    if mode == "Question libre (RAG)":
        q = st.text_input(
            "Question",
            placeholder=("Ex: Quels bénéfices concrets du RAG pour un client énergie chez IT-STORM ?")
        )
        use_jury = st.toggle(
            "Activer jury Ollama (mistral · llama · qwen)",
            value=True,
            help="Compare 3 modèles locaux sur le même contexte RAG et recommande le meilleur."
        )

        if st.button("🔎 Répondre") and q:
            with st.spinner("Recherche et réponse ancrée…"):
                res = _ask_strict_grounded(q)

            st.subheader("🔍 Réponse ancrée (paragraphe unique)")
            st.write(res.answer)

            # KPIs (sans risque de division par zéro)
            c1, c2, c3, c4 = st.columns(4)
            c1.metric("Confiance", f"{res.confidence:.2f}")
            c2.metric("Grounding", f"{float(res.quality.get('grounding',0.0) or 0.0):.2f}")
            c3.metric("Couverture", f"{float(res.quality.get('coverage',0.0) or 0.0):.2f}")
            c4.metric("Style", f"{float(res.quality.get('style',0.0) or 0.0):.2f}")

            st.markdown(_badge_conf(res.confidence))

            with st.expander("📑 Extraits (citations)"):
                if res.quotes:
                    for i, qt in enumerate(res.quotes, 1):
                        st.markdown(f"**{i}.** *« {qt.get('quote','').strip()} »* — `{qt.get('source','')}`")
                else:
                    st.info("Aucun extrait disponible.")
            with st.expander("📚 Sources (fichiers)"):
                if res.sources:
                    st.write(", ".join(sorted(set(res.sources))))
                else:
                    st.info("Aucune source unique détectée.")
            with st.expander("🛠️ Debug"):
                st.json(res.dbg)
                st.json(res.quality)

            # Jury Ollama (optionnel)
            if use_jury and ask_multi_ollama is not None:
                st.markdown("---")
                st.subheader("Jury Ollama (comparaison locale)")
                with st.spinner("Interrogation des modèles Ollama…"):
                    jury = ask_multi_ollama(
                        q,
                        models=["mistral:7b-instruct", "llama3.2:3b", "qwen2.5:7b"],
                        topk_context=6,
                        timeout=60.0
                    )
                results = jury.get("results", [])
                if results:
                    try:
                        import pandas as pd
                        rows = []
                        for r in results:
                            m = r.get("metrics", {}) or {}
                            rows.append({
                                "Modèle": r.get("model",""),
                                "Score": r.get("score", 0.0),
                                "Confiance": float(m.get("confidence", 0.0) or 0.0),
                                "Grounding": float(m.get("grounding", 0.0) or 0.0),
                                "Couverture": float(m.get("coverage", 0.0) or 0.0),
                                "Style": float(m.get("style", 0.0) or 0.0),
                                "Temps (s)": float(r.get("time", 0.0) or 0.0),
                            })
                        st.dataframe(pd.DataFrame(rows).sort_values("Score", ascending=False), use_container_width=True)
                    except Exception:
                        # Fallback simple si pandas indispo
                        for r in results:
                            st.markdown(f"**{r.get('model','')}** · score {r.get('score',0.0)} · {r.get('time',0.0)}s")
                            st.write(r.get("answer",""))
                            st.markdown("---")

                    sug = jury.get("suggestion")
                    if sug:
                        st.success(f"✅ Suggestion: privilégier **{sug['model']}** (score {sug['score']}, {sug['time']}s)")
                else:
                    st.info("Aucun résultat jury (Ollama non disponible ?)")
            elif use_jury and ask_multi_ollama is None:
                st.warning("Le module jury Ollama n'est pas disponible dans cette installation.")

    # === Mode 2: Génération complète (8 sections) — strictement ancrée ===
    
    # === Mode: Question + Jury (choix modèles) ===
    elif mode == "Question + Jury (choix modèles)":
        q = st.text_input("Question (contexte IT‑STORM)", placeholder="Ex: C'est quoi IT-STORM ?")
        c1, c2 = st.columns([1,1])
        with c1:
            if st.button("🔄 Rafraîchir modèles Ollama"):
                st.session_state.setdefault('ollama_models', _get_ollama_models())
        models_default = st.session_state.get('ollama_models', _get_ollama_models())
        selected = st.multiselect("Modèles à comparer", options=models_default, default=models_default)
        colx, coly, colz = st.columns([1,1,1])
        with colx:
            timeout = st.number_input("Timeout (s)", min_value=10, max_value=180, value=60, step=5)
        with coly:
            topk = st.slider("Top extraits (k)", 3, 12, 6, 1)
        with colz:
            do_export = st.checkbox("Exporter comparatif (DOCX/PPTX)", value=False)

        run = st.button("⚖️ Comparer & recommander", type="primary")
        if run:
            if not q:
                st.warning("Renseigne la question."); st.stop()
            if ask_multi_ollama is None:
                st.error("Le jury Ollama n'est pas disponible sur cette installation."); st.stop()
            if not selected:
                st.warning("Sélectionne au moins un modèle."); st.stop()
            with st.spinner("Interrogation des modèles…"):
                jury = ask_multi_ollama(q, models=selected, topk_context=topk, timeout=float(timeout))

            # Affichage résultats
            results = jury.get("results", [])
            if not results:
                st.info("Aucune réponse (Ollama non joignable ?)"); st.stop()
            try:
                import pandas as pd
                rows = []
                for r in results:
                    m = r.get("metrics", {}) or {}
                    rows.append({
                        "Modèle": r.get("model",""),
                        "Score": r.get("score", 0.0),
                        "Confiance": float(m.get("confidence", 0.0) or 0.0),
                        "Grounding": float(m.get("grounding", 0.0) or 0.0),
                        "Couverture": float(m.get("coverage", 0.0) or 0.0),
                        "Style": float(m.get("style", 0.0) or 0.0),
                        "Temps (s)": float(r.get("time", 0.0) or 0.0),
                    })
                df = pd.DataFrame(rows).sort_values("Score", ascending=False)
                st.dataframe(df, use_container_width=True)
            except Exception:
                for r in results:
                    st.markdown(f"**{r.get('model','')}** · score {r.get('score',0.0)} · {r.get('time',0.0)}s")
                st.markdown("---")

            sug = jury.get("suggestion")
            if sug:
                st.success(f"✅ Modèle recommandé: **{sug['model']}** (score {sug['score']}, {sug['time']}s)")

            with st.expander("Voir les réponses brutes par modèle"):
                for r in results:
                    st.markdown(f"**{r['model']}** · score {r.get('score',0.0)} · {r.get('time',0.0)}s")
                    st.write(r.get("answer",""))
                    st.markdown("---")

            # Exports comparatif (optionnel)
            if do_export:
                sections = [("Comparatif Jury", "")]
                # Table textuelle simple pour DOCX/PPTX
                lines = ["Modèle | Score | Confiance | Grounding | Couverture | Style | Temps (s)"]
                for r in results:
                    m = r.get("metrics", {}) or {}
                    line = f"{r.get('model','')} | {r.get('score',0.0)} | {m.get('confidence',0.0)} | {m.get('grounding',0.0)} | {m.get('coverage',0.0)} | {m.get('style',0.0)} | {r.get('time',0.0)}"
                    lines.append(line)
                table_txt = "\n".join(lines)
                best = jury.get("suggestion")
                summary = f"Modèle recommandé: {best['model']} (score {best['score']}, {best['time']}s)" if best else "Aucune recommandation."
                sections.append(("Synthèse", summary))
                sections.append(("Détail", table_txt))
                title = f"Comparatif_Jury_{_safe_filename(q)[:40]}"
                docx_path = export_docx(title, sections)
                pptx_path = export_pptx(title, sections)
                st.success("✅ Exports créés :")
                st.write(f"• DOCX: {docx_path}")
                st.write(f"• PPTX: {pptx_path}")

    elif mode == "Complet (8 sections)":
        topic = st.text_input("Sujet / Topic", placeholder="Ex: Proposition RAG pour client énergie")
        c1, c2, c3 = st.columns([1,1,1])
        with c1:
            run = st.button("🚀 Générer le livrable")
        with c2:
            want_docx = st.checkbox("Export DOCX", value=True)
            want_pptx = st.checkbox("Export PPTX", value=True)
        with c3:
            title_override = st.text_input("Titre export (facultatif)")

        if run and topic:
            sections_names_fr = [
                "Executive Summary","Contexte & Objectifs","Pain Points","Architecture & Solution",
                "Données & Qualité","Plan de Mise en œuvre","Sécurité & Conformité","Prochaines Étapes"
            ]
            sections_names_en = [
                "Executive Summary","Context & Objectives","Pain Points","Solution Architecture",
                "Data & Quality","Implementation Plan","Security & Compliance","Next Steps"
            ]
            names = sections_names_en if (lang=="en") else sections_names_fr

            outputs: List[Tuple[str,str]] = []
            for sec in names:
                q = f"{topic} — {sec}"
                with st.spinner(f"{sec} …"):
                    res = _ask_strict_grounded(q)
                outputs.append((sec, res.answer))
                # UI per section
                st.subheader(sec)
                st.write(res.answer)
                # Tiny KPIs row
                cols = st.columns(4)
                cols[0].caption(f"Confiance: {res.confidence:.2f}")
                cols[1].caption(f"Grounding: {float(res.quality.get('grounding',0.0) or 0.0):.2f}")
                cols[2].caption(f"Couverture: {float(res.quality.get('coverage',0.0) or 0.0):.2f}")
                cols[3].caption(f"Style: {float(res.quality.get('style',0.0) or 0.0):.2f}")
                st.markdown("---")

            exports = {}
            title = title_override or topic
            if want_docx:
                p = export_docx(title, outputs)
                exports["DOCX"] = p
            if want_pptx:
                p = export_pptx(title, outputs)
                exports["PPTX"] = p
            if exports:
                st.success("✅ Exports créés :")
                for kx, vx in exports.items():
                    st.write(f"• {kx}: {vx}")

    # === Mode 3: Résumé de document (PDF/TXT) — extractif / concis ===
    else:
        path = st.text_input("Chemin du document (PDF/TXT)", placeholder="./docs/mon_fichier.pdf")
        if st.button("📄 Résumer") and path:
            p = Path(path)
            if not p.exists():
                st.warning("Fichier introuvable.")
                st.stop()
            try:
                if _HAS_PDF and p.suffix.lower() == ".pdf":
                    reader = PdfReader(str(p))
                    txt = "\n".join((reader.pages[i].extract_text() or "") for i in range(len(reader.pages)))
                else:
                    txt = p.read_text(encoding="utf-8", errors="ignore")
            except Exception as e:
                st.error(f"Erreur lecture: {e}")
                st.stop()

            txt = _clean(txt)[:20000]
            if not txt:
                st.warning("Document vide.")
                st.stop()

            # Résumé extractif ultra-simple (0 hallucination)
            sents = [s.strip() for s in re.split(r"(?<=[\.!?])\s+", txt) if s.strip()]
            # Prendre 5–8 phrases max
            summary = " ".join(sents[:8])
            st.subheader("Résumé")
            st.write(summary or ("Je ne sais pas." if lang == "fr" else "I don't know."))

# Alias pour intégration simple dans app.py
def render():
    render_generate_docs_tab()
