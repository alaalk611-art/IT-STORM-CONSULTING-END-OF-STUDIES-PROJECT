# -*- coding: utf-8 -*-
# ============================================================
# Path: src/ui/tabs/generate_docs_rag.py
# Role: Streamlit tab – RAG ancré + Jury multi-LLM via Ollama
# Aligné avec src/rag_brain.py :
#   - smart_rag_answer(question=..., ...) -> {answer, sources, quotes, confidence, quality, dbg}
#   - ask_multi_ollama(question=..., models=[...], topk_context=6, timeout=60.0)
#       -> {"question","context_snippets","results":[{"model","answer","time","metrics","score"}], "suggestion":{...}
# Priorité: qualité de la réponse (génération ancrée) > UI.
# Aucune modification de app.py. Fourni: render_generate_docs_tab()
# ============================================================

from __future__ import annotations
import io
import re
import time
import math
from collections import Counter
from typing import List, Dict, Any, Optional, Tuple

import streamlit as st
import pandas as pd

# --- RAG strict engine (imports robustes) ---
try:
    import src.rag_brain as _rb
    smart_rag_answer = getattr(_rb, "smart_rag_answer", None)
    ask_multi_ollama = getattr(_rb, "ask_multi_ollama", None)
except Exception:
    smart_rag_answer = None
    ask_multi_ollama = None

# --- Résumé (module dédié) ---
try:
    from src.rag_sum import summarize_file, summary_quality_report
except Exception:
    summarize_file = None
    summary_quality_report = None

# =================== CSS GLOBAL ===================
# - DataFrame: afficher TOUT le texte (wrap, pas d'ellipsis)
# - Helper "?" cliquable (tooltip propre)
st.markdown("""
<style>
/* ===== DataFrame : montrer TOUTE la réponse sans coupe ===== */
[data-testid="stDataFrame"] div[role="gridcell"],
[data-testid="stDataFrame"] div[role="gridcell"] p{
  white-space: pre-wrap !important;
  overflow: visible !important;
  text-overflow: initial !important;
  line-height: 1.35 !important;
  word-break: break-word !important;
  line-break: anywhere !important;
}

/* ===== Helper “?” cliquable (tooltip) ===== */
.helper-row{
  display:flex; align-items:center; justify-content:space-between; gap:.5rem;
  margin:.15rem 0 .35rem 0;
}
.helper-label{ font-weight:600; color:#0f172a; }
.helper{
  position:relative; display:inline-flex; align-items:center; justify-content:center;
  width:22px; height:22px; border-radius:50%;
  background:#e5eefc; color:#284b9f; font-weight:700; cursor:pointer;
  border:1px solid #c7d2fe; user-select:none;
}
.helper:hover{ background:#dbe8ff; }
.helper .tooltip{
  position:absolute; top:30px; right:-8px;
  min-width:220px; max-width:360px; padding:.55rem .7rem; border-radius:.55rem;
  border:1px solid #e5e7eb; background:#fff; color:#111827;
  box-shadow:0 8px 18px rgba(0,0,0,.08); font-size:.86rem; line-height:1.25;
  display:none; z-index:20;
}
.helper:focus .tooltip, .helper:hover .tooltip{ display:block; }
</style>
""", unsafe_allow_html=True)

# ============================================================
# Métadonnées modèles (affichage léger)
# ============================================================

_MODEL_META: Dict[str, Dict[str, str]] = {
    "mistral:7b-instruct": {"emoji": "🦅", "color": "#2b7cff"},
    "llama3.2:3b":         {"emoji": "🦙", "color": "#7b5cff"},
    "qwen2.5:7b":          {"emoji": "🐉", "color": "#16a34a"},
    "tinyllama:latest":    {"emoji": "🌱", "color": "#64748b"},
    "smart_rag_answer":    {"emoji": "🔎", "color": "#334155"},
}

def _default_models() -> List[str]:
    """Liste stable des modèles affichés/ordonnés."""
    return ["mistral:7b-instruct", "llama3.2:3b", "qwen2.5:7b", "tinyllama:latest"]

def _label(name: str, rank: Optional[int] = None) -> str:
    meta = _MODEL_META.get(name, {"emoji": "🤖", "color": "#334155"})
    emo = meta["emoji"]
    badge = f" · Rang {rank}" if rank else ""
    return f"{emo} {name}{badge}"

