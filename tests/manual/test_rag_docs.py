# tests/manual/test_rag_docs.py
from __future__ import annotations
import os
import sys
import time
from pathlib import Path
from typing import List, Tuple

# Permet d'importer "src/..." même si on exécute depuis la racine
ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

# Import de ta chaîne
from src.rag.chain import build_rag_chain

# Valeurs par défaut; surchargées si déjà présentes dans ton .env
os.environ.setdefault("LLM_MODEL", "google/flan-t5-base")
os.environ.setdefault("LLM_DEVICE", "-1")
os.environ.setdefault("EMBEDDING_MODEL", "sentence-transformers/all-MiniLM-L6-v2")
os.environ.setdefault("RAG_TOPK", "4")
os.environ.setdefault("RAG_MAX_CONTEXT_CHARS", "1300")

OUTPUTS_DIR = ROOT / "outputs"
OUTPUT_FILE = OUTPUTS_DIR / "summary_tests.txt"

TESTS: List[Tuple[str, str]] = [
    ("EXECUTIVE SUMMARY", "Executive Summary of the IT STORM Proof of Concept"),
    ("TECHNICAL ARCHITECTURE", "Describe the technical architecture of the RAG solution"),
    ("BUDGET AND EFFORT", "Summarize the estimated budget and effort for the project"),
    ("RISKS", "List the main project risks and how they are mitigated"),
    ("ROADMAP", "Summarize the project roadmap and main milestones"),
    ("NEXT STEPS", "Summarize the next operational steps after the POC"),
]

def count_sentences(text: str) -> int:
    """Compte grossièrement les phrases qui se terminent par ., !, ?"""
    import re
    sents = [s.strip() for s in re.split(r"(?<=[\.\!\?])\s+", text) if s.strip()]
    return len(sents)

def ends_with_period(text: str) -> bool:
    return text.rstrip().endswith((".", "!", "?"))

def run():
    t0 = time.time()
    OUTPUTS_DIR.mkdir(parents=True, exist_ok=True)

    # Construire la chaîne RAG
    chain = build_rag_chain()

    lines = []
    lines.append("=" * 78)
    lines.append("IT STORM RAG — Automated Test Run")
    lines.append(f"Model: {os.environ.get('LLM_MODEL')} | Device: {os.environ.get('LLM_DEVICE')}")
    lines.append(f"Embedding: {os.environ.get('EMBEDDING_MODEL')} | TopK: {os.environ.get('RAG_TOPK')}")
    lines.append(f"MaxContextChars: {os.environ.get('RAG_MAX_CONTEXT_CHARS')}")
    lines.append("=" * 78)
    lines.append("")

    # Lancer les tests
    for title, prompt in TESTS:
        start = time.time()
        try:
            out = chain.generate_en(prompt)
        except Exception as e:
            out = f"[ERROR] Exception during generation: {e}"

        duration = time.time() - start

        # Vérifications simples
        n_sents = count_sentences(out)
        ok_five = (n_sents == 5)
        ok_end = ends_with_period(out)

        status = "PASS" if (ok_five and ok_end) else "WARN"
        lines.append(f"--- {title} ---")
        lines.append(f"Prompt   : {prompt}")
        lines.append(f"Duration : {duration:.2f}s")
        lines.append(f"Checks   : sentences={n_sents} | ends_with_period={ok_end} -> {status}")
        lines.append("Output   :")
        lines.append(out)
        lines.append("")

    total = time.time() - t0
    lines.append("=" * 78)
    lines.append(f"Done in {total:.2f}s")
    lines.append("=" * 78)

    # Ecrire le fichier
    OUTPUT_FILE.write_text("\n".join(lines), encoding="utf-8")

    # Echo console
    print("\n".join(lines))
    print(f"\nSaved to: {OUTPUT_FILE}")

if __name__ == "__main__":
    run()
