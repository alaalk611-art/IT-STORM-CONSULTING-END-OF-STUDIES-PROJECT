# -*- coding: utf-8 -*-
# ============================================================
# Path: src/api/tech_watch.py
# Module de veille technologique IT-STORM (version "rules-only")
# - Charge les sources YAML
# - Fetch HTML (encodage robuste anti-mojibake)
# - Extract texte brut simple (+ nettoyage bruit menus/cookies)
# - Résumé court & long 100 % règles (regex, phrases filtrées)
# - Tags auto basiques
# - Score qualité + risque login
# - Classement Hot / Trending / Fresh (basé sur published_at si dispo)
# - Filtre anti-boilerplate/menu
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
from collections import defaultdict

import requests
import yaml
from fastapi import APIRouter, HTTPException

# -----------------------------------------------------------
# ROUTER FASTAPI
# -----------------------------------------------------------
router = APIRouter(prefix="/tech", tags=["tech_watch"])

# --- PATHS ---
BASE_DIR = pathlib.Path(__file__).resolve().parents[2]
CONFIG_PATH = BASE_DIR / "config" / "tech_watch.yaml"
DATA_DIR = BASE_DIR / "data" / "tech_watch"
DATA_DIR.mkdir(parents=True, exist_ok=True)

# --- Limite "mode sprint" pour éviter le timeout UI ---
MAX_SOURCES_PER_REFRESH = int(os.getenv("TECH_WATCH_MAX_SOURCES", "40"))

TIER_WEIGHTS = {0: 1.0, 1: 0.85, 2: 0.60, 3: 0.40}


def _is_enabled(x: dict, default: bool = True) -> bool:
    v = x.get("enabled", default)
    return bool(v) if v is not None else default


def _normalize_cfg(cfg: dict) -> dict:
    """Injecte defaults + filtre enabled + enrichit tier/weight si absent."""
    meta = cfg.get("meta", {}) if isinstance(cfg, dict) else {}
    defaults = (meta.get("defaults") or {}) if isinstance(meta, dict) else {}
    default_enabled = bool(defaults.get("enabled", True))
    default_tier = int(defaults.get("tier", 2))

    out = {}
    for block_key, block in (cfg or {}).items():
        if block_key == "meta":
            continue
        if not isinstance(block, dict):
            continue

        # catégorie enabled ?
        if not _is_enabled(block, default=True):
            continue

        sources = []
        for src in (block.get("sources") or []):
            if not isinstance(src, dict):
                continue
            if not _is_enabled(src, default=default_enabled):
                continue

            tier = int(src.get("tier", default_tier))
            weight = float(src.get("weight", TIER_WEIGHTS.get(tier, 0.60)))

            src2 = dict(src)
            src2["tier"] = tier
            src2["weight"] = weight
            sources.append(src2)

        if sources:
            block2 = dict(block)
            block2["sources"] = sources
            out[block_key] = block2

    return {"meta": meta, **out}


def _iter_sources_sorted(cfg: dict) -> list[tuple[str, dict, dict]]:
    """Retourne une liste (block_key, block, src) triée tier/weight décroissant."""
    triples = []
    for block_key, block in cfg.items():
        if block_key == "meta":
            continue
        for src in (block.get("sources") or []):
            triples.append((block_key, block, src))

    # Tier ASC (0 d'abord), weight DESC
    triples.sort(key=lambda t: (int(t[2].get("tier", 2)), -float(t[2].get("weight", 0.6))))
    return triples


# ===========================================================
# LOAD SOURCES
# ===========================================================
def _load_sources() -> Dict[str, Any]:
    if not CONFIG_PATH.exists():
        raise FileNotFoundError(f"Config introuvable: {CONFIG_PATH}")

    with open(CONFIG_PATH, "r", encoding="utf-8") as f:
        raw = yaml.safe_load(f) or {}
    # ✅ normalise + filtre enabled + injecte tier/weight
    return _normalize_cfg(raw)


# ===========================================================
# FETCH URL (encodage robuste)
# ===========================================================
def _fetch_url(url: str, timeout: int = 10) -> str:
    """
    Fetch HTML avec encodage robuste :
    - requests tente parfois un mauvais encoding → mojibake (Â, ðŸ, etc.)
    - on force resp.encoding = resp.apparent_encoding quand dispo
    """
    r = requests.get(
        url,
        timeout=timeout,
        allow_redirects=True,
        headers={
            "User-Agent": "Mozilla/5.0 (TechWatch Bot IT-STORM)",
            "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
            "Accept-Language": "en-US,en;q=0.9,fr-FR,fr;q=0.8",
        },
    )
    r.raise_for_status()

    # ✅ Fix encoding (évite Â / ðŸ / etc.)
    try:
        if r.apparent_encoding:
            r.encoding = r.apparent_encoding
    except Exception:
        pass

    html = r.text or ""

    # ✅ Heuristique anti-mojibake (sans dépendances)
    bad_markers = ("Â", "ðŸ", "â€™", "â€œ", "â€", "�")
    if any(m in html for m in bad_markers):
        try:
            repaired = html.encode("latin-1", errors="ignore").decode("utf-8", errors="ignore")
            if sum(m in repaired for m in bad_markers) < sum(m in html for m in bad_markers):
                html = repaired
        except Exception:
            pass

    return html


