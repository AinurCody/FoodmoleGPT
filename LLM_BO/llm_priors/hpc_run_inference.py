#!/usr/bin/env python3
"""Self-contained LLM inference script for Hopper HPC.

This script runs FoodmoleGPT and Qwen3-base inference to select
initial points for Bayesian Optimization experiments.

Usage:
    python hpc_run_inference.py --foodmolegpt-path <path> --qwen3base-path <path>

If paths are not provided, the script will search common locations.
"""

import argparse
import json
import os
import re
import glob
import torch
from pathlib import Path


# ============================================================
# Candidate pool (66 points on mixture simplex, NO objective values shown to LLM)
# ============================================================
CANDIDATES = [
    (0, 0.00, 1.00, 1.00), (1, 0.10, 0.90, 1.00), (2, 0.10, 1.00, 0.90),
    (3, 0.20, 0.80, 1.00), (4, 0.20, 0.90, 0.90), (5, 0.20, 1.00, 0.80),
    (6, 0.30, 0.70, 1.00), (7, 0.30, 0.80, 0.90), (8, 0.30, 0.90, 0.80),
    (9, 0.30, 1.00, 0.70), (10, 0.40, 0.60, 1.00), (11, 0.40, 0.70, 0.90),
    (12, 0.40, 0.80, 0.80), (13, 0.40, 0.90, 0.70), (14, 0.40, 1.00, 0.60),
    (15, 0.50, 0.50, 1.00), (16, 0.50, 0.60, 0.90), (17, 0.50, 0.70, 0.80),
    (18, 0.50, 0.80, 0.70), (19, 0.50, 0.90, 0.60), (20, 0.50, 1.00, 0.50),
    (21, 0.60, 0.40, 1.00), (22, 0.60, 0.50, 0.90), (23, 0.60, 0.60, 0.80),
    (24, 0.60, 0.70, 0.70), (25, 0.60, 0.80, 0.60), (26, 0.60, 0.90, 0.50),
    (27, 0.60, 1.00, 0.40), (28, 0.70, 0.30, 1.00), (29, 0.70, 0.40, 0.90),
    (30, 0.70, 0.50, 0.80), (31, 0.70, 0.60, 0.70), (32, 0.70, 0.70, 0.60),
    (33, 0.70, 0.80, 0.50), (34, 0.70, 0.90, 0.40), (35, 0.70, 1.00, 0.30),
    (36, 0.80, 0.20, 1.00), (37, 0.80, 0.30, 0.90), (38, 0.80, 0.40, 0.80),
    (39, 0.80, 0.50, 0.70), (40, 0.80, 0.60, 0.60), (41, 0.80, 0.70, 0.50),
    (42, 0.80, 0.80, 0.40), (43, 0.80, 0.90, 0.30), (44, 0.80, 1.00, 0.20),
    (45, 0.90, 0.10, 1.00), (46, 0.90, 0.20, 0.90), (47, 0.90, 0.30, 0.80),
    (48, 0.90, 0.40, 0.70), (49, 0.90, 0.50, 0.60), (50, 0.90, 0.60, 0.50),
    (51, 0.90, 0.70, 0.40), (52, 0.90, 0.80, 0.30), (53, 0.90, 0.90, 0.20),
    (54, 0.90, 1.00, 0.10), (55, 1.00, 0.00, 1.00), (56, 1.00, 0.10, 0.90),
    (57, 1.00, 0.20, 0.80), (58, 1.00, 0.30, 0.70), (59, 1.00, 0.40, 0.60),
    (60, 1.00, 0.50, 0.50), (61, 1.00, 0.60, 0.40), (62, 1.00, 0.70, 0.30),
    (63, 1.00, 0.80, 0.20), (64, 1.00, 0.90, 0.10), (65, 1.00, 1.00, 0.00),
]


