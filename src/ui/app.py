from __future__ import annotations
# app.py — StormCopilot (IT-STORM) — Local HF only (UPDATED)
# === Chatbot (mutualisé) ===
from src.chatbot import ask_rag, get_chain_cached
from pathlib import Path  # si pas déjà importé
from src.ui.i18n import set_lang_from_query, get_lang, t
set_lang_from_query()       # lit ?lang=fr et initialise st.session_state["lang"]
from src.ui.components import floating_chatbot
import streamlit as st
from streamlit_javascript import st_javascript
from src.ui.components.floating_chatbot import render_chatbot
from src.ui.tabs import generate_docs_rag 
from src.utils.doc_tools import make_docx, make_ppt, summarize_text

# === UI principale ===
import os, io, base64, time, sys
from src.ui.tabs import generate_docs_rag
from pathlib import Path
from typing import List, Tuple, Optional
import io
from datetime import datetime
from typing import List, Dict
from src.ui.sections.generate_docs import render_generate_docs
import os
import streamlit as st

# ===================== I18N (EN/FR) =====================
if "lang" not in st.session_state:
    st.session_state["lang"] = "en"

LANG = {
    "en": {
        "sidebar_settings": "Settings",
        "sidebar_dark_mode": "Dark mode",
        "sidebar_diag": "Diagnostics",
        "sidebar_llm_backend": "LLM backend: **Local Hugging Face** ✅",
        "sidebar_theme_note": "Auto theme · v2.2 (Local-only, CPU-safe)",

        "kpi_indexed_docs": "Indexed Docs",
        "kpi_chunks_file": "Chunks File",
        "kpi_vector_db": "Vector DB",
        "kpi_output_folder": "Output Folder",

        "tab_chat": "💬 Knowledge Chat",
        "tab_upload": "📂 Upload & Index",
        "tab_generate": "📝 Generate Docs",
        "tab_market": "🌍 Market Watch",
        "tab_qa": "🔎 English QA (RAG EN)",

        "chat_title": "Knowledge Q&A (RAG with LangChain + Local HF)",
        "chat_input": "Ask a question about your indexed documents",
        "chat_button": "🔎 Retrieve & Answer",
        "chat_clear": "🧹 Clear",   # ✅ ajouté ici
        "chat_answer": "Answer",
        "chat_sources": "Sources (raw chunks)",
        "chat_question_too_long": "Your question is very long — I truncated it to 2000 characters for stability.",
        "chat_tip_rebuild": "Tip: if you switched embedding model, rebuild your index first.",

        "upload_title": "Upload documents & (re)build index",
        "upload_uploader": "Upload PDF/DOCX/TXT",
        "upload_save": "⬆️ Save uploads",
        "upload_saved": "Saved {n} file(s) to `data/raw/`.",
        "upload_extract": "⚙️ Extract & Chunk",
        "upload_extracted": "Created {n} chunks → {outp}",
        "upload_rebuild": "🧠 Rebuild Vector Index",
        "upload_rebuilt": "Indexed {n} chunks into ChromaDB.",
        "upload_preview": "Preview extracted chunks",

        "theme_env": "Env: Local",
        "brand_market_api": "Market API: ",
        "brand_llm": "LLM (Local HF): ",
        "brand_up": "✅ Up",
        "brand_down": "❌ Down",
        "brand_ready": "✅ Ready",
        "brand_not_ready": "⚠️ Not ready",

        "lang_picker": "Language",
        "lang_en": "English",
        "lang_fr": "Français",
    },
    "fr": {
        "sidebar_settings": "Paramètres",
        "sidebar_dark_mode": "Mode sombre",
        "sidebar_diag": "Diagnostics",
        "sidebar_llm_backend": "Moteur LLM : **Hugging Face local** ✅",
        "sidebar_theme_note": "Thème auto · v2.2 (Local uniquement, CPU-safe)",

        "kpi_indexed_docs": "Documents indexés",
        "kpi_chunks_file": "Fichier de segments",
        "kpi_vector_db": "Base vectorielle",
        "kpi_output_folder": "Dossier d’export",

        "tab_chat": "💬 Chat Connaissance",
        "tab_upload": "📂 Import & Index",
        "tab_generate": "📝 Générer des documents",
        "tab_market": "🌍 Marchés",
        "tab_qa": "🔎 QA anglais (RAG EN)",

        "chat_title": "Q&R Connaissance (RAG avec LangChain + HF local)",
        "chat_input": "Pose une question sur tes documents indexés",
        "chat_button": "🔎 Récupérer & Répondre",
        "chat_clear": "🧹 Effacer",   # ✅ ajouté ici
        "chat_answer": "Réponse",
        "chat_sources": "Sources (extraits bruts)",
        "chat_question_too_long": "Ta question est très longue — je l’ai tronquée à 2000 caractères pour la stabilité.",
        "chat_tip_rebuild": "Astuce : si tu as changé de modèle d’embedding, reconstruis l’index avant.",

        "upload_title": "Importer des documents & (re)construire l’index",
        "upload_uploader": "Importer PDF/DOCX/TXT",
        "upload_save": "⬆️ Enregistrer les fichiers",
        "upload_saved": "✅ {n} fichier(s) enregistré(s) dans `data/raw/`.",
        "upload_extract": "⚙️ Extraire & Segmenter",
        "upload_extracted": "Créé {n} segments → {outp}",
        "upload_rebuild": "🧠 Reconstruire l’index vectoriel",
        "upload_rebuilt": "Indexé {n} segments dans ChromaDB.",
        "upload_preview": "Aperçu des segments extraits",

        "theme_env": "Env : Local",
        "brand_market_api": "API Marché : ",
        "brand_llm": "LLM (HF local) : ",
        "brand_up": "✅ OK",
        "brand_down": "❌ Hors ligne",
        "brand_ready": "✅ Prêt",
        "brand_not_ready": "⚠️ Non prêt",

        "lang_picker": "Langue",
        "lang_en": "Anglais",
        "lang_fr": "Français",
    },
}

