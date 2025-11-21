# src/qa_router.py
from __future__ import annotations

import json
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Dict, List, Optional, Tuple

from src.rag_brain import smart_rag_answer


# ---------------------------------------------------------------------
# 1) Modèle et chargement de la base QA (train.txt)
# ---------------------------------------------------------------------
@dataclass
class QAItem:
    question: str
    answer: str
    path: str


def load_qa_base(path: str = "data/train.txt") -> List[QAItem]:
    """
    Fichier attendu :

    Q: ...
    A: ...
    ---
    Q: ...
    A: ...
    ---
    """
    p = Path(path)
    if not p.exists():
        raise FileNotFoundError(f"Fichier QA introuvable : {p}")

    items: List[QAItem] = []
    current_q: Optional[str] = None
    current_a: Optional[str] = None

    for line in p.read_text(encoding="utf-8").splitlines():
        s = line.strip()
        if not s:
            continue

        if s.startswith("Q:"):
            if current_q and current_a:
                items.append(QAItem(question=current_q, answer=current_a, path=p.name))
            current_q = s[2:].strip()
            current_a = None
        elif s.startswith("A:"):
            current_a = s[2:].strip()
        elif s.startswith("---"):
            if current_q and current_a:
                items.append(QAItem(question=current_q, answer=current_a, path=p.name))
            current_q, current_a = None, None
        else:
            if current_a is not None:
                current_a += " " + s

    if current_q and current_a:
        items.append(QAItem(question=current_q, answer=current_a, path=p.name))

    return items


QA_ITEMS: List[QAItem] = load_qa_base()


# ---------------------------------------------------------------------
# 2) Chargement des mots-clés (suggest_keywords.json)
# ---------------------------------------------------------------------
def load_suggest_keywords(path: str = "data/suggest_keywords.json") -> Dict[str, List[str]]:
    """
    Fichier attendu : objet JSON de la forme

    {
      "it storm": ["Explique IT STORM en quelques phrases.", ...],
      "data": [...],
      ...
    }
    """
    p = Path(path)
    if not p.exists():
        print(f"[WARN] suggest_keywords.json introuvable : {p} — suggestions mots-clés désactivées.")
        return {}

    try:
        raw = json.loads(p.read_text(encoding="utf-8"))
    except Exception as e:
        print(f"[WARN] Erreur de parsing JSON pour {p}: {e}")
        return {}

    if not isinstance(raw, dict):
        print(f"[WARN] suggest_keywords.json doit être un objet JSON {{...}}, trouvé {type(raw)}.")
        return {}

    out: Dict[str, List[str]] = {}
    for k, v in raw.items():
        if not isinstance(v, list):
            continue
        out[str(k).lower()] = [str(x) for x in v]
    return out


SUGGEST_KEYWORDS: Dict[str, List[str]] = load_suggest_keywords()


# ---------------------------------------------------------------------
# 3) Normalisation + similarité
# ---------------------------------------------------------------------
def _normalize_question(s: str) -> List[str]:
    """Normalise en tokens (minuscules, sans ponctuation)."""
    s = s.lower()
    s = re.sub(r"[^a-zàâçéèêëîïôûùüÿñæœ0-9 ]", " ", s)
    tokens = [t for t in s.split() if t]
    return tokens


def _jaccard_score(a: List[str], b: List[str]) -> float:
    sa, sb = set(a), set(b)
    if not sa or not sb:
        return 0.0
    inter = sa & sb
    union = sa | sb
    return len(inter) / len(union)


def _norm_id_router(s: str) -> str:
    """ID normalisé (pour éviter les doublons dans les suggestions)."""
    return re.sub(r"\s+", " ", (s or "").strip().lower().rstrip("?.!"))


