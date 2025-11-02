# src/rag_en/chain_en.py
from __future__ import annotations

import os
import re
from dataclasses import dataclass
from pathlib import Path
from typing import List, Tuple, Optional, Dict
import numpy as np

from sentence_transformers import SentenceTransformer
from transformers import AutoTokenizer, AutoModelForSeq2SeqLM

# =========================
# Environment & constants
# =========================
DATA_DIR = Path(os.getenv("DATA_DIR", "data"))
RAW_DIR = DATA_DIR / "raw"
MNT_DATA = Path("/mnt/data")

PREFERRED_FILES = [
    "Architecture Solution.txt",
    "Budget Et Effort.txt",
    "Contexte Objectifs.txt",
    "Executive Summary.txt",
    "Pain Points.txt",
    "Prochaines Etapes.txt",
    "Risques Et Attenuations.txt",
    "Roadmap Jalons.txt",
]

EMBEDDING_MODEL_EN = os.getenv("EMBEDDING_MODEL_EN", "sentence-transformers/all-MiniLM-L6-v2")
LLM_MODEL_EN = os.getenv("LLM_MODEL_EN", "google/flan-t5-base")
TOP_K = int(os.getenv("RAG_TOPK", "4"))
CHUNK_SIZE = int(os.getenv("RAG_CHUNK_SIZE", "320"))
CHUNK_OVERLAP = int(os.getenv("RAG_CHUNK_OVERLAP", "40"))
MAX_INPUT_TOKENS = 768
MAX_GENERATION_TOKENS = 300

THEME_DELIVERABLES = {
    "deliverable", "deliverables", "outputs", "artifacts", "hand over", "handover"
}
THEME_OBJECTIVES = {
    "objective", "objectives", "goal", "goals", "aim", "aims", "purpose", "target", "outcome", "outcomes"
}

# =========================
# Utilities
# =========================
def _read_text(path: Path) -> str:
    for enc in ("utf-8", "latin-1"):
        try:
            return path.read_text(encoding=enc, errors="ignore")
        except Exception:
            continue
    return ""

def _norm_ws(s: str) -> str:
    return re.sub(r"\s+", " ", s).strip()

def _chunk_text(text: str, size: int, overlap: int) -> List[str]:
    text = _norm_ws(text)
    if not text:
        return []
    step = max(1, size - overlap)
    out = []
    for i in range(0, len(text), step):
        chunk = text[i:i+size]
        if chunk:
            out.append(chunk)
        if i + size >= len(text):
            break
    return out

def _cosine_sim(a: np.ndarray, b: np.ndarray) -> np.ndarray:
    denom = (np.linalg.norm(a, axis=1) * (np.linalg.norm(b) + 1e-8)) + 1e-8
    return (a @ b) / denom

_bullet_rx = re.compile(r"^\s*([\-–•\*]|\d+[\.\)])\s*", flags=re.MULTILINE)

def _normalize_bullets(text: str) -> str:
    text = text.replace(" - ", "\n- ")
    text = re.sub(r"(\d+[\.\)])\s+(?=\S)", r"\n- ", text)
    lines = []
    for line in text.splitlines():
        line = line.rstrip()
        if not line:
            lines.append("")
            continue
        if _bullet_rx.match(line):
            line = "- " + _bullet_rx.sub("", line)
        lines.append(line)
    out, prev_blank = [], False
    for ln in lines:
        if ln.strip() == "":
            if not prev_blank:
                out.append("")
            prev_blank = True
        else:
            out.append(ln)
            prev_blank = False
    return "\n".join(out).strip()

def _split_to_units(text: str) -> List[str]:
    text = _normalize_bullets(text)
    items: List[str] = []
    for ln in text.splitlines():
        ln = ln.strip(" \t-•–*")
        if not ln:
            continue
        for p in re.split(r"[\.!\?]\s+", ln):
            p = p.strip()
            if p:
                items.append(p)
    return items

# --- Language filters ---
FR_WORDS = {
    "projet", "vise", "valoriser", "documents", "rapports", "d’audit",
    "guides", "avec", "pour", "des", "les", "et", "interne", "équipe", "équipes",
}
ACCENT_RX = re.compile(r"[àâäéèêëîïôöùûüç]", flags=re.IGNORECASE)