def build_prompt(k=3):
    """Build the warm-start prompt (NO objective values!)."""
    lines = []
    for idx, ce, ge, hs in CANDIDATES:
        lines.append(f"  #{idx:2d}: CE={ce:.2f}, GE={ge:.2f}, HS={hs:.2f}")
    table = "\n".join(lines)

    prompt = f"""You are a food science expert. Below is a list of {len(CANDIDATES)} candidate functional beverage formulations. Each formulation contains three plant extract components:
- CE (Cardamom Essential oil, ml/100ml)
- GE (Ginger Extract, ml/100ml)
- HS (Hibiscus Solution, ml/100ml)

The three components satisfy the constraint: CE + GE + HS = 2.0 ml/100ml.

Candidate formulations:
{table}

The goal is to maximize DPPH free radical scavenging activity (antioxidant activity, measured as % inhibition).

Please select the {k} formulations that are most worth testing first, and briefly explain your reasoning. Consider:
- The antioxidant activity contributions of ALL THREE components (CE, GE, and HS) — do not focus only on the most well-known one; each component may contribute differently to DPPH scavenging
- Possible synergistic or antagonistic effects between components at different concentration ratios
- Common effective concentration ranges in functional beverage research
- Selecting formulations that explore different regions of the design space, not just one corner

Output ONLY valid JSON: {{"selected": [list of candidate index numbers], "reasoning": "brief explanation"}}"""
    return prompt


def find_model_paths():
    """Search common HPC locations for model checkpoints."""
    search_dirs = [
        os.path.expanduser("~"),
        "/home",
        "/scratch",
        "/work",
        "/hpctmp",
    ]

    results = {"foodmolegpt": [], "qwen3_base": []}

    for base in search_dirs:
        if not os.path.exists(base):
            continue
        # Search for FoodmoleGPT (merged CPT+SFT model)
        for pattern in ["**/foodmole*merged*", "**/qwen3*cpt*sft*merged*",
                        "**/FoodmoleGPT*merged*", "**/foodmolegpt*"]:
            for p in glob.glob(os.path.join(base, pattern), recursive=True):
                if os.path.isdir(p) and any(
                    f.endswith((".safetensors", ".bin", "config.json"))
                    for f in os.listdir(p)
                ):
                    results["foodmolegpt"].append(p)

        # Search for Qwen3-8B-Base
        for pattern in ["**/Qwen3-8B*", "**/qwen3*8b*base*", "**/Qwen/Qwen3-8B"]:
            for p in glob.glob(os.path.join(base, pattern), recursive=True):
                if os.path.isdir(p) and any(
                    f.endswith((".safetensors", ".bin", "config.json"))
                    for f in os.listdir(p)
                ):
                    results["qwen3_base"].append(p)

    return results


def run_inference(model_path, prompt, model_label, temperature=0.0):
    """Run LLM inference with the given model."""
    from transformers import AutoModelForCausalLM, AutoTokenizer

    print(f"\n{'='*60}")
    print(f"Loading {model_label} from: {model_path}")
    print(f"Temperature: {temperature}")
    print(f"{'='*60}")

    tokenizer = AutoTokenizer.from_pretrained(model_path, trust_remote_code=True)
    model = AutoModelForCausalLM.from_pretrained(
        model_path,
        torch_dtype=torch.bfloat16,
        device_map="auto",
        trust_remote_code=True,
    )

    # Try chat template first, fall back to raw prompt
    try:
        messages = [{"role": "user", "content": prompt}]
        text = tokenizer.apply_chat_template(
            messages, tokenize=False, add_generation_prompt=True
        )
    except Exception:
        text = prompt + "\n\nAnswer:"

    inputs = tokenizer(text, return_tensors="pt").to(model.device)
    print(f"Input tokens: {inputs.input_ids.shape[1]}")

    gen_kwargs = dict(max_new_tokens=512)
    if temperature > 0:
        gen_kwargs.update(do_sample=True, temperature=temperature, top_p=0.9)
    else:
        gen_kwargs.update(do_sample=False)

    with torch.no_grad():
        outputs = model.generate(**inputs, **gen_kwargs)

    response = tokenizer.decode(
        outputs[0][inputs.input_ids.shape[1]:],
        skip_special_tokens=True,
    )
    print(f"\nRaw response:\n{response}\n")
    return response


