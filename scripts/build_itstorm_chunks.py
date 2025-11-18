# -*- coding: utf-8 -*-
"""
Script: build_itstorm_chunks.py
But:
  - Lire data/raw/itstorm_full.jsonl (sortie de scrape_itstorm_v2.py)
  - Découper chaque section en petits chunks ~paragraphe
  - Sauvegarder dans data/raw/itstorm_chunks.jsonl

Usage :
  (.venv) python scripts/build_itstorm_chunks.py
"""

from __future__ import annotations

import json
import re
from dataclasses import dataclass
from pathlib import Path
from typing import List, Dict, Any

INPUT_JSONL = Path("data/raw/itstorm_full.jsonl")
OUTPUT_JSONL = Path("data/raw/itstorm_chunks.jsonl")

# taille cible d'un chunk (en caractères)
CHUNK_SIZE_CHARS = 700
CHUNK_OVERLAP_CHARS = 80  # petit overlap pour éviter de couper une idée en deux


@dataclass
class Section:
    id: str
    url: str
    page_title: str
    section_title: str
    section_level: int
    text: str
    source: str


def _load_sections(path: Path) -> List[Section]:
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
                    source=obj.get("source", "it-storm.fr"),
                )
            )
    return sections


def _split_into_sentences(text: str) -> List[str]:
    """
    Split grossier en 'phrases' en coupant après . ? !
    C'est suffisant pour faire des chunks propres.
    """
    text = " ".join(text.split())  # normalise espaces
    if not text:
        return []

    # On découpe sur un espace après . ? ! (avec ou sans guillemets)
    pattern = re.compile(r"(?<=[\.\!\?])\s+")
    parts = pattern.split(text)

    sentences = [p.strip() for p in parts if p.strip()]
    return sentences


def _chunk_text(text: str, target_size: int = CHUNK_SIZE_CHARS) -> List[str]:
    """
    Construit des chunks en accumulant des phrases jusqu'à atteindre ~target_size.
    """
    sentences = _split_into_sentences(text)
    if not sentences:
        return []

    chunks: List[str] = []
    current: List[str] = []
    current_len = 0

    for sent in sentences:
        sent_len = len(sent)
        # si on est déjà bien rempli, on ouvre un nouveau chunk
        if current and current_len + 1 + sent_len > target_size:
            chunks.append(" ".join(current))
            # on commence un nouveau chunk avec la phrase courante
            current = [sent]
            current_len = sent_len
        else:
            current.append(sent)
            current_len += (1 + sent_len) if current_len > 0 else sent_len

    if current:
        chunks.append(" ".join(current))

    # ajout d'overlap simple (facultatif)
    if CHUNK_OVERLAP_CHARS > 0 and len(chunks) > 1:
        overlapped: List[str] = []
        for i, ch in enumerate(chunks):
            if i == 0:
                overlapped.append(ch)
                continue
            prev = overlapped[-1]
            # on prend la fin du chunk précédent comme overlap
            tail = prev[-CHUNK_OVERLAP_CHARS:]
            merged = tail + " " + ch
            overlapped.append(merged)
        chunks = overlapped

    return chunks


def build_chunks(sections: List[Section]) -> List[Dict[str, Any]]:
    """
    Transforme les Section (page entière / section) en petits chunks.
    """
    all_chunks: List[Dict[str, Any]] = []
    global_idx = 1

    for sec in sections:
        text = sec.text.strip()
        if not text:
            continue

        # petit nettoyage: on évite de trop découper les très petits textes
        if len(text) <= CHUNK_SIZE_CHARS:
            chunks = [text]
        else:
            chunks = _chunk_text(text, CHUNK_SIZE_CHARS)

        for i, ch in enumerate(chunks):
            chunk_id = f"{sec.id}_c{i+1}" if sec.id else f"chunk_{global_idx:04d}"
            record = {
                "id": chunk_id,
                "url": sec.url,
                "page_title": sec.page_title,
                "section_title": sec.section_title,
                "section_level": sec.section_level,
                "chunk_index": i + 1,
                "text": ch.strip(),
                "source": sec.source,
            }
            all_chunks.append(record)
            global_idx += 1

    return all_chunks


def main() -> None:
    if not INPUT_JSONL.exists():
        raise SystemExit(f"Fichier introuvable: {INPUT_JSONL}")

    sections = _load_sections(INPUT_JSONL)
    print(f"[i] Sections chargées: {len(sections)}")

    chunk_records = build_chunks(sections)
    print(f"[i] Chunks générés: {len(chunk_records)}")

    OUTPUT_JSONL.parent.mkdir(parents=True, exist_ok=True)
    with OUTPUT_JSONL.open("w", encoding="utf-8") as f:
        for rec in chunk_records:
            f.write(json.dumps(rec, ensure_ascii=False) + "\n")

    print(f"[✓] Fichier écrit: {OUTPUT_JSONL}")


if __name__ == "__main__":
    main()
