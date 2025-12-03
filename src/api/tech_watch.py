# -*- coding: utf-8 -*-
# ============================================================
# Path: src/api/tech_watch.py
# Module de veille technologique IT-STORM (version "rules-only")
# - Charge les sources YAML
# - Fetch HTML
# - Extract texte brut simple (+ nettoyage bruit menus/cookies)
# - Résumé court & long 100 % règles (regex, phrases filtrées)
# - Tags auto basiques
# - Score qualité + risque login
# - Classement Hot / Trending / Fresh
# - Sauvegarde JSONL
# - API: /tech/watch/refresh & /tech/watch/latest
# ============================================================

from __future__ import annotations
import os
import json
import time
import pathlib
from datetime import datetime
from typing import List, Dict, Any
from urllib.parse import urlparse

import requests
import yaml
from fastapi import APIRouter, HTTPException

router = APIRouter(prefix="/tech", tags=["tech_watch"])

# --- PATHS ---
BASE_DIR = pathlib.Path(__file__).resolve().parents[2]
CONFIG_PATH = BASE_DIR / "config" / "tech_watch_sources.yaml"
DATA_DIR = BASE_DIR / "data" / "tech_watch"

DATA_DIR.mkdir(parents=True, exist_ok=True)

# --- Limite "mode sprint" pour éviter le timeout UI ---
MAX_SOURCES_PER_REFRESH = int(os.getenv("TECH_WATCH_MAX_SOURCES", "40"))

# -----------------------------------------------------------
# LOAD SOURCES
# -----------------------------------------------------------
def _load_sources() -> Dict[str, Any]:
    if not CONFIG_PATH.exists():
        raise FileNotFoundError(f"Config introuvable: {CONFIG_PATH}")

    with open(CONFIG_PATH, "r", encoding="utf-8") as f:
        return yaml.safe_load(f) or {}


# -----------------------------------------------------------
# FETCH URL
# -----------------------------------------------------------
def _fetch_url(url: str, timeout: int = 8) -> str:
    """Récupère le HTML avec un timeout volontairement court (mode veille)."""
    r = requests.get(
        url,
        timeout=timeout,
        headers={
            "User-Agent": "Mozilla/5.0 (TechWatch Bot IT-STORM)",
        },
    )
    r.raise_for_status()
    return r.text


# -----------------------------------------------------------
# EXTRACT TEXT (simple) + nettoyage bruit
# -----------------------------------------------------------
_NOISE_PATTERNS = [
    "toggle navigation",
    "skip to content",
    "skip to main content",
    "sign in",
    "log in",
    "connexion",
    "login",
    "create account",
    "cookies",
    "we use cookies",
    "before you continue",
    "avant d'accéder",
    "for full functionality of this site",
    "enable javascript",
    "your browser does not support",
    "accept x",
    "accept cookies",
    "domain is for sale",
    "est en vente - vosdomaines",
]


def _simple_extract_text(html: str, max_chars: int = 9000) -> str:
    """Retire les balises HTML (simple), puis nettoie le bruit évident."""
    import re

    # suppression scripts/styles
    text = re.sub(r"<script.*?>.*?</script>", " ", html, flags=re.S | re.I)
    text = re.sub(r"<style.*?>.*?</style>", " ", text, flags=re.S | re.I)
    text = re.sub(r"<[^>]+>", " ", text)
    text = re.sub(r"\s+", " ", text)
    text = text.strip()

    text = text[: max_chars * 2]  # on garde un peu plus pour nettoyage
    text = _strip_noise(text)
    return text[:max_chars].strip()


def _strip_noise(text: str) -> str:
    """Supprime un maximum de bruit typique (menus, bannières, domaine à vendre)."""
    import re

    t = text

    low = t.lower()
    # Si on détecte explicitement une page "domaine à vendre",
    # on coupe très court pour ne garder qu'une phrase descriptive.
    if "est en vente - vosdomaines" in low or "domain is for sale" in low:
        # on prend la première phrase seulement
        parts = re.split(r"(?<=[\.\!\?])\s+", t)
        return (parts[0] if parts else t)[:400]

    for pat in _NOISE_PATTERNS:
        # on remplace par un simple point pour couper la phrase
        t = re.sub(pat, ". ", t, flags=re.I)

    # compaction espaces
    t = re.sub(r"\s+", " ", t)
    return t.strip()


