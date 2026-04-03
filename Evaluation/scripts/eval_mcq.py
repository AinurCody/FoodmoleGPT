#!/usr/bin/env python3
"""MCQ Evaluation for FoodmoleGPT ablation study.

Usage (inside singularity container on GPU node):
    python eval_mcq.py                   # all models, 0-shot
    python eval_mcq.py qwen3             # only Qwen3 models
    python eval_mcq.py --few-shot 5      # all models, 5-shot
    python eval_mcq.py --few-shot 5 qwen3-cpt+sft llama3-cpt  # specific models, 5-shot
"""
import argparse
import json
import re
import sys
import time
import torch
from pathlib import Path
from transformers import AutoModelForCausalLM, AutoTokenizer
from peft import PeftModel

# ── Paths ────────────────────────────────────────────────────────────────
HF_CACHE = "/scratch/$USER/huggingface_cache/hub"
CKPT_DIR = "/scratch/$USER/foodmole_workspace/checkpoints"
MCQ_PATH = "/scratch/$USER/foodmole_workspace/data/food_mcq/canvas_multiple_171.json"
OUTPUT_PATH = "/scratch/$USER/foodmole_workspace/data/food_mcq/eval_results.json"

QWEN3_BASE = f"{HF_CACHE}/models--Qwen--Qwen3-8B-Base"
LLAMA3_BASE = (
    f"{HF_CACHE}/models--meta-llama--Meta-Llama-3.1-8B"
    "/snapshots/d04e592bb4f6aa9cfee91e2e20afa771667e1d4b"
)

# ── Model configurations ────────────────────────────────────────────────
MODELS = [
    {
        "name": "Qwen3-8B-Base",
        "base": QWEN3_BASE,
        "adapters": [],
        "trust_remote_code": True,
    },
    {
        "name": "Qwen3-CPT",
        "base": QWEN3_BASE,
        "adapters": [f"{CKPT_DIR}/qwen3-8b-cpt"],
        "trust_remote_code": True,
    },
    {
        "name": "Qwen3-SFT-Only",
        "base": QWEN3_BASE,
        "adapters": [f"{CKPT_DIR}/qwen3-8b-sft-lora-foodmole"],
        "trust_remote_code": True,
    },
    {
        "name": "Qwen3-CPT+SFT",
        "base": QWEN3_BASE,
        "adapters": [
            f"{CKPT_DIR}/qwen3-8b-cpt",
            f"{CKPT_DIR}/qwen3-8b-cpt-sft-lora-foodmole",
        ],
        "trust_remote_code": True,
    },
    {
        "name": "Llama3-8B-Base",
        "base": LLAMA3_BASE,
        "adapters": [],
        "trust_remote_code": False,
    },
    {
        "name": "Llama3-CPT",
        "base": LLAMA3_BASE,
        "adapters": [f"{CKPT_DIR}/llama3-8b-cpt"],
        "trust_remote_code": False,
    },
    {
        "name": "Llama3-SFT-Only",
        "base": LLAMA3_BASE,
        "adapters": [f"{CKPT_DIR}/llama3-8b-sft-lora-foodmole"],
        "trust_remote_code": False,
    },
    {
        "name": "Llama3-CPT+SFT",
        "base": LLAMA3_BASE,
        "adapters": [
            f"{CKPT_DIR}/llama3-8b-cpt",              # CPT adapter → merge first
            f"{CKPT_DIR}/llama3-8b-cpt-sft-lora-foodmole",  # SFT adapter on top
        ],
        "trust_remote_code": False,
    },
]


