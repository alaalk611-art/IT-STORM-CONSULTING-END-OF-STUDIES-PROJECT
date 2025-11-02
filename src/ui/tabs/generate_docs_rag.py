# -*- coding: utf-8 -*-
# ============================================================
# Path: src/ui/tabs/generate_docs_rag.py
# Role: Streamlit tab for grounded doc generation & QA.
# Focus: ambiguity handling → auto‑reformulation → retrieval →
#        creative but NON‑hallucinatory generation with hard fallbacks.
#        (Local only: Chroma + SentenceTransformers + optional HF LLM)
# ============================================================
from __future__ import annotations
import os, re, io, json, uuid, textwrap
from dataclasses import dataclass
from pathlib import Path
from typing import List, Tuple, Dict, Any

import streamlit as st

# ---- Optional deps (handled gracefully) ----
_HAS_CHROMA = False
_HAS_ST = False
_HAS_HF = False
_HAS_DOCX = False
_HAS_PPTX = False
_HAS_PDF = False

try:  # chroma
    import chromadb
    from chromadb.config import Settings as _ChromaSettings
    _HAS_CHROMA = True
except Exception:
    pass

try:  # sentence-transformers (+ numpy)
    from sentence_transformers import SentenceTransformer
    import numpy as np
    _HAS_ST = True
except Exception:
    pass

try:  # transformers (seq2seq)
    from transformers import AutoTokenizer, AutoModelForSeq2SeqLM, pipeline
    _HAS_HF = True
except Exception:
    pass

try:  # exports
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

try:  # reading PDFs (summary mode)
    from PyPDF2 import PdfReader
    _HAS_PDF = True
except Exception:
    pass

# ---- ENV & Defaults ----
ROOT = Path(__file__).resolve().parents[3]
VECTOR_DB = os.getenv("VECTOR_DB_DIR", str(ROOT / "vectors"))
COLLECTION = os.getenv("COLLECTION_NAME", "itstorm_docs")  # must match app.py
EMB_MODEL = os.getenv("EMBEDDING_MODEL", "sentence-transformers/all-MiniLM-L6-v2")
LLM_MODEL = os.getenv("LLM_MODEL", "google/flan-t5-base")
OUTPUT_DIR = os.getenv("OUTPUT_DIR", str(ROOT / "out"))
DATA_DIR = Path(os.getenv("DATA_DIR", str(ROOT / "data")))
RAW_DIR = DATA_DIR / "raw"

SUPPORTED = {"Auto": "auto", "Français": "fr", "English": "en"}

# Domain guard (soft): we try to help, but won’t invent out of scope
ALLOWED_TOKENS = {
    "it storm","it-storm","devops","cloud","data","pipeline","pipelines",
    "rag","pfe","consulting","kubernetes","aws","gcp","azure","ml","ia","ai",
}

# ============================================================
# Utilities
# ============================================================

def _clean(x: str) -> str:
    return re.sub(r"\s+", " ", (x or "").strip())


def _tokenize(s: str) -> List[str]:
    return [t for t in re.split(r"[^\w]+", (s or "").lower()) if t]


def _is_ambiguous(q: str, min_chars: int = 18, min_tokens: int = 3) -> bool:
    qn = _clean(q)
    return len(qn) < min_chars or len(_tokenize(qn)) < min_tokens


def _allowed(q: str) -> bool:
    ql = q.lower()
    return any(k in ql for k in ALLOWED_TOKENS)


# ============================================================
# Embeddings + Retrieval (cached)
# ============================================================
@dataclass
class Hit:
    text: str
    source: str
    score: float


@st.cache_resource(show_spinner=False)
def _get_embedder(model_name: str = EMB_MODEL):
    if not _HAS_ST:
        raise RuntimeError("sentence-transformers manquant — pip install sentence-transformers")
    return SentenceTransformer(model_name)


class Embedder:
    def __init__(self, model_name: str = EMB_MODEL):
        self.model = _get_embedder(model_name)

    def encode(self, texts: List[str], normalize: bool = True):
        vecs = self.model.encode(
            texts,
            batch_size=64,
            show_progress_bar=False,
            convert_to_numpy=True,
            normalize_embeddings=normalize,
        )
        return vecs


