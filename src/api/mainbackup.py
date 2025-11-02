# src/api/main.py
from __future__ import annotations

import json
import math
import re
import time
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple
import yfinance as yf
from fastapi import APIRouter

from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel

# ============================================================
# Configuration : chemin du fichier de suggestions
# ============================================================
# 👉 Modifie ce chemin si tu déplaces le fichier.
SUGGEST_PATH = Path(
    r"C:\Users\ALA BEN LAKHAL\Desktop\intelligent_copilot IT-STORM\data\suggest_keywords.json"
)

# Fallback relatif si le chemin absolu n'existe pas (ex: environnement dev)
if not SUGGEST_PATH.exists():
    rel = Path(__file__).resolve().parents[2] / "data" / "suggest_keywords.json"
    if rel.exists():
        SUGGEST_PATH = rel

# ============================================================
# Optionnel : backend QA CLI (réponse directe quand question reconnue)
# ============================================================
# On essaie d'importer le backend CLI (facultatif).
# Si non dispo, on renverra un message d'avertissement.
def _dummy_answer_backend(q: str) -> str:
    return "⚠️ Backend QA introuvable (tools/qa_cli_pretty.py)."

try:
    # Tente d'ajouter le projet racine & tools/ au sys.path automatiquement
    import sys

    ROOT = Path(__file__).resolve().parents[2]
    TOOLS = ROOT / "tools"
    if str(ROOT) not in sys.path:
        sys.path.insert(0, str(ROOT))
    if TOOLS.exists() and str(TOOLS) not in sys.path:
        sys.path.insert(0, str(TOOLS))

    # Import réel si présent
    from tools.qa_cli_pretty import answer_from_cli_backend  # type: ignore
except Exception:
    answer_from_cli_backend = _dummy_answer_backend  # type: ignore

# ============================================================
# FastAPI init + CORS
# ============================================================
app = FastAPI(title="StormCopilot Suggest/Chat API", version="1.0.0")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],   # 🔐 à restreindre en prod
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# ============================================================
# Modèles Pydantic
# ============================================================
class ChatIn(BaseModel):
    message: str
    # Liste de labels (id de suggestion ou texte) à exclure déjà proposées
    exclude_suggestions: List[str] = []
    # Décalage (0 = première suggestion, 1 = suivante, etc.)
    hop: int = 0


class ChatOut(BaseModel):
    mode: str  # "suggest" ou "answer"
    message: str
    suggestion_id: Optional[str] = None
    normalized_question: Optional[str] = None
    answer: Optional[str] = None
    source: Optional[str] = None


# ============================================================
# Chargement / parsing de la base de suggestions
# ============================================================
_DB_CACHE: Dict[str, Any] = {}
_DB_MTIME: float = 0.0

_KEYWORD_CACHE: List[Dict[str, Any]] = []  # entries avec regex compilées


def _normalize_text(s: str) -> str:
    """Normalise une chaîne pour la comparaison stricte alias/phrases."""
    s = s.strip().lower()
    # Supprimer espaces multiples et ponctuation terminale simple
    s = re.sub(r"\s+", " ", s)
    s = re.sub(r"[?!.]+$", "", s)
    return s


def _compile_entry_regex(entry: Dict[str, Any]) -> Dict[str, Any]:
    """Pré-compile les regex des keywords, et stocke aliases normalisés."""
    keywords = entry.get("keywords", []) or []
    aliases = entry.get("aliases", []) or []

    compiled = []
    for kw in keywords:
        try:
            compiled.append(re.compile(kw, flags=re.IGNORECASE))
        except re.error:
            # Ignore une regex invalide, mais continue
            pass

    norm_aliases = [_normalize_text(a) for a in aliases] + [_normalize_text(entry.get("question", ""))]
    # Supprime les doublons vides potentiels
    norm_aliases = [x for x in dict.fromkeys(norm_aliases) if x]

    return {
        **entry,
        "_kw_regex": compiled,
        "_aliases_norm": norm_aliases,
        "_weight": float(entry.get("weight", 1.0) or 1.0),
    }