def t(key: str) -> str:
    lang = st.session_state.get("lang", "en")
    return LANG.get(lang, LANG["en"]).get(key, key)
# ============================================================

from src.rag.chain import build_rag_chain
from src.ui.tabs import generate_docs_rag  # <— ce fichier
from src.ui.tabs import rag_en_tab  # <— nouveau fichier

# Optionnel : valeurs par défaut si .env non chargé
os.environ.setdefault("LLM_MODEL", "google/flan-t5-base")
os.environ.setdefault("LLM_DEVICE", "-1")
os.environ.setdefault("EMBEDDING_MODEL", "sentence-transformers/all-MiniLM-L6-v2")
os.environ.setdefault("RAG_TOPK", "4")
os.environ.setdefault("RAG_MAX_CONTEXT_CHARS", "1300")
def _get_source_names_for_query(query: str, k: int = 4) -> List[str]:
    try:
        rows = retrieve(query, k=k, similarity_threshold=0.0)  # (doc, src, dist)
        names = []
        for _doc, src, _dist in rows:
            try:
                names.append(Path(src).name)
            except Exception:
                names.append(str(src))
        # unique en conservant l'ordre
        seen = set()
        uniq = []
        for n in names:
            if n not in seen:
                seen.add(n)
                uniq.append(n)
        return uniq
    except Exception:
        return []

@st.cache_resource(show_spinner=False)
def load_chain():
    return build_rag_chain()

# =============== Anti-crash: limiter threads & parallelism ===============
os.environ.setdefault("TOKENIZERS_PARALLELISM", "false")
os.environ.setdefault("OMP_NUM_THREADS", "1")
os.environ.setdefault("MKL_NUM_THREADS", "1")
os.environ.setdefault("NUMEXPR_MAX_THREADS", "1")

# --- Import path (project root) ---
sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

# --- Std / 3rd-party ---
import streamlit as st
import pandas as pd
import requests
import plotly.graph_objects as go
from src.ui.sections import market 
from dotenv import load_dotenv
API_BASE = os.getenv("MARKET_API_BASE_URL", "http://127.0.0.1:8001")
TIMEOUT = float(os.getenv("FINANCE_TIMEOUT", "10"))
# --- LangChain / RAG ---
from langchain_community.llms import HuggingFacePipeline
from langchain_community.vectorstores import Chroma as LCChroma
from langchain_community.embeddings import SentenceTransformerEmbeddings
from langchain_core.prompts import PromptTemplate
from langchain_core.output_parsers import StrOutputParser
from langchain_core.runnables import RunnablePassthrough

# --- PyTorch (set threads early) ---
try:
    import torch
    torch.set_num_threads(max(1, min(2, (os.cpu_count() or 2))))
except Exception:
    pass

# --- Transformers (local LLM + summarizer) ---
from transformers import AutoModelForCausalLM, AutoTokenizer, pipeline as hf_pipeline
try:
    from transformers import pipeline, AutoTokenizer as _AT, AutoModelForSeq2SeqLM as _AM
    HF_AVAILABLE = True
except Exception:
    HF_AVAILABLE = False

# --- Chroma / Embeddings ---
import chromadb
from chromadb.config import Settings
from sentence_transformers import SentenceTransformer

# --- Office formats ---
from pptx import Presentation
from docx import Document

# --- Paths / constants ---
ROOT = Path(__file__).resolve().parents[2]
DATA_RAW = ROOT / "data" / "raw"
DATA_PROCESSED = ROOT / "data" / "processed"
VEC_DIR = ROOT / "vectors"  # garde ton dossier existant si différent
OUT_DIR = ROOT / "out"
COLLECTION_NAME = "itstorm_docs"
EMB_MODEL_NAME = "sentence-transformers/all-MiniLM-L6-v2"

# --- .env ---
env_example = ROOT / ".env.example"
if env_example.exists():
    load_dotenv(dotenv_path=env_example, override=True)
else:
    load_dotenv(override=True)

# --- Page config (unique) ---
st.set_page_config(
    page_title="StormCopilot · IT-STORM",
    page_icon="💼",
    layout="wide",
    initial_sidebar_state="expanded",
)
# ============================================================
# UI Layout optimization — centrer et réduire marges
# ============================================================
st.markdown("""
<style>
/* Supprime les marges bleues et recentre tout le contenu principal */
header[data-testid="stHeader"] {
    height: 0 !important;
    visibility: hidden !important;
}

/* APRÈS — flux normal, rien ne “mange” le haut de page */
.block-container {
    /* revenir au flux normal */
    display: block;
    min-height: initial;
    padding-top: 2rem !important;   /* petite marge en haut */
    padding-bottom: 1.5rem !important;
    margin: 0 auto !important;
}

section.main {
    display: block;
}

/* si tu veux cacher l’header, compense son retrait par un padding-top global */
header[data-testid="stHeader"] {
    height: 0 !important;
    visibility: hidden !important;
}
.stAppViewContainer .main .block-container {
    padding-top: 3.5rem !important; /* compense l’header caché */
}


/* Supprime les marges / espaces inutiles en haut et bas */
.stAppViewContainer, .main {
    padding: 0 !important;
    margin: 0 !important;
}

/* Cache les diviseurs, si visibles */
hr, [role="separator"] {
    display: none !important;
}
</style>
""", unsafe_allow_html=True)

# src/api/main.py
import os
from typing import List, Any, Dict

from fastapi import FastAPI, HTTPException, Query, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse, HTMLResponse
from fastapi.staticfiles import StaticFiles

from dotenv import load_dotenv

# === Tes imports existants (marchés) ==========================
from src.api.models import Quote, OHLCV, SearchResult
from src.api.providers.yahoo import YahooProvider
from src.api.utils import is_euronext_open, paris_now
# ===============================================================

load_dotenv()

app = FastAPI(
    title="IT-Storm API",
    version="1.1.0",
    description="Market API + Chat bubble endpoint (RAG) pour it-storm.fr",
)

# --- CORS ---
def _parse_origins(env_val: str) -> List[str]:
    if not env_val:
        return []
    return [o.strip() for o in env_val.split(",") if o.strip()]

