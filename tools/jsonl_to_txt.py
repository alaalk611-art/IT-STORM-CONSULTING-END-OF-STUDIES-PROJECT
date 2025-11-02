# tools/jsonl_to_txt.py
import sys, json
from pathlib import Path

def pick_fields(obj: dict):
    """Retourne (question, answer) à partir des champs courants."""
    q = obj.get("question") or obj.get("query") or obj.get("prompt") or ""
    # on essaie d'abord 'answer', sinon 'expected_answer'
    a = obj.get("answer")
    if a is None:
        a = obj.get("expected_answer")
    if isinstance(a, dict):
        # si la réponse est un dict (rare), on tente quelques clés
        a = a.get("text") or a.get("answer") or a.get("output_text") or a.get("content")
    if a is None:
        a = ""
    return str(q).strip(), str(a).strip()

def main():
    if len(sys.argv) < 3:
        print("Usage: python -m tools.jsonl_to_txt <input.jsonl> <output.txt>")
        sys.exit(1)

    inp = Path(sys.argv[1])
    outp = Path(sys.argv[2])

    if not inp.exists():
        print(f"❌ Fichier introuvable: {inp}")
        sys.exit(2)

    outp.parent.mkdir(parents=True, exist_ok=True)
    n_ok = 0; n_skip = 0

    with open(inp, "r", encoding="utf-8") as fin, open(outp, "w", encoding="utf-8") as fout:
        for line in fin:
            line = line.strip()
            if not line:
                continue
            try:
                obj = json.loads(line)
            except Exception:
                n_skip += 1
                continue

            q, a = pick_fields(obj)
            if not q and not a:
                n_skip += 1
                continue

            fout.write(f"Q: {q}\n")
            fout.write(f"A: {a}\n\n---\n\n")
            n_ok += 1

    print(f"✅ Export: {outp} ({n_ok} paires, {n_skip} ignorées)")

if __name__ == "__main__":
    main()
