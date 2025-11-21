# scripts/scrape_itstorm_clean.py
# Scraping propre du site https://it-storm.fr/
# - Crawl toutes les pages internes
# - Extrait le texte principal (sans menus / footer / scripts)
# - Filtre un minimum le bruit
# - Sauvegarde en JSONL + TXT pour le RAG

import requests
from bs4 import BeautifulSoup
from urllib.parse import urljoin, urlparse
import re
import json
from collections import deque
from pathlib import Path

BASE_URL = "https://it-storm.fr/"
DOMAIN = urlparse(BASE_URL).netloc

# Dossier de sortie
DATA_DIR = Path("data/raw")
DATA_DIR.mkdir(parents=True, exist_ok=True)
JSONL_PATH = DATA_DIR / "itstorm_clean.jsonl"
TXT_PATH = DATA_DIR / "itstorm_clean.txt"

HEADERS = {
    "User-Agent": "Mozilla/5.0 (compatible; ITSTORM-RAG-SCRAPER/1.0)"
}

# Patterns pour filtrer certaines URLs inutiles
URL_EXCLUDE_PATTERNS = [
    r"/wp-json",
    r"/wp-content",
    r"/wp-includes",
    r"/feed",
    r"/tag/",
    r"/category/",
    r"/author/",
    r"\?s=",
]

# Phrases ou morceaux de texte clairement inutiles à filtrer
TEXT_EXCLUDE_PATTERNS = [
    r"All rights reserved",
    r"Mentions légales",
    r"Politique de confidentialité",
    r"©",
]

def is_internal_url(url: str) -> bool:
    try:
        parsed = urlparse(url)
        if not parsed.netloc:
            return True
        return parsed.netloc == DOMAIN
    except Exception:
        return False

def should_exclude_url(url: str) -> bool:
    low = url.lower()
    for pat in URL_EXCLUDE_PATTERNS:
        if re.search(pat, low):
            return True
    return False

def fetch(url: str) -> str:
    print(f"↪ GET {url}")
    resp = requests.get(url, headers=HEADERS, timeout=15)
    resp.raise_for_status()
    return resp.text

def clean_html_to_text(html: str) -> str:
    soup = BeautifulSoup(html, "html.parser")

    # Remove obvious noise
    for tag in soup(["script", "style", "noscript", "iframe"]):
        tag.decompose()

    for tag in soup.find_all(["header", "footer", "nav", "aside", "form"]):
        tag.decompose()

    # Option : essayer de viser <main> ou le contenu central si présent
    main = soup.find("main")
    if main:
        root = main
    else:
        # fallback : body
        root = soup.body or soup

    # Extraire texte brut
    text = root.get_text(separator="\n")
    text = re.sub(r"\r", "\n", text)
    lines = [l.strip() for l in text.split("\n")]
    lines = [l for l in lines if l]  # remove empty

    # Filtrer encore un peu le bruit
    cleaned_lines = []
    for l in lines:
        # Trop court = souvent menu ou bouton
        if len(l) < 10:
            continue
        # Trop 'technique' (tel, email, etc.) → garder éventuellement
        if re.match(r"^\+?\d[\d\s\-\./]{5,}$", l):
            continue
        if "cookies" in l.lower():
            continue
        # Exclure certaines phrases globales
        if any(re.search(pat, l, flags=re.IGNORECASE) for pat in TEXT_EXCLUDE_PATTERNS):
            continue
        cleaned_lines.append(l)

    # Fusionner en paragraphes
    out = "\n".join(cleaned_lines)
    # Normaliser espaces
    out = re.sub(r"\n{2,}", "\n\n", out)
    out = re.sub(r"\s{2,}", " ", out)
    return out.strip()

def crawl_site(start_url: str, max_pages: int = 50):
    visited = set()
    queue = deque([start_url])
    pages = []

    while queue and len(visited) < max_pages:
        url = queue.popleft()
        if url in visited:
            continue
        if not is_internal_url(url) or should_exclude_url(url):
            continue
        visited.add(url)

        try:
            html = fetch(url)
        except Exception as e:
            print(f"⚠️ Erreur fetch {url}: {e}")
            continue

        try:
            text = clean_html_to_text(html)
        except Exception as e:
            print(f"⚠️ Erreur parsing {url}: {e}")
            continue

        if not text or len(text.split()) < 30:
            print(f"   → Contenu trop faible, on ignore.")
        else:
            print(f"   → {len(text.split())} mots extraits.")
            pages.append({"url": url, "text": text})

        # Découverte des nouveaux liens
        soup = BeautifulSoup(html, "html.parser")
        for a in soup.find_all("a", href=True):
            href = a["href"]
            full = urljoin(url, href)
            if is_internal_url(full) and not should_exclude_url(full) and full not in visited:
                queue.append(full)

    return pages

def save_jsonl(pages):
    with JSONL_PATH.open("w", encoding="utf-8") as f:
        for p in pages:
            f.write(json.dumps(p, ensure_ascii=False) + "\n")
    print(f"✅ Sauvé en JSONL: {JSONL_PATH} ({len(pages)} pages)")

def save_txt(pages):
    # On construit un gros texte RAG-friendly
    parts = []
    for p in pages:
        parts.append(f"### URL: {p['url']}\n\n{p['text']}\n")
    all_text = "\n\n-----\n\n".join(parts)
    with TXT_PATH.open("w", encoding="utf-8") as f:
        f.write(all_text)
    print(f"✅ Sauvé en TXT: {TXT_PATH} (~{len(all_text.split())} mots)")

def main():
    print(f"🚀 Crawl de {BASE_URL}")
    pages = crawl_site(BASE_URL, max_pages=50)
    print(f"\n📄 {len(pages)} pages valides récupérées.")
    save_jsonl(pages)
    save_txt(pages)

if __name__ == "__main__":
    main()
