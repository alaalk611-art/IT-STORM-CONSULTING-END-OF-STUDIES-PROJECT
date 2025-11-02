# src/chatbot.py
from __future__ import annotations
from pathlib import Path
from functools import lru_cache
from typing import Callable, Dict, List, Any, Optional

def _safe_get_answer(res: Any) -> str:
    # Essaye de récupérer un texte depuis divers formats (dict LCEL, str, etc.)
    if isinstance(res, str):
        return res.strip()
    if isinstance(res, dict):
        for k in ("answer", "result", "output_text", "text", "content"):
            if k in res and res[k]:
                return str(res[k]).strip()
        return str(res).strip()
    return str(res).strip()

@lru_cache(maxsize=1)
def get_chain_cached(k: int = 4):
    """
    Retourne une instance de la chaîne RAG (mise en cache process).
    Ne dépend que du paramètre k (Top-K).
    """
    from src.rag.chain import build_rag_chain  # import tardif pour éviter cycles
    return build_rag_chain(k=k)

def ask_rag(
    question: str,
    k: int = 4,
    get_sources_fn: Optional[Callable[[str, int], List[str]]] = None,
    topn_suggestions: int = 5,
) -> Dict[str, Any]:
    """
    Pose une question au moteur RAG.
    - question : texte de la question
    - k : Top-K retrieval (pour get_sources_fn si fourni)
    - get_sources_fn : fonction optionnelle qui reçoit (question, k) et renvoie une liste de noms de fichiers
    - topn_suggestions : nombre de suggestions de reformulation en cas de "Je ne sais pas"
    Retour:
      { "answer": str, "sources": [str], "suggestions": [str] }
    """
    chain = get_chain_cached(k=k)

    # 1) Invoquer la chaîne
    try:
        # Tente plusieurs signatures possibles
        try:
            out = chain.invoke({"query": question})
        except Exception:
            try:
                out = chain.invoke(question)
            except Exception:
                try:
                    out = chain.run(question)
                except Exception as e:
                    return {"answer": f"[Erreur RAG] {e}", "sources": [], "suggestions": []}
        answer = _safe_get_answer(out) or ""
    except Exception as e:
        return {"answer": f"[Erreur RAG] {e}", "sources": [], "suggestions": []}

    # 2) Sources (optionnel — via callback)
    sources: List[str] = []
    if get_sources_fn:
        try:
            sources = list(dict.fromkeys(get_sources_fn(question, k)))  # unique, ordre conservé
        except Exception:
            sources = []

    # 3) Suggestions si "Je ne sais pas"
    suggestions: List[str] = []
    if answer.strip().lower() in {"je ne sais pas", "je ne sais pas."}:
        try:
            # Si la chaîne expose suggest_questions(topn=..)
            if hasattr(chain, "suggest_questions"):
                sugs = chain.suggest_questions(question, topn=topn_suggestions) or []
                # sugs = objets avec .q_raw, sinon string
                for s in sugs:
                    if isinstance(s, str):
                        suggestions.append(s)
                    else:
                        q = getattr(s, "q_raw", None)
                        if q:
                            suggestions.append(q)
        except Exception:
            pass

    return {"answer": answer, "sources": sources, "suggestions": suggestions}
# =============================