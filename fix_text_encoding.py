from pathlib import Path

FILES = [
    Path(r"data\raw\itstorm_site.txt"),
    Path(r"data\raw\itstorm_rag_global.txt"),
]

def looks_mojibake(s: str) -> bool:
    return any(x in s for x in ["Ã", "â€™", "â€", "Â", "prÃ", "dâ", "lâ"])

def fix_mojibake(s: str) -> str:
    # Corrige "prÃ©sente" -> "présente" si le texte a été mal décodé
    try:
        return s.encode("latin1").decode("utf-8")
    except Exception:
        return s

for fp in FILES:
    if not fp.exists():
        print(f"[SKIP] not found: {fp.resolve()}")
        continue

    raw = fp.read_bytes()

    # 1) On tente UTF-8
    try:
        text = raw.decode("utf-8")
        decoded_as = "utf-8"
    except UnicodeDecodeError:
        # 2) Sinon latin-1
        text = raw.decode("latin1")
        decoded_as = "latin1"

    before = text
    if looks_mojibake(text):
        text = fix_mojibake(text)

    # Sauvegarde finale en UTF-8
    fp.write_text(text, encoding="utf-8", newline="\n")

    print(f"[OK] {fp} decoded_as={decoded_as} changed={before != text}")