@st.cache_resource(show_spinner=False)
def _get_chroma_client(persist_dir: str = VECTOR_DB):
    if not _HAS_CHROMA:
        raise RuntimeError("ChromaDB manquant — pip install chromadb")
    os.makedirs(persist_dir, exist_ok=True)
    return chromadb.PersistentClient(path=persist_dir, settings=_ChromaSettings())


class VectorDB:
    def __init__(self, persist_dir: str = VECTOR_DB, collection: str = COLLECTION):
        self.client = _get_chroma_client(persist_dir)
        try:
            self.col = self.client.get_collection(collection)
        except Exception:
            self.col = self.client.create_collection(collection, metadata={"hnsw:space": "cosine"})
        self.embedder = Embedder()

    def search(self, query: str, k: int = 6) -> List[Hit]:
        qv = self.embedder.encode([query])[0].tolist()
        res = self.col.query(query_embeddings=[qv], n_results=int(k))
        docs = res.get("documents", [[]])[0]
        metas = res.get("metadatas", [[]])[0]
        dists = res.get("distances", [[]])[0]
        out: List[Hit] = []
        for i, txt in enumerate(docs):
            src = (metas[i] or {}).get("source") if i < len(metas) else None
            dist = dists[i] if i < len(dists) else None
            score = 1.0 - (float(dist) if dist is not None else 0.0)
            out.append(Hit(text=_clean(txt or ""), source=Path(str(src or "unknown")).name, score=score))
        return out

    def top_score(self, query: str) -> float:
        hits = self.search(query, k=1)
        return float(hits[0].score) if hits else 0.0


# ============================================================
# LLM (grounded)
# ============================================================
@st.cache_resource(show_spinner=False)
def _get_hf_pipe(model_name: str = LLM_MODEL):
    if not _HAS_HF:
        return None
    try:
        tok = AutoTokenizer.from_pretrained(model_name)
        mdl = AutoModelForSeq2SeqLM.from_pretrained(model_name)
        return pipeline(
            task="text2text-generation",
            model=mdl,
            tokenizer=tok,
            max_new_tokens=300,
            min_new_tokens=120,
            num_beams=4,
            early_stopping=True,
            length_penalty=1.0,
            do_sample=False,
            no_repeat_ngram_size=4,
            repetition_penalty=1.15,
            truncation=True,
            clean_up_tokenization_spaces=True,
        )
    except Exception:
        return None