def find_best_qa_match(
    q: str,
    qa_items: List[QAItem],
    min_score: float = 0.80,
) -> Optional[Tuple[QAItem, float]]:
    """
    Cas 1 : question déjà dans la base.
    """
    q_tokens = _normalize_question(q)
    if not q_tokens:
        return None

    best_item: Optional[QAItem] = None
    best_score = 0.0

    for item in qa_items:
        t_tokens = _normalize_question(item.question)
        score = _jaccard_score(q_tokens, t_tokens)
        if score > best_score:
            best_score = score
            best_item = item

    if best_item and best_score >= min_score:
        return best_item, best_score
    return None


# ---------------------------------------------------------------------
# 4) Suggestions QA (keywords + sémantique)
# ---------------------------------------------------------------------
def is_keyword_like(q: str) -> bool:
    """
    On considère "mot-clé" si <= 2 mots.
    """
    tokens = _normalize_question(q)
    return len(tokens) <= 2


def suggest_questions_semantic(
    q: str,
    qa_items: List[QAItem],
    topn: int = 5,
) -> List[QAItem]:
    """Suggestions sémantiques (Jaccard)."""
    q_tokens = set(_normalize_question(q))
    if not q_tokens:
        return []

    scored: List[Tuple[float, QAItem]] = []
    for item in qa_items:
        t_tokens = set(_normalize_question(item.question))
        if not t_tokens:
            continue
        inter = q_tokens & t_tokens
        if not inter:
            continue
        score = len(inter) / len(t_tokens)
        scored.append((score, item))

    scored.sort(key=lambda x: x[0], reverse=True)
    return [it for _, it in scored[:topn]]


def suggest_questions_from_keywords(
    q: str,
    qa_items: List[QAItem],
) -> List[QAItem]:
    """
    Utilise SUGGEST_KEYWORDS :
    - si le mot-clé "it storm", "data", "portage", etc. apparaît dans q
    - on retourne les QA correspondantes.
    """
    if not SUGGEST_KEYWORDS:
        return []

    ql = (q or "").lower()
    results: List[QAItem] = []
    seen_ids = set()

    for key, questions in SUGGEST_KEYWORDS.items():
        if key.lower() in ql:
            for qc in questions:
                nid = _norm_id_router(qc)
                if nid in seen_ids:
                    continue
                seen_ids.add(nid)
                for item in qa_items:
                    if _norm_id_router(item.question) == nid:
                        results.append(item)
                        break

    return results


def get_suggestions_for_text(
    q: str,
    qa_items: List[QAItem],
    topn: int = 10,
) -> List[QAItem]:
    """
    Combine :
    - suggestions via keywords (suggest_keywords.json)
    - suggestions sémantiques (train.txt)
    """
    results: List[QAItem] = []
    seen_ids = set()

    # 1) depuis suggest_keywords.json
    kw_items = suggest_questions_from_keywords(q, qa_items)
    for it in kw_items:
        nid = _norm_id_router(it.question)
        if nid in seen_ids:
            continue
        seen_ids.add(nid)
        results.append(it)

    # 2) sémantique
    sem_items = suggest_questions_semantic(q, qa_items, topn=topn)
    for it in sem_items:
        nid = _norm_id_router(it.question)
        if nid in seen_ids:
            continue
        seen_ids.add(nid)
        results.append(it)

    return results


# ---------------------------------------------------------------------
# 5) Nettoyage des réponses (lisibilité)
# ---------------------------------------------------------------------
def _clean_qa_answer(ans: str) -> str:
    """
    Nettoie les réponses QA :
    - enlève les blocs « (variante XXX) ... »
    - enlève un préfixe "IT-STORM:" éventuel
    - ajoute un point final si besoin
    """
    if not ans:
        return ans

    # couper tout ce qui vient après les variantes
    ans2 = re.sub(r";\s*«\s*\(variante.*$", "", ans)
    # enlever un éventuel préfixe IT-STORM:
    ans2 = re.sub(r"^IT-STORM:\s*", "", ans2, flags=re.IGNORECASE)

    ans2 = ans2.strip(" ;,\n\t")
    if ans2 and ans2[-1] not in ".!?":
        ans2 += "."
    return ans2