# Par défaut on autorise it-storm.fr + localhost dev ; surcharge possible par CORS_ORIGINS
_default_origins = [
    "https://it-storm.fr",
    "https://www.it-storm.fr",
    "http://localhost:3000",
    "http://127.0.0.1:3000",
    "http://localhost:8000",
    "http://127.0.0.1:8000",
]
allow_origins = _parse_origins(os.getenv("CORS_ORIGINS")) or _default_origins

app.add_middleware(
    CORSMiddleware,
    allow_origins=allow_origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# --- Static: servir la bulle (embed.js) ---
# Dossier vu dans ton arbo : client_chatbot/public/embed.js
STATIC_CLIENT_DIR = os.path.join(os.getcwd(), "client_chatbot", "public")
if os.path.isdir(STATIC_CLIENT_DIR):
    app.mount("/client-chat", StaticFiles(directory=STATIC_CLIENT_DIR), name="client-chat")
else:
    # On ne crashe pas l'appli si le dossier n'existe pas ; simple warning en logs
    print(f"[WARN] Static dir not found for chat bubble: {STATIC_CLIENT_DIR}")

# =======================
#  ROUTES MARCHÉ (existantes)
# =======================
PROVIDER = YahooProvider()

@app.get("/v1/health")
async def health():
    return {"status": "ok", "time": paris_now().isoformat()}

@app.get("/v1/marketstatus")
async def market_status():
    return {"market": "Euronext Paris", "is_open": is_euronext_open(), "time": paris_now().isoformat()}

@app.get("/v1/search", response_model=List[SearchResult])
async def search(q: str = Query(..., min_length=1)):
    return await PROVIDER.search(q)

@app.get("/v1/quote/{symbol}", response_model=Quote)
async def get_quote(symbol: str):
    try:
        return await PROVIDER.quote(symbol)
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))

@app.get("/v1/ohlcv/{symbol}", response_model=OHLCV)
async def get_ohlcv(symbol: str, interval: str = "1m", range: str = "1d"):
    try:
        return await PROVIDER.ohlcv(symbol, interval=interval, range_=range)
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))

# =======================
#  CHAT / RAG (nouveaux)
# =======================

# Chargement paresseux de la chaîne QA (même logique que tools/qa_cli)
_QA_CHAIN: Any = None
_QA_LOADED: bool = False

def _try_build_chain() -> Any:
    """
    Essaie plusieurs méthodes classiques pour récupérer la même chaîne
    utilisée par `tools/qa_cli.py`.
    Adapte si besoin selon tes vrais noms de fonctions.
    """
    # 1) src.rag.chain: get_chain / build_chain
    try:
        from src.rag.chain import get_chain  # type: ignore
        return get_chain()
    except Exception:
        pass
    try:
        from src.rag.chain import build_chain  # type: ignore
        return build_chain()
    except Exception:
        pass

    # 2) src.rag (ex: get_chain au niveau du package)
    try:
        from src import rag  # type: ignore
        if hasattr(rag, "get_chain"):
            return rag.get_chain()
        if hasattr(rag, "build_chain"):
            return rag.build_chain()
    except Exception:
        pass

    # 3) tools.qa_cli: chaîne exposée ?
    try:
        # Si ton qa_cli expose une fonction utilitaire (à adapter si tu en as une)
        from tools.qa_cli import get_chain as cli_get_chain  # type: ignore
        return cli_get_chain()
    except Exception:
        pass

    # 4) Rien trouvé
    raise RuntimeError(
        "Impossible de charger la chaîne QA. "
        "Expose une fonction `get_chain()` ou `build_chain()` dans `src.rag.chain` "
        "ou adapte `_try_build_chain()` à ton projet."
    )

def _ensure_chain() -> Any:
    global _QA_CHAIN, _QA_LOADED
    if _QA_LOADED and _QA_CHAIN is not None:
        return _QA_CHAIN
    _QA_CHAIN = _try_build_chain()
    _QA_LOADED = True
    return _QA_CHAIN

def _invoke_chain(chain: Any, query: str) -> str:
    """
    Normalise l'appel pour différents types de chaînes (LCEL LangChain, fonctions, etc.).
    """
    # Cas LangChain LCEL: chain.invoke({"query": ...})
    try:
        out = chain.invoke({"query": query})
        if isinstance(out, dict):
            # Champs possibles: 'result', 'answer', 'output_text', etc.
            for k in ("result", "answer", "output_text", "text", "content"):
                if k in out and out[k]:
                    return str(out[k])
            # Sinon, tout le dict
            return str(out)
        return str(out)
    except Exception:
        pass

    # Cas fonction simple: chain(query)
    try:
        return str(chain(query))
    except Exception:
        pass

    # Cas méthode .run
    try:
        return str(chain.run(query))
    except Exception:
        pass

    # Dernier recours
    return "Je n’ai pas pu générer de réponse (chaîne non compatible)."

@app.post("/chat")
async def chat(req: Request):
    """
    Endpoint utilisé par la bulle JS (embed.js) ou tout frontend.
    Reçoit { "message": "..." } et renvoie { "answer", "sources", "suggestions" }.
    """
    try:
        payload: Dict[str, Any] = await req.json()
    except Exception:
        raise HTTPException(status_code=400, detail="Payload JSON invalide")

    q = str(payload.get("message") or "").strip()
    if not q:
        raise HTTPException(status_code=422, detail="Champ 'message' requis")

    try:
        # k = top_k UI si dispo, sinon défaut 4
        k = 4
        try:
            # si un slider Streamlit a posé top_k dans session_state (facultatif)
            k = int(st.session_state.get("top_k_from_ui", 4))
        except Exception:
            pass

        result = ask_rag(
            question=q,
            k=k,
            get_sources_fn=_get_source_names_for_query
        )
        return JSONResponse(result)
    except Exception as e:
        return JSONResponse(
            {"answer": f"[Erreur backend] {e}", "sources": [], "suggestions": []},
            status_code=500
        )