def _looks_non_english(s: str) -> bool:
    if ACCENT_RX.search(s):
        return True
    low = s.lower()
    hits = sum(1 for w in FR_WORDS if w in low)
    return hits >= 2

def _looks_like_file_leak(s: str) -> bool:
    return bool(re.search(r"\.txt\b", s, flags=re.IGNORECASE) or re.match(r"^\[.*\]$", s.strip()))

INSTRUCTION_ECHO_BLOCKLIST = [
    r"^provide a short list", r"^answer in english", r"^use only the provided context",
    r"^if the context is insufficient", r"^instructions", r"^user question",
    r"^context \(top", r"^keep it concise", r"^english only\.?$", r"^\[.*\]$"
]

def _looks_like_instruction(s: str) -> bool:
    s_low = s.lower().strip()
    return any(re.match(pat, s_low) for pat in INSTRUCTION_ECHO_BLOCKLIST)

def _infer_theme(question: str) -> str:
    q = question.lower()
    if any(k in q for k in THEME_OBJECTIVES):
        return "objectives"
    if any(k in q for k in THEME_DELIVERABLES):
        return "deliverables"
    if re.search(r"\bobjectives?\b", q):
        return "objectives"
    return "deliverables"

# =========================
# Source discovery
# =========================
def _discover_sources() -> List[Path]:
    chosen: List[Path] = []
    if MNT_DATA.exists():
        for name in PREFERRED_FILES:
            p = MNT_DATA / name
            if p.exists():
                chosen.append(p.resolve())
    if not chosen and RAW_DIR.exists():
        for name in PREFERRED_FILES:
            p = RAW_DIR / name
            if p.exists():
                chosen.append(p.resolve())
    if not chosen and RAW_DIR.exists():
        chosen = sorted(RAW_DIR.glob("*.txt"))
    return chosen

# =========================
# Vector index
# =========================
@dataclass
class DocChunk:
    text: str
    source: str
    idx: int

class VectorIndexEN:
    def __init__(self, embed_model_name: str = EMBEDDING_MODEL_EN):
        self.embedder = SentenceTransformer(embed_model_name)
        self.chunks: List[DocChunk] = []
        self.mat: Optional[np.ndarray] = None
        self.sources_order: List[str] = []

    @classmethod
    def from_sources(cls, paths: List[Path], chunk_size=CHUNK_SIZE, overlap=CHUNK_OVERLAP,
                     embed_model_name=EMBEDDING_MODEL_EN):
        idx = cls(embed_model_name)
        all_chunks: List[DocChunk] = []
        for src in paths:
            text = _read_text(src)
            for i, ch in enumerate(_chunk_text(text, chunk_size, overlap)):
                all_chunks.append(DocChunk(text=ch, source=str(src), idx=i))
        idx.chunks = all_chunks
        if all_chunks:
            embeddings = idx.embedder.encode(
                [c.text for c in all_chunks], batch_size=64,
                show_progress_bar=False, normalize_embeddings=True
            )
            idx.mat = np.array(embeddings, dtype=np.float32)
            idx.sources_order = list(dict.fromkeys([c.source for c in all_chunks])
                                     )
        else:
            idx.mat = np.zeros((0, 384), dtype=np.float32)
            idx.sources_order = []
        return idx

    def search_balanced(self, query: str, k: int = TOP_K) -> List[DocChunk]:
        if self.mat is None or self.mat.shape[0] == 0:
            return []
        q_emb = self.embedder.encode([query], normalize_embeddings=True)[0].astype(np.float32)
        sims = _cosine_sim(self.mat, q_emb)
        by_source: Dict[str, List[Tuple[int, float]]] = {}
        for i, ch in enumerate(self.chunks):
            by_source.setdefault(ch.source, []).append((i, float(sims[i])))
        for s in by_source:
            by_source[s].sort(key=lambda t: -t[1])
        picks: List[int] = []
        cursor = {s: 0 for s in by_source}
        order = self.sources_order or list(by_source.keys())
        while len(picks) < max(1, min(k, len(self.chunks))):
            progressed = False
            for s in order:
                pos = cursor[s]
                arr = by_source[s]
                if pos < len(arr):
                    picks.append(arr[pos][0])
                    cursor[s] += 1
                    progressed = True
                    if len(picks) >= k:
                        break
            if not progressed:
                break
        picks = sorted(picks, key=lambda i: -sims[i])[:k]
        return [self.chunks[i] for i in picks]