def format_question(q, few_shot_examples=None):
    """Format a single MCQ question as a prompt, optionally with few-shot examples."""
    instruction = (
        "Answer the following question. Select ALL correct options. "
        "Output ONLY the letter(s) of your answer (e.g., A or ABD), nothing else."
    )

    parts = [instruction]

    # Add few-shot examples if provided
    if few_shot_examples:
        for ex in few_shot_examples:
            ex_opts = "\n".join(f"{k}. {v}" for k, v in ex["options"].items())
            gt = "".join(sorted(ex["answer"]))
            parts.append(f"\nQuestion: {ex['question']}\n{ex_opts}\n\nAnswer: {gt}")

    # Add the actual question
    opts = "\n".join(f"{k}. {v}" for k, v in q["options"].items())
    parts.append(f"\nQuestion: {q['question']}\n{opts}\n\nAnswer:")

    return "\n".join(parts)


def extract_answer(text, valid_options=None):
    """Extract answer letters from generated text, handling thinking blocks."""
    # Remove <think>...</think> blocks if present
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

    # Strategy 2: Comma/and-separated letters like "A, B, D" or "A and B"
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


def load_model_and_tokenizer(config):
    """Load base model, apply adapters, return (model, tokenizer, is_sft)."""
    base_path = config["base"]
    adapters = config["adapters"]
    trust = config.get("trust_remote_code", False)

    tokenizer = AutoTokenizer.from_pretrained(
        base_path, trust_remote_code=trust, padding_side="left"
    )
    if tokenizer.pad_token is None:
        tokenizer.pad_token = tokenizer.eos_token

    model = AutoModelForCausalLM.from_pretrained(
        base_path, torch_dtype=torch.bfloat16, device_map="auto", trust_remote_code=trust
    )

    if len(adapters) == 2:
        # CPT→SFT: load CPT adapter, merge into base, then load SFT adapter
        print(f"  Loading CPT adapter: {Path(adapters[0]).name}")
        model = PeftModel.from_pretrained(model, adapters[0])
        model = model.merge_and_unload()
        print(f"  CPT merged. Loading SFT adapter: {Path(adapters[1]).name}")
        model = PeftModel.from_pretrained(model, adapters[1])
        # Use tokenizer from SFT checkpoint (has chat template)
        tokenizer = AutoTokenizer.from_pretrained(adapters[1], padding_side="left")
        if tokenizer.pad_token is None:
            tokenizer.pad_token = tokenizer.eos_token
    elif len(adapters) == 1:
        print(f"  Loading adapter: {Path(adapters[0]).name}")
        model = PeftModel.from_pretrained(model, adapters[0])
        tokenizer = AutoTokenizer.from_pretrained(adapters[0], padding_side="left")
        if tokenizer.pad_token is None:
            tokenizer.pad_token = tokenizer.eos_token

    model.eval()
    return model, tokenizer, len(adapters) > 0


def build_input(prompt_text, tokenizer, is_sft):
    """Build model input, applying chat template for SFT models."""
    if is_sft and hasattr(tokenizer, "chat_template") and tokenizer.chat_template:
        messages = [{"role": "user", "content": prompt_text}]
        try:
            input_text = tokenizer.apply_chat_template(
                messages, tokenize=False, add_generation_prompt=True,
                enable_thinking=False,
            )
        except TypeError:
            # Fallback if enable_thinking not supported
            input_text = tokenizer.apply_chat_template(
                messages, tokenize=False, add_generation_prompt=True
            )
    else:
        input_text = prompt_text

    return tokenizer(input_text, return_tensors="pt")


