# tools/qa_cli_pretty.py
# Expose: answer_from_cli_backend(question: str) -> str
from __future__ import annotations

import os, sys
from pathlib import Path
from typing import List, Optional

# --- rendre le projet importable (src/...) ---
_THIS = os.path.abspath(__file__)
_TOOLS = os.path.dirname(_THIS)
_ROOT = os.path.dirname(_TOOLS)
if _ROOT not in sys.path:
    sys.path.insert(0, _ROOT)
# ---------------------------------------------

from src.rag.chain import build_rag_chain  # même chaîne que qa_cli.py

BANNER = """
========================================
  QA CLI — Intelligent Copilot (assisté)
  Pose ta question.
  Si elle est incomplète/ambiguë :
    → Je propose UNE suggestion à la fois
    → J'attends "o" (oui) / "n" (non)
    → Entrée vide = quitter
========================================
""".strip()


# ---------------------------
# Helpers d'affichage
# ---------------------------
def _format_sources_plain(sources: List[dict]) -> str:
    """Affiche 'Source : (file.txt)' ou 'Sources : (f1.txt, f2.txt)'."""
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


def _is_out_of_scope(q: str) -> bool:
    """Heuristique 'hors-contexte IT-STORM' si rien d'IT-storm-esque n'apparaît."""
    qn = (q or "").lower()
    it_terms = [
        "it storm", "it-storm", "itstorm", "stormcopilot", "consulting",
        "data", "données", "pipeline", "qualité", "cloud", "kubernetes",
        "docker", "rag", "ia", "ia générative", "ml", "machine learning",
        "devops",
    ]
    return not any(t in qn for t in it_terms)


# ---------------------------
# Backend principal (importable)
# ---------------------------
_chain = None  # cache


def _get_chain():
    global _chain
    if _chain is None:
        # même paramétrage que qa_cli.py pour garantir un comportement identique
        _chain = build_rag_chain(k=4)
    return _chain


def answer_from_cli_backend(question: str) -> str:
    """
    Logique identique à qa_cli.py :
      - Si réponse directe connue : retour immédiat (avec sources).
      - Sinon : on propose des reformulations. (format 'SUGGEST:' pour intégration UI)
      - Si hors-contexte : message explicite domaine IT-STORM uniquement.
    NOTE: Cette fonction est *non interactive* (pas de [o/n]). Pour le CLI interactif,
          utilise le main() ci-dessous.
    """
    q = (question or "").strip()
    if not q:
        return "Posez une question."

    chain = _get_chain()

    # 1) Essai direct (QA lookup / RAG)
    try:
        res = chain.invoke(q)
    except Exception as e:
        # En cas d'erreur de chaîne, on échoue en douceur
        return f"Je ne sais pas. (backend indisponible: {e})"

    ans = (res or {}).get("answer", "")
    sources = (res or {}).get("sources", [])

    # Réponse directe trouvée
    if ans and ans.lower() != "je ne sais pas":
        return f"{ans}\n\n{_format_sources_plain(sources)}"

    # 2) Suggestions si pas de réponse
    suggestions = []
    try:
        suggestions = chain.suggest_questions(q, topn=5) or []
    except Exception:
        suggestions = []

    if suggestions:
        # Format neutre pour UI : la bulle peut détecter "SUGGEST:" et afficher des boutons Oui/Non.
        # On propose une SEULE suggestion à la fois (la première), comme dans qa_cli.py.
        sug = suggestions[0]
        # On encode également la réponse associée pour validation ultérieure côté UI si besoin.
        # Format :
        # SUGGEST:<question_suggérée>\nSOURCE:<fichier>\nIF_YES_ANSWER:<réponse_prête>
        lines = [
            "SUGGEST:" + str(getattr(sug, "q_raw", "")),
            "SOURCE:" + Path(getattr(sug, "path", "inconnu")).name,
            "IF_YES_ANSWER:" + str(getattr(sug, "a_raw", "Je ne sais pas")),
            # UI côté Streamlit : afficher la question suggérée avec boutons [Oui] [Non].
            # - Oui  -> afficher IF_YES_ANSWER + SOURCE
            # - Non  -> appeler à nouveau answer_from_cli_backend(question) pour forcer la suggestion suivante,
            #           ou bien la bulle peut décider d'afficher toutes les suggestions restantes.
        ]
        return "\n".join(lines)

    # 3) Hors-contexte explicite si rien de pertinent
    if _is_out_of_scope(q):
        return (
            "Ce chat répond uniquement aux questions liées à IT-STORM "
            "(services, data, IA, cloud, projets, entreprise)."
        )

    # 4) Par défaut : pas de réponse
    return f"Je ne sais pas.\n\n{_format_sources_plain(sources)}"


# ---------------------------
# CLI interactif (o/n) — même UX que qa_cli.py
# ---------------------------
def _ask_yes_no_or_quit(prompt: str) -> Optional[bool]:
    """
    Demande o/n. Retourne True (oui), False (non), None (quitter = entrée vide).
    """
    while True:
        try:
            ans = input(f"{prompt} [o/n] > ").strip().lower()
        except (EOFError, KeyboardInterrupt):
            return None
        if ans == "":
            return None  # quitter
        if ans in ("o", "oui", "y", "yes"):
            return True
        if ans in ("n", "non", "no"):
            return False
        print("Réponds par o (oui) / n (non), ou vide pour quitter.")


def main():
    chain = _get_chain()
    print(BANNER)

    while True:
        try:
            q = input("\nEntrez votre question (vide pour quitter) > ").strip()
        except (EOFError, KeyboardInterrupt):
            print("\nBye.")
            break

        if not q:
            print("Bye.")
            break

        # Réponse directe
        try:
            res = chain.invoke(q)
        except Exception as e:
            print(f"\n[ERREUR backend] {e}\n")
            continue

        ans = (res or {}).get("answer", "")
        sources = (res or {}).get("sources", [])

        if ans and ans.lower() != "je ne sais pas":
            print(f"\nQ: {q}\n")
            print(f"Answer: {ans}\n")
            print(_format_sources_plain(sources))
            print("\n" + "-" * 40)
            continue

        # Proposer des reformulations (une à la fois) avec validation
        try:
            suggestions = chain.suggest_questions(q, topn=5) or []
        except Exception:
            suggestions = []

        if not suggestions:
            if _is_out_of_scope(q):
                print(
                    "\nAnswer: Ce chat répond uniquement aux questions liées à IT-STORM "
                    "(services, data, IA, cloud, projets, entreprise).\n"
                )
            else:
                print(f"\nQ: {q}\n")
                print("Answer: Je ne sais pas\n")
                print(_format_sources_plain(sources))
            print("\n" + "-" * 40)
            continue

        accepted = False
        for sug in suggestions:
            yn = _ask_yes_no_or_quit(f'Tu veux dire : « {sug.q_raw} » ?')
            if yn is None:
                print("\nBye.")
                return
            if yn is True:
                print(f"\nQ: {q}\n")
                print(f"Précision confirmée → « {sug.q_raw} »\n")
                print(f"Answer: {sug.a_raw}\n")
                print(f"Source : ({Path(sug.path).name})\n")
                print("-" * 40)
                accepted = True
                break

        if not accepted:
            if _is_out_of_scope(q):
                print(
                    "\nAnswer: Ce chat répond uniquement aux questions liées à IT-STORM "
                    "(services, data, IA, cloud, projets, entreprise).\n"
                )
            else:
                print(f"\nQ: {q}\n")
                print("Answer: Je ne sais pas\n")
                print(_format_sources_plain(sources))
            print("\n" + "-" * 40)


if __name__ == "__main__":
    main()