class GroundedGen:
    """
    Wraps a seq2seq LLM (FLAN‑T5 by default). If not available, falls back to extractive.
    Enforces: short, grounded, no-invention. Post‑checks ensure coverage; otherwise, fallback to snippets.
    """
    def __init__(self, model_name: str = LLM_MODEL):
        self.pipe = _get_hf_pipe(model_name)
        self.ok = self.pipe is not None

    @staticmethod
    def _prompt(question: str, context: str, lang: str = "fr") -> str:
        if lang == "en":
            return (
                "You are an internal consulting assistant. Answer ONLY using the context.\n"
                "- Keep it concise (4–6 sentences).\n"
                "- If information is missing, say you don't know.\n"
                "- Cite sources like [Source: filename].\n\n"
                f"Question: {question}\n\nContext:\n{context}\n\nAnswer:"
            )
        else:
            return (
                "Tu es un assistant interne. Réponds UNIQUEMENT depuis le contexte.\n"
                "- Réponse concise (4–6 phrases).\n"
                "- Si l'info manque, dis que tu ne sais pas.\n"
                "- Cite les sources comme [Source: fichier].\n\n"
                f"Question : {question}\n\nContexte :\n{context}\n\nRéponse :"
            )

    @staticmethod
    def _postprocess(raw: str, sources: List[str], lang: str = "fr") -> str:
        txt = _clean(raw)
        if not txt:
            return ""
        # Limit 6 sentences max
        sents = re.split(r"(?<=[\.!?])\s+(?=[A-ZÀ-ÖØ-Þ0-9])", txt)
        if len(sents) > 6:
            txt = " ".join(sents[:6]).strip()
        # Ensure at least one source
        if sources:
            has_src = any(f"[Source: {Path(s).name}]" in txt for s in sources)
            if not has_src:
                txt += f"\n[Source: {Path(sources[0]).name}]"
        return txt

    @staticmethod
    def _coverage_score(answer: str, ctx_snippets: List[str]) -> float:
        if not answer or not ctx_snippets:
            return 0.0
        ans = _clean(answer).lower()
        total = 0.0
        for sn in ctx_snippets:
            sn = _clean(sn).lower()
            if not sn:
                continue
            ta = set(_tokenize(ans))
            ts = set(_tokenize(sn))
            if not ts:
                continue
            inter = len(ta & ts)
            union = len(ts)
            total += inter / max(1, union)
        return total / max(1, len(ctx_snippets))

    def generate(self, question: str, context: str, ctx_snippets: List[str], sources: List[str], lang: str) -> str:
        if self.ok and self.pipe is not None:
            prompt = self._prompt(question, context, lang)
            out = self.pipe(prompt)
            cand = out[0].get("generated_text", "") if isinstance(out, list) and out and isinstance(out[0], dict) else str(out)
            cand = self._postprocess(cand, sources, lang)
            cov = self._coverage_score(cand, ctx_snippets)
            if cov >= 0.10:  # modest bar
                return cand
        # Extractive fallback (human-friendly)
        bullets = [f"• {s}" for s in ctx_snippets[:6] if s]
        if not bullets:
            return ("Je ne sais pas." if lang == "fr" else "I don't know.")
        intro = ("Réponse (extraits, basées sur les documents) :\n" if lang == "fr" else "Answer (extracts from documents):\n")
        ans = intro + "\n".join(bullets)
        if sources:
            ans += f"\n[Source: {Path(sources[0]).name}]"
        return ans


# ============================================================
# Ambiguity handling → auto‑reformulation (silent)
# ============================================================
_DEFAULT_SUGGEST = {
    "it storm": [
        "Quel est le cœur de métier d’IT Storm ?",
        "Quelles solutions IT Storm développe‑t‑elle pour la donnée ?",
        "Quelles priorités IT Storm met‑elle en avant (sécurité, coûts, fiabilité) ?",
    ],
    "data": [
        "Quels pipelines de données IT Storm met‑elle en place ?",
        "Quelles solutions data IT Storm propose‑t‑elle (collecte, qualité, exploitation) ?",
    ],
    "rag": [
        "Comment IT Storm met‑elle en œuvre une solution RAG pour un client ?",
        "Quelle valeur apporte le RAG aux consultants IT Storm ?",
    ],
}


def _load_suggest_map() -> Dict[str, List[str]]:
    p = Path(os.getenv("SUGGEST_PATH", "./src/data/suggest_keywords.json"))
    if p.exists():
        try:
            return json.loads(p.read_text(encoding="utf-8"))
        except Exception:
            return _DEFAULT_SUGGEST
    return _DEFAULT_SUGGEST


def make_reformulations(q: str, lang: str = "fr", max_vars: int = 4) -> List[str]:
    base = _clean(q)
    out = [base]
    m = _load_suggest_map()
    low = base.lower()
    for k, lst in m.items():
        if k in low:
            out.extend(lst)
    # Generic clarifiers
    if lang == "en":
        out.extend([
            f"{base} — please answer from internal IT‑STORM documents only",
            f"In one paragraph: {base}",
        ])
    else:
        out.extend([
            f"{base} — réponse basée uniquement sur les documents IT‑STORM",
            f"En un paragraphe : {base}",
        ])
    # Dedup & cap
    seen = set(); uniq = []
    for s in out:
        s = _clean(s)
        if s and s not in seen:
            seen.add(s); uniq.append(s)
    return uniq[: max_vars]


# ============================================================
# Core QA / Generation
# ============================================================
@dataclass
class QAResult:
    answer: str
    sources: List[str]
    used_queries: List[str]