def _decorate_model_label(name: str, rank: Optional[int] = None) -> str:
    """Pastille colorée + emoji + rang (HTML sûr pour st.markdown)."""
    meta = _MODEL_META.get(name, {"emoji": "🤖", "color": "#334155"})
    emoji = meta["emoji"]; color = meta["color"]
    medal = ""
    if rank is not None:
        if rank == 1: medal = "🥇"
        elif rank == 2: medal = "🥈"
        elif rank == 3: medal = "🥉"
        else: medal = f"🏁{rank}"
    return f"""
<span style="display:inline-flex;align-items:center;gap:.55rem;padding:.35rem .65rem;
      border:1px solid #e5e7eb;background:#f8fafc;border-radius:999px;font-weight:600;">
  <span style="width:12px;height:12px;border-radius:50%;display:inline-block;background:{color};"></span>
  <span>{emoji} {name}</span>
  {"<span>"+medal+"</span>" if medal else ""}
</span>
""".strip()

# ============================================================
# Helpers de base (priorité: contenu)
# ============================================================

def _safe_num(x, default: float = 0.0) -> float:
    try:
        return float(x)
    except Exception:
        return default

def _score_from_result(r: Dict[str, Any]) -> float:
    # Score → r["score"] (jury) sinon r["confidence"] (RAG)
    if "score" in r:
        return _safe_num(r["score"])
    if "confidence" in r:
        return _safe_num(r["confidence"])
    return 0.0

def _legend_metrics() -> None:
    """
    Affiche les légendes des métriques principales (avec helpers natifs Streamlit).
    """
    lang = st.session_state.get("lang", "fr")

    c1, c2, c3, c4 = st.columns(4)
    if lang == "en":
        with c1:
            st.markdown("**Confidence**", help="Global reliability of the generated answer (0–1).")
        with c2:
            st.markdown("**Grounding**", help="How well the answer is anchored in the retrieved context (0–1).")
        with c3:
            st.markdown("**Coverage**", help="Diversity and completeness of the answer versus the retrieved context (0–1).")
        with c4:
            st.markdown("**Style**", help="Readability and formatting quality of the generated text (0–1).")
    else:
        with c1:
            st.markdown("**Confiance**", help="Fiabilité globale de la réponse générée (0–1).")
        with c2:
            st.markdown("**Grounding**", help="Degré d’ancrage de la réponse sur les extraits sources (0–1).")
        with c3:
            st.markdown("**Couverture**", help="Diversité et exhaustivité du contenu par rapport au contexte (0–1).")
        with c4:
            st.markdown("**Style**", help="Lisibilité et clarté de la rédaction (0–1).")

# ============================================================
# Slider Top-K dans la sidebar (avec helper “?”)
# ============================================================

def _sidebar_topk_slider(default:int=6) -> int:
    """Slider Top-K dans la sidebar avec étiquette + helper “?” (FR/EN auto)."""
    lang = st.session_state.get("lang", "en")
    is_en = (lang == "en")

    label_txt = "Top-K results" if is_en else "Top-K résultats"
    help_txt  = (
        "Number of most similar document chunks retrieved from the vector database to build the context for each question."
        if is_en else
        "Nombre de segments de documents similaires utilisés pour construire le contexte des réponses."
    )
    with st.sidebar:
        st.markdown(
            f"""
<div class="helper-row">
  <div class="helper-label">{label_txt}</div>
  <div class="helper" tabindex="0">?
    <div class="tooltip">{help_txt}</div>
  </div>
</div>
""",
            unsafe_allow_html=True
        )
        value = st.slider(" ", min_value=2, max_value=12, value=default, step=1, key="topk_sidebar_slider")
    return int(value)

# ============================================================
# Appels moteur
# ============================================================

def _call_smart_rag(question: str, lang: str = "fr", mode: str = "definition") -> Dict[str, Any]:
    if not (smart_rag_answer and callable(smart_rag_answer)):
        return {}
    try:
        return smart_rag_answer(question=question, lang=lang, mode=mode) or {}
    except Exception as e:
        st.error(f"smart_rag_answer a échoué: {e}")
        return {}

def _call_jury(question: str, models: List[str], topk_context: int = 6, timeout: float = 60.0) -> Dict[str, Any]:
    """
    Retour du jury (dict complet) aligné avec rag_brain.ask_multi_ollama
    {
      "question":..., "context_snippets":[...],
      "results":[{"model","answer","time","metrics":{"coverage","grounding","style","confidence"},"score"}],
      "suggestion":{"model","score","time"} | None
    }
    """
    if not (ask_multi_ollama and callable(ask_multi_ollama)):
        return {}
    try:
        return ask_multi_ollama(question=question, models=models,
                                topk_context=int(topk_context), timeout=float(timeout)) or {}
    except TypeError:
        # Signature de secours (selon version)
        try:
            return ask_multi_ollama(question=question, models=models) or {}
        except Exception as e:
            st.warning(f"Jury indisponible: {e}")
            return {}
    except Exception as e:
        st.warning(f"Jury indisponible: {e}")
        return {}