# ===========================================================
# PUBLISHED_AT (vrai timestamp article) + parsing
# ===========================================================
def _extract_published_at(html: str) -> str:
    """
    Tente d'extraire une date de publication réelle depuis :
    - meta property="article:published_time"
    - meta name="pubdate"/"publishdate"/"date"/"DC.date.issued"
    - <time datetime="...">
    - JSON-LD datePublished
    Retourne une string ISO si trouvé, sinon "".
    """
    import re

    if not html:
        return ""

    # 1) OpenGraph article:published_time
    m = re.search(
        r'<meta[^>]+property=["\']article:published_time["\'][^>]+content=["\']([^"\']+)["\']',
        html,
        flags=re.I,
    )
    if m:
        return m.group(1).strip()

    # 2) meta name="pubdate" / "date" / "publishdate"
    m = re.search(
        r'<meta[^>]+name=["\'](?:pubdate|publishdate|date|DC\.date\.issued)["\'][^>]+content=["\']([^"\']+)["\']',
        html,
        flags=re.I,
    )
    if m:
        return m.group(1).strip()

    # 3) <time datetime="...">
    m = re.search(r"<time[^>]+datetime=['\"]([^'\"]+)['\"]", html, flags=re.I)
    if m:
        return m.group(1).strip()

    # 4) JSON-LD "datePublished":"..."
    m = re.search(r'"datePublished"\s*:\s*"([^"]+)"', html, flags=re.I)
    if m:
        return m.group(1).strip()

    return ""


def _parse_dt_or_empty(value: str) -> datetime | None:
    """Parse ISO / RFC-ish. Retourne None si impossible."""
    if not value:
        return None
    v = str(value).strip()
    try:
        if v.endswith("Z"):
            v = v[:-1]
        if "T" not in v and " " in v:
            v = v.replace(" ", "T")
        dt = datetime.fromisoformat(v)
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=timezone.utc)
        else:
            dt = dt.astimezone(timezone.utc)
        return dt
    except Exception:
        return None


# ===========================================================
# BOILERPLATE/MENU DETECTOR
# ===========================================================
_MENU_TERMS = [
    "skip to content",
    "toggle navigation",
    "products",
    "solutions",
    "pricing",
    "docs",
    "documentation",
    "developers",
    "resources",
    "learn",
    "training",
    "customers",
    "partners",
    "company",
    "careers",
    "about",
    "contact",
    "privacy",
    "terms",
    "sign in",
    "log in",
    "login",
    "register",
    "subscribe",
]