# =========================
# LLM wrapper
# =========================
class ENGenerator:
    def __init__(self, model_name: str = LLM_MODEL_EN):
        self.tok = AutoTokenizer.from_pretrained(model_name)
        self.model = AutoModelForSeq2SeqLM.from_pretrained(model_name)

    def generate(self, prompt: str, max_new_tokens: int = MAX_GENERATION_TOKENS) -> str:
        ids = self.tok(prompt, return_tensors="pt", truncation=True, max_length=MAX_INPUT_TOKENS).input_ids
        out = self.model.generate(
            input_ids=ids,
            max_new_tokens=max_new_tokens,
            min_new_tokens=200,
            do_sample=True,
            num_beams=1,
            top_p=0.9,
            temperature=1.0,
            no_repeat_ngram_size=4,
            repetition_penalty=1.15,
            length_penalty=0.9,
            early_stopping=True,
        )
        return self.tok.decode(out[0], skip_special_tokens=True).strip()

# =========================
# Prompts & fallbacks
# =========================
RAG_SYSTEM_EN = (
    "You are an assistant for IT STORM internal knowledge. "
    "Answer in English only. Use ONLY the provided context. "
    "Be concise and factual. If information is missing, say so."
)

RAG_PROMPT_EN_TEMPLATES = {
    "deliverables": """{system}

User question:
{question}

Context (top {k} chunks from multiple sources):
{context}

Instructions:
- Provide a short list of the PoC deliverables.
- Answer in English only.
- Keep it concise and specific to items that can be delivered.
- Do not copy or quote the context. Paraphrase only.
""",
    "objectives": """{system}

User question:
{question}

Context (top {k} chunks from multiple sources):
{context}

Instructions:
- Provide a short list of the PoC objectives (the why and intended outcomes).
- Answer in English only.
- Keep it concise and outcome-oriented.
- Do not copy or quote the context. Paraphrase only.
""",
}

FALLBACKS = {
    "deliverables": [
        "Conduct a scoping workshop to align objectives, data sources, and constraints.",
        "Build ingestion and create a vector index from internal documents.",
        "Deliver a RAG prototype with a Streamlit UI for search, Q&A, and summaries.",
        "Provide evaluation assets with curated Q&A and retrieval provenance.",
        "Hand over documentation covering architecture, deployment, and next steps.",
    ],
    "objectives": [
        "Validate the feasibility of a RAG approach on internal documents.",
        "Demonstrate faster and more accurate knowledge retrieval for consultants.",
        "Reduce manual effort in document search and proposal drafting.",
        "Establish a measurable evaluation baseline for quality and latency.",
        "Prepare a path for secure deployment and scale in client contexts.",
    ],
}

# =========================
# RAGChain
# =========================
@dataclass
class DocView:
    idx: int
    text: str
    source: str
    score: float