def _load_db(force: bool = False) -> List[Dict[str, Any]]:
    """Charge le JSON si modifié (ou à la première fois)."""
    global _DB_CACHE, _DB_MTIME, _KEYWORD_CACHE

    if not SUGGEST_PATH.exists():
        raise FileNotFoundError(f"Fichier introuvable : {SUGGEST_PATH}")

    mtime = SUGGEST_PATH.stat().st_mtime
    if force or mtime > _DB_MTIME or not _KEYWORD_CACHE:
        with open(SUGGEST_PATH, "r", encoding="utf-8") as f:
            data = json.load(f)

        # Supporte soit {items:[...]}, soit un tableau direct
        items = data["items"] if isinstance(data, dict) and "items" in data else data
        if not isinstance(items, list):
            raise ValueError("Structure JSON inattendue : attend une liste d'objets.")

        _KEYWORD_CACHE = [_compile_entry_regex(e) for e in items]
        _DB_CACHE = {"items": items}
        _DB_MTIME = mtime

    return _KEYWORD_CACHE


# ============================================================
# Moteur de matching / scoring
# ============================================================
def _score_candidate(user_text: str, entry: Dict[str, Any]) -> Tuple[float, int]:
    """
    Score = nb_matches_regex + bonus légère si l'alias exact existe dans le texte,
    le tout * weight.
    Retourne (score, nb_hits) pour tri stable si égalité.
    """
    hits = 0
    for rgx in entry.get("_kw_regex", []):
        if rgx.search(user_text):
            hits += 1

    # Bonus si l'un des aliases normalisés est sous-chaîne du texte normalisé
    norm_user = _normalize_text(user_text)
    alias_hit = any(a in norm_user for a in entry.get("_aliases_norm", []))
    bonus = 0.5 if alias_hit else 0.0

    raw = hits + bonus
    weight = entry.get("_weight", 1.0)
    return (raw * weight, hits)


def _find_direct_match(user_text: str, entries: List[Dict[str, Any]]) -> Optional[Dict[str, Any]]:
    """Si user_text == alias/question normalisé → retour direct pour répondre sans proposition."""
    norm = _normalize_text(user_text)
    for e in entries:
        if norm in e.get("_aliases_norm", []):
            return e
    return None


def _pick_suggestion(
    user_text: str,
    entries: List[Dict[str, Any]],
    exclude: List[str],
    hop: int,
) -> Optional[Dict[str, Any]]:
    """
    Classe les entrées par score décroissant et renvoie la (hop)-ième
    non exclue. hop=0 => première, hop=1 => suivante, etc.
    """
    # Filtrage des exclusions par id OU libellé exact
    exc_norm = set(_normalize_text(x) for x in exclude)

    scored: List[Tuple[float, int, Dict[str, Any]]] = []
    for e in entries:
        s, hits = _score_candidate(user_text, e)
        scored.append((s, hits, e))

    # Tri : score desc, hits desc, poids desc, titre asc pour stabilité
    scored.sort(key=lambda t: (t[0], t[1], t[2].get("_weight", 1.0), t[2].get("question", "")), reverse=True)

    # Balayage en sautant les exclus
    candidates: List[Dict[str, Any]] = []
    for _, __, e in scored:
        id_norm = _normalize_text(str(e.get("id", "")))
        q_norm = _normalize_text(e.get("question", ""))
        if id_norm in exc_norm or q_norm in exc_norm:
            continue
        candidates.append(e)

    if not candidates:
        return None

    # Sélection selon hop (cyclique si hop dépasse la taille)
    idx = hop % len(candidates) if len(candidates) > 0 else 0
    return candidates[idx]


# ============================================================
# Endpoints
# ============================================================
@app.get("/health")
def health() -> Dict[str, str]:
    return {"status": "ok", "ts": str(int(time.time()))}


@app.get("/version")
def version() -> Dict[str, str]:
    return {"name": "StormCopilot Suggest/Chat API", "version": app.version}


