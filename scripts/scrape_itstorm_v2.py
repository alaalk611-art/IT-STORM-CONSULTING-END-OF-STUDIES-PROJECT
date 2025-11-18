# -*- coding: utf-8 -*-
"""
Script: scrape_itstorm_v2.py
But:
  - Récupérer un maximum de texte utile sur it-storm.fr
  - Pages ciblées: accueil, portage salarial, portage commercial, nos offres,
    simulateur, à propos + toutes les autres pages internes trouvées.
  - Produit un JSONL prêt à ingérer dans ton RAG.

Usage (depuis la racine du projet) :
  (.venv) python scripts/scrape_itstorm_v2.py
"""

from __future__ import annotations

import json
import time
from collections import deque
from dataclasses import dataclass, asdict
from pathlib import Path
from typing import List, Dict, Any, Optional
from urllib.parse import urljoin, urlparse, urldefrag

import requests
from bs4 import BeautifulSoup, Tag, NavigableString


# =========================
# Config de base
# =========================

# Pages clés (celles de tes captures d’écran)
SEED_URLS = [
    "https://it-storm.fr/",
    "https://it-storm.fr/?page_id=6122",          # Qu'est-ce que le Portage Salarial ?
    "https://it-storm.fr/?page_id=6137",          # Qu'est-ce que le Portage Commercial ?
    "https://it-storm.fr/?page_id=1179",          # À propos
    "https://it-storm.fr/?stm_service=nos-offres",  # Nos offres
    "https://it-storm.fr/?stm_service=project-insurances",  # Simulez vos revenus
]

START_URL = "https://it-storm.fr/"
ALLOWED_DOMAINS = {"it-storm.fr", "www.it-storm.fr"}

MAX_PAGES = 100        # le site est petit, 100 = large marge
REQUEST_DELAY = 1.0    # secondes entre requêtes

OUTPUT_PATH = Path("data/raw/itstorm_full.jsonl")


# =========================
# Modèle de données
# =========================

@dataclass
class SectionRecord:
    id: str
    url: str
    page_title: str
    section_title: str
    section_level: int
    text: str
    source: str = "it-storm.fr"


# =========================
# Helpers URL
# =========================

def normalize_url(base_url: str, href: str) -> Optional[str]:
    """Construit une URL absolue nettoyée (sans fragment), limitée au domaine autorisé."""
    if not href:
        return None

    href = href.strip()
    low = href.lower()
    if low.startswith(("mailto:", "tel:", "javascript:", "#")):
        return None

    full = urljoin(base_url, href)
    full, _ = urldefrag(full)

    parsed = urlparse(full)
    if parsed.scheme not in ("http", "https"):
        return None
    if parsed.netloc not in ALLOWED_DOMAINS:
        return None

    # normalisation simple (on enlève juste le slash final)
    if full.endswith("/"):
        full = full[:-1]

    return full


def clean_text(text: str) -> str:
    """Nettoie le texte: supprime les espaces multiples, trims."""
    if not text:
        return ""
    return " ".join(text.split())


def pick_main_node(soup: BeautifulSoup) -> Tag:
    """
    Essaie de trouver le bloc principal de contenu:
    - <main>
    - id in {'main', 'primary', 'content'}
    - sinon <body>
    """
    main = soup.find("main")
    if main:
        return main

    for cid in ("main", "primary", "content"):
        node = soup.find(id=cid)
        if node:
            return node

    return soup.body or soup


# =========================
# Extraction par page
# =========================