def _ask_one_model(question: str, model: str, topk_context: int = 6, timeout: float = 60.0) -> Dict[str, Any]:
    """
    Interroge un seul modèle via ask_multi_ollama (models=[model]).
    Retourne le premier résultat normalisé, sinon fallback sur smart_rag_answer.
    """
    jury = _call_jury(question, models=[model], topk_context=topk_context, timeout=timeout)
    res = (jury.get("results") or [])
    if res:
        r = res[0]
        out = {
            "model": r.get("model", model),
            "answer": r.get("answer", ""),
            "score": _safe_num(r.get("score", 0.0)),
            "confidence": _safe_num((r.get("metrics") or {}).get("confidence", r.get("score", 0.0))),
            "grounding": _safe_num((r.get("metrics") or {}).get("grounding", 0.0)),
            "coverage": _safe_num((r.get("metrics") or {}).get("coverage", 0.0)),
            "style": _safe_num((r.get("metrics") or {}).get("style", 0.0)),
            "time": _safe_num(r.get("time", 0.0)),
        }
        return out

    # Fallback (pas par modèle, mais garantit une réponse ancrée)
    base = _call_smart_rag(question) or {}
    qual = base.get("quality") or {}
    return {
        "model": model,
        "answer": base.get("answer", ""),
        "score": _safe_num(base.get("confidence", 0.0)),
        "confidence": _safe_num(base.get("confidence", 0.0)),
        "grounding": _safe_num(qual.get("grounding", 0.0)),
        "coverage": _safe_num(qual.get("coverage", 0.0)),
        "style": _safe_num(qual.get("style", 0.0)),
        "time": 0.0,
    }

# ============================================================
# Lecture upload (TXT/PDF) — conservé pour compat (non utilisé en résumé)
# ============================================================

def _read_uploaded_file(upload) -> Tuple[str, str]:
    """Retourne (text, ext) pour .txt/.pdf ; best-effort sans dépendances dures."""
    if not upload:
        return "", ""
    name = (upload.name or "").lower()
    if name.endswith(".txt"):
        try:
            raw = upload.read()
            return raw.decode("utf-8", errors="ignore"), ".txt"
        except Exception:
            return "", ".txt"
    if name.endswith(".pdf"):
        try:
            import PyPDF2  # optionnel
            reader = PyPDF2.PdfReader(io.BytesIO(upload.read()))
            pages = []
            for p in reader.pages:
                try:
                    pages.append(p.extract_text() or "")
                except Exception:
                    pages.append("")
            return "\n".join(pages), ".pdf"
        except Exception:
            return "", ".pdf"
    return "", ""

# ============================================================
# 🔎 Helpers qualité de résumé (locaux) — conservés pour compat
# ============================================================

def _tok(s: str) -> list[str]:
    return re.findall(r"\w+", (s or "").lower(), flags=re.UNICODE)

def _ngrams(tokens: list[str], n: int) -> list[tuple]:
    return [tuple(tokens[i:i+n]) for i in range(len(tokens)-n+1)] if n > 0 else []

def _rouge_prf(ref: str, hyp: str, n: int = 1) -> dict:
    r_toks, h_toks = _tok(ref), _tok(hyp)
    r_ngr, h_ngr = Counter(_ngrams(r_toks, n)), Counter(_ngrams(h_toks, n))
    overlap = sum((r_ngr & h_ngr).values())
    R = overlap / (sum(r_ngr.values()) or 1)
    P = overlap / (sum(h_ngr.values()) or 1)
    F = (2*P*R)/(P+R) if (P+R) > 0 else 0.0
    return {"P": P, "R": R, "F1": F}

def _keyword_overlap(ref: str, hyp: str, k: int = 20) -> float:
    rt = [t for t in _tok(ref) if len(t) > 2]
    ht = set([t for t in _tok(hyp) if len(t) > 2])
    if not rt or not ht:
        return 0.0
    top = [w for w, _ in Counter(rt).most_common(k)]
    hit = sum(1 for w in top if w in ht)
    return hit / max(1, len(top))