def grounded_answer(question: str, lang: str = "fr", k: int = 6) -> QAResult:
    # Modules guard
    if not _HAS_CHROMA or not _HAS_ST:
        msg = (
            "Modules manquants : chromadb et/ou sentence-transformers. Installe-les pour activer le RAG."
            if lang == "fr" else
            "Missing modules: chromadb and/or sentence-transformers. Install them to enable RAG."
        )
        return QAResult(answer=msg, sources=[], used_queries=[])

    # Soft domain guard
    if not _allowed(question):
        msg = (
            "Ce moteur couvre le périmètre IT‑STORM (cloud/devops/data/IA). Merci de reformuler dans ce contexte."
            if lang == "fr" else
            "This engine covers IT‑STORM scope (cloud/devops/data/AI). Please reformulate within scope."
        )
        return QAResult(answer=msg, sources=[], used_queries=[])

    db = VectorDB(VECTOR_DB, COLLECTION)
    gen = GroundedGen(LLM_MODEL)

    # Reformulations si ambigu (silencieux)
    queries = [question]
    if _is_ambiguous(question):
        queries = make_reformulations(question, lang=lang, max_vars=4)

    # Retrieve per reformulation; keep best by mean top-3 score
    best_ctx: List[Hit] = []
    best_q: str = queries[0]
    best_score = -1.0
    for q in queries:
        hits = db.search(q, k=k)
        if _HAS_ST:
            mean3 = float(np.mean([h.score for h in hits[:3]])) if hits else 0.0
        else:
            mean3 = sum(h.score for h in hits[:3]) / max(1, len(hits[:3])) if hits else 0.0
        if mean3 > best_score:
            best_score = mean3
            best_ctx = hits
            best_q = q

    if not best_ctx:
        return QAResult(answer=("Je ne sais pas." if lang == "fr" else "I don't know."), sources=[], used_queries=queries)

    # Balance snippets across sources (round‑robin)
    by_src: Dict[str, List[Hit]] = {}
    for h in best_ctx:
        by_src.setdefault(h.source, []).append(h)
    snippets: List[str] = []
    src_order = list(by_src.keys())
    cursor = {s: 0 for s in src_order}
    while len(snippets) < min(k, sum(len(v) for v in by_src.values())):
        progressed = False
        for s in src_order:
            i = cursor[s]
            arr = by_src[s]
            if i < len(arr):
                snippets.append(arr[i].text)
                cursor[s] += 1
                progressed = True
                if len(snippets) >= k:
                    break
        if not progressed:
            break

    context = "\n\n---\n\n".join(snippets)
    sources = [h.source for h in best_ctx]
    ans = gen.generate(question, context, snippets, sources, lang if lang != "auto" else "fr")
    return QAResult(answer=ans, sources=sources[:3], used_queries=[best_q] if queries else [])


# ============================================================
# Exports
# ============================================================

def _safe_filename(x: str) -> str:
    return re.sub(r"[^A-Za-z0-9_\- ]+", "", x).strip().replace(" ", "_") or f"export_{uuid.uuid4().hex[:8]}"


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
    slide.placeholders[1].text = "Hosted by IT‑STORM — RAG Local"
    layout = prs.slide_layouts[1]
    for name, content in sections:
        s = prs.slides.add_slide(layout)
        s.shapes.title.text = name
        tf = s.placeholders[1].text_frame
        tf.clear()
        for line in textwrap.wrap(_clean(str(content)), width=110)[:14]:
            p = tf.add_paragraph(); p.text = line; p.level = 0
    prs.save(path)
    return path


# ============================================================
# Streamlit UI
# ============================================================

def _modules_banner():
    missing = []
    if not _HAS_CHROMA: missing.append("chromadb")
    if not _HAS_ST: missing.append("sentence-transformers (+ numpy)")
    txt = ", ".join(missing)
    if missing:
        st.warning(
            f"Modules requis absents: {txt}. Installe-les pour activer la recherche RAG.")


