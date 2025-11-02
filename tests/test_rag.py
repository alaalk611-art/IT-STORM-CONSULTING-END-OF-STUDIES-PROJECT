import sys
from pathlib import Path

# Ajouter src/ au path
ROOT = Path(__file__).resolve().parents[1]
sys.path.append(str(ROOT))

from src.rag.ingest import run_ingest
from src.rag.chain import build_rag_chain

if __name__ == "__main__":
    print("=== Étape 1: Ingestion des documents ===")
    run_ingest()

    print("\n=== Étape 2: Questions de test ===")
    chain = build_rag_chain(k=4)

    questions = [
        "Donne un résumé du document principal.",
        "Quels sont les objectifs clés mentionnés ?",
        "Quels livrables ou actions concrètes sont prévus ?"
    ]

    for q in questions:
        print("\n--- Question:", q)
        result = chain.invoke(q)
        print("Réponse:\n", result["answer"])
        print("Sources:", result["sources"])