def evaluate_model(config, questions, few_shot_examples=None):
    """Evaluate a single model on all questions."""
    name = config["name"]
    print(f"\n{'=' * 60}")
    print(f"Evaluating: {name}")
    print(f"{'=' * 60}")

    t0 = time.time()
    model, tokenizer, is_sft = load_model_and_tokenizer(config)
    load_time = time.time() - t0
    print(f"  Loaded in {load_time:.1f}s")

    results = []
    correct = 0
    t1 = time.time()

    for i, q in enumerate(questions):
        prompt_text = format_question(q, few_shot_examples)
        inputs = build_input(prompt_text, tokenizer, is_sft)
        inputs = {k: v.to(model.device) for k, v in inputs.items()}

        with torch.no_grad():
            outputs = model.generate(
                **inputs,
                max_new_tokens=30,
                do_sample=False,
            )

        generated = tokenizer.decode(
            outputs[0][inputs["input_ids"].shape[1]:],
            skip_special_tokens=True,
        )

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
            "type": q["type"],
            "category": q["category"],
        })

        if (i + 1) % 20 == 0:
            print(f"  Progress: {i+1}/{len(questions)} | Acc so far: {correct/(i+1):.1%}")

    eval_time = time.time() - t1

    # Breakdown by type
    single = [r for r in results if r["type"] == "single_choice"]
    multi = [r for r in results if r["type"] == "multiple_choice"]
    single_acc = sum(r["correct"] for r in single) / len(single) if single else 0
    multi_acc = sum(r["correct"] for r in multi) / len(multi) if multi else 0

    # Breakdown by category
    cats = {}
    for r in results:
        cat = r["category"]
        if cat not in cats:
            cats[cat] = {"correct": 0, "total": 0}
        cats[cat]["total"] += 1
        if r["correct"]:
            cats[cat]["correct"] += 1

    accuracy = correct / len(questions)
    print(f"\n  Overall:  {correct}/{len(questions)} = {accuracy:.1%}")
    print(f"  Single:   {sum(r['correct'] for r in single)}/{len(single)} = {single_acc:.1%}")
    print(f"  Multiple: {sum(r['correct'] for r in multi)}/{len(multi)} = {multi_acc:.1%}")
    print(f"  Eval time: {eval_time:.1f}s")

    # Free GPU memory
    del model
    torch.cuda.empty_cache()

    return {
        "model": name,
        "accuracy": accuracy,
        "single_acc": single_acc,
        "multi_acc": multi_acc,
        "correct": correct,
        "total": len(questions),
        "load_time_s": round(load_time, 1),
        "eval_time_s": round(eval_time, 1),
        "per_category": {k: v["correct"] / v["total"] for k, v in sorted(cats.items())},
        "details": results,
    }


