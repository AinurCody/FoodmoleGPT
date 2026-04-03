#!/usr/bin/env python3
"""Evaluate Gemini-3.1-Pro on MCQ benchmarks.

Runs on login node (API calls only, no GPU needed).

Usage:
    python eval_gemini.py --api-key YOUR_KEY
    python eval_gemini.py --api-key YOUR_KEY --data cpt_mcq_200.json
    python eval_gemini.py --api-key YOUR_KEY --data canvas_multiple_171.json
"""
import argparse
import json
import re
import sys
import time
from pathlib import Path

import google.generativeai as genai

# ── Paths ────────────────────────────────────────────────────────────────
MCQ_DIR = "/scratch/$USER/foodmole_workspace/data/food_mcq"

BENCHMARKS = [
    {"file": "cpt_mcq_200.json", "name": "CPT-MCQ"},
    {"file": "canvas_multiple_171.json", "name": "Canvas-MCQ"},
]


def extract_answer(text, valid_options=None):
    """Extract answer letters from generated text."""
    text = text.strip()

    # Strategy 1: Compact letter group like "ABC", "ABD"
    first_token = text.split()[0].rstrip(".,;:!") if text.split() else ""
    if len(first_token) >= 2 and first_token.isalpha() and first_token.isupper():
        letters = sorted(set(first_token))
        if valid_options:
            letters = [l for l in letters if l in valid_options]
        if letters:
            return "".join(letters)

    # Strategy 2: Comma/and-separated letters
    first_line = text.split("\n")[0].strip()
    first_line = re.sub(r"^(The\s+)?(correct\s+)?(answer|answers?)\s*(is|are|:)\s*", "", first_line, flags=re.IGNORECASE)
    m = re.match(r"^([A-Z](?:\s*(?:,|;|&|\band\b)\s*[A-Z])+)\b", first_line)
    if m:
        letters = sorted(set(re.findall(r"[A-Z]", m.group(1))))
        if valid_options:
            letters = [l for l in letters if l in valid_options]
        if letters:
            return "".join(letters)

    # Strategy 3: Single letter
    m = re.match(r"^([A-Z])(?:\.|,|\s|$)", first_line)
    if m:
        letter = m.group(1)
        if not valid_options or letter in valid_options:
            return letter

    # Strategy 4: Fallback
    letters = sorted(set(re.findall(r"(?<![A-Za-z])[A-Z](?![a-z])", first_line)))
    if valid_options:
        letters = [l for l in letters if l in valid_options]
    return "".join(letters)


def format_question(q):
    """Format MCQ question as prompt."""
    instruction = (
        "Answer the following question. Select ALL correct options. "
        "Output ONLY the letter(s) of your answer (e.g., A or ABD), nothing else."
    )
    opts = "\n".join(f"{k}. {v}" for k, v in q["options"].items())
    return f"{instruction}\n\nQuestion: {q['question']}\n{opts}\n\nAnswer:"