@app.post("/chat", response_model=ChatOut)
def chat(payload: ChatIn) -> ChatOut:
    """
    Comportement :
    1) Si la question est reconnue exactement (alias/phrase) → on renvoie "answer".
    2) Sinon → on renvoie "suggest" avec UNE proposition, en tenant compte de exclude_suggestions + hop.
    """
    try:
        entries = _load_db()
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Erreur chargement suggestions: {e}")

    user_text = payload.message or ""
    if not user_text.strip():
        return ChatOut(
            mode="suggest",
            message="Veuillez saisir une question.",
        )

    # 1) Match direct -> réponse
    direct = _find_direct_match(user_text, entries)
    if direct:
        # Question canonique pour affichage
        q = direct.get("question", user_text).strip()
        ans = answer_from_cli_backend(q)  # via tools/qa_cli_pretty si dispo
        return ChatOut(
            mode="answer",
            message=f"Précision confirmée → « {q} »",
            normalized_question=q,
            answer=ans,
            source="cli_backend",
        )

    # 2) Sinon : proposer une suggestion (cyclage hop / exclusions)
    sug = _pick_suggestion(user_text, entries, payload.exclude_suggestions, payload.hop)
    if not sug:
        # Rien à proposer → message générique contrôlé
        return ChatOut(
            mode="suggest",
            message="Aucune suggestion disponible pour cette requête. Reformulez ou précisez votre question.",
        )

    q = sug.get("question", "").strip()
    sug_id = str(sug.get("id", "")).strip() or _normalize_text(q)  # id si présent, sinon fallback
    return ChatOut(
        mode="suggest",
        message=f"Tu veux dire : « {q} » ?  Oui (o)  Non (n)",
        suggestion_id=sug_id,
        normalized_question=q,
    )
# ============================================================
# API Marché (v1) — /v1/quote/{symbol} et /v1/ohlcv/{symbol}
# ============================================================
v1 = APIRouter(prefix="/v1")

def _to_float(x, default=None):
    try:
        if x is None:
            return default
        return float(x)
    except Exception:
        return default

@v1.get("/quote/{symbol}")
def get_quote(symbol: str):
    """
    Ex: /v1/quote/%5EFCHI   (=%5E -> '^')
        /v1/quote/BNP.PA
        /v1/quote/MC.PA
    """
    try:
        sym = symbol  # FastAPI décodera %5E en '^' automatiquement
        t = yf.Ticker(sym)
        info = t.fast_info if hasattr(t, "fast_info") else {}
        price = getattr(info, "last_price", None) or info.get("last_price")
        currency = getattr(info, "currency", None) or info.get("currency")
        # fallback si fast_info vide
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
    Ex: /v1/ohlcv/%5EFCHI?interval=1d&period=6mo
    """
    try:
        sym = symbol
        t = yf.Ticker(sym)
        df = t.history(period=period, interval=interval)
        if df is None or df.empty:
            raise HTTPException(status_code=404, detail="No OHLCV data")

        df = df.reset_index()
        time_col = "Datetime" if "Datetime" in df.columns else "Date"

        out = []
        for _, r in df.iterrows():
            ts = r[time_col]
            try:
                ts = ts.isoformat()
            except Exception:
                ts = str(ts)
            out.append({
                "t": ts,
                "o": _to_float(r.get("Open")),
                "h": _to_float(r.get("High")),
                "l": _to_float(r.get("Low")),
                "c": _to_float(r.get("Close")),
                "v": _to_float(r.get("Volume")),
            })

        # ⚠️ Retour unifié: on expose à la fois "bars" (ancien)
        # et "candles" (ce que lit l'UI actuelle).
        return {
            "symbol": sym,
            "interval": interval,
            "period": period,
            "bars": out,
            "candles": out,
            "source": "yfinance",
        }
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"ohlcv error: {e}")

# Monte le router v1
app.include_router(v1)


# ============================================================
# Démarrage rapide (uvicorn)
# uvicorn src.api.main:app --reload --port 8001
# ============================================================