# -----------------------------------------------------------
# META (favicon / OG image)
# -----------------------------------------------------------
def _extract_meta(html: str) -> Dict[str, str]:
    """Extrait éventuellement og:image depuis le HTML."""
    import re

    og_image = ""
    m = re.search(
        r'<meta[^>]+property=["\']og:image["\'][^>]+content=["\']([^"\']+)["\']',
        html,
        flags=re.I,
    )
    if m:
        og_image = m.group(1).strip()

    return {"og_image": og_image}


# -----------------------------------------------------------
# HELPERS RÈGLES / RÉSUMÉS
# -----------------------------------------------------------
def _normalize_spaces(t: str) -> str:
    import re
    return re.sub(r"\s+", " ", (t or "").strip())


def _split_sentences(t: str) -> List[str]:
    """Découpe très simplement en phrases."""
    import re

    raw = _normalize_spaces(t)
    if not raw:
        return []
    parts = re.split(r"(?<=[\.!\?…])\s+|\n+", raw)
    return [p.strip() for p in parts if p.strip()]


# phrases à éviter en tête
_BAD_SENTENCE_PREFIXES = [
    "blog |",
    "documentation |",
    "use cases |",
    "announcements |",
    "ecosystem |",
    "before you continue",
    "avant d'accéder",
    "se connecter",
    "sign in",
    "log in",
    "connexion",
]


def _is_good_sentence(s: str) -> bool:
    """Filtre global pour éviter les menus moches et phrases inutiles."""
    import re

    if not s:
        return False

    s_clean = _normalize_spaces(s)
    low = s_clean.lower()

    # éviter phrases trop courtes ou trop longues
    if len(s_clean) < 40:   # ex: "Blog | Apache Airflow ..."
        return False
    if len(s_clean) > 400:
        return False

    # éviter les préfixes type menus / navigation
    for pref in _BAD_SENTENCE_PREFIXES:
        if low.startswith(pref):
            return False

    # éviter les phrases sans espace (un seul mot)
    if " " not in s_clean:
        return False

    # éviter lignes avec trop de '|' (menus)
    if s_clean.count("|") >= 2:
        return False

    # éviter qu'il y ait > 60% de mots en MAJ (menus, titres).
    words = s_clean.split()
    if words:
        upper_words = sum(1 for w in words if len(w) > 2 and w.isupper())
        if upper_words / len(words) > 0.6:
            return False

    # éviter phrases qui ne contiennent que des mots très génériques
    if re.fullmatch(r"[A-Za-z0-9\-\| ]+", s_clean) and len(set(words)) <= 3:
        return False

    return True


def _build_summary_from_text(text: str, max_len: int = 350) -> str:
    """
    Construit un résumé "propre" à partir du texte :
      - découpe en phrases
      - filtre les phrases moches (menus, cookies, etc.)
      - prend les 2–3 premières phrases utiles jusqu'à max_len
    """
    sents = _split_sentences(text)
    good: List[str] = [s for s in sents if _is_good_sentence(s)]

    if not good:
        # fallback ultra simple : tronque le texte brut nettoyé
        return _dummy_summarize(text, max_len=max_len)

    out_parts: List[str] = []
    current_len = 0

    for s in good:
        s2 = s.strip()
        if not s2:
            continue

        # si on dépasse trop, on stoppe
        if current_len + len(s2) > max_len + 80 and out_parts:
            break

        out_parts.append(s2)
        current_len += len(s2)

        # 2 à 3 phrases max
        if len(out_parts) >= 3:
            break

    out = " ".join(out_parts).strip()
    if not out:
        return _dummy_summarize(text, max_len=max_len)

    # On force un point final
    if out and out[-1] not in ".!?…":
        out += "."
    # on s'assure de ne pas dépasser max_len de trop
    if len(out) > max_len:
        out = out[:max_len].rstrip() + "…"
    return out


# -----------------------------------------------------------
# PLACEHOLDER SUMMARY (truncate brut)
# -----------------------------------------------------------
def _dummy_summarize(text: str, max_len: int = 600) -> str:
    t = _normalize_spaces(text)
    if len(t) <= max_len:
        return t
    return t[:max_len].rstrip() + "…"


def _smart_summarize(text: str, max_len: int = 350) -> str:
    """
    Résumé 100 % règles, sans aucun RAG / LLM :
      - Extraction + nettoyage
      - Découpage en phrases
      - Filtrage par regex (_is_good_sentence)
      - 2–3 phrases max, limité à max_len
    """
    if not text:
        return ""
    return _build_summary_from_text(text, max_len=max_len)


