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
import math
from datetime import datetime, timezone
from typing import List, Dict, Any
from urllib.parse import urlparse

import requests
import yaml
from fastapi import APIRouter, HTTPException

# -----------------------------------------------------------
# ROUTER FASTAPI
# -----------------------------------------------------------
router = APIRouter(prefix="/tech", tags=["tech_watch"])

# --- PATHS ---
BASE_DIR = pathlib.Path(__file__).resolve().parents[2]
CONFIG_PATH = BASE_DIR / "config" / "tech_watch_sources.yaml"
DATA_DIR = BASE_DIR / "data" / "tech_watch"
DATA_DIR.mkdir(parents=True, exist_ok=True)

# --- Limite "mode sprint" pour éviter le timeout UI ---
MAX_SOURCES_PER_REFRESH = int(os.getenv("TECH_WATCH_MAX_SOURCES", "40"))


# ===========================================================
# LOAD SOURCES
# ===========================================================
def _load_sources() -> Dict[str, Any]:
    if not CONFIG_PATH.exists():
        raise FileNotFoundError(f"Config introuvable: {CONFIG_PATH}")

    with open(CONFIG_PATH, "r", encoding="utf-8") as f:
        return yaml.safe_load(f) or {}


# ===========================================================
# FETCH URL
# ===========================================================
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


# ===========================================================
# EXTRACT TEXT (simple) + nettoyage bruit
# ===========================================================
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

    # enlève les balises restantes
    text = re.sub(r"<[^>]+>", " ", text)

    # normalise les espaces
    text = re.sub(r"\s+", " ", text)
    text = text.strip()

    # filtre quelques patterns bruyants
    lower = text.lower()
    for p in _NOISE_PATTERNS:
        if p in lower:
            # si la page est surtout du bruit login/cookies, on coupe très court
            text = text[:1200]
            break

    if len(text) > max_chars:
        text = text[:max_chars]

    return text


# ===========================================================
# SUMMARIES
# ===========================================================
def _dummy_summarize(text: str, max_len: int = 320) -> str:
    text = (text or "").strip()
    if len(text) <= max_len:
        return text
    return text[:max_len].rsplit(" ", 1)[0] + "…"


def _smart_summarize(raw_text: str, max_len: int = 480) -> str:
    """
    Résumé "rules-only" :
    - split en phrases
    - on garde celles qui contiennent des mots-clés intéressants
    - on coupe à max_len
    """
    import re

    raw = (raw_text or "").strip()
    if not raw:
        return ""

    # split phrases
    sentences = re.split(r"(?<=[.!?])\s+", raw)
    if len(sentences) <= 3:
        return _dummy_summarize(raw, max_len=max_len)

    # filtre simple par mots-clés tech / data / cloud
    KEYWORDS = [
        "cloud",
        "kubernetes",
        "docker",
        "data",
        "machine learning",
        "deep learning",
        "ai ",
        "intelligence artificielle",
        "devops",
        "cicd",
        "freelance",
        "portage",
    ]

    selected: List[str] = []
    for s in sentences:
        lower = s.lower()
        if any(k in lower for k in KEYWORDS):
            selected.append(s.strip())

    if not selected:
        selected = sentences[:4]

    summary = " ".join(selected)
    return _dummy_summarize(summary, max_len=max_len)


# ===========================================================
# META + TAGGING
# ===========================================================
def _extract_meta(html: str) -> Dict[str, Any]:
    import re

    meta: Dict[str, Any] = {}
    og_image = re.search(
        r'<meta[^>]+property=["\']og:image["\'][^>]+content=["\']([^"\']+)["\']',
        html,
        flags=re.I,
    )
    if og_image:
        meta["og_image"] = og_image.group(1)
    return meta


