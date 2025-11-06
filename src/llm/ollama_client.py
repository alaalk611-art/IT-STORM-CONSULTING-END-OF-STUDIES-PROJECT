# -*- coding: utf-8 -*-
# src/llm/ollama_client.py — Adaptive Ollama client (robuste)
# - Auto-détection BASE (OLLAMA_BASE_URL | OLLAMA_URL | LOCAL_LLM_BASEURL)
# - Support http(s) + host:port, normalisation sûre
# - HTTP client: requests si dispo, sinon http.client
# - Retries exponentiels + timeouts
# - generate_ollama() compatible (model, prompt, temperature, max_tokens)
# - Options avancées: stop, options={}, stream=False
# - Helpers: ping(), list_models(), model_exists(), get_base(), set_base()

from __future__ import annotations
import os, json, time, http.client, urllib.parse
from typing import Any, Dict, List, Optional, Tuple

try:
    import requests  # facultatif
except Exception:
    requests = None  # type: ignore

def _env_base() -> str:
    return (
        os.getenv("OLLAMA_BASE_URL")
        or os.getenv("OLLAMA_URL")
        or os.getenv("LOCAL_LLM_BASEURL")
        or "http://127.0.0.1:11434"
    )

_BASE = _env_base().strip()

def _normalize_base(url: str) -> Tuple[str, bool]:
    if "://" not in url:
        url = "http://" + url
    p = urllib.parse.urlparse(url)
    scheme = p.scheme or "http"
    host = p.hostname or "127.0.0.1"
    port = p.port or (443 if scheme == "https" else 11434)
    https = scheme == "https"
    base = f"{scheme}://{host}:{port}"
    return base, https

def set_base(url: str) -> None:
    global _BASE
    _BASE = url.strip()

def get_base() -> str:
    return _BASE

def _post(path: str, payload: Dict[str, Any], timeout: float) -> Tuple[int, str]:
    base, use_https = _normalize_base(get_base())
    if requests is not None:
        r = requests.post(
            base + path, json=payload, timeout=timeout, headers={"Content-Type": "application/json"}
        )
        return r.status_code, r.text
    conn_cls = http.client.HTTPSConnection if use_https else http.client.HTTPConnection
    p = urllib.parse.urlparse(base)
    conn = conn_cls(p.hostname, p.port, timeout=timeout)
    try:
        body = json.dumps(payload).encode("utf-8")
        conn.request("POST", path, body=body, headers={"Content-Type": "application/json"})
        resp = conn.getresponse()
        raw = resp.read().decode("utf-8", errors="ignore")
        return resp.status, raw
    finally:
        try:
            conn.close()
        except Exception:
            pass

def _get(path: str, timeout: float) -> Tuple[int, str]:
    base, use_https = _normalize_base(get_base())
    if requests is not None:
        r = requests.get(base + path, timeout=timeout)
        return r.status_code, r.text
    conn_cls = http.client.HTTPSConnection if use_https else http.client.HTTPConnection
    p = urllib.parse.urlparse(base)
    conn = conn_cls(p.hostname, p.port, timeout=timeout)
    try:
        conn.request("GET", path)
        resp = conn.getresponse()
        raw = resp.read().decode("utf-8", errors="ignore")
        return resp.status, raw
    finally:
        try:
            conn.close()
        except Exception:
            pass

def ping(timeout: float = 3.0) -> bool:
    try:
        code, _ = _get("/api/tags", timeout=timeout)
        return 200 <= code < 300
    except Exception:
        return False

def list_models(timeout: float = 8.0) -> List[str]:
    code, txt = _get("/api/tags", timeout=timeout)
    if not (200 <= code < 300):
        raise RuntimeError(f"Ollama /api/tags HTTP {code}: {txt[:300]}")
    try:
        data = json.loads(txt)
        return [t.get("name") for t in data.get("models", []) if t.get("name")]
    except Exception as e:
        raise RuntimeError(f"Parse tags error: {e} / raw={txt[:300]}")

def model_exists(name: str, timeout: float = 8.0) -> bool:
    try:
        names = list_models(timeout=timeout)
        return name in names
    except Exception:
        return False

def generate_ollama(
    model: str,
    prompt: str,
    temperature: float = 0.0,
    max_tokens: int = 300,
    *,
    stop: Optional[List[str]] = None,
    options: Optional[Dict[str, Any]] = None,
    stream: bool = False,
    timeout: float = 120.0,
    retries: int = 2,
    retry_backoff: float = 0.75,
) -> str:
    payload: Dict[str, Any] = {
        "model": model,
        "prompt": prompt,
        "stream": bool(stream),
        "options": {
            "temperature": float(temperature),
            "num_predict": int(max_tokens),
            "repeat_penalty": 1.1,
        },
    }
    if stop:
        payload["stop"] = stop
    if options:
        payload["options"].update(options)

    last_err = None
    for attempt in range(retries + 1):
        try:
            code, raw = _post("/api/generate", payload, timeout=timeout)
            if not (200 <= code < 300):
                raise RuntimeError(f"HTTP {code}: {raw[:300]}")
            if not stream:
                data = json.loads(raw)
                resp = (data.get("response") or "").strip()
                if not resp and data.get("error"):
                    raise RuntimeError(str(data["error"]))
                return resp
            out = []
            for line in raw.splitlines():
                line = line.strip()
                if not line:
                    continue
                try:
                    evt = json.loads(line)
                    chunk = evt.get("response", "")
                    out.append(chunk)
                except Exception:
                    out.append(line)
            return "".join(out).strip()
        except Exception as e:
            last_err = e
            if attempt < retries:
                time.sleep(retry_backoff * (attempt + 1))
                continue
            raise RuntimeError(f"Ollama generate failed ({model}): {e}") from e

# (Optionnel) Compat: classes client si tu veux les utiliser ailleurs
class OllamaClient:
    def __init__(self, model: str, base: Optional[str] = None):
        if base:
            set_base(base)
        self.model = model

    def generate(self, prompt: str, timeout: float = 120.0, **kwargs) -> str:
        return generate_ollama(self.model, prompt, timeout=timeout, **kwargs)

class LLMClient(OllamaClient):
    pass