def _clean_rag_answer(ans: str) -> str:
    """
    Nettoie les réponses RAG :
    - enlève '### PAGE', 'URL:', 'NIVEAU:'
    """
    if not ans:
        return ans

    ans = re.sub(
        r"### PAGE ?:[^\n]*\nURL:[^\n]*\nNIVEAU:[^\n]*\n?",
        "",
        ans,
        flags=re.IGNORECASE,
    )

    lines = []
    for line in ans.splitlines():
        ls = line.strip()
        us = ls.upper()
        if us.startswith("### PAGE") or us.startswith("PAGE:"):
            continue
        if us.startswith("URL:"):
            continue
        if us.startswith("NIVEAU:"):
            continue
        lines.append(ls)

    ans = " ".join(l for l in lines if l)
    return ans.strip()


# ---------------------------------------------------------------------
# 6) Hors périmètre
# ---------------------------------------------------------------------
OUT_OF_SCOPE_MSG = (
    "Ce système répond uniquement aux questions liées à IT-STORM, "
    "au cloud, à la data, au DevOps, à l'IA et aux projets associés."
)

IT_TERMS = [
    "it storm", "it-storm", "itstorm",
    "consulting", "portage", "cloud", "data", "données",
    "devops", "ia", "intelligence artificielle",
    "kubernetes", "docker", "pipeline", "rag",
]


def is_out_of_scope(q: str) -> bool:
    qn = (q or "").lower()
    return not any(t in qn for t in IT_TERMS)


# ---------------------------------------------------------------------
# 7) Fallback RAG
# ---------------------------------------------------------------------
def answer_with_rag(q: str) -> str:
    res = smart_rag_answer(question=q)
    ans = (res or {}).get("answer", "").strip()
    if not ans or ans.lower().startswith("je ne sais pas"):
        return ""
    return _clean_rag_answer(ans)


# ---------------------------------------------------------------------
# 8) Routeur principal
# ---------------------------------------------------------------------
def route_question(q: str) -> str:
    """
    1) Hors périmètre -> OUT_OF_SCOPE_MSG
    2) Mot-clé -> SUGGEST:... (pas de RAG)
    3) Question dans la base -> réponse QA nettoyée
    4) Sinon -> RAG nettoyé
    5) Sinon -> SUGGEST ou "Je ne sais pas."
    """
    q = (q or "").strip()
    if not q:
        return "Merci de reformuler ta question."

    # 1) Hors périmètre
    if is_out_of_scope(q):
        return OUT_OF_SCOPE_MSG

    # 2) Mot-clé -> suggestions
    if is_keyword_like(q):
        suggs = get_suggestions_for_text(q, QA_ITEMS, topn=20)
        if suggs:
            s0 = suggs[0]
            return (
                "SUGGEST:" + s0.question + "\n"
                f"SOURCE:{s0.path}\n"
                "IF_YES_ANSWER:" + _clean_qa_answer(s0.answer)
            )
        return "Je ne sais pas."

    # 3) Question connue -> QA
    best = find_best_qa_match(q, QA_ITEMS, min_score=0.80)
    if best:
        item, score = best
        return _clean_qa_answer(item.answer)

    # 4) Nouveau mais dans le périmètre -> RAG
    rag_ans = answer_with_rag(q)
    if rag_ans:
        return rag_ans

    # 5) Dernier recours -> suggestion QA
    suggs = get_suggestions_for_text(q, QA_ITEMS, topn=5)
    if suggs:
        s0 = suggs[0]
        return (
            "SUGGEST:" + s0.question + "\n"
            f"SOURCE:{s0.path}\n"
            "IF_YES_ANSWER:" + _clean_qa_answer(s0.answer)
        )

    return "Je ne sais pas."
