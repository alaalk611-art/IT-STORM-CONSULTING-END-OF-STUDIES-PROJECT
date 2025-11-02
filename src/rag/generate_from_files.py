from __future__ import annotations
from pathlib import Path
from typing import Dict
from src.rag.postprocess import postprocess

# Emplacements préférés (ton repo). On prévoit aussi un fallback sous /mnt/data pour tes tests.
PREFERRED_DIR = Path("data/raw")
FALLBACK_DIR = Path("/mnt/data")

FILES: Dict[str, str] = {
    "Executive Summary": "Executive Summary.txt",
    "Contexte & Objectifs": "Contexte Objectifs.txt",
    "Pain Points": "Pain Points.txt",
    "Architecture Technique": "Architecture Solution.txt",
    "Budget & Effort": "Budget Et Effort.txt",
    "Risques & Atténuations": "Risques Et Attenuations.txt",
    "Roadmap & Jalons": "Roadmap Jalons.txt",
    "Prochaines Étapes": "Prochaines Etapes.txt",
}

def _resolve_path(name: str) -> Path | None:
    fname = FILES[name]
    p1 = PREFERRED_DIR / fname
    if p1.exists():
        return p1
    p2 = FALLBACK_DIR / fname
    if p2.exists():
        return p2
    return None

def generate_from_files() -> Dict[str, str]:
    sections: Dict[str, str] = {}
    for title in FILES:
        path = _resolve_path(title)
        if not path:
            sections[title] = "File not found."
            continue
        raw = path.read_text(encoding="utf-8")
        force_list = title in {"Pain Points", "Risques & Atténuations", "Roadmap & Jalons", "Prochaines Étapes"}
        sections[title] = postprocess(raw, force_list=force_list)
    return sections
# ========= Fin src/rag/generate_from_files.py =========