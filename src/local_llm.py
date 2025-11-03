# -*- coding: utf-8 -*-
# src/local_llm.py — client LLM local (Ollama par défaut), pour reformulation stricte

import os, requests

BACKEND = os.getenv("LOCAL_LLM_BACKEND", "ollama")  # ollama | openai_compat
MODEL   = os.getenv("LOCAL_LLM_MODEL",   "mistral:7b-instruct")
BASEURL = os.getenv("LOCAL_LLM_BASEURL", "http://localhost:11434")  # ollama default

def refine_with_llm(text: str, quotes):
    """Reformule en 1 paragraphe SANS ajouter d'info (fidèle aux citations)."""
    if not text or not quotes:
        return text
    system = (
        "Tu es un assistant de reformulation FR. "
        "NE RAJOUTE AUCUNE INFORMATION ET NE DÉDUIS RIEN. "
        "Rédige en UN paragraphe fluide, STRICTEMENT fidèle aux citations."
    )
    prompt = (
        f"{system}\n\n"
        "Citations (ne JAMAIS inventer au-delà) :\n"
        + "\n".join([f"- {q}" for q in quotes[:4]]) +
        "\n\nParagraphe à lisser (respect strict du sens) :\n"
        f"{text}\n\n"
        "==> Donne uniquement le paragraphe final, sans préfixe."
    )

    if BACKEND == "ollama":
        r = requests.post(f"{BASEURL}/api/generate",
                          json={"model": MODEL, "prompt": prompt, "stream": False}, timeout=120)
        r.raise_for_status()
        out = r.json().get("response", "").strip()
        return out or text
    else:
        headers = {"Content-Type": "application/json"}
        payload = {
            "model": MODEL,
            "messages": [{"role": "user", "content": prompt}],
            "temperature": 0.2,
            "max_tokens": 256,
        }
        r = requests.post(f"{BASEURL}/v1/chat/completions", json=payload, headers=headers, timeout=120)
        r.raise_for_status()
        return (r.json()["choices"][0]["message"]["content"] or "").strip() or text
