# -*- coding: utf-8 -*-
# src/app.py — Entrée simple qui appelle UNIQUEMENT le RAG strict (zéro hallucination)

import sys

try:
    from src.rag_brain import smart_rag_answer
except Exception as e:
    print(f"[ERREUR] Chargement RAG: {e}")
    sys.exit(1)

def ask(q: str):
    res = smart_rag_answer(q)
    print("\n🔎 Question:", q)
    print("✅ Réponse:", res["answer"])
    print("📚 Sources:", ", ".join(res["sources"]) if res["sources"] else "—")
    print("🔒 Confiance:", res["confidence"], "| Qualité:", res["quality"])

if __name__ == "__main__":
    # Mode CLI: python src/app.py "ta question"
    if len(sys.argv) > 1:
        q = " ".join(sys.argv[1:])
    else:
        q = input("Ta question: ").strip() or "Qu’est-ce qu’IT-STORM ?"
    ask(q)
