# rag_test.py — vérif rapide du RAG strict
from src.rag_brain import smart_rag_answer

tests = [
    "Qu’est-ce qu’IT-STORM ?",
    "Quels bénéfices concrets du RAG pour un client du secteur énergie ?",
    "Comment déployer rapidement une première version du RAG en local ?",
    "Quelle est la politique salariale détaillée d’IT-STORM ?",
]

for q in tests:
    r = smart_rag_answer(q)
    print("\nQ:", q)
    print("Answer:", r["answer"])
    print("Confidence:", r["confidence"], "Quality:", r["quality"])
    print("Sources:", r["sources"])