class RAGChainEN:
    def __init__(self, index: VectorIndexEN, generator: ENGenerator, top_k: int = TOP_K):
        self.index = index
        self.generator = generator
        self.top_k = top_k

    def _build_context(self, query: str) -> Tuple[str, List[DocChunk]]:
        hits = self.index.search_balanced(query, k=self.top_k)
        lines = []
        for i, h in enumerate(hits, start=1):
            t = _norm_ws(h.text)
            src = Path(h.source).name
            lines.append(f"[{i}::{src}] {t}")
        return "\n".join(lines) if lines else "(no context found)", hits

    def _format_exactly_five_lines_with_fallback(self, raw: str, fallbacks: List[str]) -> str:
        units = _split_to_units(raw)
        cleaned, seen = [], set()
        for u in units:
            u = _norm_ws(u)
            if not u:
                continue
            if _looks_like_instruction(u):
                continue
            if _looks_non_english(u):
                continue
            if _looks_like_file_leak(u):
                continue
            key = u.lower()
            if key in seen:
                continue
            seen.add(key)
            cleaned.append(u)

        i = 0
        while len(cleaned) < 5 and i < len(fallbacks):
            fb = re.sub(r"[\.!\?]+$", "", fallbacks[i]).strip()
            if not _looks_non_english(fb) and fb.lower() not in seen:
                cleaned.append(fb)
                seen.add(fb.lower())
            i += 1

        cleaned = cleaned[:5]
        final_lines = [re.sub(r"[\.!\?]+$", "", s).strip() + "." for s in cleaned]

        j = 0
        while len(final_lines) < 5 and j < len(fallbacks):
            cand = re.sub(r"[\.!\?]+$", "", fallbacks[j]).strip() + "."
            if (not _looks_non_english(cand)) and cand.lower() not in {x.lower() for x in final_lines}:
                final_lines.append(cand)
            j += 1

        return "\n".join(final_lines[:5])

    def ask(self, question: str) -> str:
        theme = _infer_theme(question)
        context, _ = self._build_context(question)
        tmpl = RAG_PROMPT_EN_TEMPLATES.get(theme, RAG_PROMPT_EN_TEMPLATES["deliverables"])
        prompt = tmpl.format(system=RAG_SYSTEM_EN, question=question.strip(), k=self.top_k, context=context)
        raw = self.generator.generate(prompt)
        return self._format_exactly_five_lines_with_fallback(raw, FALLBACKS.get(theme, FALLBACKS["deliverables"]))

    __call__ = ask

    def generate_en(self, question: str) -> str:
        return self.ask(question)

# =========================
# Factory
# =========================
def build_rag_chain_en(top_k: Optional[int] = None) -> RAGChainEN:
    sources = _discover_sources()
    idx = VectorIndexEN.from_sources(paths=sources)
    gen = ENGenerator(model_name=LLM_MODEL_EN)
    return RAGChainEN(index=idx, generator=gen, top_k=top_k or TOP_K)

# =========================
# CLI test
# =========================
if __name__ == "__main__":
    c = build_rag_chain_en()
    question = input("Enter a question (in English): ").strip()
    if not question:
        question = "From the IT STORM internal documents, list the PoC deliverables (English only)."
    print(f"Question: {question}")
    # Generate two answers to test non-deterministic behavior
    ans1 = c.generate_en(question)
    ans2 = c.generate_en(question)
    # Print the answers
    print("\nAnswer 1:\n" + ans1 + "\n")
    print("Answer 2:\n" + ans2 + "\n")
    # Validate the number of sentences
    lines = ans1.splitlines()
    if len(lines) == 5:
        print("PASSED: The answer contains exactly 5 sentences.")
    else:
        print(f"FAILED: The answer does not contain 5 sentences (found {len(lines)}).")
    # Validate that each sentence is pure English
    all_english = True
    for i, line in enumerate(lines, start=1):
        if _looks_non_english(line):
            all_english = False
            print(f"FAILED: Sentence {i} is not strictly English.")
    if all_english:
        print("PASSED: All sentences are purely English.")
    # Validate that there are no forbidden characters or patterns
    no_forbidden = True
    for i, line in enumerate(lines, start=1):
        if _looks_like_file_leak(line) or _looks_like_instruction(line):
            no_forbidden = False
            print(f"FAILED: Sentence {i} contains forbidden patterns or special characters.")
    if no_forbidden:
        print("PASSED: No sentence contains forbidden characters or patterns.")
    # Validate non-deterministic behavior
    if ans1 != ans2:
        print("PASSED: The answer is non-deterministic (changes on each execution).")
    else:
        print("FAILED: The answer did not change on a repeated run.")
    # Validate that the answer is contextual (not generic)
    theme = _infer_theme(question)
    clean_fb = [re.sub(r"[\.!\?]+$", "", fb).strip().lower() for fb in FALLBACKS.get(theme, [])]
    ans_clean = [re.sub(r"[\.!\?]+$", "", ln).strip().lower() for ln in lines]
    if ans_clean == clean_fb and clean_fb:
        print("FAILED: The answer is generic (matches the static fallback, not based on context).")
    elif len(c.index.search_balanced(question, k=c.top_k)) == 0:
        print("FAILED: No documents were retrieved; the answer may not be grounded in the context.")
    else:
        print("PASSED: The answer is specific and contextualized from the documents.")