def _auto_tags(block_key: str, label: str, text: str) -> List[str]:
    tags: List[str] = []
    t = (text or "").lower()

    def add_if(cond: bool, tag: str):
        if cond and tag not in tags:
            tags.append(tag)

    # block principal
    add_if(True, block_key)

    # quelques tags basiques
    add_if("kubernetes" in t or "docker" in t, "kubernetes")
    add_if("spark" in t or "hadoop" in t, "apache-spark")
    add_if("kafka" in t, "apache-kafka")
    add_if("airflow" in t, "apache-airflow")
    add_if("devops" in t or "cicd" in t, "devops")
    add_if("mistral" in t or "llama" in t or "hugging face" in t, "genai")
    add_if("rag" in t or "retrieval augmented generation" in t, "rag")
    add_if("portage" in t or "freelance" in t, "portage-salarial")

    return tags


# ===========================================================
# STORAGE JSONL
# ===========================================================
def _save_batch(items: List[Dict[str, Any]]) -> str:
    ts = datetime.utcnow().strftime("%Y%m%d_%H%M%S")
    path = DATA_DIR / f"tech_watch_{ts}.jsonl"
    with open(path, "w", encoding="utf-8") as f:
        for it in items:
            f.write(json.dumps(it, ensure_ascii=False) + "\n")
    return str(path)


def _load_latest(limit: int = 200) -> List[Dict[str, Any]]:
    files = sorted(DATA_DIR.glob("tech_watch_*.jsonl"), reverse=True)
    out: List[Dict[str, Any]] = []

    for path in files:
        try:
            with open(path, "r", encoding="utf-8") as f:
                for line in f:
                    if not line.strip():
                        continue
                    out.append(json.loads(line))
                    if len(out) >= limit:
                        break
        except Exception:
            continue
        if len(out) >= limit:
            break

    # tri par date décroissante
    out.sort(key=lambda x: x.get("created_at", ""), reverse=True)
    return out[:limit]


