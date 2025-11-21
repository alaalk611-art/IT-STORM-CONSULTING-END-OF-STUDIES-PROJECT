# -*- coding: utf-8 -*-
from __future__ import annotations
import os, sys

ROOT_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if ROOT_DIR not in sys.path:
    sys.path.insert(0, ROOT_DIR)

from src.qa_router import route_question

def ask(q: str):
    print("=" * 80)
    print("Q:", q)
    ans = route_question(q)
    print("R:", ans)

if __name__ == "__main__":
    ask("Qu'est-ce que le portage salarial chez IT STORM ?")      # cas 1: QA si question existe
    ask("Explique IT STORM en quelques phrases")                  # cas 2: RAG
    ask("portage")                                                # cas 3: mot-clé -> SUGGEST
    ask("Quelle est la capitale de l'Australie ?")                # cas 4: hors périmètre
