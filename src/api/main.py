# -*- coding: utf-8 -*-
# Path: src/api/main.py
# Version 2025 — Cohérente avec STT/TTS/VoiceCopilot Premium
# - Garder toutes tes anciennes fonctions (suggestions / matching)
# - Ajouter intégration STT/TTS propre
# - Ajouter endpoint /chat compatible Voice Copilot et Bulle
# - Conserver l’API Market (quote/ohlcv)
# - CORS sécurisé + clean

from __future__ import annotations

import json
import math
import re
import time
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple
import yfinance as yf
from fastapi import APIRouter
from fastapi import FastAPI, HTTPException, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

from pydantic import BaseModel

# ---------------------------------------------------------------------
# Import STT + TTS mis à jour
# ---------------------------------------------------------------------
from src.api import speech_stt, speech_tts
from src.api import tech_watch
from fastapi import APIRouter
from fastapi.responses import FileResponse
import os

router = APIRouter()
#app = FastAPI()

@router.get("/assets/itstorm-logo.png")
def get_itstorm_logo():
    # ✅ Mets ici le chemin réel côté MACHINE qui lance FastAPI (Windows)
    logo_path = r"C:\Users\ALA BEN LAKHAL\Desktop\intelligent_copilot IT-STORM\src\ui\assets\itstorm_logo.png"
    return FileResponse(logo_path, media_type="image/png", filename="itstorm_logo.png")



# ---------------------------------------------------------------------
# Import backend CLI
# ---------------------------------------------------------------------
def _dummy_answer_backend(q: str) -> str:
    return "⚠️ Backend QA introuvable (tools/qa_cli_pretty.py)."

try:
    import sys
    ROOT = Path(__file__).resolve().parents[2]
    TOOLS = ROOT / "tools"
    if str(ROOT) not in sys.path:
        sys.path.insert(0, str(ROOT))
    if TOOLS.exists() and str(TOOLS) not in sys.path:
        sys.path.insert(0, str(TOOLS))

    from tools.qa_cli_pretty import answer_from_cli_backend
except Exception:
    answer_from_cli_backend = _dummy_answer_backend

# ---------------------------------------------------------------------
# Path fichier suggestions
# ---------------------------------------------------------------------
SUGGEST_PATH = Path(
    r"C:\Users\ALA BEN LAKHAL\Desktop\intelligent_copilot IT-STORM\data\suggest_keywords.json"
)

if not SUGGEST_PATH.exists():
    rel = Path(__file__).resolve().parents[2] / "data" / "suggest_keywords.json"
    if rel.exists():
        SUGGEST_PATH = rel

# ---------------------------------------------------------------------
# FASTAPI INIT
# ---------------------------------------------------------------------
app = FastAPI(
    title="StormCopilot Backend (STT/TTS/Suggest/RAG/Market)",
    version="3.0.0"
)

# ---------------------------------------------------------------------
# CORS (cohérent avec Streamlit + Voice UI + Bubble)
# ---------------------------------------------------------------------
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],   # ⚠️ resserrer en prod
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# ---------------------------------------------------------------------
# Mount routers Speech STT / TTS
# ---------------------------------------------------------------------
app.include_router(speech_stt.router, prefix="/stt", tags=["speech-stt"])
app.include_router(speech_tts.router, prefix="/tts", tags=["speech-tts"])

# ---------------------------------------------------------------------
# MODELES Pydantic (Suggest Engine)
# ---------------------------------------------------------------------
class ChatIn(BaseModel):
    message: str
    exclude_suggestions: List[str] = []
    hop: int = 0

class ChatOut(BaseModel):
    mode: str
    message: str
    suggestion_id: Optional[str] = None
    normalized_question: Optional[str] = None
    answer: Optional[str] = None
    source: Optional[str] = None

# ---------------------------------------------------------------------
# DATABASE SUGGESTIONS CACHE
# ---------------------------------------------------------------------
_DB_CACHE: Dict[str, Any] = {}
_DB_MTIME: float = 0.0
_KEYWORD_CACHE: List[Dict[str, Any]] = []

def _normalize_text(s: str) -> str:
    s = s.strip().lower()
    s = re.sub(r"\s+", " ", s)
    s = re.sub(r"[?!.]+$", "", s)
    return s

def _compile_entry_regex(entry: Dict[str, Any]) -> Dict[str, Any]:
    keywords = entry.get("keywords", []) or []
    aliases = entry.get("aliases", []) or []
    compiled = []

    for kw in keywords:
        try:
            compiled.append(re.compile(kw, flags=re.IGNORECASE))
        except re.error:
            pass

    norm_aliases = [_normalize_text(a) for a in aliases] + [
        _normalize_text(entry.get("question", ""))
    ]
    norm_aliases = [x for x in dict.fromkeys(norm_aliases) if x]

    return {
        **entry,
        "_kw_regex": compiled,
        "_aliases_norm": norm_aliases,
        "_weight": float(entry.get("weight", 1.0)),
    }

def _load_db(force: bool = False) -> List[Dict[str, Any]]:
    global _DB_CACHE, _DB_MTIME, _KEYWORD_CACHE

    if not SUGGEST_PATH.exists():
        raise FileNotFoundError(f"Fichier introuvable : {SUGGEST_PATH}")

    mtime = SUGGEST_PATH.stat().st_mtime
    if force or mtime > _DB_MTIME or not _KEYWORD_CACHE:
        with open(SUGGEST_PATH, "r", encoding="utf-8") as f:
            data = json.load(f)

        items = data["items"] if isinstance(data, dict) and "items" in data else data
        if not isinstance(items, list):
            raise ValueError("Structure JSON inattendue.")

        _KEYWORD_CACHE = [_compile_entry_regex(e) for e in items]
        _DB_CACHE = {"items": items}
        _DB_MTIME = mtime

    return _KEYWORD_CACHE

