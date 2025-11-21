
# scripts/scrape_itstorm_site.py
# -*- coding: utf-8 -*-

import os
import re
import requests
from bs4 import BeautifulSoup

# -------------------------------------------------------------------------
# URLs du site IT STORM à scraper
# -------------------------------------------------------------------------
URLS = [
    "https://it-storm.fr/",
    "https://it-storm.fr/?page_id=6122",
    "https://it-storm.fr/?page_id=6137",
    "https://it-storm.fr/?stm_service=nos-offres",
    "https://it-storm.fr/?stm_service=project-insurances",
    "https://it-storm.fr/?page_id=1179",
]

# Dossier de sortie du fichier texte (adapté à ta structure)
BASE_DIR = r"C:\Users\ALA BEN LAKHAL\Desktop\intelligent_copilot IT-STORM\data\raw"
OUT_FILE = os.path.join(BASE_DIR, "itstorm_site.txt")


def clean_line(text: str) -> str:
    """Nettoie une ligne brute (espaces, tab, etc.)."""
    if not text:
        return ""
    text = re.sub(r"\s+", " ", text)
    return text.strip()


def is_noise(line: str) -> bool:
    """Filtre les lignes sans intérêt (menus, boutons, etc.)."""
    if not line:
        return True

    low = line.lower()

    # Lignes trop courtes
    if len(line.split()) < 4:
        return True

    # Quelques motifs de bruit fréquents (menus, boutons)
    noise_patterns = [
        "accueil",
        "contact",
        "mentions légales",
        "tous droits réservés",
        "copyright",
        "politique de confidentialité",
        "consentement",
        "cookies",
        "en savoir plus",
        "plus d'infos",
        "voir plus",
        "suivez-nous",
        "linkedin",
        "facebook",
        "twitter",
        "instagram",
        "tiktok",
        "©",
    ]
    for pat in noise_patterns:
        if pat in low:
            return True

    return False


def scrape_url(url: str) -> str:
    """Scrape une URL et retourne un bloc de texte nettoyé."""
    print(f"🔎 Scraping: {url}")
    headers = {
        "User-Agent": "Mozilla/5.0 (compatible; ITStormScraper/1.0; +https://it-storm.fr/)"
    }
    resp = requests.get(url, headers=headers, timeout=15)
    resp.raise_for_status()

    soup = BeautifulSoup(resp.text, "html.parser")

    # On enlève les scripts / styles / nav / footer si possible
    for tag in soup(["script", "style", "nav", "footer", "header"]):
        tag.decompose()

    raw_text = soup.get_text(separator="\n")
    lines = [clean_line(l) for l in raw_text.split("\n")]
    lines = [l for l in lines if l]           # non vides
    lines = [l for l in lines if not is_noise(l)]

    # Déduplication grossière en gardant l'ordre
    seen = set()
    cleaned_lines = []
    for l in lines:
        if l not in seen:
            seen.add(l)
            cleaned_lines.append(l)

    block = "\n".join(cleaned_lines).strip()
    return block


def main():
    os.makedirs(BASE_DIR, exist_ok=True)

    all_blocks = []
    for url in URLS:
        try:
            block = scrape_url(url)
            if block:
                all_blocks.append(f"### URL: {url}\n\n{block}\n")
        except Exception as e:
            print(f"⚠️ Erreur sur {url} : {e}")

    if not all_blocks:
        print("❌ Aucun contenu récupéré, fichier non écrit.")
        return

    final_text = "\n\n" + ("\n\n" + ("-" * 80) + "\n\n").join(all_blocks) + "\n"

    with open(OUT_FILE, "w", encoding="utf-8") as f:
        f.write(final_text)

    print(f"\n✅ Fichier écrit : {OUT_FILE}")
    print("Tu peux maintenant le réindexer avec reindex_txt_file ou ton script reindex_itstorm.py.")


if __name__ == "__main__":
    main()
