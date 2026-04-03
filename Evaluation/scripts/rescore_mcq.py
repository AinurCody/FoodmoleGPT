#!/usr/bin/env python3
"""Re-score MCQ results from saved raw_output without re-running models.

Usage: python rescore_mcq.py [eval_results.json]
"""
import json
import re
import sys
from collections import Counter

EVAL_PATH = "/scratch/$USER/foodmole_workspace/data/food_mcq/eval_results.json"
MCQ_PATH = "/scratch/$USER/foodmole_workspace/data/food_mcq/canvas_multiple_171.json"


def extract_answer(text, valid_options=None):
    """Improved answer extraction - handles ABC, A/B/D, A. False, etc."""
    text = re.sub(r"<think>.*?</think>", "", text, flags=re.DOTALL)
    text = text.strip()

    # Strategy 1: Compact letter group like "ABC", "ABD" (2+ consecutive letters, no separators)
    first_token = text.split()[0].rstrip(".,;:!") if text.split() else ""
    if len(first_token) >= 2 and first_token.isalpha() and first_token.isupper():
        letters = sorted(set(first_token))
        if valid_options:
            letters = [l for l in letters if l in valid_options]
        if letters:
            return "".join(letters)

    # Strategy 2: Comma/and-separated like "A, B, D" or "A and B"
    first_line = text.split("\n")[0].strip()
    first_line = re.sub(r"^(The\s+)?(correct\s+)?(answer|answers?)\s*(is|are|:)\s*", "", first_line, flags=re.IGNORECASE)
    m = re.match(r"^([A-Z](?:\s*(?:,|;|&|\band\b)\s*[A-Z])+)\b", first_line)
    if m:
        letters = sorted(set(re.findall(r"[A-Z]", m.group(1))))
        if valid_options:
            letters = [l for l in letters if l in valid_options]
        if letters:
            return "".join(letters)

    # Strategy 3: Single letter followed by period/space/end (e.g., "B. False" → "B")
    m = re.match(r"^([A-Z])(?:\.|,|\s|$)", first_line)
    if m:
        letter = m.group(1)
        if not valid_options or letter in valid_options:
            return letter

    # Strategy 4: Fallback — standalone capital letters not part of words
    letters = sorted(set(re.findall(r"(?<![A-Za-z])[A-Z](?![a-z])", first_line)))
    if valid_options:
        letters = [l for l in letters if l in valid_options]
    return "".join(letters)


def main():
    eval_path = sys.argv[1] if len(sys.argv) > 1 else EVAL_PATH

    with open(eval_path) as f:
        data = json.load(f)
    with open(MCQ_PATH) as f:
        questions = {q["id"]: q for q in json.load(f)}

    print(f"Re-scoring results from {eval_path}\n")

    for model_name, details in data.get("details", {}).items():
        correct = 0
        total = len(details)
        single_correct = single_total = 0
        multi_correct = multi_total = 0
        mismatches = []

        for r in details:
            q = questions[r["id"]]
            valid_opts = set(q["options"].keys())
            new_pred = extract_answer(r["raw_output"], valid_opts)
            gt = "".join(sorted(r["ground_truth"]))
            is_correct = new_pred == gt

            if is_correct:
                correct += 1

            if r["type"] == "single_choice":
                single_total += 1
                if is_correct:
                    single_correct += 1
            else:
                multi_total += 1
                if is_correct:
                    multi_correct += 1

            # Track cases where old and new scoring differ
            old_pred = r.get("predicted", "")
            if new_pred != old_pred:
                mismatches.append({
                    "id": r["id"],
                    "old": old_pred,
                    "new": new_pred,
                    "gt": gt,
                    "raw": r["raw_output"][:100],
                    "old_correct": old_pred == gt,
                    "new_correct": is_correct,
                })

        acc = correct / total if total else 0
        s_acc = single_correct / single_total if single_total else 0
        m_acc = multi_correct / multi_total if multi_total else 0

        print(f"{'=' * 60}")
        print(f"{model_name}")
        print(f"  Overall:  {correct}/{total} = {acc:.1%}")
        print(f"  Single:   {single_correct}/{single_total} = {s_acc:.1%}")
        print(f"  Multiple: {multi_correct}/{multi_total} = {m_acc:.1%}")

        if mismatches:
            improved = sum(1 for m in mismatches if m["new_correct"] and not m["old_correct"])
            degraded = sum(1 for m in mismatches if not m["new_correct"] and m["old_correct"])
            print(f"  Re-scoring changes: {len(mismatches)} questions affected "
                  f"(+{improved} improved, -{degraded} degraded)")

            # Show a few examples
            for m in mismatches[:5]:
                status = "FIXED" if m["new_correct"] else "STILL WRONG"
                print(f"    Q{m['id']}: '{m['old']}' -> '{m['new']}' (gt={m['gt']}) [{status}]")
                print(f"      raw: {m['raw']}")

    # Summary table
    print(f"\n{'=' * 60}")
    print("RESCORED SUMMARY")
    print(f"{'=' * 60}")
    print(f"{'Model':<25} {'Overall':>8} {'Single':>8} {'Multi':>8}")
    print("-" * 55)
    for model_name, details in data.get("details", {}).items():
        correct = total = 0
        s_c = s_t = m_c = m_t = 0
        for r in details:
            q = questions[r["id"]]
            valid_opts = set(q["options"].keys())
            pred = extract_answer(r["raw_output"], valid_opts)
            gt = "".join(sorted(r["ground_truth"]))
            ok = pred == gt
            total += 1
            correct += ok
            if r["type"] == "single_choice":
                s_t += 1; s_c += ok
            else:
                m_t += 1; m_c += ok
        print(f"{model_name:<25} {correct/total:>7.1%} {s_c/s_t:>7.1%} {m_c/m_t:>7.1%}")


if __name__ == "__main__":
    main()
