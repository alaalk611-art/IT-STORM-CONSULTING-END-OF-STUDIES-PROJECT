from __future__ import annotations
from typing import Dict
from src.rag.postprocess import postprocess

PROMPTS_EN: Dict[str, str] = {
    "Executive Summary": (
        "[EXECUTIVE_SUMMARY]\n"
        "Write a crisp executive summary (4–6 sentences) about the IT STORM POC.\n"
        "Use only facts found in the retrieved internal documents. No company boilerplate.\n"
        "Avoid meta language. If unsure, write “Insufficient evidence”.\n"
        "End with: <END>"
    ),
    "Technical Architecture": (
        "[TECHNICAL_ARCHITECTURE]\n"
        "Describe the RAG technical architecture as a numbered flow (1–6): "
        "1) Ingestion, 2) Chunking+metadata, 3) Embeddings+VectorDB, "
        "4) Retrieval (k, filters), 5) LLM (model, params, guardrails), "
        "6) UI/API (Streamlit+endpoints) + observability.\n"
        "Only use details present in the indexed docs. 120–180 words. End with: <END>"
    ),
    "Budget & Effort": (
        "[BUDGET_AND_EFFORT]\n"
        "Summarize effort & cost (assumptions, split by phase, person-days, € ranges if stated, "
        "ops costs). No invented numbers; use “Insufficient evidence” if missing. End with: <END>"
    ),
    "Risks": (
        "[RISKS]\n"
        "List 5–7 risks with mitigations as: "
        "- Risk: <title> — Impact: <short> — Mitigation: <action>\n"
        "Only if evidenced in docs. End with: <END>"
    ),
    "Roadmap": (
        "[ROADMAP]\n"
        "3-phase roadmap (Early, Mid, Late) with 2–3 milestones each (weeks/months only if present). "
        "6–9 bullets total. No meta text. End with: <END>"
    ),
    "Next Steps": (
        "[NEXT_STEPS]\n"
        "5–8 immediate next steps grouped by theme: Technical, Data, Change Management/Adoption. "
        "Only items found in docs. No filler. End with: <END>"
    ),
}

_MAX = {
    "Executive Summary": 6,
    "Technical Architecture": 8,
    "Budget & Effort": 10,
    "Risks": 7,
    "Roadmap": 9,
    "Next Steps": 8,
}

def generate_all_sections(c) -> Dict[str, str]:
    out: Dict[str, str] = {}
    for name, prompt in PROMPTS_EN.items():
        gen_kwargs = dict(top_k=3, max_new_tokens=220, temperature=0.3)
        try:
            raw = c.generate_en(prompt, **gen_kwargs)  # type: ignore
        except TypeError:
            raw = c.generate_en(prompt)  # fallback
        force_list = name in {"Technical Architecture", "Risks", "Roadmap", "Next Steps"}
        out[name] = postprocess(raw, max_sentences=_MAX[name], force_list=force_list)
    return out
# ========= Fin src/rag/generate_sections.py =========