def _cosine_sim(ref: str, hyp: str) -> float:
    r, h = Counter(_tok(ref)), Counter(_tok(h))
    if not r or not h:
        return 0.0
    inter = set(r) & set(h)
    num = sum(r[w]*h[w] for w in inter)
    nr = math.sqrt(sum(v*v for v in r.values()))
    nh = math.sqrt(sum(v*v for v in h.values()))
    return num / (nr*nh) if nr*nh > 0 else 0.0

def _unsupported_sentences(ref: str, hyp: str, thr: float = 0.15) -> list[str]:
    """Phrases du résumé faiblement chevauchées (3-grammes) → possiblement non ancrées."""
    ref_3 = set(_ngrams(_tok(ref), 3))
    out = []
    for sent in re.split(r"(?<=[\.\!\?])\s+", (hyp or "").strip()):
        if not sent:
            continue
        s3 = _ngrams(_tok(sent), 3)
        if not s3:
            continue
        overlap = sum(1 for g in s3 if g in ref_3) / len(s3)
        if overlap < thr:
            out.append(sent.strip())
    return out

def _summary_quality_report(source_text: str, summary_text: str) -> dict:
    Ls, Lh = len(_tok(source_text)), len(_tok(summary_text))
    comp = (1 - (Lh / max(1, Ls))) if Ls else 0.0
    rouge1 = _rouge_prf(source_text, summary_text, n=1)
    rouge2 = _rouge_prf(source_text, summary_text, n=2)
    sim   = _cosine_sim(source_text, summary_text)
    kw    = _keyword_overlap(source_text, summary_text, k=20)
    unsup = _unsupported_sentences(source_text, summary_text, thr=0.15)
    return {
        "tokens_source": Ls,
        "tokens_summary": Lh,
        "compression": comp,           # ~0.6–0.9 attendu
        "cosine": sim,                 # 0–1
        "rouge1_f1": rouge1["F1"],
        "rouge2_f1": rouge2["F1"],
        "keyword_overlap": kw,         # 0–1 (≥0.4 rassurant)
        "unsupported": unsup,          # phrases potentiellement non ancrées
    }

# ============================================================
# UI (centrée sur la réponse) + Podium/Course
# ============================================================

def _pick_models() -> List[str]:
    """
    Sélection interactive des modèles via cartes cliquables (multi-sélection).
    - Aucun checkbox/radio
    - Clic = (dé)sélection
    - Anti flip-flop au rerun + ordre stable selon _default_models()
    """
    st.caption("Clique sur un modèle pour l’activer ou le désactiver.")

    defaults = _default_models()
    if "selected_models" not in st.session_state:
        st.session_state["selected_models"] = defaults[:3]  # 3 premiers actifs par défaut
    selected = list(st.session_state["selected_models"])

    # CSS
    st.markdown("""
<style>
.model-grid {
  display:flex; flex-wrap:wrap; gap:10px; margin-bottom:12px;
}
.model-card {
  flex: 1 1 calc(25% - 10px);
  border: 2px solid transparent;
  border-radius: 14px;
  padding: 10px 14px;
  background: #ffffff;
  box-shadow: 0 4px 12px rgba(0,0,0,0.05);
  cursor: pointer;
  display: flex; align-items: center; justify-content:center; gap:8px;
  font-weight: 700; color: #111827; text-align:center;
  transition: all .2s ease;
}
.model-card:hover { transform: scale(1.03); box-shadow: 0 6px 16px rgba(0,0,0,0.08); }
.model-card.active { background: linear-gradient(135deg,#dbeafe,#bfdbfe); border-color:#2563eb; color:#1e3a8a; }
.model-dot { display:inline-block; width:10px; height:10px; border-radius:50%; }
</style>
""", unsafe_allow_html=True)

    st.markdown('<div class="model-grid">', unsafe_allow_html=True)

    for i, m in enumerate(defaults):
        meta = _MODEL_META.get(m, {"emoji": "🤖", "color": "#334155"})
        active = m in selected
        card_key = f"model_card_{i}"
        color = meta["color"]
        bg_class = "active" if active else ""

        # Carte + JS (déclencheur)
        st.markdown(
            f"""
<div class="model-card {bg_class}" id="{card_key}">
  <span class="model-dot" style="background:{color};"></span>
  {meta['emoji']} {m}
</div>
<script>
const el_{i} = window.parent.document.getElementById("{card_key}");
if (el_{i}) {{
  el_{i}.onclick = function() {{
    const api = window.parent.streamlitApi;
    if (api) {{
      api.setComponentValue("{card_key}", !{str(active).lower()});
    }}
  }}
}}
</script>
""",
            unsafe_allow_html=True,
        )

        # Gestion du clic (anti flip-flop + ordre stable)
        clicked = st.session_state.get(card_key, None)
        if clicked is not None:
            if active:
                if m in selected:
                    selected.remove(m)
            else:
                if m not in selected:
                    selected.append(m)

            # ordre stable selon defaults + pas de doublons
            selected = [x for x in defaults if x in set(selected)]

            # persiste + reset clé pour éviter re-toggle au rerun
            st.session_state["selected_models"] = selected
            st.session_state[card_key] = None
            st.rerun()

    st.markdown('</div>', unsafe_allow_html=True)
    return selected

