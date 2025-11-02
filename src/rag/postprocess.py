from __future__ import annotations
import re
from difflib import SequenceMatcher
from typing import List

END_TOKEN = "<END>"

_BAD_PATTERNS = [
    r"^Paragraph\b.*",
    r"^Use only these excerpts\b.*",
    r"^The (timeline|following) (is|are)\b.*",
    r"^Additionally[, ]*",
    r"^Moreover[, ]*",
    r"^In addition[, ]*",
    r"\bIT Storm is (a|an) (IT )?consulting company\b.*",
    r"\bThe company is based in\b.*",
    r"\bgrouped into a few themes\b.*",
    r"\bNo generic tutorial text\b.*",
    r"\bEnd with:\s*<END>\b.*",
]

def _split_sentences(text: str) -> List[str]:
    text = text.strip()
    text = re.sub(r"[ \t]+", " ", text)
    lines = [l.strip() for l in text.splitlines() if l.strip()]
    if any(l.startswith(("-", "•", "–", "*")) for l in lines):
        return lines
    sents = re.split(r"(?<=[\.\!\?])\s+(?=[A-Z0-9«“])", text)
    return [s.strip() for s in sents if s.strip()]

def _too_similar(a: str, b: str, thresh: float = 0.92) -> bool:
    return SequenceMatcher(None, a.lower(), b.lower()).ratio() >= thresh

def _remove_placeholders(lines: List[str]) -> List[str]:
    cleaned = []
    for ln in lines:
        if any(re.search(pat, ln, flags=re.IGNORECASE) for pat in _BAD_PATTERNS):
            continue
        if re.search(r"\b\w+ing\b\s+(questions|consequences)\b", ln):
            continue
        if re.search(r"\bhingles\b", ln):
            continue
        cleaned.append(ln)
    return cleaned

def _dedup(lines: List[str]) -> List[str]:
    out: List[str] = []
    for ln in lines:
        if any(_too_similar(ln, prev) for prev in out):
            continue
        out.append(ln)
    return out

def _limit_length(lines: List[str], n: int | None) -> List[str]:
    return lines if not n else lines[:n]

def _strip_end_token(text: str) -> str:
    return text.split(END_TOKEN, 1)[0].strip() if END_TOKEN in text else text.strip()

def postprocess(raw: str, *, max_sentences: int | None = None, force_list: bool | None = None) -> str:
    text = _strip_end_token(raw or "")
    if not text:
        return "Insufficient evidence"
    lines = _split_sentences(text)
    lines = _remove_placeholders(lines)
    lines = _dedup(lines)
    lines = _limit_length(lines, max_sentences)
    if not lines:
        return "Insufficient evidence"
    if force_list or any(l.startswith(("-", "•", "–", "*")) for l in lines):
        return "\n".join(("- " + l.lstrip("-•–* ").strip()) for l in lines)
    out = " ".join(lines)
    return re.sub(r"\s{2,}", " ", out).strip()
