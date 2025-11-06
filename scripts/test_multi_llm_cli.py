# -*- coding: utf-8 -*-
"""
Test rapide Multi-LLM (CLI) — StormCopilot
- Interroge 3 modèles Ollama (configurables)
- Construit un contexte RAG UNIQUEMENT depuis it_storm_1000_QA.txt
- Normalisation question/texte (accents, espaces, variantes "it-storm")
- Retrieval déterministe (tie-breaks)
- Filtre anti-hallucination (extractif) + citation normalisée
- Métriques + Support + Confiance (≥ 0.95 si ancrage fort)

Usage:
  python scripts/test_multi_llm_cli.py --q "C'est quoi IT-STORM ?" \
      --models "mistral:7b-instruct,llama3.2:3b,qwen2.5:7b" \
      --file "C:\\Users\\ALA BEN LAKHAL\\Desktop\\intelligent_copilot IT-STORM\\data\\it_storm_1000_QA.txt" \
      --topk 6 --timeout 60
"""

from __future__ import annotations
import os, re, time, argparse, unicodedata
from pathlib import Path
from typing import List, Tuple, Dict

# --- ensure project root on sys.path (src/ is under project root) ---
import sys
ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

# ---- Import du client Ollama (version adaptive) ----
try:
    from src.llm.ollama_client import generate_ollama, get_base, ping, list_models
except Exception as e:
    raise SystemExit(f"[FATAL] Impossible d'importer src.llm.ollama_client: {e}")

# ----------------- Config par défaut -----------------
DEF_QUESTION = "C'est quoi IT-STORM ?"
DEF_MODELS = "mistral:7b-instruct,llama3.2:3b,qwen2.5:7b"
DEF_FILE = (
    os.getenv("RAG_ONLY_FILE")
    or r"C:\Users\ALA BEN LAKHAL\Desktop\intelligent_copilot IT-STORM\data\it_storm_1000_QA.txt"
)

# ----------------- Normalisation robuste -----------------
def _strip_accents(s: str) -> str:
    return "".join(c for c in unicodedata.normalize("NFD", s) if unicodedata.category(c) != "Mn")

def _canon(s: str) -> str:
    s = (s or "").strip().lower()
    s = _strip_accents(s)
    # Variantes usuelles de la marque
    s = s.replace("it storm", "it-storm").replace("itstorm", "it-storm")
    s = re.sub(r"\s+", " ", s)
    return s

# ----------------- Helpers RAG (fichier unique) -----------------
def _norm(p: str) -> str:
    try: return str(Path(p).resolve())
    except Exception: return p

def _read_only_file(path: str) -> str:
    p = Path(_norm(path))
    if not p.exists():
        return ""
    try:
        return p.read_text(encoding="utf-8", errors="ignore")
    except Exception:
        return ""

def retrieve_from_single_file(query: str, file_path: str, k: int = 6) -> List[Tuple[str,str,float]]:
    """
    Retrieval déterministe sur un seul fichier:
    - split par paragraphes (double newline)
    - score = nombre d'occurrences des termes canonisés
    - tri stable: (dist_like asc, score desc, longueur desc, index asc)
    """
    raw = _read_only_file(file_path)
    if not raw:
        return []

    paras = [p.strip() for p in re.split(r"\n{2,}", raw) if p.strip()]
    q_can = _canon(query)
    q_terms = [w for w in re.findall(r"[a-z0-9\-]+", q_can) if len(w) > 2]

    scored = []
    for idx, p in enumerate(paras):
        txt_can = _canon(p)
        score = sum(txt_can.count(t) for t in q_terms) or 0
        if score > 0:
            # dist_like = 1/(score+eps)
            scored.append((p, _norm(file_path), 1.0/(score+1e-6), -score, -len(txt_can), idx))

    if not scored and paras:
        # aucun match → prends un paragraphe informatif
        p0 = paras[0]
        scored.append((p0[:900], _norm(file_path), 1.0, 0, -len(_canon(p0)), 0))

    scored.sort(key=lambda x: (x[2], x[3], x[4], x[5]))
    return [(p, src, dist) for (p, src, dist, *_rest) in scored[:k]]

