# tests/test_rag_eval.py
import os, json, importlib, pathlib, pytest
from typing import Any, List
import unicodedata, re
from difflib import SequenceMatcher

# --- Config via ENV (avec défauts locaux) ---
JSONL_PATH = os.getenv("RAG_JSONL", "./data/finetune/val.jsonl")
MODULE_NAME = os.getenv("RAG_MODULE", "src.rag.chain")
BUILDER_NAME = os.getenv("RAG_BUILDER", "build_rag_chain")
TOP_K = int(os.getenv("RAG_TOPK", "6"))

# --- Normalisation robuste pour le matching ---
def _norm(s: str) -> str:
    """
    Normalise le texte pour un matching robuste :
    - retire les préfixes [Source: ...] et la section "Sources:"
    - normalise unicode + enlève les accents
    - met en minuscule + compacte les espaces
    """
    if not s:
        return ""
    # enlève les préfixes [Source: ...] (éventuels en début de ligne)
    s = re.sub(r'^\[Source:\s*[^\]]+\]\s*', '', s, flags=re.MULTILINE)
    # enlève tout ce qui suit la section "Sources:"
    s = s.split("\n\nSources:")[0]

    # normalise unicode puis enlève les accents (combining marks)
    s = unicodedata.normalize("NFKD", s)
    s = "".join(ch for ch in s if not unicodedata.combining(ch))

    # minuscule + espaces compactés
    s = s.lower()
    s = re.sub(r"\s+", " ", s).strip()
    return s

def _to_text(obj: Any) -> str:
    if obj is None:
        return ""
    if isinstance(obj, str):
        return obj
    if isinstance(obj, dict):
        for k in ("answer", "output_text", "result", "content"):
            if k in obj and isinstance(obj[k], str):
                return obj[k]
        return str(obj)
    return str(obj)

def _extract_sources(result: Any) -> List[str]:
    out = []
    if isinstance(result, dict):
        for key in ("sources", "source_documents", "docs", "references"):
            raw = result.get(key)
            if not raw:
                continue
            if isinstance(raw, list):
                for it in raw:
                    if isinstance(it, str):
                        out.append(it)
                    elif isinstance(it, dict):
                        meta = it.get("metadata", {})
                        src = meta.get("source") or meta.get("file_path") or ""
                        if src:
                            out.append(str(src))
                        else:
                            pc = it.get("page_content", "")
                            if pc:
                                out.append(pc[:80])
                    else:
                        out.append(str(it))
    return [s for s in dict.fromkeys(out) if s.strip()]

def _answer_matches(ans: str, expected: str) -> bool:
    na, ne = _norm(ans), _norm(expected)
    if not ne:
        return False
    # match par sous-chaîne après normalisation OU similarité suffisante
    return (ne in na) or (SequenceMatcher(None, na, ne).ratio() >= 0.92)

@pytest.fixture(scope="session")
def qa_items():
    p = pathlib.Path(JSONL_PATH)
    assert p.exists(), f"JSONL introuvable: {JSONL_PATH}"
    data = []
    for line in p.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line:
            continue
        data.append(json.loads(line))
    assert data, f"Aucune question dans {JSONL_PATH}"
    return data

@pytest.fixture(scope="session")
def rag_chain():
    mod = importlib.import_module(MODULE_NAME)
    builder = getattr(mod, BUILDER_NAME)
    try:
        return builder(k=TOP_K)
    except TypeError:
        return builder()

@pytest.mark.parametrize("idx", range(5))
def test_rag_eval(idx, qa_items, rag_chain):
    if idx >= len(qa_items):
        pytest.skip("Fin des questions.")
    q = qa_items[idx]["question"]
    expected = qa_items[idx]["expected_answer"]
    must_src = qa_items[idx]["must_find_source"]

    try:
        result = rag_chain.invoke(q)
    except Exception:
        result = rag_chain(q)

    answer = _to_text(result)
    sources = _extract_sources(result)

    assert _answer_matches(answer, expected), (
        f"[Q{idx}] Sous-chaîne attendue absente.\n"
        f"Q: {q}\nAttendu: {expected}\nRéponse: {answer}\nSources: {sources}"
    )

    if must_src:
        assert len(sources) > 0, (
            f"[Q{idx}] Attendu au moins une source.\nQ: {q}\nRéponse: {answer}"
        )
    else:
        assert "je ne sais pas" in answer.lower(), (
            f"[Q{idx}] Cas 'Je ne sais pas.' attendu.\nQ: {q}\nRéponse: {answer}"
        )