def evaluate_benchmark(model, questions, benchmark_name):
    """Evaluate Gemini on a set of questions."""
    results = []
    correct = 0

    for i, q in enumerate(questions):
        prompt = format_question(q)

        # Retry with backoff on rate limit / safety blocks
        for attempt in range(3):
            try:
                response = model.generate_content(
                    prompt,
                    generation_config=genai.types.GenerationConfig(
                        temperature=0,
                        max_output_tokens=30,
                    ),
                    safety_settings={
                        "HARM_CATEGORY_HARASSMENT": "BLOCK_NONE",
                        "HARM_CATEGORY_HATE_SPEECH": "BLOCK_NONE",
                        "HARM_CATEGORY_SEXUALLY_EXPLICIT": "BLOCK_NONE",
                        "HARM_CATEGORY_DANGEROUS_CONTENT": "BLOCK_NONE",
                    },
                )
                # Handle safety-blocked responses (finish_reason=2)
                if response.candidates and response.candidates[0].content.parts:
                    generated = response.text.strip()
                else:
                    fr = response.candidates[0].finish_reason if response.candidates else "unknown"
                    print(f"  Safety blocked q{q['id']} (finish_reason={fr}), skipping")
                    generated = ""
                break
            except Exception as e:
                err_str = str(e).lower()
                if "429" in str(e) or "quota" in err_str:
                    if "per_day" in err_str or "day" in err_str:
                        print(f"  DAILY QUOTA EXHAUSTED. Saving partial results and exiting.")
                        return None
                    wait = min(2 ** attempt * 15, 90)
                    print(f"  Rate limited (attempt {attempt+1}/3), waiting {wait}s...")
                    time.sleep(wait)
                elif "finish_reason" in err_str:
                    # Safety filter triggered via exception
                    print(f"  Safety blocked q{q['id']}, skipping")
                    generated = ""
                    break
                else:
                    print(f"  ERROR on question {q['id']}: {e}")
                    generated = ""
                    break
        else:
            print(f"  FAILED after 3 retries on question {q['id']}, skipping")
            generated = ""

        # Rate limit: pause between requests (free tier is very restrictive)
        time.sleep(15)

        valid_opts = set(q["options"].keys())
        predicted = extract_answer(generated, valid_opts)
        ground_truth = "".join(sorted(q["answer"]))
        is_correct = predicted == ground_truth

        if is_correct:
            correct += 1

        results.append({
            "id": q["id"],
            "question": q["question"][:80],
            "ground_truth": ground_truth,
            "predicted": predicted,
            "raw_output": generated[:200],
            "correct": is_correct,
            "type": q.get("type", "unknown"),
            "category": q.get("category", "unknown"),
        })

        if (i + 1) % 20 == 0:
            print(f"  Progress: {i+1}/{len(questions)} | Acc: {correct/(i+1):.1%}")

    # Summary
    accuracy = correct / len(questions)
    single = [r for r in results if r["type"] == "single_choice"]
    multi = [r for r in results if r["type"] == "multiple_choice"]
    single_acc = sum(r["correct"] for r in single) / len(single) if single else 0
    multi_acc = sum(r["correct"] for r in multi) / len(multi) if multi else 0

    cats = {}
    for r in results:
        cat = r["category"]
        if cat not in cats:
            cats[cat] = {"correct": 0, "total": 0}
        cats[cat]["total"] += 1
        if r["correct"]:
            cats[cat]["correct"] += 1

    print(f"\n  Overall:  {correct}/{len(questions)} = {accuracy:.1%}")
    print(f"  Single:   {sum(r['correct'] for r in single)}/{len(single)} = {single_acc:.1%}")
    print(f"  Multiple: {sum(r['correct'] for r in multi)}/{len(multi)} = {multi_acc:.1%}")

    return {
        "model": "Gemini-3.1-Pro",
        "benchmark": benchmark_name,
        "accuracy": accuracy,
        "single_acc": single_acc,
        "multi_acc": multi_acc,
        "correct": correct,
        "total": len(questions),
        "per_category": {k: v["correct"] / v["total"] for k, v in sorted(cats.items())},
        "details": results,
    }


def main():
    parser = argparse.ArgumentParser(description="Gemini MCQ Evaluation")
    parser.add_argument("--api-key", required=True, help="Gemini API key")
    parser.add_argument("--model", default="gemini-3.1-pro-preview", help="Gemini model name")
    parser.add_argument("--data", type=str, default=None, help="Specific MCQ file (or run all)")
    parser.add_argument("--output", type=str, default=None, help="Output JSON path")
    args = parser.parse_args()

    genai.configure(api_key=args.api_key)
    model = genai.GenerativeModel(args.model)
    print(f"Using model: {args.model}")

    # Determine benchmarks
    if args.data:
        data_path = args.data if "/" in args.data else f"{MCQ_DIR}/{args.data}"
        benchmarks = [{"file": Path(data_path).name, "name": Path(data_path).stem, "path": data_path}]
    else:
        benchmarks = [{**b, "path": f"{MCQ_DIR}/{b['file']}"} for b in BENCHMARKS]

    all_results = []
    for bench in benchmarks:
        print(f"\n{'#' * 60}")
        print(f"# {bench['name']} ({bench['path']})")
        print(f"{'#' * 60}")

        with open(bench["path"]) as f:
            questions = json.load(f)
        print(f"  Loaded {len(questions)} questions")

        result = evaluate_benchmark(model, questions, bench["name"])
        all_results.append(result)

        # Save incrementally
        output_path = args.output or f"{MCQ_DIR}/eval_gemini_{bench['name'].lower().replace('-', '_')}.json"
        save_data = {
            "eval_date": time.strftime("%Y-%m-%d %H:%M"),
            "model": args.model,
            "benchmark": bench["name"],
            "num_questions": result["total"],
            "accuracy": result["accuracy"],
            "single_acc": result["single_acc"],
            "multi_acc": result["multi_acc"],
            "per_category": result["per_category"],
            "details": result["details"],
        }
        with open(output_path, "w") as f:
            json.dump(save_data, f, indent=2, ensure_ascii=False)
        print(f"  Saved to {output_path}")

    # Final summary
    print(f"\n{'=' * 60}")
    print("SUMMARY — Gemini-3.1-Pro")
    print(f"{'=' * 60}")
    for r in all_results:
        print(f"  {r['benchmark']}: {r['accuracy']:.1%} (Single: {r['single_acc']:.1%}, Multi: {r['multi_acc']:.1%})")


if __name__ == "__main__":
    main()
