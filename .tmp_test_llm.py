import os
from transformers import AutoTokenizer, AutoModelForSeq2SeqLM, pipeline

model_id = "google/flan-t5-small"
tok = AutoTokenizer.from_pretrained(model_id)
mdl = AutoModelForSeq2SeqLM.from_pretrained(model_id)
pipe = pipeline("text2text-generation", model=mdl, tokenizer=tok, device=-1)

out = pipe("Réponds: 2+2=? (réponds seulement par le nombre)", max_new_tokens=10)
print(out[0]["generated_text"])