# Petite page de test locale (facultatif)
@app.get("/")
async def home():
    return HTMLResponse("""
<!doctype html>
<html lang="fr">
  <head>
    <meta charset="utf-8">
    <title>IT-Storm — Test bulle</title>
  </head>
  <body>
    <h1>Test bulle IT-Storm</h1>
    <p>Si la bulle apparaît en bas à droite, clique et pose une question.</p>

    <script defer
      src="/client-chat/embed.js"
      data-api="/chat"
      data-brand="#2563eb"
      data-title="IT-Storm Chatbot"></script>
  </body>
</html>
""" )

# --------------------------------------------------------------------------------------
# THEME & BRANDING
# --------------------------------------------------------------------------------------
LOGO_PATH = os.path.join(os.path.dirname(__file__), "assets", "itstorm_logo.png")

THEME_LIGHT = dict(
    bg="#ffffff", text="#0e1626", subbg="#f5f7fb", card="#ffffff", border="#e7edf7", accent="#1a73e8"
)
THEME_DARK = dict(
    bg="#0b1220", text="#e6f0ff", subbg="#111a2b", card="#0f1a2e", border="#1f2b42", accent="#4da3ff"
)

def _logo_b64() -> str:
    try:
        with open(LOGO_PATH, "rb") as f:
            return base64.b64encode(f.read()).decode("utf-8")
    except Exception:
        return ""

def apply_theme(theme: dict):
    css = f"""
    <style>
    :root {{
      --bg: {theme['bg']};
      --text: {theme['text']};
      --subbg: {theme['subbg']};
      --card: {theme['card']};
      --border: {theme['border']};
      --accent: {theme['accent']};
    }}

    * {{ transition: background-color .25s ease, color .25s ease, border-color .25s ease; }}

    html, body, [data-testid="stAppViewContainer"] {{
      background: var(--bg) !important;
      color: var(--text) !important;
    }}
    [data-testid="stSidebar"] {{ background: var(--subbg) !important; }}

    [data-testid="stAppViewContainer"] > .main .block-container {{
      padding-top: 2.6rem !important;
      padding-bottom: 2rem !important;
    }}

    header[data-testid="stHeader"] {{
      background: transparent !important;
      box-shadow: none !important;
    }}

    .brandbar {{
      background: var(--card);
      border: 1px solid var(--border);
      border-radius: 18px;
      padding: 10px 14px;
      margin: .25rem 0 10px;
      box-shadow: 0 8px 24px rgba(0,0,0,.08);
    }}
    .brand-title {{ font-weight: 800; font-size: 22px; line-height: 1.1; }}
    .brand-sub   {{ opacity: .85; font-size: 13px; }}

    .brandbar img {{
      display: block;
      height: 56px;
      width: auto;
      object-fit: contain;
      border-radius: 12px;
      filter: drop-shadow(0 2px 6px rgba(0,0,0,.25));
    }}

    .big-title {{ font-size: 2.0rem; font-weight: 800; color: var(--text); margin-bottom: .25rem; }}
    .sub-title {{ font-size: .95rem; color: var(--text); opacity: .75; }}

    .kpi-card {{
      border: 1px solid var(--border);
      border-radius: 16px;
      padding: 14px 16px;
      background: var(--card);
      box-shadow: 0 1px 2px rgba(10, 30, 80, 0.05);
    }}
    .kpi-label {{ color: var(--text); opacity: .7; font-size: .8rem; margin-bottom: .15rem; }}
    .kpi-value {{ color: var(--text); font-size: 1.35rem; font-weight: 700; }}

    .card {{
      border: 1px solid var(--border);
      border-radius: 16px;
      padding: 18px;
      background: var(--card);
      box-shadow: 0 1px 2px rgba(10, 30, 80, 0.05);
    }}

    .stButton>button, .stDownloadButton>button {{
      border-radius: 10px;
      padding: .55rem .9rem;
      font-weight: 600;
      border: 1px solid var(--border);
      background: var(--accent);
      color: #fff;
    }}
    .stButton>button:hover {{ filter: brightness(1.06); }}

    .chip {{
      display: inline-block;
      padding: 3px 9px;
      background: var(--subbg);
      border: 1px solid var(--border);
      border-radius: 9999px;
      color: var(--text);
      font-size: 12px;
      margin-right: 6px;
    }}
    .source {{
      font-size: 12px;
      color: var(--text);
      opacity: .75;
      background: var(--subbg);
      padding: 4px 8px;
      border-radius: 9999px;
      display: inline-block;
      margin-right: 8px;
      margin-top: 6px;
    }}

    .stTabs [role="tablist"] button {{ border-radius: 10px; }}
    hr {{ border: none; border-top: 1px solid var(--border); margin: .8rem 0 1rem; }}
    </style>
    """
    st.markdown(css, unsafe_allow_html=True)

def render_brand_header(api_ok: Optional[bool]=None, llm_ok: Optional[bool]=None):
    logo = _logo_b64()
    c1, c2, c3 = st.columns([0.10, 0.72, 0.18])
    with c1:
        if logo:
            st.markdown(
                f"""
                <div class="brandbar" style="display:flex;align-items:center;justify-content:center;">
                    <img src="data:image/png;base64,{logo}" width="56" style="border-radius:12px;"/>
                </div>
                """,
                unsafe_allow_html=True
            )
        else:
            st.markdown('<div class="brandbar"><span class="brand-title">IS</span></div>', unsafe_allow_html=True)
    with c2:
        st.markdown(
            """
            <div class="brandbar">
              <div class="brand-title">StormCopilot</div>
              <div class="brand-sub">Hosted by <b>IT-STORM · Innovation & Consulting</b> — Knowledge, RAG & Market Intelligence</div>
            </div>
            """,
            unsafe_allow_html=True,
        )
    with c3:
        st.markdown('<div class="brandbar" style="text-align:right;">', unsafe_allow_html=True)
        if api_ok is not None:
            st.markdown(f'<span class="chip">Market API: {"✅ Up" if api_ok else "❌ Down"}</span>', unsafe_allow_html=True)
        if llm_ok is not None:
            st.markdown(f'<span class="chip">LLM (Local HF): {"✅ Ready" if llm_ok else "⚠️ Not ready"}</span>', unsafe_allow_html=True)
        st.markdown('<span class="chip">Env: Local</span>', unsafe_allow_html=True)
        st.markdown('</div>', unsafe_allow_html=True)

