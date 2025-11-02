import sys
from pathlib import Path

# Ajoute le dossier racine du projet à sys.path
sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from src.rag.chain import build_rag_chain
from src.ui.tabs.generate_docs_rag import _ask_rag, DEFAULT_SECTIONS

def main():
    print("Initialisation de la chaîne RAG...")
    try:
        chain = build_rag_chain()
    except Exception as e:
        print(f"Erreur lors de l'initialisation de la chaîne RAG : {e}")
        return
    print("✅ Chaîne RAG initialisée avec succès.\n")

    contexte_utilisateur = "Exemple de contexte : entreprise Retail, migration cloud en cours."
    sections_a_tester = ["Executive Summary", "Contexte & Objectifs"]

    for section in sections_a_tester:
        print(f"=== Section : {section} ===")
        texte_genere = _ask_rag(chain, section, contexte_utilisateur)
        print(texte_genere)
        print("\n" + "-"*40 + "\n")

if __name__ == "__main__":
    main()