def _display_grounded_block(block: Dict[str, Any]) -> None:
    st.markdown("### 🔍 Réponse ancrée")
    ans = block.get("answer") or "Je ne sais pas."
    st.write(ans)

    conf = _safe_num(block.get("confidence", 0.0))
    qual = block.get("quality") or {}
    grd  = _safe_num(qual.get("grounding", 0.0))
    cov  = _safe_num(qual.get("coverage", 0.0))
    sty  = _safe_num(qual.get("style", 0.0))

    _legend_metrics()
    c1, c2, c3, c4 = st.columns(4)
    with c1: st.metric("Confiance", f"{conf:0.2f}")
    with c2: st.metric("Grounding", f"{grd:0.2f}")
    with c3: st.metric("Couverture", f"{cov:0.2f}")
    with c4: st.metric("Style", f"{sty:0.2f}")

    quotes = block.get("quotes") or []
    if quotes:
        with st.expander("Extraits cités"):
            for q in quotes:
                st.write(f"- « {q.get('quote','').strip()} » ({q.get('source','')})")

def _render_podium(results: List[Dict[str, Any]]) -> None:
    if not results:
        return
    st.subheader("🏆 Podium (Top 3)")

    top3 = sorted(results, key=_score_from_result, reverse=True)[:3]
    data = []
    for i, r in enumerate(top3, start=1):
        data.append({"rank": i, "model": r.get("model", "—"), "score": f"{_score_from_result(r):0.3f}"})
    while len(data) < 3:
        data.append({"rank": len(data)+1, "model": "—", "score": "—"})

    html = f"""
<style>
.podium-wrap {{
  width:100%; 
  margin:16px 0 18px 0;
}}
.podium {{
  display:flex; align-items:flex-end; justify-content:center; gap:36px;
  width:100%; height:260px; padding-bottom:10px;
}}
.podium .col {{
  display:flex; flex-direction:column; align-items:center; gap:14px;
}}
.podium .block {{
  width:180px; 
  border-radius:14px 14px 0 0;
  background: linear-gradient(180deg,#ffe27a 0%,#f5b400 45%,#b67b00 100%);
  box-shadow:0 6px 16px rgba(0,0,0,.15), inset 0 2px 0 rgba(255,255,255,.4);
  border:1px solid rgba(0,0,0,.08);
}}
.podium .rank1 .block {{ height:160px; background: linear-gradient(180deg,#fff176 0%,#fdd835 45%,#f9a825 100%); }}
.podium .rank2 .block {{ height:130px; background: linear-gradient(180deg,#d1d5db 0%,#9ca3af 45%,#6b7280 100%); }}
.podium .rank3 .block {{ height:110px; background: linear-gradient(180deg,#fbc8a2 0%,#f59e0b 45%,#b45309 100%); }}
.podium .model {{
  font-weight:800; 
  font-size:1.05rem; 
  color:#111827; 
  text-align:center;
  letter-spacing:.3px;
}}
.podium .score {{
  font-size:1rem; 
  color:#1e3a8a; 
  background:#eef2ff;
  border-radius:999px;
  padding:6px 16px;
  font-weight:700;
  box-shadow:inset 0 1px 2px rgba(0,0,0,.08);
}}
.podium .medal {{
  font-size:2rem; 
  margin-bottom:-6px;
}}
@media (max-width: 900px) {{
  .podium .block {{ width:120px; }}
  .podium .score {{ font-size:0.9rem; padding:4px 10px; }}
  .podium .model {{ font-size:0.95rem; }}
  .podium .medal {{ font-size:1.6rem; }}
}}
</style>

<div class="podium-wrap">
  <div class="podium">
    <div class="col rank2">
      <div class="medal">🥈</div>
      <div class="block"></div>
      <div class="model">{data[1]['model']}</div>
      <div class="score">Score : <b>{data[1]['score']}</b></div>
    </div>
    <div class="col rank1">
      <div class="medal">🥇</div>
      <div class="block"></div>
      <div class="model">{data[0]['model']}</div>
      <div class="score">Score : <b>{data[0]['score']}</b></div>
    </div>
    <div class="col rank3">
      <div class="medal">🥉</div>
      <div class="block"></div>
      <div class="model">{data[2]['model']}</div>
      <div class="score">Score : <b>{data[2]['score']}</b></div>
    </div>
  </div>
</div>
"""
    st.markdown(html, unsafe_allow_html=True)