# -----------------------------------------------------------
# TAGS AUTOMATIQUES (très simples)
# -----------------------------------------------------------
_KEYWORD_TAGS = {
    "kubernetes": "kubernetes",
    "docker": "docker",
    "spark": "apache-spark",
    "kafka": "apache-kafka",
    "airflow": "apache-airflow",
    "mistral": "mistral-ai",
    "llama": "llama",
    "hugging face": "hugging-face",
    "genai": "genai",
    "rag": "rag",
    "freelance": "freelance",
    "portage": "portage-salarial",
    "devops": "devops",
    "cloud": "cloud",
    "aws": "aws",
    "azure": "azure",
    "gcp": "gcp",
}


def _auto_tags(block_key: str, block_label: str, text: str) -> List[str]:
    txt = (text or "").lower()
    tags = {block_key, block_label}
    for k, tag in _KEYWORD_TAGS.items():
        if k in txt:
            tags.add(tag)
    return sorted(t for t in tags if t)


# -----------------------------------------------------------
# SAVE BATCH JSONL
# -----------------------------------------------------------
def _save_batch(items: List[Dict[str, Any]]) -> str:
    ts = datetime.utcnow().strftime("%Y%m%d_%H%M%S")
    out_path = DATA_DIR / f"tech_watch_{ts}.jsonl"

    with open(out_path, "w", encoding="utf-8") as f:
        for it in items:
            f.write(json.dumps(it, ensure_ascii=False) + "\n")

    return str(out_path)


# -----------------------------------------------------------
# LOAD LATEST JSONL
# -----------------------------------------------------------
def _load_latest(limit: int = 50) -> List[Dict[str, Any]]:
    files = sorted(DATA_DIR.glob("tech_watch_*.jsonl"))
    if not files:
        return []

    latest = files[-1]
    out: List[Dict[str, Any]] = []

    with open(latest, "r", encoding="utf-8") as f:
        for line in f:
            try:
                out.append(json.loads(line))
            except Exception:
                continue

    # Tri par date décroissante brute
    out.sort(key=lambda x: x.get("created_at", ""), reverse=True)
    return out[:limit]


# -----------------------------------------------------------
# SCORING & RANKING
# -----------------------------------------------------------
_BAD_PATTERNS_LOGIN = [
    "avant d'accéder à youtube",
    "before you continue to youtube",
    "we use cookies",
    "sign in",
    "log in",
    "connexion",
    "login",
    "accept cookies",
    "enable javascript",
    "for full functionality of this site",
    "domain is for sale",
    "est en vente - vosdomaines",
]


def _compute_score_and_rank(it: Dict[str, Any]) -> Dict[str, Any]:
    """
    Ajoute score (0-1), risk_login (bool), rank_label (str).

    Logique scoring 2.0 :
    - score basé sur la longueur de texte utile (raw_len)
    - forte pénalisation si page login / cookies / domaine à vendre
    - seuils :
        score >= 0.85  -> 🔥 Hot
        0.60–0.85      -> ⭐ Trending
        sinon          -> 🆕 Fresh
    """
    summary = (it.get("summary") or "").lower()
    raw_len = int(it.get("raw_len") or 0)

    # Qualité basique: longueur de texte utile
    # < 400        => faible
    # 400–6000     => linéaire vers 1.0
    # 6000–15000   => plateau ~1.0
    # > 15000      => légère pénalité (page trop longue / doc complet)
    if raw_len <= 400:
        quality = 0.25
    elif raw_len >= 15000:
        quality = 0.7
    elif raw_len >= 6000:
        quality = 1.0
    else:
        # interpolation linéaire entre 0.4 et 1.0
        quality = max(0.4, min(1.0, raw_len / 6000.0))

    # Risque login/cookies / domaine à vendre
    risk_login = any(p in summary for p in _BAD_PATTERNS_LOGIN)
    if risk_login:
        quality *= 0.3  # on pénalise fortement

    score = max(0.0, min(1.0, quality))

    # Classement Hot / Trending / Fresh
    if score >= 0.85:
        rank_label = "🔥 Hot"
    elif score >= 0.60:
        rank_label = "⭐ Trending"
    else:
        rank_label = "🆕 Fresh"

    it["score"] = round(score, 3)
    it["risk_login"] = bool(risk_login)
    it["rank_label"] = rank_label
    return it


