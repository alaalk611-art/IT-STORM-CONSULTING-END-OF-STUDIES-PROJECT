# scripts/test_adapter_cpu.py
from transformers import AutoTokenizer, AutoModelForCausalLM
from peft import PeftModel
import torch

BASE = "TinyLlama/TinyLlama-1.1B-Chat-v1.0"
ADAPTER_DIR = "out/ft-tinyllama-cpu/adapter"  # ajuste si besoin

tok = AutoTokenizer.from_pretrained(ADAPTER_DIR)     # tokenizer sauvegardé avec l'adapter
base = AutoModelForCausalLM.from_pretrained(BASE)    # CPU
model = PeftModel.from_pretrained(base, ADAPTER_DIR)
model.eval()

# 1) Construire un "chat prompt" avec le template du tokenizer
messages = [
    {"role": "user", "content": "Explique en 3 puces le rôle d'un adapter LoRA pour TinyLlama."}
]
prompt = tok.apply_chat_template(messages, tokenize=False, add_generation_prompt=True)

# 2) Tokeniser et générer
inputs = tok(prompt, return_tensors="pt")
with torch.no_grad():
    outputs = model.generate(
        **inputs,
        max_new_tokens=200,
        do_sample=False,          # si tu veux échantillonner, passe True et ajoute temperature=0.7
        repetition_penalty=1.1,
        pad_token_id=tok.eos_token_id,
        eos_token_id=tok.eos_token_id,
    )

text = tok.decode(outputs[0], skip_special_tokens=False)

# 3) Afficher uniquement la "réponse" (sans reprint le prompt)
generated_only = text[len(prompt):].strip()
print("\n=== Réponse ===\n", generated_only if generated_only else "[Sortie vide]")
# Fin du script