def _render_race(results: List[Dict[str, Any]], steps: int = 12, sleep: float = 0.06) -> None:
    if not results or len(results) < 3:
        return
    st.subheader("🏁 Course (visualisation rapide)")
    rs = sorted(results, key=_score_from_result, reverse=True)[:5]
    max_score = max(_score_from_result(r) for r in rs) or 1.0
    cols = st.columns(len(rs))
    bars = []
    for i, (c, r) in enumerate(zip(cols, rs), start=1):
        with c:
            st.markdown(_decorate_model_label(r.get("model", "—"), rank=i if i <= 3 else None), unsafe_allow_html=True)
            bars.append(st.progress(0, text="Départ…"))
    for t in range(1, steps + 1):
        for bar, r in zip(bars, rs):
            pct = min(1.0, (_score_from_result(r) / max_score) * (t / steps))
            bar.progress(int(pct * 100), text=f"{int(pct*100)}%")
        time.sleep(sleep)

def _table_results(results: List[Dict[str, Any]], title: str = "📊 Comparatif des réponses") -> None:
    if not results:
        return

    from html import escape as _esc

    # ----- Données triées (Rang = 1..n) -----
    ordered = sorted(results, key=_score_from_result, reverse=True)
    rows_all = []
    for i, r in enumerate(ordered, start=1):
        rows_all.append({
            "Rang": i,
            "Modèle": r.get("model", "—"),
            "Score": round(_score_from_result(r), 3),
            "Confiance": round(_safe_num(r.get("confidence", r.get("score", 0.0))), 3),
            "Grounding": round(_safe_num(r.get("grounding", 0.0)), 3),
            "Couverture": round(_safe_num(r.get("coverage", 0.0)), 3),
            "Style": round(_safe_num(r.get("style", 0.0)), 3),
            "Réponse": str(r.get("answer", "")).strip(),
        })

    # =======================
    # 1) Tableau MÉTRIQUES
    # =======================
    st.subheader(title)

    st.markdown("""
<style>
/* === WRAPPER === */
.tbl-wrap { width:100%; overflow-x:auto; }

/* === TABLES : bordures continues + lisibilité === */
.tbl, .tbl2 {
  width:100%; max-width:1500px; margin:0 auto 18px auto;
  border-collapse: collapse;             /* << important : CONTINU */
  table-layout: fixed;
  background:#fff;
  border:1px solid #d1d5db;              /* bordure externe visible */
  border-radius:10px; overflow:hidden;
  box-shadow:0 3px 12px rgba(0,0,0,.06);
}

.tbl th, .tbl td, .tbl2 th, .tbl2 td {
  border:1px solid #d1d5db;              /* bordures internes continues */
  padding:10px 12px;
  font-size:.98rem; line-height:1.45;
  text-align:center; vertical-align:middle;
}

.tbl thead th, .tbl2 thead th {
  position: sticky; top: 0; z-index: 1;
  background:#f1f5f9; color:#0f172a; font-weight:700;
}

.tbl tbody tr:nth-child(even),
.tbl2 tbody tr:nth-child(even){ background:#f9fafb; }

.tbl tbody tr:hover,
.tbl2 tbody tr:hover{ background:#e0f2fe; transition: background .15s ease; }

/* === Colonnes chiffres compactes (pas de wrap) === */
.tbl td:nth-child(1), .tbl td:nth-child(2),
.tbl td:nth-child(3), .tbl td:nth-child(4),
.tbl td:nth-child(5), .tbl td:nth-child(6),
.tbl td:nth-child(7) { white-space:nowrap; }

/* === Largeurs cohérentes (métriques) === */
.tbl th:nth-child(1), .tbl td:nth-child(1) { min-width:80px; }   /* Rang */
.tbl th:nth-child(2), .tbl td:nth-child(2) { min-width:220px; }  /* Modèle */
.tbl th:nth-child(3), .tbl td:nth-child(3) { min-width:110px; }  /* Score */
.tbl th:nth-child(4), .tbl td:nth-child(4) { min-width:130px; }  /* Confiance */
.tbl th:nth-child(5), .tbl td:nth-child(5) { min-width:130px; }  /* Grounding */
.tbl th:nth-child(6), .tbl td:nth-child(6) { min-width:130px; }  /* Couverture */
.tbl th:nth-child(7), .tbl td:nth-child(7) { min-width:110px; }  /* Style */

/* === Tableau 2 (réponses longues) === */
.tbl2 th:nth-child(1), .tbl2 td:nth-child(1) { min-width:80px; text-align:center; }
.tbl2 th:nth-child(2), .tbl2 td:nth-child(2) { min-width:220px; text-align:center; }
.tbl2 th:nth-child(3), .tbl2 td:nth-child(3) {
  min-width:760px; width:65vw; text-align:left;
  white-space: normal; word-break: break-word; overflow-wrap: anywhere;
  line-height: 1.55;
}
</style>
""", unsafe_allow_html=True)

    # --- Metrics table (sans "Réponse") ---
    headers_metrics = ["Rang", "Modèle", "Score", "Confiance", "Grounding", "Couverture", "Style"]
    colgroup_metrics = """
<colgroup>
  <col style="width:90px">
  <col style="width:240px">
  <col style="width:120px">
  <col style="width:140px">
  <col style="width:140px">
  <col style="width:140px">
  <col style="width:120px">
</colgroup>
"""
    html1 = ['<div class="tbl-wrap"><table class="tbl">', colgroup_metrics, "<thead><tr>"]
    for h in headers_metrics:
        html1.append(f"<th>{_esc(h)}</th>")
    html1.append("</tr></thead><tbody>")

    for r in rows_all:
        html1.append("<tr>")
        for h in headers_metrics:
            html1.append(f"<td>{_esc(str(r[h]))}</td>")
        html1.append("</tr>")
    html1.append("</tbody></table></div>")
    st.markdown("".join(html1), unsafe_allow_html=True)

    # Espacement entre les deux tableaux
    st.markdown("<div style='height:14px'></div>", unsafe_allow_html=True)

    # =======================
    # 2) Tableau RÉPONSES
    # =======================
    st.subheader("📝 Réponses détaillées")

    headers_resp = ["Rang", "Modèle", "Réponse"]
    colgroup_resp = """
<colgroup>
  <col style="width:90px">
  <col style="width:240px">
  <col style="width:auto">
</colgroup>
"""
    html2 = ['<div class="tbl-wrap"><table class="tbl2">', colgroup_resp, "<thead><tr>"]
    for h in headers_resp:
        html2.append(f"<th>{_esc(h)}</th>")
    html2.append("</tr></thead><tbody>")

    for r in rows_all:
        html2.append("<tr>")
        html2.append(f"<td>{_esc(str(r['Rang']))}</td>")
        html2.append(f"<td>{_esc(str(r['Modèle']))}</td>")
        html2.append(f"<td>{_esc(str(r['Réponse']))}</td>")
        html2.append("</tr>")

    html2.append("</tbody></table></div>")
    st.markdown("".join(html2), unsafe_allow_html=True)

