# src/ui/tabs/rag_en_tab.py
from __future__ import annotations
import os
from pathlib import Path
import inspect
import streamlit as st

# =============================
# Helpers — apply runtime config
# =============================
def _try_apply_runtime_config(chain, temperature: float | None, top_k: int | None):
    """
    Tente d'appliquer des réglages à chaud sur une chaîne LCEL/LC :
    - search_kwargs.k
    - llm_temperature / temperature
    - top_k (alias)
    Ignore proprement si non supporté.
    """
    # Variante LCEL: with_config(configurable=...)
    try:
        if hasattr(chain, "with_config"):
            cfg = {}
            if top_k is not None:
                cfg.setdefault("search_kwargs", {})["k"] = int(top_k)
                cfg["top_k"] = int(top_k)
            if temperature is not None:
                # différents noms possibles
                cfg["llm_temperature"] = float(temperature)
                cfg["temperature"] = float(temperature)
            return chain.with_config(configurable=cfg)
    except Exception:
        pass
    return chain

# =============================
# RAG EN — builders & caching
# =============================
@st.cache_resource(show_spinner=False)
def _load_chain_en(top_k: int | None = None, temperature: float | None = None):
    """
    Charge la chaîne RAG EN en essayant plusieurs signatures.
    Ordre:
      1) build_rag_chain_en(top_k=?, temperature=?)
      2) build_rag_chain_en(top_k=?)
      3) build_rag_chain_en()
      4) build_rag_chain(...)
      5) get_chain_en(...)
    Si aucun ne marche, on tente via variables d'env puis on re-applique une config runtime.
    """
    builder = None
    # 1) builder principal recommandé
    try:
        from src.rag_en.chain_en import build_rag_chain_en as builder  # type: ignore
    except Exception:
        pass

    # 2) variantes courantes
    if builder is None:
        try:
            from src.rag_en.chain_en import build_rag_chain as builder  # type: ignore
        except Exception:
            pass
    if builder is None:
        try:
            from src.rag_en.chain_en import get_chain_en as builder  # type: ignore
        except Exception:
            pass

    if builder is None:
        raise RuntimeError(
            "Can't load EN chain. Expose build_rag_chain_en() (ou build_rag_chain / get_chain_en) "
            "dans src.rag_en.chain_en."
        )

    # On inspecte la signature pour savoir si les kwargs existent
    sig = None
    try:
        sig = inspect.signature(builder)
    except Exception:
        sig = None

    chain = None
    # 1) top_k + temperature
    if sig and all(p in sig.parameters for p in ("top_k", "temperature")):
        try:
            chain = builder(top_k=top_k, temperature=temperature)
        except Exception:
            chain = None
    # 2) seulement top_k
    if chain is None and sig and "top_k" in sig.parameters:
        try:
            chain = builder(top_k=top_k)
        except Exception:
            chain = None
    # 3) aucun param
    if chain is None:
        try:
            chain = builder()
        except Exception:
            chain = None

    # Plan B: variables d'environnement si builder ne supporte pas les kwargs
    # (beaucoup de chaînes les lisent au build)
    if chain is None:
        if top_k is not None:
            os.environ["RAG_TOPK_EN"] = str(top_k)
        if temperature is not None:
            os.environ["LLM_TEMPERATURE_EN"] = str(temperature)
        chain = builder()  # dernier essai

    # Application runtime (si possible)
    chain = _try_apply_runtime_config(chain, temperature, top_k)
    return chain

def _generate_answer(chain, query: str) -> str:
    """
    Normalise l'appel selon l'implémentation :
    - chain.generate_en(q)
    - chain.invoke / run
    - appel direct chain(q)
    """
    # API dédiée
    try:
        return str(chain.generate_en(query))
    except Exception:
        pass
    # LCEL invoke
    try:
        out = chain.invoke({"query": query})
        if isinstance(out, dict):
            for k in ("result", "answer", "output_text", "text", "content"):
                if k in out and out[k]:
                    return str(out[k])
        return str(out)
    except Exception:
        pass
    # run
    try:
        return str(chain.run(query))
    except Exception:
        pass
    # appel direct
    try:
        return str(chain(query))
    except Exception:
        pass
    return "[RAG EN] No compatible generate method found."