# -----------------------------------------------------------
# API ENDPOINT: Refresh watch
# -----------------------------------------------------------
@router.post("/watch/refresh")
def refresh_watch() -> Dict[str, Any]:
    try:
        cfg = _load_sources()
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

    items: List[Dict[str, Any]] = []
    nb_ok, nb_err = 0, 0
    processed = 0  # compteur global de sources traitées

    # Flag pour savoir si on a tronqué le refresh
    truncated = False

    for block_key, block in cfg.items():
        label = block.get("label", block_key)
        sources = block.get("sources", [])

        for src in sources:
            if processed >= MAX_SOURCES_PER_REFRESH:
                truncated = True
                break

            name = src.get("name")
            url = src.get("url")
            lang = src.get("lang", "en")

            if not url:
                continue

            try:
                html = _fetch_url(url)
                raw_text = _simple_extract_text(html)

                # Résumé principal (rules-only) + résumé court
                full_summary = _smart_summarize(raw_text, max_len=350)
                short_summary = _dummy_summarize(full_summary, max_len=350)

                # Pour compatibilité frontend : même contenu que summary
                tw_summary_2_sent = full_summary

                # Meta images
                meta = _extract_meta(html)
                og_image = meta.get("og_image") or ""

                # Favicon (via domaine)
                parsed = urlparse(url)
                favicon_url = ""
                if parsed.netloc:
                    favicon_url = (
                        f"https://www.google.com/s2/favicons?sz=64&domain={parsed.netloc}"
                    )

                tags = _auto_tags(block_key, label, raw_text)

                item = {
                    "block": block_key,
                    "block_label": label,
                    "source_name": name,
                    "url": url,
                    "lang": lang,
                    "created_at": datetime.utcnow().isoformat() + "Z",
                    "raw_len": len(raw_text),
                    "summary": full_summary,
                    "short_summary": short_summary,
                    "tw_summary_2_sent": tw_summary_2_sent,
                    "og_image": og_image,
                    "favicon_url": favicon_url,
                    "tags": tags,
                }

                # score + rank
                item = _compute_score_and_rank(item)

                items.append(item)
                nb_ok += 1

            except Exception as e:
                items.append(
                    {
                        "block": block_key,
                        "block_label": label,
                        "source_name": name,
                        "url": url,
                        "error": str(e),
                        "created_at": datetime.utcnow().isoformat() + "Z",
                    }
                )
                nb_err += 1

            processed += 1
            time.sleep(0.1)  # Anti-DDoS mais léger

        if processed >= MAX_SOURCES_PER_REFRESH:
            break

    if not items:
        # Rien n'a pu être traité → on évite d'écraser un ancien fichier vide
        return {
            "status": "error",
            "message": "Aucune source traitée (timeouts ou erreurs).",
            "nb_ok": nb_ok,
            "nb_err": nb_err,
            "total": 0,
            "truncated": truncated,
        }

    path = _save_batch(items)

    return {
        "status": "ok",
        "saved_file": path,
        "nb_ok": nb_ok,
        "nb_err": nb_err,
        "total": len(items),
        "truncated": truncated,
        "max_sources": MAX_SOURCES_PER_REFRESH,
    }


# -----------------------------------------------------------
# API ENDPOINT: Get latest watch
# -----------------------------------------------------------
@router.get("/watch/latest")
def get_latest_watch(limit: int = 50) -> Dict[str, Any]:
    # On charge un peu plus large, tri ensuite
    data = _load_latest(limit * 4)

    cleaned: List[Dict[str, Any]] = []
    for it in data:
        # 1) ignorer les erreurs HTTP
        if it.get("error"):
            continue

        # 2) ignorer les pages quasi vides
        if int(it.get("raw_len") or 0) < 200:
            continue

        # 3) s'assurer d'avoir short_summary & score même pour anciens fichiers
        if not it.get("short_summary"):
            it["short_summary"] = _dummy_summarize(it.get("summary", ""), 320)

        # tw_summary_2_sent peut manquer dans les anciens fichiers → pas grave,
        # le frontend retombera sur short_summary / summary.
        it = _compute_score_and_rank(it)
        cleaned.append(it)

    # Tri final : score décroissant, puis date
    cleaned.sort(
        key=lambda x: (x.get("score", 0.0), x.get("created_at", "")),
        reverse=True,
    )

    cleaned = cleaned[:limit]

    return {
        "status": "ok",
        "count": len(cleaned),
        "items": cleaned,
    }
