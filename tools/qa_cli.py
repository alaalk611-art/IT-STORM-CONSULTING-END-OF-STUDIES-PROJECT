# tools/qa_cli.py
from __future__ import annotations
import os, sys
from pathlib import Path

# --- rendre le projet importable (src/...) ---
_THIS = os.path.abspath(__file__)
_TOOLS = os.path.dirname(_THIS)
_ROOT = os.path.dirname(_TOOLS)
if _ROOT not in sys.path:
    sys.path.insert(0, _ROOT)
# ---------------------------------------------

from src.rag.chain import build_rag_chain

BANNER = """
========================================
  QA CLI — Intelligent Copilot (assisté)
  Pose ta question.
  Si elle est incomplète/ambiguë :
    → Je propose UNE suggestion à la fois
    → J'attends "o" (oui) / "n" (non)
    → Entrée vide = quitter
========================================
"""

def _format_sources_plain(sources):
    """Affiche 'Source : (file.txt)' ou 'Sources : (f1.txt, f2.txt)'. Pas de JSON."""
    if not sources:
        return "Source : (aucune)"
    names = []
    for s in sources:
        p = s.get("path")
        if p:
            names.append(Path(p).name)
    names = sorted(set(names))
    if not names:
        return "Source : (inconnue)"
    if len(names) == 1:
        return f"Source : ({names[0]})"
    return f"Sources : ({', '.join(names)})"

def _ask_yes_no_or_quit(prompt: str):
    """
    Demande o/n. Retourne True (oui), False (non), None (quitter = entrée vide).
    """
    while True:
        ans = input(f"{prompt} [o/n] > ").strip().lower()
        if ans == "":
            return None  # quitter
        if ans in ("o", "oui", "y", "yes"):
            return True
        if ans in ("n", "non", "no"):
            return False
        print("Réponds par o (oui) / n (non), ou vide pour quitter.")

def main():
    chain = build_rag_chain(k=4)
    print(BANNER)

    while True:
        try:
            q = input("Entrez votre question (vide pour quitter) > ").strip()
        except (EOFError, KeyboardInterrupt):
            print("\nBye.")
            break

        if not q:
            print("Bye.")
            break

        try:
            # 1) Essai direct (QA lookup / RAG)
            res = chain.invoke(q)
            ans = res.get("answer", "")
            sources = res.get("sources", [])

            if ans.lower() != "je ne sais pas":
                print(f"\nQ: {q}\n")
                print(f"Answer: {ans}\n")
                print(_format_sources_plain(sources))
                print("\n" + "-"*40 + "\n")
                continue

            # 2) Sinon : suggestions une par une, avec confirmation explicite
            suggestions = chain.suggest_questions(q, topn=5)
            if not suggestions:
                print(f"\nQ: {q}\n")
                print("Answer: Je ne sais pas\n")
                print(_format_sources_plain(sources))
                print("\n" + "-"*40 + "\n")
                continue

            accepted = False
            for sug in suggestions:
                # IMPORTANT : on attend OBLIGATOIREMENT oui/non avant de répondre
                yn = _ask_yes_no_or_quit(f'Tu veux dire : « {sug.q_raw} » ?')
                if yn is None:
                    print("\nBye.")
                    return
                if yn is True:
                    # On génère/retourne la réponse seulement après "oui"
                    print(f"\nQ: {q}\n")
                    print(f"Précision confirmée → « {sug.q_raw} »\n")
                    print(f"Answer: {sug.a_raw}\n")
                    print(f"Source : ({Path(sug.path).name})\n")
                    print("-" * 40 + "\n")
                    accepted = True
                    break
                # si "non", on propose la suggestion suivante (et on RE-attend oui/non)

            if not accepted:
                print(f"\nQ: {q}\n")
                print("Answer: Je ne sais pas\n")
                print(_format_sources_plain(sources))
                print("\n" + "-"*40 + "\n")

        except Exception as e:
            print(f"\n[ERREUR] {e}\n")

if __name__ == "__main__":
    main()