def build_context(chunks: List[Tuple[str,str,float]]) -> str:
    parts=[]
    for text, src, _ in chunks:
        parts.append(f"[Source: {Path(src).name}] {text}")
    return "\n\n".join(parts)

# ----------------- Prompt strict -----------------
RAG_SYSTEM_PROMPT = """Tu es un assistant de conseil IT-STORM.
Réponds UNIQUEMENT avec les informations présentes dans le CONTEXTE.
Si la réponse n’y est pas, écris exactement: "Je ne sais pas.".

Contraintes:
- Français
- ≤ 8 lignes
- 1 à 3 puces max si pertinent
- Cite les sources entre crochets sous la forme [Source: fichier.ext]
- Pas d’invention, pas d’URL externes.
"""

def build_user_prompt(question: str, context: str) -> str:
    return f"""{RAG_SYSTEM_PROMPT}

QUESTION:
{question}

CONTEXTE:
{context}

RÉPONSE:
""".strip()

# ----------------- Anti-hallucination (support contexte) -----------------
def _ngrams(tokens, n=3):
    return {" ".join(tokens[i:i+n]) for i in range(len(tokens)-n+1)} if len(tokens) >= n else set()

def _tok(s: str):
    return re.findall(r"[a-z0-9\-]+", _canon(s))

def sentence_support_ratio(sentence: str, context: str, ngram_n: int = 3) -> float:
    s_tokens = _tok(sentence)
    c_tokens = _tok(context)
    if not s_tokens or not c_tokens:
        return 0.0
    s_ngr = _ngrams(s_tokens, n=ngram_n)
    c_ngr = _ngrams(c_tokens, n=ngram_n)
    if s_ngr and c_ngr:
        inter = len(s_ngr & c_ngr)
        if inter > 0:
            return 1.0
    # fallback: Jaccard tokens
    s_set, c_set = set(s_tokens), set(c_tokens)
    j = len(s_set & c_set) / max(1, len(s_set | c_set))
    return j  # 0..1

def enforce_strict_grounding(answer: str, context: str, thr: float = 0.12) -> str:
    """
    Garde uniquement les phrases qui ont un recouvrement suffisant avec le CONTEXTE.
    """
    raw_lines = re.split(r"\n+", (answer or "").strip())
    kept_lines = []
    for line in raw_lines:
        parts = re.split(r"(?<=[\.\!\?…])\s+", line)
        kept_parts = []
        for part in parts:
            s = part.strip()
            if not s:
                continue
            support = sentence_support_ratio(s, context)
            if support >= thr:
                kept_parts.append(s)
        if kept_parts:
            kept_lines.append(" ".join(kept_parts))
    clean = "\n".join(kept_lines).strip()
    return clean if clean else 'Je ne sais pas.'

def overall_support(answer: str, context: str) -> float:
    sents = [s.strip() for s in re.split(r"[\.!\?…]+", answer or "") if s.strip()]
    if not sents:
        return 0.0
    vals = [sentence_support_ratio(s, context) for s in sents]
    return sum(vals)/len(vals)

# ----------------- Métriques -----------------
def _norm_text(s: str) -> str:
    return re.sub(r"\s+", " ", _canon(s)).strip()

def metric_coverage(question: str, answer: str) -> float:
    q = _norm_text(question)
    a = _norm_text(answer)
    # synonymes/variantes déjà gérées par _canon
    stop = {"le","la","les","un","une","des","de","du","et","en","dans","pour","avec","sur","ou","au","aux","est","c","d"}
    q_tokens = [w for w in re.findall(r"[a-z0-9\-]+", q) if w not in stop]
    a_tokens = set(re.findall(r"[a-z0-9\-]+", a))
    if not q_tokens:
        return 0.6
    hit = sum(1 for w in q_tokens if w in a_tokens)
    return min(1.0, hit / max(3, len(q_tokens)))

