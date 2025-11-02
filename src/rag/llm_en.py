# src/rag_en/llm_en.py
from __future__ import annotations
import os
from transformers import AutoTokenizer, AutoModelForSeq2SeqLM, pipeline

MODEL_NAME_EN = os.getenv("LLM_MODEL_EN", "google/flan-t5-base")
DEVICE = int(os.getenv("LLM_DEVICE", "-1"))

def get_llm_en():
    """Return an English generation pipeline (Flan-T5-base)."""
    tok = AutoTokenizer.from_pretrained(MODEL_NAME_EN)
    tok.model_max_length = 600
    tok.truncation_side = "right"

    mdl = AutoModelForSeq2SeqLM.from_pretrained(MODEL_NAME_EN)

    gen = pipeline(
        "text2text-generation",
        model=mdl,
        tokenizer=tok,
        device=DEVICE,
        max_new_tokens=300,
        min_new_tokens=200,
        num_beams=1,
        do_sample=True,
        top_p=0.9,
        temperature=1.0,
        early_stopping=True,
        length_penalty=0.9,
        repetition_penalty=1.15,
        no_repeat_ngram_size=4,
    )
    return gen
