# test_chain_en.py (mis à jour pour affichage immédiat)

import sys
import time
from chain_en import (
    build_rag_chain_en,
    _looks_non_english,
    _split_to_units,
    _looks_like_file_leak,
    _looks_like_instruction,
    _infer_theme,
    FALLBACKS
)

def validate_english_sentences(lines):
    for i, line in enumerate(lines):
        if _looks_non_english(line):
            return False, f"Sentence {i+1} is not strictly English."
    return True, "All sentences are in English."

def validate_no_forbidden_patterns(lines):
    for i, line in enumerate(lines):
        if _looks_like_file_leak(line) or _looks_like_instruction(line):
            return False, f"Sentence {i+1} contains forbidden patterns."
    return True, "No forbidden patterns detected."

def validate_not_fallback_only(lines, question):
    theme = _infer_theme(question)
    fb_clean = [s.lower().strip() for s in FALLBACKS.get(theme, [])]
    lines_clean = [s.lower().strip() for s in lines]
    if lines_clean == fb_clean:
        return False, "Response matches fallback list only."
    return True, "Response is not generic."

def run_tests(question):
    print(f"\n▶️ Running tests for question: {question}\n")
    chain = build_rag_chain_en()
    ans1 = chain.generate_en(question)
    time.sleep(1)
    ans2 = chain.generate_en(question)

    print("Answer 1:\n" + ans1 + "\n")
    print("Answer 2:\n" + ans2 + "\n")

    lines1 = ans1.strip().splitlines()
    lines2 = ans2.strip().splitlines()

    tests = []
    tests.append((len(lines1) == 5, "Answer contains exactly 5 sentences."))
    tests.append(validate_english_sentences(lines1))
    tests.append(validate_no_forbidden_patterns(lines1))
    tests.append((ans1 != ans2, "Non-deterministic output (Answer 1 != Answer 2)."))
    tests.append(validate_not_fallback_only(lines1, question))

    for passed, message in tests:
        print(f"{'✅ PASSED' if passed else '❌ FAILED'}: {message}")

if __name__ == "__main__":
    print("🚀 test_chain_en.py started...")
    questions = [
        "What are the main objectives of the IT STORM Proof of Concept?",
        "List the expected PoC deliverables from IT STORM.",
        "What are the main risks mentioned in IT STORM's documents?",
        "Summarize the context and goals of the initiative.",
    ]

    for q in questions:
        run_tests(q)
        print("-" * 60)