def metric_style(answer: str) -> float:
    a = _norm_text(answer)
    if not a or "je ne sais pas" in a:
        return 0.5
    sents = re.split(r"[\.!?…]+", a)
    sents = [s.strip() for s in sents if s.strip()]
    if not sents:
        return 0.6
    avg_len = sum(len(s) for s in sents)/len(sents)
    score_len = 1.0 if 40 <= avg_len <= 220 else 0.7
    bullets = len(re.findall(r"^\s*[-•]", answer, flags=re.M))
    score_bul = 1.0 if bullets <= 3 else 0.7
    score_cit = 1.0 if re.search(r"\[source:", answer, flags=re.I) else 0.8
    return max(0.0, min(1.0, 0.5*score_len + 0.3*score_bul + 0.2*score_cit))

def metric_grounding(answer: str, target_basename: str, support: float) -> float:
    """
    Grounding = 1.0 si:
      - la réponse cite explicitement [Source: <basename>] ET
      - support (recouvrement contexte) >= 0.60.
    Sinon: base sur nb de tags, bonus si la bonne source apparaît.
    """
    if not answer:
        return 0.0
    has_target = re.search(
        rf"\[source:\s*{re.escape(target_basename)}\s*\]", answer, flags=re.I
    ) is not None
    tags = re.findall(r"\[source:\s*([^\]]+)\]", answer, flags=re.I)
    uniq = len(set(_canon(t) for t in tags))
    if has_target and support >= 0.60:
        return 1.0
    base = 0.5 + 0.25 * min(3, uniq)
    if has_target:
        base = max(base, 0.9 if support >= 0.40 else 0.85)
    return max(0.0, min(1.0, base))

def metric_confidence(answer: str,
                      context_chunks: List[Tuple[str,str,float]],
                      grounding: float,
                      support: float,
                      target_basename: str) -> float:
    """
    Confiance = combinaison (grounding, longueur, présence de contexte, support)
    + plancher 0.95 si conditions "zéro hallucination" remplies.
    """
    if not (answer or "").strip():
        return 0.0
    L = len(answer.strip())
    if L < 40:
        len_score = 0.6
    elif L > 1800:
        len_score = 0.7
    else:
        len_score = 1.0
    ctx_bonus = 0.9 if context_chunks else 0.7
    conf = (0.5 * grounding) + (0.2 * len_score) + (0.2 * ctx_bonus) + (0.1 * max(0.0, min(1.0, support)))
    conf = min(1.0, max(0.0, conf))
    has_target = re.search(rf"\[source:\s*{re.escape(target_basename)}\s*\]", answer or "", flags=re.I) is not None
    if grounding >= 0.95 and support >= 0.60 and has_target and 60 <= L <= 220:
        conf = max(conf, 0.95)
    return round(conf, 2)

def compute_all_metrics(question: str,
                        answer: str,
                        chunks: List[Tuple[str,str,float]],
                        target_basename: str,
                        support: float) -> Dict[str, float]:
    if not answer or answer.strip().startswith("[Erreur LLM"):
        return {"confidence": 0.0, "grounding": 0.0, "coverage": 0.0, "style": 0.0}
    g = metric_grounding(answer, target_basename, support)
    return {
        "confidence": metric_confidence(answer, chunks, g, support, target_basename),
        "grounding":  round(g, 2),
        "coverage":   round(metric_coverage(question, answer), 2),
        "style":      round(metric_style(answer), 2),
    }

def score_for_ranking(m: Dict[str, float]) -> float:
    return round(0.4*m.get("confidence",0) + 0.3*m.get("grounding",0)
                 + 0.2*m.get("coverage",0) + 0.1*m.get("style",0), 3)