def _boilerplate_score(text: str) -> float:
    """
    Score 0..1 : plus haut = ressemble à un header/menu/footer.
    Heuristique simple & efficace pour filtrer homepages.
    """
    import re

    t = (text or "").strip().lower()
    if not t:
        return 1.0

    toks = re.findall(r"[a-z0-9]{2,}", t)
    if len(toks) < 120:
        # texte trop court -> souvent menu
        return 0.75

    menu_hits = 0
    for term in _MENU_TERMS:
        if term in t:
            menu_hits += 1

    density = menu_hits / max(1, len(_MENU_TERMS))
    uniq_ratio = len(set(toks)) / max(1, len(toks))
    short_ratio = sum(1 for x in toks if len(x) <= 3) / max(1, len(toks))

    score = 0.0
    score += 0.55 * density
    score += 0.25 * (1.0 - uniq_ratio)
    score += 0.20 * short_ratio

    if score < 0:
        score = 0.0
    if score > 1:
        score = 1.0
    return score


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

    text = re.sub(r"<script.*?>.*?</script>", " ", html, flags=re.S | re.I)
    text = re.sub(r"<style.*?>.*?</style>", " ", text, flags=re.S | re.I)
    text = re.sub(r"<[^>]+>", " ", text)
    text = re.sub(r"\s+", " ", text).strip()

    lower = text.lower()
    for p in _NOISE_PATTERNS:
        if p in lower:
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

    sentences = re.split(r"(?<=[.!?])\s+", raw)
    if len(sentences) <= 3:
        return _dummy_summarize(raw, max_len=max_len)

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

    add_if(True, block_key)

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

    IMPORTANT: on base l'âge sur published_at si dispo, sinon fallback created_at
    """
    try:
        base = float(it.get("score") or 0.0)
    except Exception:
        base = 0.0

    dt_ref = _parse_dt_safe(it.get("published_at") or it.get("created_at") or "")
    age_hours = max((now - dt_ref).total_seconds() / 3600.0, 0.0)

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
        sources = _load_sources()
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

    # ✅ quotas par bloc + respect enabled:false
    meta = sources.get("meta", {}) or {}
    quotas = (meta.get("quotas") or {})  # ex: {"cloud":10, "security":10, ...}
    default_quota = int(os.getenv("TECH_WATCH_MAX_PER_BLOCK", "10"))
    used_per_block: dict[str, int] = defaultdict(int)

    items: List[Dict[str, Any]] = []
    nb_ok, nb_err = 0, 0
    processed = 0
    truncated = False

    triples = _iter_sources_sorted(sources)
    sources_total = len(triples)

    for block_key, block, src in triples:
        if processed >= MAX_SOURCES_PER_REFRESH:
            truncated = True
            break

        # ✅ skip si disabled dans YAML (redondant avec normalize, mais safe)
        if src.get("enabled") is False:
            processed += 1
            continue

        # ✅ quotas par bloc
        q = int(quotas.get(block_key, default_quota))
        if used_per_block[block_key] >= q:
            processed += 1
            continue

        label = block.get("label", block_key)

        name = src.get("name")
        url = src.get("url")
        lang = src.get("lang", "en")
        if not url:
            processed += 1
            continue

        try:
            html = _fetch_url(url)
            raw_text = _simple_extract_text(html)

            # ✅ boilerplate/menu + published_at réel
            boiler = _boilerplate_score(raw_text)
            published_at = _extract_published_at(html)

            full_summary = _smart_summarize(raw_text, max_len=350)
            short_summary = _dummy_summarize(full_summary, max_len=350)
            tw_summary_2_sent = full_summary

            meta2 = _extract_meta(html)
            og_image = meta2.get("og_image") or ""

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
                "published_at": published_at,
                "raw_len": len(raw_text),
                "summary": full_summary,
                "short_summary": short_summary,
                "tw_summary_2_sent": tw_summary_2_sent,
                "og_image": og_image,
                "favicon_url": favicon_url,
                "tags": tags,
                "tier": src.get("tier"),
                "weight": src.get("weight"),
                "boilerplate_score": round(float(boiler), 3),
                "is_boilerplate": bool(float(boiler) >= 0.55),
            }

            item = _compute_score_and_rank(item)

            # ✅ Skip direct si login/cookies très probable
            if item.get("risk_login"):
                processed += 1
                time.sleep(0.1)
                continue

            # ✅ Skip direct si boilerplate extrême (homepage/menu)
            if float(item.get("boilerplate_score") or 0.0) >= 0.72:
                processed += 1
                time.sleep(0.1)
                continue

            # ✅ Pénalité si "un peu" boilerplate
            if float(item.get("boilerplate_score") or 0.0) >= 0.55:
                item["score"] = round(float(item.get("score") or 0.0) * 0.25, 3)

            items.append(item)
            nb_ok += 1
            used_per_block[block_key] += 1

        except Exception as e:
            items.append(
                {
                    "block": block_key,
                    "block_label": label,
                    "source_name": name,
                    "url": url,
                    "error": str(e),
                    "created_at": datetime.utcnow().isoformat() + "Z",
                    "tier": src.get("tier"),
                    "weight": src.get("weight"),
                }
            )
            nb_err += 1

        processed += 1
        time.sleep(0.1)

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
    data = _load_latest(limit * 8)

    cleaned: List[Dict[str, Any]] = []
    for it in data:
        if it.get("error"):
            continue

        raw_len = int(it.get("raw_len") or 0)
        if raw_len < 200:
            continue

        # ✅ filtrer boilerplate/menu (strict)
        bp = float(it.get("boilerplate_score") or 0.0)
        if bp >= 0.72:
            continue

        if not it.get("short_summary"):
            it["short_summary"] = _dummy_summarize(it.get("summary", ""), 320)

        # ✅ supprimer items dont le résumé est identique au short_summary
        s = (it.get("summary") or "").strip()
        ss = (it.get("short_summary") or "").strip()
        if s and ss and s == ss and _boilerplate_score(s) >= 0.55:
            continue

        it = _compute_score_and_rank(it)
        cleaned.append(it)

    cleaned = enrich_items_with_rank(cleaned)

    # ✅ tri cohérent jury : tier desc, score desc, published_at desc
    def _dt_key(x: Dict[str, Any]) -> str:
        return x.get("published_at") or x.get("created_at") or ""

    cleaned.sort(
        key=lambda x: (
            int(x.get("tier") or 0),
            float(x.get("score") or 0.0),
            _dt_key(x),
        ),
        reverse=True,
    )

    # ✅ 1 item max par source_name
    uniq: List[Dict[str, Any]] = []
    seen_sources = set()

    for it in cleaned:
        src_name = (it.get("source_name") or "").strip().lower()
        if not src_name:
            src_name = (it.get("url") or "").strip().lower()

        if src_name in seen_sources:
            continue

        seen_sources.add(src_name)
        uniq.append(it)

        if len(uniq) >= limit:
            break

    return {
        "status": "ok",
        "count": len(uniq),
        "items": uniq,
    }