def parse_response(response, k=3):
    """Parse LLM response to extract selected indices."""
    # Try JSON extraction
    json_match = re.search(r'\{[^{}]*"selected"\s*:\s*\[([^\]]*)\][^{}]*\}', response)
    if json_match:
        try:
            result = json.loads(json_match.group())
            if len(result.get("selected", [])) == k:
                return result
        except json.JSONDecodeError:
            pass

    # Fallback: extract numbers
    nums = [int(n) for n in re.findall(r'\b(\d{1,2})\b', response)
            if 0 <= int(n) <= 65]
    # Deduplicate while preserving order
    seen = set()
    unique = []
    for n in nums:
        if n not in seen:
            seen.add(n)
            unique.append(n)
    selected = unique[:k]

    return {"selected": selected, "reasoning": f"Parsed from raw output: {response[:200]}"}


def save_result(model_name, result, response, output_dir="."):
    """Save inference result to JSON."""
    output = {
        "model": model_name,
        "k": 3,
        "n_candidates": 66,
        "selected": result["selected"],
        "reasoning": result.get("reasoning", ""),
        "raw_response": response,
    }
    path = os.path.join(output_dir, f"{model_name}_init.json")
    with open(path, "w") as f:
        json.dump(output, f, indent=2, ensure_ascii=False)
    print(f"Saved: {path}")
    return path


def main():
    parser = argparse.ArgumentParser(description="Run LLM inference for BO warm-start")
    parser.add_argument("--foodmolegpt-path", type=str, default=None,
                        help="Path to FoodmoleGPT merged model directory")
    parser.add_argument("--qwen3base-path", type=str, default=None,
                        help="Path to Qwen3-8B-Base model directory")
    parser.add_argument("--output-dir", type=str, default=".",
                        help="Directory to save output JSONs")
    parser.add_argument("--k", type=int, default=3)
    parser.add_argument("--temperature", type=float, default=0.3,
                        help="Sampling temperature (0=greedy, >0=sampling)")
    parser.add_argument("--n-runs", type=int, default=3,
                        help="Number of inference runs per model")
    args = parser.parse_args()

    prompt = build_prompt(k=args.k)
    os.makedirs(args.output_dir, exist_ok=True)

    print(f"Prompt length: {len(prompt)} chars")
    print(f"Number of candidates: {len(CANDIDATES)}")
    print(f"k (init points to select): {args.k}")
    print(f"Temperature: {args.temperature}")
    print(f"Runs per model: {args.n_runs}")

    for model_name, model_path, label in [
        ("foodmolegpt", args.foodmolegpt_path, "FoodmoleGPT"),
        ("qwen3base", args.qwen3base_path, "Qwen3-8B-Base"),
    ]:
        if not model_path:
            print(f"\nSkipping {label} (no path provided)")
            continue

        all_runs = []
        for run_idx in range(args.n_runs):
            print(f"\n--- {label} run {run_idx+1}/{args.n_runs} ---")
            response = run_inference(model_path, prompt, label, args.temperature)
            result = parse_response(response, args.k)
            result["run_idx"] = run_idx
            result["raw_response"] = response
            all_runs.append(result)
            print(f"  Selected: {result['selected']}")

        # Use first run as primary, save all runs for analysis
        output = {
            "model": model_name,
            "k": args.k,
            "n_candidates": 66,
            "temperature": args.temperature,
            "n_runs": args.n_runs,
            "selected": all_runs[0]["selected"],
            "reasoning": all_runs[0].get("reasoning", ""),
            "all_runs": [
                {"selected": r["selected"], "reasoning": r.get("reasoning", "")}
                for r in all_runs
            ],
        }
        path = os.path.join(args.output_dir, f"{model_name}_init.json")
        with open(path, "w") as f:
            json.dump(output, f, indent=2, ensure_ascii=False)
        print(f"\nSaved: {path}")

        # Print summary of all runs
        print(f"\n{'='*60}")
        print(f"{label} summary ({args.n_runs} runs, temp={args.temperature}):")
        for i, r in enumerate(all_runs):
            print(f"  Run {i+1}: {r['selected']}")
        from collections import Counter
        all_selected = [idx for r in all_runs for idx in r["selected"]]
        print(f"  Most frequent picks: {Counter(all_selected).most_common(5)}")
        print(f"{'='*60}")

    print("\nDone! Transfer the *_init.json files back to your local machine.")


if __name__ == "__main__":
    main()