def render_generate_docs_tab():
    st.header("🧠 Génération automatique de documents RAG (local, sans hallucination)")
    st.caption("Chroma + SentenceTransformers + HF (optionnel) · Ambiguïté → Reformulation auto → Réponse ancrée")

    _modules_banner()

    lang_lbl = st.selectbox("Langue / Language", list(SUPPORTED.keys()), index=1)
    lang = SUPPORTED[lang_lbl]

    mode = st.radio(
        "Mode",
        ["Question libre (RAG)", "Complet (8 sections)", "Résumé de document (PDF/TXT)"],
        horizontal=True,
    )

    st.divider()

    # === Question libre ===
    if mode == "Question libre (RAG)":
        q = st.text_input(
            "Question",
            placeholder=("Pose une question (même vague) — je clarifie et je réponds sans inventer" if lang=="fr" else "Ask anything (even vague) — I'll clarify and answer without inventing"),
        )
        k = st.slider("Top chunks (k)", 3, 12, 6, 1)
        if st.button("🔎 Répondre" if lang=="fr" else "🔎 Answer") and q:
            with st.spinner("Recherche et génération en cours…" if lang=="fr" else "Retrieving and generating…"):
                res = grounded_answer(q, lang=lang if lang!="auto" else "fr", k=k)
            st.subheader("Réponse" if lang=="fr" else "Answer")
            st.write(res.answer)
            if res.sources:
                st.caption("Sources: " + ", ".join(sorted(set(res.sources))))
            if res.used_queries:
                st.caption(("Reformulation utilisée: " if lang=="fr" else "Used reformulation: ") + res.used_queries[0])
        with st.expander("Pourquoi cette réponse est fiable ? / Why grounded?"):
            st.markdown(
                "- **Ambiguïté gérée automatiquement** (reformulations silencieuses).\n"
                "- **Récupération multi-sources équilibrée** (round‑robin) pour éviter les biais.\n"
                "- **Décodage contraint** (4–6 phrases) avec **contrôle de couverture** contextuelle.\n"
                "- **Fallback extractif** si la génération n’est pas suffisamment ancrée."
            )

    # === Génération complète ===
    elif mode == "Complet (8 sections)":
        topic = st.text_input("Sujet / Topic", placeholder=("Ex: Proposition RAG pour client énergie"))
        k = st.slider("Top chunks (k)", 3, 12, 6, 1, help="Nombre d'extraits par section")
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
                "Executive Summary","Contexte & Objectifs","Pain Points","Architecture Solution",
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
                    res = grounded_answer(q, lang=lang if lang!="auto" else "fr", k=k)
                outputs.append((sec, res.answer))
                st.subheader(sec)
                st.write(res.answer)
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

    # === Résumé de document ===
    else:
        path = st.text_input("Chemin du document (PDF/TXT)", placeholder="./docs/mon_fichier.pdf")
        if st.button("📄 Résumer") and path:
            p = Path(path)
            if not p.exists():
                st.warning("Fichier introuvable."); return
            try:
                if _HAS_PDF and p.suffix.lower() == ".pdf":
                    reader = PdfReader(str(p))
                    txt = "\n".join((reader.pages[i].extract_text() or "") for i in range(len(reader.pages)))
                else:
                    txt = p.read_text(encoding="utf-8", errors="ignore")
            except Exception as e:
                st.error(f"Erreur lecture: {e}"); return
            txt = _clean(txt)[:10000]
            if not txt:
                st.warning("Document vide."); return
            gen = GroundedGen(LLM_MODEL)
            prompt = (f"Résumé factuel (6 phrases max) :\n{txt}" if lang!="en" else f"Summarize factually in <=6 sentences:\n{txt}")
            if gen.ok and gen.pipe is not None:
                out = gen.pipe(prompt)
                ans = out[0]["generated_text"] if isinstance(out, list) else str(out)
                st.subheader("Résumé"); st.write(_clean(ans))
            else:
                # Extractive fallback
                sents = [s.strip() for s in re.split(r"(?<=[\.!?])\s+", txt) if s.strip()][:6]
                st.subheader("Résumé (extraits)")
                st.write("\n".join([f"- {s}" for s in sents]))


# Backward-compat alias (used by existing app)
render = render_generate_docs_tab