# --------------------------------------------------------------------------------------
# Ensure folders exist
# --------------------------------------------------------------------------------------
for p in [DATA_RAW, DATA_PROCESSED, VEC_DIR, OUT_DIR]:
    p.mkdir(parents=True, exist_ok=True)

# --------------------------------------------------------------------------------------
# CACHED HELPERS (DB, LLM, Retriever, etc.)
# --------------------------------------------------------------------------------------
@st.cache_resource
def get_db():
    client = chromadb.Client(Settings(persist_directory=str(VEC_DIR), is_persistent=True))
    names = [c.name for c in client.list_collections()]
    coll = client.get_collection(COLLECTION_NAME) if COLLECTION_NAME in names else client.create_collection(COLLECTION_NAME)
    return client, coll

@st.cache_resource
def get_embedder():
    return SentenceTransformer(EMB_MODEL_NAME)

@st.cache_resource
def get_summarizer():
    if not HF_AVAILABLE:
        return None
    for name in ["google/pegasus-xsum", "t5-small"]:
        try:
            tok = _AT.from_pretrained(name)
            mdl = _AM.from_pretrained(name)
            return pipeline("summarization", model=mdl, tokenizer=tok)
        except Exception:
            continue
    return None

@st.cache_resource
def get_lc_embeddings():
    return SentenceTransformerEmbeddings(model_name=EMB_MODEL_NAME)

@st.cache_resource
def get_llm(model_name: str = "TinyLlama/TinyLlama-1.1B-Chat-v1.0"):
    """
    Local HF pipeline (CPU par défaut) — aucun appel réseau.
    Ajuste max_new_tokens/temperature ici si besoin.
    Plus robuste: pad/eos définis, low_cpu_mem_usage, dtype auto.
    """
    tok = AutoTokenizer.from_pretrained(model_name)
    if tok.pad_token_id is None and tok.eos_token_id is not None:
        tok.pad_token = tok.eos_token

    mdl = AutoModelForCausalLM.from_pretrained(
        model_name,
        low_cpu_mem_usage=True,
        torch_dtype="auto",
        device_map=None  # CPU
    )

    gen = hf_pipeline(
        task="text-generation",
        model=mdl,
        tokenizer=tok,
        max_new_tokens=256,     # un peu plus court par défaut (stabilité)
        do_sample=False,
        temperature=0.0,
        repetition_penalty=1.1,
        pad_token_id=tok.pad_token_id or tok.eos_token_id,
    )
    return HuggingFacePipeline(pipeline=gen)

@st.cache_resource
def get_retriever():
    lc_emb = get_lc_embeddings()
    vs = LCChroma(
        collection_name=COLLECTION_NAME,
        persist_directory=str(VEC_DIR),
        embedding_function=lc_emb
    )
    return vs.as_retriever(search_type="similarity")

RAG_PROMPT = PromptTemplate.from_template("""
You are a consulting assistant. Answer the user using ONLY the provided context.
If the answer is not in the context, say "Je ne sais pas.".

Answer concisely (<= 10 lines) and include a short bullet list of key points.
Cite sources like: [Source: filename].

Question:
{question}

Context:
{context}

Answer:
""".strip())

def build_rag_chain(k: int = 4):
    retriever = get_retriever()
    llm = get_llm()
    def _format_docs(docs):
        parts = []
        for d in docs:
            src = d.metadata.get("source", "unknown")
            parts.append(f"[Source: {Path(src).name}] {d.page_content}")
        return "\n\n".join(parts)
    chain = (
        {
            "question": RunnablePassthrough(),
            "context": retriever.with_config(run_name="Retriever") | (lambda docs: _format_docs(docs))
        }
        | RAG_PROMPT
        | llm
        | StrOutputParser()
    )
    chain = chain.with_config(configurable={"search_kwargs": {"k": k}})
    return chain

def retrieve(query: str, k: int = 4, similarity_threshold: float = 0.0):
    _, coll = get_db()
    emb = get_embedder()
    q = emb.encode([query], normalize_embeddings=True).tolist()[0]
    res = coll.query(query_embeddings=[q], n_results=k)
    docs = res.get("documents", [[]])[0]
    metas = res.get("metadatas", [[]])[0]
    dists = res.get("distances", [[]])[0] if res.get("distances") else [0.0] * len(docs)
    pairs = []
    for doc, meta, dist in zip(docs, metas, dists):
        if similarity_threshold > 0 and dist > similarity_threshold:
            continue
        pairs.append((doc, meta.get("source", "unknown"), dist))
    return pairs

def save_uploaded_files(files):
    saved = []
    for f in files:
        target = DATA_RAW / f.name
        with open(target, "wb") as out:
            out.write(f.read())
        saved.append(str(target))
    return saved