def extract_sections_from_page(soup: BeautifulSoup, url: str) -> List[SectionRecord]:
    records: List[SectionRecord] = []

    page_title = ""
    if soup.title and soup.title.string:
        page_title = clean_text(soup.title.string)

    root = pick_main_node(soup)

    # 0) Record "page entière"
    page_text = clean_text(root.get_text(separator=" ", strip=True))
    if page_text:
        records.append(
            SectionRecord(
                id="",  # rempli plus tard
                url=url,
                page_title=page_title,
                section_title="(page entière)",
                section_level=0,
                text=page_text,
            )
        )

    # 1) Records par section (h1/h2/h3)
    headings: List[Tag] = root.find_all(["h1", "h2", "h3"])
    if not headings:
        return records

    for h in headings:
        level = int(h.name[1])
        raw_title = clean_text(h.get_text(separator=" ", strip=True)) or "(sans titre)"

        content_parts: List[str] = []

        for sibling in h.next_siblings:
            if isinstance(sibling, NavigableString):
                t = clean_text(str(sibling))
                if t:
                    content_parts.append(t)
                continue

            if isinstance(sibling, Tag):
                if sibling.name in ["h1", "h2", "h3"]:
                    # prochain titre de même ou plus haut niveau => fin de la section
                    next_level = int(sibling.name[1])
                    if next_level <= level:
                        break
                    break

                if sibling.name in ["p", "li", "span", "div"]:
                    t = clean_text(sibling.get_text(separator=" ", strip=True))
                    if t:
                        content_parts.append(t)

        # Heuristique: sur la home, les KPI ont un titre "0" et le vrai libellé est dans le contenu.
        section_title = raw_title
        if (len(raw_title) <= 3) and content_parts:
            # si le titre est très court (genre "0" ou "10%"), on utilise le 1er texte comme titre
            first = content_parts[0]
            if len(first) > len(raw_title):
                section_title = first
                content_parts = content_parts[1:]

        full_text = clean_text(" ".join(content_parts))
        if not full_text:
            continue

        records.append(
            SectionRecord(
                id="",
                url=url,
                page_title=page_title,
                section_title=section_title,
                section_level=level,
                text=full_text,
            )
        )

    return records


# =========================
# Crawler principal
# =========================

def crawl_itstorm() -> List[SectionRecord]:
    visited: set[str] = set()
    queue: deque[str] = deque()

    # URLs de départ: home + pages clés
    for u in [START_URL] + SEED_URLS:
        u_norm = normalize_url(START_URL, u)
        if u_norm and u_norm not in queue:
            queue.append(u_norm)

    all_sections: List[SectionRecord] = []

    session = requests.Session()
    session.headers.update({
        "User-Agent": "Mozilla/5.0 (compatible; ITStormCrawler/2.0)"
    })

    while queue and len(visited) < MAX_PAGES:
        url = queue.popleft()
        if not url or url in visited:
            continue
        visited.add(url)

        print(f"[+] GET {url}")
        try:
            resp = session.get(url, timeout=20)
        except Exception as e:
            print(f"[!] Erreur requête sur {url}: {e}")
            continue

        ctype = resp.headers.get("Content-Type", "")
        if resp.status_code != 200 or "text/html" not in ctype:
            print(f"    Status {resp.status_code}, type={ctype}, skip.")
            continue

        soup = BeautifulSoup(resp.text, "html.parser")

        # 1) extraction des sections (page + h1/h2/h3)
        page_sections = extract_sections_from_page(soup, url)
        print(f"    -> {len(page_sections)} sections trouvées")
        all_sections.extend(page_sections)

        # 2) découverte de nouveaux liens internes
        for a in soup.find_all("a", href=True):
            nxt = normalize_url(url, a["href"])
            if not nxt:
                continue
            if nxt not in visited and nxt not in queue:
                queue.append(nxt)

        time.sleep(REQUEST_DELAY)

    # Numéroter les sections
    for idx, rec in enumerate(all_sections, start=1):
        rec.id = f"itstorm_{idx:04d}"

    print(f"[✓] Pages visitées: {len(visited)}")
    return all_sections


# =========================
# Sauvegarde JSONL
# =========================

def save_as_jsonl(sections: List[SectionRecord], output_path: Path) -> None:
    output_path.parent.mkdir(parents=True, exist_ok=True)
    with output_path.open("w", encoding="utf-8") as f:
        for rec in sections:
            f.write(json.dumps(asdict(rec), ensure_ascii=False) + "\n")
    print(f"[✓] Fichier écrit: {output_path} ({len(sections)} sections)")


def main() -> None:
    print("=== CRAWL IT-STORM (v2) ===")
    sections = crawl_itstorm()
    save_as_jsonl(sections, OUTPUT_PATH)


if __name__ == "__main__":
    main()