# ============================================================
# Render
# ============================================================

def render():
    st.header("🧠 Generate Docs (RAG zéro-hallucination)")
    mode = st.radio("Mode", ["Répondre à une question", "Résumer un document (PDF/TXT)"], horizontal=True)

    # (fix essentiel) : suppression du paramètre non standard border=True
    with st.form("gen_form"):
        models = _pick_models()
        # Slider Top-K dans la sidebar (avec helper “?”)
        topk_context = _sidebar_topk_slider(default=6)

        if mode == "Répondre à une question":
            q = st.text_area("Question", placeholder="Ex: C'est quoi IT-STORM ?", height=100)
            c1, c2 = st.columns([1, 1])
            with c1:
                do_gen = st.form_submit_button("Générer (séquentiel)")
            with c2:
                do_cmp = st.form_submit_button("Comparer (jury)")
            do_sum = False
            up = None
        else:
            q = None
            up = st.file_uploader("Importer un document (.pdf ou .txt)", type=["pdf", "txt"])
            do_sum = st.form_submit_button("Résumer")
            do_gen = do_cmp = False

    # === Branche Question / RAG ===
    if mode == "Répondre à une question":
        if not (do_gen or do_cmp):
            st.stop()
        if not q or not q.strip():
            st.error("Merci de saisir une question.")
            st.stop()

        # 1) Réponse ancrée (smart_rag_answer) — prioritaire
        base = _call_smart_rag(q) or {}
        if base:
            _display_grounded_block(base)

        # 2) Séquentiel par modèle (option)
        collected: List[Dict[str, Any]] = []
        if do_gen:
            st.subheader("🧪 Réponses par modèle (séquentiel)")
            for m in models:
                with st.spinner(f"{m} génère une réponse..."):
                    r = _ask_one_model(q, model=m, topk_context=topk_context, timeout=60.0)
                st.markdown(_decorate_model_label(r.get("model","—")), unsafe_allow_html=True)
                st.write(r.get("answer", ""))
                collected.append(r)

            if collected:
                best = sorted(collected, key=_score_from_result, reverse=True)[0]
                st.subheader("✅ Réponse finale conseillée")
                st.markdown(_decorate_model_label(best.get("model","—"), rank=1), unsafe_allow_html=True)
                st.write(best.get("answer", ""))

        # 3) Jury multi-modèles (option)
        results: List[Dict[str, Any]] = []
        if do_cmp:
            if len(models) < 3:
                st.info("Astuce: pour une comparaison significative, sélectionne ≥ 3 modèles.")
            jury = _call_jury(q, models=models, topk_context=topk_context, timeout=60.0) or {}
            results = jury.get("results") or []
            # normalisation légère (assure présence des champs)
            for r in results:
                met = r.get("metrics") or {}
                r["confidence"] = _safe_num(met.get("confidence", r.get("score", 0.0)))
                r["grounding"]  = _safe_num(met.get("grounding", 0.0))
                r["coverage"]   = _safe_num(met.get("coverage", 0.0))
                r["style"]      = _safe_num(met.get("style", 0.0))

        # 4) Podium + Course + Comparatif
        final_list = results or collected
        if final_list:
            _render_podium(final_list)
            _render_race(final_list)
            _table_results(final_list, title="📊 Comparatif des réponses")

        st.stop()

    # === Branche Résumé — désormais branchée sur src.rag_sum ===
    else:
        if not do_sum:
            st.stop()

        if summarize_file is None or summary_quality_report is None:
            st.error("Module de résumé indisponible (src.rag_sum). Vérifie l'import.")
            st.stop()

        if up is None:
            st.error("Importe un fichier .pdf ou .txt à résumer.")
            st.stop()

        # Lecture binaire + appel du moteur de résumé dédié
        file_bytes = up.read()
        try:
            raw = summarize_file(file_bytes, up.name, models=models, timeout=90.0) or {}
        except Exception as e:
            st.error(f"Résumé indisponible: {e}")
            st.stop()

        best = raw.get("best") or {}
        results = raw.get("results") or []
        report = raw.get("report") or {}
        used = raw.get("used", "none")

        if not best:
            st.error("Aucun résumé exploitable n'a été produit.")
            st.stop()

        # Meilleure proposition
        st.subheader("📝 Résumé — meilleure proposition")
        st.caption(f"Mode utilisé : **{used}** · Source : {raw.get('source_name','?')} ({raw.get('source_ext','')})")
        st.markdown(_decorate_model_label(best.get("model","—"), rank=1), unsafe_allow_html=True)
        st.write(best.get("answer", ""))

        # Indicateurs de qualité (depuis rag_sum.summary_quality_report)
        if report:
            c1, c2, c3, c4 = st.columns(4)
            with c1: st.metric("Compression", f"{report.get('compression',0.0)*100:0.0f}%")
            with c2: st.metric("Similarité (cosine)", f"{report.get('cosine',0.0):.2f}")
            with c3: st.metric("ROUGE-1 F1", f"{report.get('rouge1_f1',0.0):.2f}")
            with c4: st.metric("Mots-clés couverts", f"{report.get('keyword_overlap',0.0)*100:0.0f}%")

            with st.expander("🔎 Détails & vérifications"):
                st.write(f"- Jetons source : **{report.get('tokens_source',0)}**")
                st.write(f"- Jetons résumé : **{report.get('tokens_summary',0)}**")
                st.write(f"- ROUGE-2 F1 : **{report.get('rouge2_f1',0.0):.2f}**")
                if report.get("unsupported"):
                    st.warning("⚠️ Phrases possiblement non ancrées :")
                    for s in report["unsupported"]:
                        st.write(f"- {s}")
                else:
                    st.success("Aucune phrase douteuse détectée par l’heuristique.")

        # Tous les résumés par modèle
        if results:
            st.subheader("📑 Résumés par modèle")
            for i, r in enumerate(sorted(results, key=_score_from_result, reverse=True), start=1):
                with st.expander(f"{i}. {_label(r.get('model','—'))} ({_score_from_result(r):0.3f})", expanded=(i == 1)):
                    st.write(r.get("answer", ""))

# Compat app.py
def render_generate_docs_tab():
    render()