def extract_and_chunk(
    in_dir=DATA_RAW,
    out_path=DATA_PROCESSED / "chunks.jsonl",
    chunk_size=900,
    overlap=150,
):
    """
    Extrait le texte de plusieurs formats (PDF, DOCX, TXT/MD, PPTX, CSV, XLS/XLSX, HTML/HTM, JSON),
    le découpe en segments, puis écrit un JSONL pour l’indexation RAG.
    Retourne (nb_chunks, out_path, stats_dict).
    """
    import json
    from pathlib import Path

    # ---- Helpers par type ----
    def extract_pdf(p: Path) -> str:
        try:
            from pypdf import PdfReader
            reader = PdfReader(p)
            return "\n".join((page.extract_text() or "") for page in reader.pages)
        except Exception:
            return ""

    def extract_docx(p: Path) -> str:
        try:
            import docx2txt
            return docx2txt.process(p)
        except Exception:
            return ""

    def extract_txt_like(p: Path) -> str:
        try:
            return p.read_text(encoding="utf-8", errors="ignore")
        except Exception:
            return ""

    def extract_pptx(p: Path) -> str:
        try:
            from pptx import Presentation
            prs = Presentation(p)
            parts = []
            for slide in prs.slides:
                for sh in slide.shapes:
                    if hasattr(sh, "text") and sh.text:
                        parts.append(sh.text)
            return "\n".join(parts)
        except Exception:
            return ""

    def extract_csv(p: Path) -> str:
        try:
            import pandas as pd
            df = pd.read_csv(p)
            return df.to_string(index=False)
        except Exception:
            return ""

    def extract_xlsx(p: Path) -> str:
        try:
            import pandas as pd
            xls = pd.ExcelFile(p)
            parts = []
            for sheet in xls.sheet_names:
                df = xls.parse(sheet)
                parts.append(f"# Sheet: {sheet}\n{df.to_string(index=False)}")
            return "\n\n".join(parts)
        except Exception:
            return ""

    def extract_html(p: Path) -> str:
        try:
            from bs4 import BeautifulSoup
            html = p.read_text(encoding="utf-8", errors="ignore")
            return BeautifulSoup(html, "html.parser").get_text(separator="\n")
        except Exception:
            # Fallback minimal au cas où
            import re
            html = p.read_text(encoding="utf-8", errors="ignore")
            text = re.sub(r"<(script|style)[^>]*>.*?</\\1>", "", html, flags=re.S|re.I)
            text = re.sub(r"<[^>]+>", " ", text)
            return re.sub(r"\s+", " ", text).strip()

    def extract_json(p: Path) -> str:
        try:
            raw = json.loads(p.read_text(encoding="utf-8", errors="ignore"))
        except Exception:
            return ""
        parts = []
        def walk(x):
            if isinstance(x, dict):
                for k, v in x.items():
                    parts.append(str(k))
                    walk(v)
            elif isinstance(x, list):
                for it in x:
                    walk(it)
            else:
                s = str(x)
                if s and s != "None":
                    parts.append(s)
        walk(raw)
        return "\n".join(parts)

    # ---- Boucle fichiers ----
    recs = []
    stats = {"seen": 0, "processed": 0, "ignored": 0, "by_ext": {}}
    for p in Path(in_dir).glob("*"):
        if not p.is_file():
            continue
        stats["seen"] += 1
        ext = p.suffix.lower()
        stats["by_ext"].setdefault(ext, 0)

        text = ""
        if ext == ".pdf":
            text = extract_pdf(p)
        elif ext == ".docx":
            text = extract_docx(p)
        elif ext in {".txt", ".md"}:
            text = extract_txt_like(p)
        elif ext == ".pptx":
            text = extract_pptx(p)
        elif ext == ".csv":
            text = extract_csv(p)
        elif ext in {".xlsx", ".xls"}:
            text = extract_xlsx(p)
        elif ext in {".html", ".htm"}:
            text = extract_html(p)
        elif ext == ".json":
            text = extract_json(p)
        else:
            stats["ignored"] += 1
            continue

        if not text:
            stats["ignored"] += 1
            continue

        # Chunking
        words = text.split()
        step = max(1, (chunk_size - overlap))
        i = 0
        while i < len(words):
            chunk_words = words[i : i + chunk_size]
            recs.append({"source": str(p), "text": " ".join(chunk_words)})
            i += step

        stats["processed"] += 1
        stats["by_ext"][ext] += 1

    # Écriture JSONL
    out_path.parent.mkdir(parents=True, exist_ok=True)
    with open(out_path, "w", encoding="utf-8") as f:
        for r in recs:
            f.write(json.dumps(r, ensure_ascii=False) + "\n")

    return len(recs), out_path, stats

def rebuild_index(in_path=DATA_PROCESSED / "chunks.jsonl"):
    client, _ = get_db()
    try:
        client.delete_collection(COLLECTION_NAME)
    except Exception:
        pass
    coll = client.create_collection(COLLECTION_NAME)
    model = get_embedder()
    texts, metas, ids = [], [], []
    import json
    with open(in_path, "r", encoding="utf-8") as f:
        for k, line in enumerate(f):
            r = json.loads(line)
            texts.append(r["text"])
            metas.append({"source": r["source"]})
            ids.append(f"id_{k}")
    emb = model.encode(texts, normalize_embeddings=True).tolist()
    coll.add(documents=texts, embeddings=emb, metadatas=metas, ids=ids)
    return len(texts)

def kpi_card(label: str, value: str):
    st.markdown(f"""
    <div class="kpi-card">
      <div class="kpi-label">{label}</div>
      <div class="kpi-value">{value}</div>
    </div>
    """, unsafe_allow_html=True)

def render_sources(rows: List[Tuple[str, str, float]]):
    if not rows:
        st.info("No sources retrieved yet.")
        return
    for i, (doc, src, dist) in enumerate(rows, 1):
        with st.expander(f"Context #{i} — {Path(src).name}"):
            st.write(doc[:1200] + ("..." if len(doc) > 1200 else ""))
            st.markdown(f'<span class="source">Source: {src}</span>', unsafe_allow_html=True)

def summarize_text(text: str, max_chars=1200):
    if not text:
        return ""
    text = text[:4000]
    if get_summarizer() is None:
        parts = [p.strip() for p in text.split("\n") if p.strip()]
        return " ".join(parts[:4])[:max_chars]
    summarizer = get_summarizer()
    try:
        out = summarizer(text, max_length=128, min_length=50, do_sample=False)
        return out[0]["summary_text"]
    except Exception:
        return text[:max_chars]

def make_ppt(title="Client Update", bullets=None) -> bytes:
    prs = Presentation()
    slide = prs.slides.add_slide(prs.slide_layouts[0])
    slide.shapes.title.text = title
    if bullets:
        s2 = prs.slides.add_slide(prs.slide_layouts[1])
        s2.shapes.title.text = "Key Points"
        tf = s2.shapes.placeholders[1].text_frame
        tf.clear()
        for b in bullets:
            p = tf.add_paragraph()
            p.text = b
            p.level = 0
    bio = io.BytesIO()
    prs.save(bio)
    bio.seek(0)
    return bio.read()

