# src/rag/text_utils.py
import re

def clean_to_5_sentences(text: str) -> str:
    # supprime puces
    text = re.sub(r"^\s*[-•]\s*", "", text, flags=re.MULTILINE).strip()
    # split grossier en phrases
    sents = re.split(r"(?<=[\.\!\?])\s+", text)
    seen, uniq = set(), []
    for s in sents:
        s = s.strip()
        if not s:
            continue
        k = re.sub(r"\s+", " ", s.lower())
        if k not in seen:
            seen.add(k)
            uniq.append(s)
    if len(uniq) >= 5:
        uniq = uniq[:5]
    return " ".join(uniq)
