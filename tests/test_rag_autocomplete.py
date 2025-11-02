import pytest
from src.rag import chain as rag_chain
from src.ui.tabs import generate_docs_rag

def test_autocomplete_rag(monkeypatch):
    """Test unitaire de l'autocomplétion RAG via build_rag_chain et _ask_rag."""
    # 1. Définition d'un LLM factice qui renvoie toujours une réponse prédéfinie.
    class DummyLLM:
        def generate(self, question: str, context: str, max_new_tokens: int = 160) -> str:
            # On peut vérifier que la question contient bien le nom de section ou d'autres éléments ici si besoin.
            return "Réponse de test"  # Réponse prédéfinie attendue

    # 2. Monkey-patch des fonctions critiques pour éviter les dépendances externes.
    # Patch de get_llm pour utiliser le DummyLLM à la place du LLM réel.
    monkeypatch.setattr(rag_chain, "get_llm", lambda *args, **kwargs: DummyLLM())
    # Patch de la classification de requête pour forcer un chemin 'in_domain' (pas d'ambiguïté ni hors sujet).
    monkeypatch.setattr(rag_chain, "_classify_query", lambda query, suggester: "in_domain")
    # Patch de l’index vectoriel pour éviter le chargement de modèles d’embedding.
    class DummyVectorIndex:
        def search(self, query: str, k: int = 4):
            # Retourne un résultat factice de document (texte court) pour simuler le retrieval.
            return [{
                "id": "dummy_doc_1",
                "text": "Contenu factice du document pertinent.",
                "path": "dummy_doc.txt",
                "start": 0,
                "end": 100
            }]
    monkeypatch.setattr(rag_chain.VectorIndex, "from_files",
                        lambda paths, model_name=None: DummyVectorIndex())
    # Patch pour que le chargement de paires QA renvoie une liste vide (pas de QA pairs).
    monkeypatch.setattr(rag_chain, "_load_qa_pairs", lambda paths: [])
    # Patch du suggesteur de QA pour éviter tout calcul (retourne un suggesteur vide).
    monkeypatch.setattr(rag_chain.QASuggester, "build",
                        lambda pairs, model_name=None: rag_chain.QASuggester(pairs=[], model_name=model_name or ""))

    # 3. Construction de la chaîne RAG via la fonction existante.
    chain = rag_chain.build_rag_chain()
    # Vérifie que la chaîne est bien construite et est du bon type.
    assert isinstance(chain, rag_chain.RAGChain)
    
    # 4. Exécution de l'auto-remplissage sur un exemple de section.
    section_name = "Executive Summary"
    contexte_user = "Contexte utilisateur de test"
    resultat = generate_docs_rag._ask_rag(chain, section_name, contexte_user)
    
    # 5. Vérifications :
    # - La réponse retournée correspond exactement à ce que DummyLLM.generate a renvoyé.
    assert resultat == "Réponse de test"
    # - La réponse ne doit pas être vide.
    assert resultat.strip() != ""