def make_docx(title="Executive Summary", paragraphs=None) -> bytes:
    doc = Document()
    doc.add_heading(title, 0)
    if paragraphs:
        for p in paragraphs:
            doc.add_paragraph(p)
    bio = io.BytesIO()
    doc.save(bio)
    bio.seek(0)
    return bio.read()

# --------------------------------------------------------------------------------------
# SIDEBAR — DRAPEAUX CLIQUABLES (FR / EN) + THEME + effet visuel
# --------------------------------------------------------------------------------------
import base64
from pathlib import Path
import streamlit as st


# Chemins vers les drapeaux
flag_en_path = Path("src/ui/assets/flag_en.png")
flag_fr_path = Path("src/ui/assets/flag_fr.png")

def _b64(p: Path) -> str:
    """Encode une image en base64 pour affichage HTML"""
    with open(p, "rb") as f:
        return base64.b64encode(f.read()).decode("utf-8")

# Langue (session_state ou URL ?lang=fr)
url_lang = st.query_params.get("lang")
if "lang" not in st.session_state:
    st.session_state["lang"] = url_lang if url_lang in {"en", "fr"} else "en"
else:
    if url_lang in {"en", "fr"} and url_lang != st.session_state["lang"]:
        st.session_state["lang"] = url_lang

def _set_lang(lang: str):
    st.session_state["lang"] = lang
    st.query_params["lang"] = lang
    st.toast("Français activé 🇫🇷" if lang == "fr" else "English enabled 🇬🇧")

# --------------------------------------------------------------------------------------
# CSS pour les drapeaux + effet clic
# --------------------------------------------------------------------------------------
st.sidebar.markdown("""
<style>
.lang-flags {
    display:flex;
    gap:12px;
    align-items:center;
    margin-bottom:10px;
}
.lang-flag img {
    height:36px;
    border-radius:8px;
    box-shadow:0 2px 8px rgba(0,0,0,.18);
    border:2px solid transparent;
    transition:transform 0.2s, border-color 0.2s;
    cursor:pointer;
}
.lang-flag.active img {
    border-color:#4f46e5;
}
.lang-flag img:hover {
    transform:scale(1.07);
}
/* Effet visuel temporaire au clic */
.lang-flag img:active {
    border-color:#2563eb !important;
    box-shadow:0 0 8px rgba(37,99,235,0.6);
    transform:scale(0.97);
}
</style>
""", unsafe_allow_html=True)

# --------------------------------------------------------------------------------------
# HTML cliquable (même fenêtre)
# --------------------------------------------------------------------------------------
lang = st.session_state["lang"]
html_flags = f"""
<div class="lang-flags">
  <a class="lang-flag {'active' if lang=='en' else ''}" href="?lang=en" target="_self" title="English">
    <img src="data:image/png;base64,{_b64(flag_en_path)}" />
  </a>
  <a class="lang-flag {'active' if lang=='fr' else ''}" href="?lang=fr" target="_self" title="Français">
    <img src="data:image/png;base64,{_b64(flag_fr_path)}" />
  </a>
</div>
"""
st.sidebar.markdown("### 🌐 Language / Langue")
st.sidebar.markdown(html_flags, unsafe_allow_html=True)

# --------------------------------------------------------------------------------------
# MODE SOMBRE / CLAIR
# --------------------------------------------------------------------------------------
# --------------------------------------------------------------------------------------
# MODE SOMBRE / CLAIR — unique key to avoid StreamlitDuplicateElementKey
# --------------------------------------------------------------------------------------
dark_mode_key = "ui_dark_mode_toggle_unique"

# Ensure a default state
if "dark_mode" not in st.session_state:
    st.session_state["dark_mode"] = False

dark_mode = st.sidebar.toggle(
    "Dark mode" if st.session_state.get("lang", "en") == "en" else "Mode sombre",
    value=st.session_state["dark_mode"],
    help="Toggle dark/light theme" if st.session_state.get("lang", "en") == "en" else "Basculer clair/sombre",
    key=dark_mode_key,
)

st.session_state["dark_mode"] = dark_mode

apply_theme(THEME_DARK if dark_mode else THEME_LIGHT)

# --------------------------------------------------------------------------------------
# AUTRES PARAMÈTRES
# --------------------------------------------------------------------------------------
st.sidebar.caption("IT-STORM · Innovation & Consulting")

top_k = st.sidebar.slider(
    "Top-K results" if st.session_state.get("lang", "en") == "en" else "Top-K résultats",
    2, 12, 4, 1,
    help=(
        "Number of most similar document chunks retrieved from the vector database "
        "to build the context for each question."
        if st.session_state.get("lang", "en") == "en"
        else "Nombre de segments de documents similaires utilisés pour construire le contexte des réponses."
    ),
)

sim_thresh = st.sidebar.slider(
    "Similarity threshold (distance)" if st.session_state.get("lang", "en") == "en" else "Seuil de similarité (distance)",
    0.0, 1.5, 0.0, 0.05,
    help=(
        "Maximum cosine distance between your query and a document chunk. "
        "Lower values mean stricter matching."
        if st.session_state.get("lang", "en") == "en"
        else "Distance maximale de similarité entre la question et un segment de document. "
             "Plus la valeur est faible, plus la correspondance est stricte."
    ),
)

model_name = st.sidebar.text_input(
    "Embedding model" if st.session_state.get("lang", "en") == "en" else "Modèle d’embedding",
    EMB_MODEL_NAME,
    help=(
        "The model used to transform text into numerical embeddings for semantic search."
        if st.session_state.get("lang", "en") == "en"
        else "Modèle utilisé pour convertir le texte en vecteurs numériques (recherche sémantique)."
    ),
)
if model_name != EMB_MODEL_NAME:
    st.sidebar.warning(
        "This UI uses MiniLM; change in code to switch model safely."
        if st.session_state.get("lang", "en") == "en"
        else "Cette interface utilise MiniLM ; change dans le code pour modifier le modèle en sécurité."
    )