# =============================
# UI (tab)
# =============================
def render():
    st.subheader("🔎 English QA (RAG EN)")

    # DATA_DIR — clé unique pour éviter tout conflit avec d’autres tabs
    default_data_dir = os.getenv("DATA_DIR") or str(Path("data").resolve())
    data_dir = st.text_input(
        "DATA_DIR (folder containing /raw/*.txt)",
        value=default_data_dir,
        key="rag_en_data_dir",  # <= UNIQUE
        help="Path to your data folder containing /raw/*.txt files",
    )
    if data_dir and data_dir != os.getenv("DATA_DIR"):
        os.environ["DATA_DIR"] = data_dir
        st.info(f"DATA_DIR set to: {data_dir}. Click ‘Reload chain’ to re-init with this path.")

    # === NEW: controls ===
    c1, c2, c3 = st.columns([0.33, 0.33, 0.34])
    with c1:
        top_k = st.slider(
            "Top chunks (k)",
            min_value=1, max_value=12, value=4, step=1,
            key="rag_en_topk",
            help="Number of retrieved chunks from the vector index."
        )
    with c2:
        temperature = st.slider(
            "Temperature",
            min_value=0.0, max_value=1.5, value=0.2, step=0.05,
            key="rag_en_temperature",
            help="Higher = more diverse, lower = more deterministic."
        )
    with c3:
        if st.button("🔁 Reload chain", use_container_width=True, key="rag_en_reload"):
            # Invalide le cache pour forcer un rebuild avec les nouveaux params
            _load_chain_en.clear()
            st.success("RAG EN chain reloaded.")

    # Chargement (lazy) de la chaîne avec tes paramètres
    try:
        with st.spinner("Initializing RAG EN chain..."):
            chain = _load_chain_en(top_k=top_k, temperature=temperature)
        st.caption(f"✅ RAG EN ready · k={top_k} · temperature={temperature}")
    except Exception as e:
        st.error(f"❌ Failed to initialize RAG EN: {e}")
        st.stop()

    # Zone de question — clé unique
    query = st.text_input(
        "Ask your question in English",
        key="rag_en_query",
        help="Example: List the PoC deliverables from IT-STORM internal documents."
    )

    # Actions — clés uniques
    c4, c5 = st.columns([0.45, 0.55])
    with c4:
        run = st.button("🔎 Run RAG QA", use_container_width=True, key="rag_en_run")
    with c5:
        sample = st.selectbox(
            "Quick prompts",
            [
                "— Choose a sample —",
                "List the PoC deliverables.",
                "Give a concise Executive Summary (4–6 sentences).",
                "Summarize the proposed RAG architecture.",
                "What are the next steps and timeline?",
            ],
            key="rag_en_samples",
        )
        if sample and sample != "— Choose a sample —" and not query:
            query = sample

    if run:
        if not query or not query.strip():
            st.warning("Please enter a question.")
            return
        q = query.strip()
        if len(q) > 1200:
            st.info("Your question is long; truncating to 1200 chars for stability.")
            q = q[:1200]

        with st.spinner("Retrieving and generating..."):
            try:
                answer = _generate_answer(chain, q)
                st.markdown("#### Answer")
                st.write(answer)
            except Exception as e:
                st.error(f"[RAG EN] Failed to generate answer: {e}")

    with st.expander("ℹ️ Tips"):
        st.markdown(
            "- **Top chunks (k)** controls how many passages are retrieved; start small (3–6).\n"
            "- **Temperature** controls creativity; for QA on internal docs, 0.0–0.3 is usually safest.\n"
            "- After changing **DATA_DIR**, **k** or **temperature**, use **Reload chain** to rebuild."
        )

