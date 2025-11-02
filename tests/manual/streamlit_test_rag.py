import sys
from pathlib import Path
import streamlit as st
from src.rag.chain import build_rag_chain
from src.ui.tabs.generate_docs_rag import _ask_rag, DEFAULT_SECTIONS

st.title("📝 Test de génération d'une section (RAG)")

if st.button("⚙️ Initialiser la chaîne RAG"):
    with st.spinner("Chargement de la chaîne RAG, veuillez patienter..."):
        try:
            chain = build_rag_chain()
            st.session_state.rag_chain = chain
            st.success("Chaîne RAG prête ✅")
        except Exception as e:
            st.error(f"Échec de l'initialisation : {e}")
            st.session_state.rag_chain = None

section_choisie = st.selectbox("Section à auto-remplir", list(DEFAULT_SECTIONS.keys()))
contexte_user = st.text_area(
    "Contexte utilisateur (optionnel)",
    placeholder="Indiquez ici un contexte pour guider la génération (facultatif).",
    height=100
)

if st.button("✨ Générer la section"):
    if "rag_chain" not in st.session_state or st.session_state.rag_chain is None:
        st.warning("Veuillez initialiser la chaîne RAG avant de générer du texte.")
    else:
        resultat = _ask_rag(st.session_state.rag_chain, section_choisie, contexte_user)
        st.markdown(f"**Section générée : _{section_choisie}_**")
        st.write(resultat)
