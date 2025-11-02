# src/rag/llm.py
from __future__ import annotations
import os
from transformers import AutoTokenizer, AutoModelForSeq2SeqLM, pipeline

# ===== Config =====
MODEL_NAME = os.getenv("LLM_MODEL", "google/flan-t5-base")  # English-only generation
DEVICE = int(os.getenv("LLM_DEVICE", "-1"))  # -1 = CPU, >=0 = GPU id

def get_llm():
    """
    Text2Text pipeline with FLAN-T5-base tuned for stable 5-sentence summaries.
    """
    tok = AutoTokenizer.from_pretrained(MODEL_NAME)
    tok.model_max_length = 512
    tok.truncation_side = "right"

    mdl = AutoModelForSeq2SeqLM.from_pretrained(MODEL_NAME)

    gen = pipeline(
        task="text2text-generation",
        model=mdl,
        tokenizer=tok,
        device=DEVICE,
        # Passed to model.generate()
        max_new_tokens=300,       # allow finishing the last sentence
        min_new_tokens=200,       # avoid too-short outputs
        num_beams=5,              # stability over sampling
        early_stopping=True,      # stop cleanly on EOS
        length_penalty=1.0,
        do_sample=False,          # deterministic
        repetition_penalty=1.20,  # discourage loops
        no_repeat_ngram_size=4,   # reduce duplicate n-grams
        truncation=True,
        clean_up_tokenization_spaces=True,
    )
    return gen