def main():
    parser = argparse.ArgumentParser(description="MCQ Evaluation for FoodmoleGPT")
    parser.add_argument("filters", nargs="*", help="Model name filters (e.g., qwen3 llama3-cpt)")
    parser.add_argument("--few-shot", type=int, default=0, metavar="N",
                        help="Number of few-shot examples (default: 0). Uses --example-ids if given, else first N questions.")
    parser.add_argument("--example-ids", type=str, default=None,
                        help="Comma-separated question IDs for few-shot (e.g., 4,16,23,28,13). Implies --few-shot.")
    parser.add_argument("--data", type=str, default=None,
                        help="Path to MCQ JSON file (overrides default)")
    parser.add_argument("--output", type=str, default=None,
                        help="Path to output JSON file (overrides default)")
    args = parser.parse_args()

    mcq_path = args.data or MCQ_PATH
    output_path = args.output or OUTPUT_PATH
    with open(mcq_path) as f:
        questions = json.load(f)
    print(f"Loaded {len(questions)} questions from {mcq_path}")
    print(f"  ({sum(1 for q in questions if q['type']=='single_choice')} single, "
          f"{sum(1 for q in questions if q['type']=='multiple_choice')} multi)")

    # Few-shot: select specific examples and exclude them from eval
    few_shot_examples = None
    eval_questions = questions
    if args.example_ids:
        example_ids = [int(x.strip()) for x in args.example_ids.split(",")]
        id_to_q = {q["id"]: q for q in questions}
        few_shot_examples = [id_to_q[i] for i in example_ids if i in id_to_q]
        if len(few_shot_examples) != len(example_ids):
            missing = [i for i in example_ids if i not in id_to_q]
            print(f"WARNING: example IDs not found: {missing}")
        eval_questions = [q for q in questions if q["id"] not in set(example_ids)]
        args.few_shot = len(few_shot_examples)
        print(f"Few-shot mode: {len(few_shot_examples)} examples (IDs: {example_ids}), evaluating {len(eval_questions)} questions")
    elif args.few_shot > 0:
        if args.few_shot >= len(questions):
            print(f"ERROR: --few-shot {args.few_shot} >= total questions {len(questions)}")
            sys.exit(1)
        few_shot_examples = questions[:args.few_shot]
        eval_questions = questions[args.few_shot:]
        print(f"Few-shot mode: {args.few_shot} examples (first {args.few_shot}), evaluating {len(eval_questions)} questions")

    # Filter models by command-line args
    if args.filters:
        includes = [a.lower() for a in args.filters if not a.startswith("!")]
        excludes = [a[1:].lower() for a in args.filters if a.startswith("!")]
        if includes:
            models_to_eval = [m for m in MODELS if any(f in m["name"].lower() for f in includes)]
        else:
            models_to_eval = list(MODELS)
        if excludes:
            models_to_eval = [m for m in models_to_eval if not any(f in m["name"].lower() for f in excludes)]
    else:
        models_to_eval = list(MODELS)

    # Skip models whose adapter checkpoints don't exist or are incomplete
    ready = []
    for m in models_to_eval:
        missing = []
        for a in m["adapters"]:
            if not Path(a).exists():
                missing.append(a)
            elif not (Path(a) / "adapter_config.json").exists():
                missing.append(a)  # directory exists but training incomplete
        if missing:
            print(f"SKIPPING {m['name']}: adapter not ready: {[Path(a).name for a in missing]}")
        else:
            ready.append(m)
    models_to_eval = ready

    if not models_to_eval:
        print(f"No models matched filters: {sys.argv[1:]}")
        print(f"Available: {[m['name'] for m in MODELS]}")
        sys.exit(1)

    print(f"Will evaluate: {[m['name'] for m in models_to_eval]}")
    if few_shot_examples:
        print(f"Few-shot examples: {[ex['id'] for ex in few_shot_examples]}")

    # Use separate output file for few-shot to avoid overwriting 0-shot results
    if not args.output:
        output_path = OUTPUT_PATH
        if args.few_shot > 0:
            output_path = OUTPUT_PATH.replace(".json", f"_{args.few_shot}shot.json")

    all_results = []
    for config in models_to_eval:
        try:
            result = evaluate_model(config, eval_questions, few_shot_examples)
            all_results.append(result)

            # ── Incremental save after each model ─────────────────────────
            existing = {}
            if Path(output_path).exists():
                with open(output_path) as f:
                    existing = json.load(f)
            save_data = existing if existing else {"eval_date": "", "num_questions": len(eval_questions), "few_shot": args.few_shot, "results": {}, "details": {}}
            save_data["eval_date"] = time.strftime("%Y-%m-%d %H:%M")
            save_data["num_questions"] = len(eval_questions)
            name = result["model"]
            save_data["results"][name] = {k: v for k, v in result.items() if k != "details"}
            save_data["details"][name] = result["details"]
            with open(output_path, "w") as f:
                json.dump(save_data, f, indent=2, ensure_ascii=False)
            print(f"  Results saved to {output_path}")
        except Exception as e:
            print(f"\nERROR evaluating {config['name']}: {e}")
            print("  Skipping to next model...")
            torch.cuda.empty_cache()

    # ── Summary table ────────────────────────────────────────────────────
    print(f"\n{'=' * 60}")
    print("SUMMARY")
    print(f"{'=' * 60}")
    print(f"{'Model':<25} {'Overall':>8} {'Single':>8} {'Multi':>8}")
    print("-" * 55)
    for r in all_results:
        print(f"{r['model']:<25} {r['accuracy']:>7.1%} {r['single_acc']:>7.1%} {r['multi_acc']:>7.1%}")
    print(f"\nAll results saved to {output_path}")


if __name__ == "__main__":
    main()