st.sidebar.markdown("---")
st.sidebar.subheader("Diagnostics" if st.session_state.get("lang", "en") == "en" else "Diagnostics")
st.sidebar.markdown(
    "LLM backend: **Local Hugging Face** ✅"
    if st.session_state.get("lang", "en") == "en"
    else "Moteur LLM : **Hugging Face local** ✅"
)
st.sidebar.caption(
    "Auto theme · v2.2 (Local-only, CPU-safe)"
    if st.session_state.get("lang", "en") == "en"
    else "Thème auto · v2.2 (Local uniquement, CPU-safe)"
)

# --------------------------------------------------------------------------------------
# HEADER
# --------------------------------------------------------------------------------------
render_brand_header(api_ok=None, llm_ok=True)

# KPI row
k1, k2, k3, k4 = st.columns(4)
with k1: kpi_card(t("kpi_indexed_docs"), f"{len(list(DATA_RAW.glob('*')))} files")
with k2: kpi_card(t("kpi_chunks_file"), "✅" if (DATA_PROCESSED / "chunks.jsonl").exists() else "❌")
with k3: kpi_card(t("kpi_vector_db"), "✅" if any(VEC_DIR.glob('*')) else "❌")
with k4: kpi_card(t("kpi_output_folder"), "✅" if any(OUT_DIR.glob('*')) else "—")

# --------------------------------------------------------------------------------------
# TABS
# --------------------------------------------------------------------------------------
tab_chat, tab_upload, tab_generate, tab_market = st.tabs(
    [t("tab_chat"), t("tab_upload"), t("tab_generate"), t("tab_market")]
)
render_chatbot()
# ---- TAB 1: CHAT ----
# ---- TAB 1: CHAT ----
with tab_chat:
    st.markdown("### " + t("chat_title"))

    # Conserver top_k côté session pour l’endpoint /chat (optionnel)
    st.session_state["top_k_from_ui"] = top_k

    q = st.text_input(t("chat_input"), key="q_chat_input")
    c1, c2 = st.columns([1, 1])
    do_search = c1.button(t("chat_button"), use_container_width=True, key="btn_chat_search")
    clear_box = c2.button(t("chat_clear"), use_container_width=True, key="btn_chat_clear")

    if clear_box:
        st.session_state.pop("last_chat_result", None)
        st.rerun()

    if do_search and q:
        query = q[:2000] if len(q) > 2000 else q
        if len(q) > 2000:
            st.info(t("chat_question_too_long"))
        with st.spinner(t("chat_spinner")):
            try:
                result = ask_rag(
                    question=query,
                    k=top_k,
                    get_sources_fn=_get_source_names_for_query
                )
                st.session_state["last_chat_result"] = {"q": query, **result}
            except Exception as e:
                st.error(f"{t('chat_error_prefix')} {e}")

    # Affichage du dernier résultat
    last = st.session_state.get("last_chat_result")
    if last:
        st.markdown("#### " + t("chat_question_h"))
        st.write(last["q"])

        st.markdown("#### " + t("chat_answer_h"))
        st.write(last["answer"])

        if last.get("sources"):
            st.markdown("#### " + t("chat_sources_h"))
            st.markdown(", ".join(f"`{s}`" for s in last["sources"]))

        # Suggestions si "Je ne sais pas"
        if last.get("suggestions"):
            st.info(t("chat_suggestions_info"))
            sug_choice = st.radio(
                t("chat_suggestions_label"),
                last["suggestions"],
                key="q_suggestion_radio"
            )
            if st.button(t("chat_suggestions_btn"), key="btn_chat_suggest"):
                with st.spinner(t("chat_spinner")):
                    new_res = ask_rag(
                        question=sug_choice,
                        k=top_k,
                        get_sources_fn=_get_source_names_for_query
                    )
                    st.session_state["last_chat_result"] = {"q": sug_choice, **new_res}
                    st.rerun()

# ---- TAB 2: UPLOAD & INDEX ----
with tab_upload:
    st.markdown("### Upload documents & (re)build index")

    # ✅ Uploader élargi (on garde juste le contrôle d’upload)
    files = st.file_uploader(
        "Upload PDF/DOCX/TXT/MD/PPTX/CSV/XLSX/HTML/JSON",
        type=["pdf", "docx", "txt", "md", "pptx", "csv", "xlsx", "xls", "html", "htm", "json"],
        accept_multiple_files=True
    )

    # ✅ Ligne des 2 premiers boutons
    c1, c2 = st.columns(2)
    if c1.button("⬆️  Save uploads", use_container_width=True) and files:
        saved = save_uploaded_files(files)
        st.success(f"✅ {len(saved)} file(s) saved to `data/raw/`.")

    if c2.button("⚙️  Extract & Chunk", use_container_width=True):
        with st.spinner("Extracting & chunking..."):
            n, outp, stats = extract_and_chunk()
        st.success(f"✅ Created {n} chunks → {outp}")
        st.caption(f"Seen: {stats['seen']} • Processed: {stats['processed']} • Ignored: {stats['ignored']} • By ext: {stats['by_ext']}")

    # ✅ 3e bouton (plein largeur)
    if st.button("🧠  Rebuild Vector Index", use_container_width=True):
        with st.spinner("Encoding & indexing..."):
            total = rebuild_index()
        st.success(f"✅ Indexed {total} chunks into ChromaDB.")

    # Aperçu (optionnel)
    if (DATA_PROCESSED / "chunks.jsonl").exists():
        st.markdown("#### Preview extracted chunks")
        import json, itertools, pandas as pd
        rows = []
        with open(DATA_PROCESSED / "chunks.jsonl", "r", encoding="utf-8") as f:
            for line in itertools.islice(f, 3):
                rows.append(json.loads(line))
        if rows:
            df = pd.DataFrame(rows)
            st.dataframe(df, use_container_width=True, height=200)

# ---- TAB 3: DOCS GENERATION ----
from src.ui.tabs import generate_docs_rag  # put near your other imports
with tab_generate:
    generate_docs_rag.render()

# ---- TAB 4: MARKET WATCH ----
with tab_market:
    market.render()



# --------------------------------------------------------------------------------------
# END OF FILE
# --------------------------------------------------------------------------------------


