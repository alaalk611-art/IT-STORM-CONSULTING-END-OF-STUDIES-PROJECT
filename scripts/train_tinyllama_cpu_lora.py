# scripts/train_tinyllama_cpu_lora.py
# TRL 0.23.0 · CPU only · LoRA (pas de 4-bit)
# Dataset JSONL attendu (1 objet JSON par ligne) :
#   data/finetune/train.jsonl
#   data/finetune/val.jsonl

import os
from pathlib import Path
from datasets import load_dataset
from transformers import (
    AutoModelForCausalLM,
    AutoTokenizer,
    TrainingArguments,
    set_seed,
)
from trl import SFTTrainer
from peft import LoraConfig, TaskType

# ----------------------------
# Chemins robustes
# ----------------------------
THIS_FILE = Path(__file__).resolve()
REPO_ROOT = THIS_FILE.parents[1]
DATA_DIR  = REPO_ROOT / "data" / "finetune"
OUT_DIR_D = REPO_ROOT / "out" / "ft-tinyllama-cpu"
DATA_DIR.mkdir(parents=True, exist_ok=True)
OUT_DIR_D.mkdir(parents=True, exist_ok=True)

# ----------------------------
# Paramètres (env override ok)
# ----------------------------
BASE_MODEL  = os.environ.get("BASE_MODEL", "TinyLlama/TinyLlama-1.1B-Chat-v1.0")
DATA_TRAIN  = os.environ.get("DATA_TRAIN", str(DATA_DIR / "train.jsonl"))
DATA_VAL    = os.environ.get("DATA_VAL",   str(DATA_DIR / "val.jsonl"))
OUT_DIR     = os.environ.get("OUT_DIR",    str(OUT_DIR_D))
SEQ_LEN     = int(os.environ.get("SEQ_LEN", "512"))     # 384 si RAM serrée
ACCUM_STEPS = int(os.environ.get("ACCUM_STEPS", "16"))  # 32 si RAM serrée
EPOCHS      = float(os.environ.get("EPOCHS", "1"))
LR          = float(os.environ.get("LR", "2e-4"))
SEED        = int(os.environ.get("SEED", "42"))

set_seed(SEED)

print("== Config ==")
print("BASE_MODEL :", BASE_MODEL)
print("DATA_TRAIN :", DATA_TRAIN)
print("DATA_VAL   :", DATA_VAL)
print("OUT_DIR    :", OUT_DIR)
print("SEQ_LEN    :", SEQ_LEN, "| ACCUM_STEPS:", ACCUM_STEPS, "| EPOCHS:", EPOCHS, "| LR:", LR)

# ----------------------------
# 1) Dataset → colonne "text"
# ----------------------------
dataset = load_dataset("json", data_files={"train": DATA_TRAIN, "eval": DATA_VAL})

def to_text(ex):
    instr = (ex.get("instruction") or "").strip()
    inp   = (ex.get("input") or "").strip()
    out   = (ex.get("output") or "").strip()
    if inp:
        prompt = f"### Instruction:\n{instr}\n\n### Input:\n{inp}\n\n### Response:\n{out}"
    else:
        prompt = f"### Instruction:\n{instr}\n\n### Response:\n{out}"
    return {"text": prompt}

dataset = dataset.map(to_text, remove_columns=dataset["train"].column_names)

# ----------------------------
# 2) Tokenizer (contrôle longueur)
# ----------------------------
tok = AutoTokenizer.from_pretrained(BASE_MODEL, use_fast=True)
if tok.pad_token is None:
    tok.pad_token = tok.eos_token
tok.model_max_length = SEQ_LEN
tok.padding_side = "right"

# ----------------------------
# 3) LoRA léger (CPU-friendly)
# ----------------------------
peft_cfg = LoraConfig(
    r=8,
    lora_alpha=16,
    lora_dropout=0.05,
    task_type=TaskType.CAUSAL_LM,
    target_modules=["q_proj","k_proj","v_proj","o_proj","gate_proj","up_proj","down_proj"],
)

# ----------------------------
# 4) Modèle base (CPU)
# ----------------------------
model = AutoModelForCausalLM.from_pretrained(BASE_MODEL)
# Option RAM: activer si besoin
# model.gradient_checkpointing_enable()

# ----------------------------
# 5) Entraînement (Transformers + TRL)
# ----------------------------
training_args = TrainingArguments(
    output_dir=OUT_DIR,
    num_train_epochs=EPOCHS,
    per_device_train_batch_size=1,
    gradient_accumulation_steps=ACCUM_STEPS,
    learning_rate=LR,
    lr_scheduler_type="cosine",
    warmup_ratio=0.03,
    logging_steps=10,
    save_steps=200,
    bf16=False,                 # CPU
    optim="adamw_torch",
)

# TRL 0.23.0 :
# - pas de tokenizer=...
# - pas de dataset_text_field=...
# - pas de packing=...
# -> utiliser processing_class=tok + formatting_func
trainer = SFTTrainer(
    model=model,
    args=training_args,
    train_dataset=dataset["train"],
    eval_dataset=dataset.get("eval"),
    peft_config=peft_cfg,

    processing_class=tok,                  # tokenizer/processor
    formatting_func=lambda ex: ex["text"], # lit la colonne "text"
    # pas de max_seq_length, pas de packing
)

# ----------------------------
# 6) Train + save adapter
# ----------------------------
trainer.train()
save_dir = Path(OUT_DIR) / "adapter"
trainer.model.save_pretrained(save_dir)
tok.save_pretrained(save_dir)
print(f"✅ Adapter LoRA sauvegardé dans: {save_dir}")
