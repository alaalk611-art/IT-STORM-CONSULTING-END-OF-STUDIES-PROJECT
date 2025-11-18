# -*- coding: utf-8 -*-
"""
Script: build_itstorm_txt.py
But:
  - Lire data/raw/itstorm_full.jsonl (généré par scrape_itstorm_v2.py)
  - Générer un fichier texte unique data/raw/itstorm.txt
    structuré par sections, prêt pour ingestion RAG.

Usage :
  (.venv) python scripts/build_itstorm_txt.py
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from typing import List

INPUT_JSONL = Path("data/raw/itstorm_full.jsonl")
OUTPUT_TXT = Path("data/raw/itstorm.txt")


@dataclass
class Section:
    id: str
    url: str
    page_title: str
    section_title: str
    section_level: int
    text: str
    source: str


def load_sections(path: Path) -> List[Section]:
    sections: List[Section] = []
    with path.open("r", encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            obj = json.loads(line)
            sections.append(
                Section(
                    id=obj.get("id", ""),
                    url=obj.get("url", ""),
                    page_title=obj.get("page_title", ""),
                    section_title=obj.get("section_title", ""),
                    section_level=int(obj.get("section_level", 0)),
                    text=obj.get("text", ""),
                    source=obj.get("source", ""),
                )
            )
    return sections


def build_txt(sections: List[Section]) -> str:
    # Tri : par URL, puis par niveau de section (0 = page entière), puis par id
    sections_sorted = sorted(
        sections,
        key=lambda s: (s.url, s.section_level, s.id),
    )

    blocks: List[str] = []

    for s in sections_sorted:
        if s.section_title == "(page entière)":
            title_line = f"### PAGE : {s.page_title or s.url}"
        else:
            title_line = f"### SECTION : {s.section_title}"

        header = [
            title_line,
            f"URL: {s.url}",
            f"NIVEAU: {s.section_level}",
            "",
        ]
        body = s.text.strip()

        blocks.append("\n".join(header) + body + "\n")

    # Séparateur clair entre les blocs
    return "\n\n-----\n\n".join(blocks)


def main() -> None:
    if not INPUT_JSONL.exists():
        raise SystemExit(f"Fichier introuvable: {INPUT_JSONL}")

    sections = load_sections(INPUT_JSONL)
    print(f"[i] Sections chargées: {len(sections)}")

    content = build_txt(sections)
    OUTPUT_TXT.parent.mkdir(parents=True, exist_ok=True)
    OUTPUT_TXT.write_text(content, encoding="utf-8")
    print(f"[✓] Fichier texte généré: {OUTPUT_TXT}")


if __name__ == "__main__":
    main()