# ----------------- Main -----------------
def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--q", "--question", dest="question", default=DEF_QUESTION, help="Question en français")
    ap.add_argument("--models", default=DEF_MODELS, help="Liste de modèles Ollama, séparés par des virgules")
    ap.add_argument("--file", default=DEF_FILE, help="Chemin du fichier it_storm_1000_QA.txt")
    ap.add_argument("--topk", type=int, default=6, help="Top-K context")
    ap.add_argument("--timeout", type=float, default=60.0, help="Timeout par modèle (secondes)")
    args = ap.parse_args()

    models = [m.strip() for m in args.models.split(",") if m.strip()]
    file_path = args.file
    target_basename = Path(file_path).name

    # Diagnostic Ollama
    base = get_base() if "get_base" in globals() or "get_base" in dir() else os.getenv("OLLAMA_BASE_URL", "http://127.0.0.1:11434")
    print(f"🧪 Ollama base: {base}")
    try:
        ok = ping()
        avail = list_models() if ok else []
        print(f"Ping: {'OK' if ok else 'KO'} · Models: {', '.join(avail) if avail else '—'}")
    except Exception as e:
        print(f"[WARN] Diagnostic Ollama partiel: {e}")

    # Contexte
    chunks = retrieve_from_single_file(args.question, file_path, k=args.topk)
    context = build_context(chunks) if chunks else ""
    if not context:
        print(f"[WARN] Aucun contexte trouvé dans {file_path}")
    prompt = build_user_prompt(args.question, context)

    print("\n" + "="*80)
    print(f"Question: {args.question}")
    print(f"Fichier:  {file_path}")
    print(f"Modèles:  {', '.join(models)}")
    print("="*80 + "\n")

    results = []
    for mdl in models:
        t0 = time.time()
        try:
            ans = generate_ollama(
                mdl, prompt,
                temperature=0.0,
                max_tokens=160,  # concis = plus rapide + meilleur style
                stream=True,
                timeout=float(args.timeout),
                options={"num_ctx": 1536, "top_k": 40, "top_p": 0.9, "repeat_penalty": 1.1}
            )
            backend = "ollama"
        except Exception as e:
            ans = f"[Erreur LLM {mdl}] {e}"
            backend = "error"
        dt = time.time() - t0

        # Ajout auto de la citation si contexte présent et citation absente
        if context and not re.search(rf"\[source:\s*{re.escape(target_basename)}\s*\]", ans or "", flags=re.I):
            ans = (ans or "").rstrip() + f" [Source: {target_basename}]"

        # Filtre adaptatif: tolérer un peu plus pour certaines requêtes
        thr = 0.10 if "portage salarial" in _canon(args.question) else 0.12
        ans = enforce_strict_grounding(ans, context, thr=thr)

        # Métriques + Support
        support = overall_support(ans, context)
        metrics = compute_all_metrics(args.question, ans, chunks, target_basename, support)
        score = score_for_ranking(metrics)
        if support < 0.10:
            score *= 0.6
            score = round(score, 3)

        results.append({
            "model": mdl, "backend": backend, "answer": ans, "time": dt,
            "metrics": metrics, "support": round(support, 2), "score": score
        })

        # Affichage
        print(f"--- {mdl} · backend: {backend} · {dt:.2f}s · score: {score}")
        if backend == "error" or (ans or "").strip().startswith("[Erreur LLM"):
            print(ans + "\n")
        else:
            print(ans.strip() + "\n")
            print(f"Confiance: {metrics['confidence']}  |  Grounding: {metrics['grounding']}  |  Couverture: {metrics['coverage']}  |  Style: {metrics['style']}  |  Support: {support:.2f}")
            print("-"*80)

    # Tri & suggestion
    valid = [r for r in results if r["backend"] != "error" and not r["answer"].strip().startswith("[Erreur LLM")]
    if valid:
        best = max(valid, key=lambda x: x["score"])
        print(f"\n✅ Suggestion: privilégier {best['model']} (score {best['score']}, {best['time']:.2f}s)")
    else:
        print("\n⚠️ Aucune réponse valide (toutes en erreur ou vides). Vérifie Ollama / modèles / temps d’attente.")

if __name__ == "__main__":
    main()
