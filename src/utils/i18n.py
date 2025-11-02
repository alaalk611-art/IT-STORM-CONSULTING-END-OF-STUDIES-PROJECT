from __future__ import annotations
import streamlit as st

# ============================================================
# Dictionnaire des traductions FR / EN
# ============================================================
I18N = {
    # Sidebar
    "sidebar.language": {"en": "Language / Langue", "fr": "Langue / Language"},
    "sidebar.dark_mode": {"en": "Dark mode", "fr": "Mode sombre"},
    "sidebar.org_line": {
        "en": "IT-STORM · Innovation & Consulting",
        "fr": "IT-STORM · Innovation & Consulting",
    },
    "sidebar.topk": {"en": "Top-K results", "fr": "Top-K résultats"},
    "sidebar.sim_thresh": {
        "en": "Similarity threshold (distance)",
        "fr": "Seuil de similarité (distance)",
    },
    "sidebar.embedding": {"en": "Embedding model", "fr": "Modèle d’embedding"},
    "sidebar.diagnostics": {"en": "Diagnostics", "fr": "Diagnostics"},
    "sidebar.llm_engine": {"en": "LLM engine", "fr": "Moteur LLM"},

    # Header badges
    "header.indexed_docs": {"en": "Indexed documents", "fr": "Documents indexés"},
    "header.chunks_file": {"en": "Chunks file", "fr": "Fichier de segments"},
    "header.vector_db": {"en": "Vector DB", "fr": "Base vectorielle"},
    "header.export_dir": {"en": "Export folder", "fr": "Dossier d’export"},
    "header.llm_ready": {"en": "LLM (Local HF):", "fr": "LLM (HF local) :"},
    "header.env": {"en": "Env:", "fr": "Env :"},

    # Tabs
    "tab.chat": {"en": "Knowledge Chat", "fr": "Chat Connaissance"},
    "tab.ingest": {"en": "Import & Index", "fr": "Import & Index"},
    "tab.generate": {"en": "Generate Docs", "fr": "Générer des documents"},
    "tab.market": {"en": "Markets", "fr": "Marchés"},
    "tab.rag_en": {"en": "English QA (RAG EN)", "fr": "QA anglais (RAG EN)"},

    # Q&A principale
    "qa.title": {
        "en": "Knowledge Q&A (RAG with LangChain + Local HF)",
        "fr": "Questions / Réponses sur la base de connaissances (RAG avec LangChain et HF local)"
    },
    "qa.ask_placeholder": {
        "en": "Ask a question about your indexed documents",
        "fr": "Posez une question sur vos documents indexés"
    },
    "qa.retrieve": {
        "en": "🔎 Retrieve & Answer",
        "fr": "🔎 Rechercher et répondre"
    },
    "qa.clear": {
        "en": "🧹 Clear",
        "fr": "🧹 Effacer"
    },
    "qa.autotranslate": {
        "en": "🗣️ Auto-translate",
        "fr": "🗣️ Traduction automatique"
    },

    # Génération de documents (RAG EN)
    "gen.title": {
        "en": "Generate Docs (RAG EN) — Smart Autofill + Sources",
        "fr": "Génération de documents (RAG EN) — Remplissage intelligent et sources"
    },
    "gen.how": {
        "en": "💡 How it works",
        "fr": "💡 Fonctionnement"
    },
    "gen.topk": {
        "en": "Top-K context",
        "fr": "Contexte Top-K"
    },
    "gen.init": {
        "en": "⚙️ Initialize RAG EN",
        "fr": "⚙️ Initialiser le module RAG EN"
    },
    "gen.status": {
        "en": "RAG EN status:",
        "fr": "Statut du module RAG EN :"
    },
    "gen.not_init": {
        "en": "not initialized",
        "fr": "non initialisé"
    },
    "gen.opt_ctx": {
        "en": "Optional project context (EN or FR)",
        "fr": "Contexte du projet (facultatif, EN ou FR)"
    },
    "gen.title_doc": {
        "en": "Document title",
        "fr": "Titre du document"
    },
    "gen.client": {
        "en": "Client (optional)",
        "fr": "Client (facultatif)"
    },
    "gen.autofill_all": {
        "en": "✨ Auto-fill ALL",
        "fr": "✨ Remplir tout automatiquement"
    },
    "gen.clear_all": {
        "en": "🧹 Clear ALL",
        "fr": "🧹 Effacer tout"
    },
    "gen.export_docx": {
        "en": "💾 Export DOCX",
        "fr": "💾 Exporter en DOCX"
    },

    # Status génériques
    "status.ready": {"en": "Ready", "fr": "Prêt"},
    "status.local": {"en": "Local", "fr": "Local"},
}


# ============================================================
# Gestion de la langue (session/query)
# ============================================================
def set_lang_from_query():
    """Lit ?lang=fr ou ?lang=en dans l’URL"""
    qp = st.query_params or {}
    lang = qp.get("lang", None)
    if lang in {"en", "fr"}:
        st.session_state["lang"] = lang
    elif "lang" not in st.session_state:
        st.session_state["lang"] = "en"


def get_lang() -> str:
    """Retourne la langue active"""
    return st.session_state.get("lang", "en")


def t(key: str, **fmt) -> str:
    """Renvoie la traduction correspondant à la clé"""
    lang = get_lang()
    entry = I18N.get(key, {})
    text = entry.get(lang) or entry.get("en") or key
    if fmt:
        try:
            text = text.format(**fmt)
        except Exception:
            pass
    return text
