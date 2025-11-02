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
I18N.update({
    # Chat tab
    "chat_title": {
        "en": "Knowledge Q&A (RAG with LangChain + Local HF)",
        "fr": "Q&R Connaissance (RAG avec LangChain + HF local)",
    },
    "chat_input": {
        "en": "Ask a question about your indexed documents",
        "fr": "Pose une question sur tes documents indexés",
    },
    "chat_button": {
        "en": "🔎 Retrieve & Answer",
        "fr": "🔎 Récupérer & Répondre",
    },
    "chat_clear": {
        "en": "🧹 Clear",
        "fr": "🧹 Effacer",
    },
    "chat_spinner": {
        "en": "Retrieving context & generating answer...",
        "fr": "Récupération du contexte & génération de la réponse…",
    },
    "chat_error_prefix": {
        "en": "RAG chain failed:",
        "fr": "Échec de la chaîne RAG :",
    },
    "chat_question_h": {
        "en": "Question",
        "fr": "Question",
    },
    "chat_answer_h": {
        "en": "Answer",
        "fr": "Réponse",
    },
    "chat_sources_h": {
        "en": "Sources",
        "fr": "Sources",
    },
    "chat_suggestions_info": {
        "en": "I couldn't find a precise answer. Try one of these:",
        "fr": "Je n’ai pas trouvé de réponse précise. Essaie l’une de ces suggestions :",
    },
    "chat_suggestions_label": {
        "en": "Suggestions",
        "fr": "Suggestions",
    },
    "chat_suggestions_btn": {
        "en": "✅ Ask this suggestion",
        "fr": "✅ Poser cette suggestion",
    },
})
I18N.update({
    # ----- Generate Docs tab -----
    "gen_title": {
        "en": "📝 Generate Docs",
        "fr": "📝 Générer des documents",
    },
    "gen_title_label": {
        "en": "Document title",
        "fr": "Titre du document",
    },
    "gen_subtitle_label": {
        "en": "Subtitle",
        "fr": "Sous-titre",
    },
    "gen_author_label": {
        "en": "Author",
        "fr": "Auteur",
    },
    "gen_date_label": {
        "en": "Date",
        "fr": "Date",
    },
    "gen_theme_color": {
        "en": "Theme color",
        "fr": "Couleur du thème",
    },
    "gen_logo": {
        "en": "Logo (PNG/JPG)",
        "fr": "Logo (PNG/JPG)",
    },
    "gen_export_docx": {
        "en": "Export DOCX",
        "fr": "Exporter DOCX",
    },
    "gen_export_pptx": {
        "en": "Export PPTX",
        "fr": "Exporter PPTX",
    },
    "gen_sections_h": {
        "en": "Sections",
        "fr": "Sections",
    },
    "gen_section_title": {
        "en": "Section {n} — Title",
        "fr": "Section {n} — Titre",
    },
    "gen_section_body": {
        "en": "Section {n} — Content",
        "fr": "Section {n} — Contenu",
    },
    "gen_generate_btn": {
        "en": "Generate documents",
        "fr": "Générer les documents",
    },
    "gen_warn_select_format": {
        "en": "Select at least one format.",
        "fr": "Sélectionne au moins un format.",
    },
    "gen_download_docx": {
        "en": "📄 Download DOCX",
        "fr": "📄 Télécharger DOCX",
    },
    "gen_download_pptx": {
        "en": "📊 Download PPTX",
        "fr": "📊 Télécharger PPTX",
    },
    "gen_error_docx": {
        "en": "DOCX error:",
        "fr": "Erreur DOCX :",
    },
    "gen_error_pptx": {
        "en": "PPTX error:",
        "fr": "Erreur PPTX :",
    },
    "gen_section_fallback": {
        "en": "Section",
        "fr": "Section",
    },

    # Placeholders (multilingues)
    "gen_s1_title_ph": {
        "en": "Executive Summary",
        "fr": "Résumé exécutif",
    },
    "gen_s1_body_ph": {
        "en": "• Project objective\n• Key results",
        "fr": "• Objectif du projet\n• Résultats clés",
    },
    "gen_s2_title_ph": {
        "en": "Details & Methodology",
        "fr": "Détails & Méthodologie",
    },
    "gen_s2_body_ph": {
        "en": "• RAG pipeline\n• Local LLM & generation",
        "fr": "• Pipeline RAG\n• LLM & génération locale",
    },
    "gen_s3_title_ph": {
        "en": "Conclusions",
        "fr": "Conclusions",
    },
    "gen_s3_body_ph": {
        "en": "• Learnings\n• Next steps",
        "fr": "• Enseignements\n• Étapes suivantes",
    },
})
# --- i18n: clés dédiées au tab "Generate Docs" (gd.*) ---
GD_I18N = {
    "gd.title_h": {"en": "📝 Generate Docs", "fr": "📝 Générer des documents"},
    "gd.desc": {
        "en": "Create **DOCX** or **PPTX** from a short brief. You can type your own brief, or ask the **local RAG** to propose one.",
        "fr": "Crée des **DOCX** ou **PPTX** à partir d’un court brief. Tu peux écrire ton brief, ou laisser le **RAG local** en proposer un."
    },
    "gd.brief_h": {"en": "1) Brief", "fr": "1) Brief"},
    "gd.title_label": {"en": "Title", "fr": "Titre"},
    "gd.title_default": {"en": "Executive Summary", "fr": "Synthèse exécutive"},
    "gd.source_label": {"en": "Content Source", "fr": "Source du contenu"},
    "gd.source_manual": {"en": "Manual (I will type a brief)", "fr": "Manuel (je saisis un brief)"},
    "gd.source_auto": {"en": "Auto (use RAG to generate brief)", "fr": "Auto (générer un brief avec le RAG)"},
    "gd.manual_label": {"en": "Write your brief (1–2 paragraphs or bullet points)", "fr": "Écris ton brief (1–2 paragraphes ou puces)"},
    "gd.manual_placeholder": {"en": "Context, objectives, approach, results, next steps.", "fr": "Contexte, objectifs, approche, résultats, prochaines étapes."},
    "gd.rag_prompt_label": {"en": "RAG prompt (what should the document summarize?)", "fr": "Prompt RAG (que doit résumer le document ?)"},
    "gd.rag_prompt_default": {"en": "Summarize the current project status and next steps for the client.", "fr": "Résumer l’état du projet et les prochaines étapes pour le client."},
    "gd.rag_topk": {"en": "Top-K (retrieval)", "fr": "Top-K (recherche)"},
    "gd.rag_btn": {"en": "⚙️ Generate brief with RAG", "fr": "⚙️ Générer un brief avec le RAG"},
    "gd.rag_spinner": {"en": "Querying local RAG...", "fr": "Interrogation du RAG local..."},
    "gd.rag_error": {"en": "RAG error: ", "fr": "Erreur RAG : "},
    "gd.rag_success": {"en": "Brief generated from RAG.", "fr": "Brief généré via le RAG."},
    "gd.rag_result_h": {"en": "RAG Result", "fr": "Résultat RAG"},
    "gd.suggestions_h": {"en": "Suggestions:", "fr": "Suggestions :"},
    "gd.sources_prefix": {"en": "Sources: ", "fr": "Sources : "},
    "gd.outputs_h": {"en": "2) Output Options", "fr": "2) Options de sortie"},
    "gd.docx": {"en": "DOCX", "fr": "DOCX"},
    "gd.pptx": {"en": "PPTX", "fr": "PPTX"},
    "gd.tip_both": {"en": "Tip: You can generate both at once.", "fr": "Astuce : tu peux générer les deux en même temps."},
    "gd.preview_h": {"en": "3) Preview & Export", "fr": "3) Aperçu & Export"},
    "gd.preview_info": {"en": "Write a brief on the left, or generate one with RAG to see a preview here.", "fr": "Écris un brief à gauche, ou génère-en un avec le RAG pour voir un aperçu ici."},
    "gd.preview_first_chars": {"en": "Preview (first 1200 chars)", "fr": "Aperçu (premiers 1200 caractères)"},
    "gd.generate_btn": {"en": "🧾 Generate", "fr": "🧾 Générer"},
    "gd.warn_select_format": {"en": "Select at least one output format (DOCX/PPTX).", "fr": "Sélectionne au moins un format de sortie (DOCX/PPTX)."},
    "gd.success_files": {"en": "Files generated.", "fr": "Fichiers générés."},
    "gd.gen_error": {"en": "Generation error: ", "fr": "Erreur de génération : "},
    "gd.sources_h": {"en": "Sources", "fr": "Sources"},
    "gd.pptx_title_default": {"en": "Client Update", "fr": "Mise à jour client"},
}
I18N.update({
    # Chat tab labels
    "chat_button":  {"en": "🔎 Retrieve & Answer", "fr": "🔎 Récupérer & Répondre"},
    "chat_clear":   {"en": "🧹 Clear",              "fr": "🧹 Effacer"},
    "chat_spinner": {"en": "Retrieving context & generating answer…",
                     "fr": "Récupération du contexte & génération de la réponse…"},
    "chat_question_h": {"en": "Question", "fr": "Question"},
    "chat_answer_h":   {"en": "Answer",   "fr": "Réponse"},
    "chat_sources_h":  {"en": "Sources",  "fr": "Sources"},
})

# Appliquer les clés du tab Generate Docs uniquement
I18N.update(GD_I18N)

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