# ===========================================================
# SCORING & RANKING
# ===========================================================
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
    Ajoute score (0-1), risk_login (bool).
    Le rank_label final sera ajusté plus finement par enrich_items_with_rank().
    """
    summary = (it.get("summary") or "").lower()
    raw_len = int(it.get("raw_len") or 0)

    if raw_len <= 400:
        quality = 0.25
    elif raw_len >= 15000:
        quality = 0.7
    elif raw_len >= 6000:
        quality = 1.0
    else:
        quality = max(0.4, min(1.0, raw_len / 6000.0))

    risk_login = any(p in summary for p in _BAD_PATTERNS_LOGIN)
    if risk_login:
        quality *= 0.3

    score = max(0.0, min(1.0, quality))

    it["score"] = round(score, 3)
    it["risk_login"] = bool(risk_login)
    # rank_label sera recalculé par enrich_items_with_rank(...)
    return it


# --------- Temps & ranking Hot / Trending / Fresh ---------
def _parse_dt_safe(value: str) -> datetime:
    """Parse une date ISO (avec ou sans 'Z') ou renvoie maintenant en UTC si problème."""
    if not value:
        return datetime.now(timezone.utc)

    v = str(value)
    try:
        if v.endswith("Z"):
            v = v[:-1]
        if "T" not in v and " " in v:
            v = v.replace(" ", "T")
        dt = datetime.fromisoformat(v)
    except Exception:
        return datetime.now(timezone.utc)

    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    else:
        dt = dt.astimezone(timezone.utc)
    return dt


def _compute_time_scores(it: Dict[str, Any], now: datetime) -> Dict[str, float]:
    """
    Calcule score_24h, score_48h et freshness à partir du score de base + âge.
    """
    try:
        base = float(it.get("score") or 0.0)
    except Exception:
        base = 0.0

    dt = _parse_dt_safe(it.get("created_at") or it.get("published_at") or "")
    age_hours = max((now - dt).total_seconds() / 3600.0, 0.0)

    # Décroissance exponentielle
    decay_24h = math.exp(-age_hours / 24.0)
    decay_48h = math.exp(-age_hours / 48.0)
    freshness = math.exp(-age_hours / 72.0)

    score_24h = base * decay_24h
    score_48h = base * decay_48h

    return {
        "score_24h": score_24h,
        "score_48h": score_48h,
        "freshness": freshness,
    }


def enrich_items_with_rank(items: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    """
    Ajoute : score_24h, score_48h, freshness, rank_label à chaque item.

    Règle :
      - tri par score_24h décroissant
      - top 25% -> 🔥 Hot
      - suivants 25% -> ⭐ Trending
      - reste -> 🆕 Fresh
      - si item très vieux / très faible -> forcé en Fresh
    """
    now = datetime.now(timezone.utc)

    for it in items:
        scores = _compute_time_scores(it, now)
        it.update(scores)

    items_sorted = sorted(items, key=lambda x: x.get("score_24h", 0.0), reverse=True)
    n = len(items_sorted)
    if n == 0:
        return items_sorted

    n_hot = max(1, int(0.25 * n))
    n_trend = max(1, int(0.25 * n))

    for idx, it in enumerate(items_sorted):
        s24 = float(it.get("score_24h", 0.0))
        fresh = float(it.get("freshness", 0.0))

        label = "🆕 Fresh"
        if s24 <= 0.01 and fresh < 0.2:
            label = "🆕 Fresh"
        else:
            if idx < n_hot:
                label = "🔥 Hot"
            elif idx < n_hot + n_trend:
                label = "⭐ Trending"
            else:
                label = "🆕 Fresh"

        it["rank_label"] = label

    return items_sorted


# ===========================================================
# API ENDPOINT: Refresh watch
# ===========================================================
@router.post("/watch/refresh")
def refresh_watch() -> Dict[str, Any]:
    start = time.time()
    try:
        cfg = _load_sources()
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

    items: List[Dict[str, Any]] = []
    nb_ok, nb_err = 0, 0
    processed = 0
    truncated = False

    # nombre total de sources (pour les KPI)
    sources_total = 0
    for _block_key, block in cfg.items():
        sources_total += len(block.get("sources", []) or [])

    for block_key, block in cfg.items():
        label = block.get("label", block_key)
        sources = block.get("sources", []) or []

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

                full_summary = _smart_summarize(raw_text, max_len=350)
                short_summary = _dummy_summarize(full_summary, max_len=350)
                tw_summary_2_sent = full_summary

                meta = _extract_meta(html)
                og_image = meta.get("og_image") or ""

                parsed = urlparse(url)
                favicon_url = ""
                if parsed.netloc:
                    favicon_url = f"https://www.google.com/s2/favicons?sz=64&domain={parsed.netloc}"

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

                item = _compute_score_and_rank(item)
                items.append(item)
                nb_ok += 1

            except Exception as e:  # noqa: F841
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
            time.sleep(0.1)

        if processed >= MAX_SOURCES_PER_REFRESH:
            break

    if not items:
        return {
            "status": "error",
            "message": "Aucune source traitée (timeouts ou erreurs).",
            "nb_ok": nb_ok,
            "nb_err": nb_err,
            "total": 0,
            "truncated": truncated,
            "sources_total": sources_total,
            "sources_ok": nb_ok,
            "sources_error": nb_err,
            "duration": round(time.time() - start, 2),
        }

    path = _save_batch(items)
    duration = round(time.time() - start, 2)

    return {
        "status": "ok",
        "saved_file": path,
        "nb_ok": nb_ok,
        "nb_err": nb_err,
        "total": len(items),
        "truncated": truncated,
        "max_sources": MAX_SOURCES_PER_REFRESH,
        "sources_total": sources_total,
        "sources_ok": nb_ok,
        "sources_error": nb_err,
        "duration": duration,
    }


# ===========================================================
# API ENDPOINT: Get latest watch
# ===========================================================
@router.get("/watch/latest")
def get_latest_watch(limit: int = 50) -> Dict[str, Any]:
    data = _load_latest(limit * 4)

    cleaned: List[Dict[str, Any]] = []
    for it in data:
        if it.get("error"):
            continue

        if int(it.get("raw_len") or 0) < 200:
            continue

        if not it.get("short_summary"):
            it["short_summary"] = _dummy_summarize(it.get("summary", ""), 320)

        it = _compute_score_and_rank(it)
        cleaned.append(it)

    # 🔥 Nouveau : enrichir avec scores temporels + Hot / Trending / Fresh
    cleaned = enrich_items_with_rank(cleaned)
    cleaned = cleaned[:limit]

    return {
        "status": "ok",
        "count": len(cleaned),
        "items": cleaned,
    }