def _score_candidate(user_text: str, entry: Dict[str, Any]) -> Tuple[float, int]:
    hits = 0
    for rgx in entry.get("_kw_regex", []):
        if rgx.search(user_text):
            hits += 1

    norm_user = _normalize_text(user_text)
    alias_hit = any(a in norm_user for a in entry.get("_aliases_norm", []))
    bonus = 0.5 if alias_hit else 0.0

    raw = hits + bonus
    weight = entry.get("_weight", 1.0)
    return (raw * weight, hits)

def _find_direct_match(user_text: str, entries: List[Dict[str, Any]]):
    norm = _normalize_text(user_text)
    for e in entries:
        if norm in e.get("_aliases_norm", []):
            return e
    return None

def _pick_suggestion(user_text: str, entries, exclude, hop):
    exc_norm = set(_normalize_text(x) for x in exclude)
    scored = [( *_score_candidate(user_text, e), e) for e in entries ]

    scored.sort(
        key=lambda t: (t[0], t[1], t[2].get("_weight", 1.0), t[2].get("question", "")),
        reverse=True
    )

    candidates = []
    for _, __, e in scored:
        id_norm = _normalize_text(str(e.get("id", "")))
        q_norm = _normalize_text(e.get("question", ""))
        if id_norm not in exc_norm and q_norm not in exc_norm:
            candidates.append(e)

    if not candidates:
        return None

    idx = hop % len(candidates)
    return candidates[idx]

# ---------------------------------------------------------------------
# ENDPOINTS SUGGESTIONS
# ---------------------------------------------------------------------
@app.get("/health")
def health():
    return {"status": "ok", "ts": str(int(time.time()))}

@app.get("/version")
def version():
    return {"name": "StormCopilot Backend", "version": app.version}

@app.post("/chat", response_model=ChatOut)
def chat(payload: ChatIn) -> ChatOut:
    try:
        entries = _load_db()
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Erreur suggestions: {e}")

    user_text = payload.message or ""
    if not user_text.strip():
        return ChatOut(mode="suggest", message="Veuillez saisir une question.")

    # Match direct
    direct = _find_direct_match(user_text, entries)
    if direct:
        q = direct.get("question", user_text).strip()
        ans = answer_from_cli_backend(q)
        return ChatOut(
            mode="answer",
            message=f"Précision confirmée → « {q} »",
            normalized_question=q,
            answer=ans,
            source="cli_backend",
        )

    # Suggestion simple
    sug = _pick_suggestion(user_text, entries, payload.exclude_suggestions, payload.hop)
    if not sug:
        return ChatOut(
            mode="suggest",
            message="Aucune suggestion disponible."
        )

    q = sug.get("question", "").strip()
    sug_id = str(sug.get("id", "")).strip() or _normalize_text(q)

    return ChatOut(
        mode="suggest",
        message=f"Tu veux dire : « {q} » ?  Oui (o)  Non (n)",
        suggestion_id=sug_id,
        normalized_question=q,
    )

# ---------------------------------------------------------------------
# API MARCHÉ (v1)
# ---------------------------------------------------------------------
v1 = APIRouter(prefix="/v1")

def _to_float(x, default=None):
    try:
        return float(x) if x is not None else default
    except:
        return default

@v1.get("/quote/{symbol}")
def get_quote(symbol: str):
    try:
        sym = symbol
        t = yf.Ticker(sym)
        info = getattr(t, "fast_info", {}) or {}
        price = info.get("last_price")
        currency = info.get("currency")

        if price is None:
            hist = t.history(period="1d", interval="1d")
            if not hist.empty:
                price = hist["Close"].iloc[-1]

        return {
            "symbol": sym,
            "price": _to_float(price),
            "currency": currency or "EUR",
            "source": "yfinance",
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"quote error: {e}")


@v1.get("/ohlcv/{symbol}")
def get_ohlcv(symbol: str, interval: str = "1d", period: str = "6mo"):
    """
    Endpoint OHLCV robuste :
    - Interroge yfinance avec history()
    - Normalise les colonnes en t/o/h/l/c/v
    - Retourne toujours un JSON cohérent, même sans données
    - Ajoute une clé 'warning' en cas de dataset vide
    """
    try:
        ticker = yf.Ticker(symbol)
        df = ticker.history(period=period, interval=interval, actions=False)

        # --- Aucun résultat → on renvoie un payload vide mais explicite ---
        if df is None or df.empty:
            return {
                "symbol": symbol,
                "interval": interval,
                "period": period,
                "bars": [],
                "candles": [],
                "source": "yfinance",
                "warning": "NO_DATA",
            }

        df = df.reset_index()
        time_col = "Datetime" if "Datetime" in df.columns else "Date"

        out = []
        for _, r in df.iterrows():
            ts = r[time_col]
            try:
                ts = ts.isoformat()
            except Exception:
                ts = str(ts)

            out.append(
                {
                    "t": ts,
                    "o": _to_float(r.get("Open")),
                    "h": _to_float(r.get("High")),
                    "l": _to_float(r.get("Low")),
                    "c": _to_float(r.get("Close")),
                    "v": _to_float(r.get("Volume")),
                }
            )

        return {
            "symbol": symbol,
            "interval": interval,
            "period": period,
            "bars": out,
            "candles": out,
            "source": "yfinance",
            "warning": None,
        }

    except Exception as e:
        raise HTTPException(status_code=500, detail=f"ohlcv error: {e}")

from src.api.routes import mlops_market
app.include_router(mlops_market.router)

from src.api.routes import pdf
app.include_router(pdf.router)

app.include_router(v1)
app.include_router(tech_watch.router)
app.include_router(router)
# src/api