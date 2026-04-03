"""Generate LLM warm-start priors for BO experiments.

Run on Hopper with GPU access:
    python llm_priors/generate_prior.py --model foodmolegpt --k 3
    python llm_priors/generate_prior.py --model qwen3-base --k 3

The script:
  1. Loads the candidate pool (features only, NO objective values)
  2. Formats the prompt from the template
  3. Runs LLM inference
  4. Parses the JSON output
  5. Saves the selected indices to a JSON file
"""

import argparse
import json
import re
import pandas as pd
from pathlib import Path


def load_candidates(csv_path: str) -> pd.DataFrame:
    df = pd.read_csv(csv_path)
    return df[["idx", "CE_ml_per_100ml", "GE_ml_per_100ml", "HS_ml_per_100ml"]]


def format_prompt(candidates_df: pd.DataFrame, k: int, template_path: str) -> str:
    with open(template_path) as f:
        template = f.read()

    # Format candidate table (NO objective values!)
    lines = []
    for _, row in candidates_df.iterrows():
        lines.append(
            f"  #{int(row['idx']):2d}: CE={row['CE_ml_per_100ml']:.2f}, "
            f"GE={row['GE_ml_per_100ml']:.2f}, HS={row['HS_ml_per_100ml']:.2f}"
        )
    table = "\n".join(lines)

    return template.format(
        N=len(candidates_df),
        k=k,
        candidate_table=table,
    )


def run_inference(prompt: str, model_name: str) -> str:
    """Run LLM inference. Adapt this to your specific setup."""
    if model_name == "foodmolegpt":
        # Load FoodmoleGPT (Qwen3-CPT+SFT LoRA merged)
        from transformers import AutoModelForCausalLM, AutoTokenizer
        import torch

        model_path = "/path/to/foodmolegpt/merged"  # UPDATE THIS
        tokenizer = AutoTokenizer.from_pretrained(model_path, trust_remote_code=True)
        model = AutoModelForCausalLM.from_pretrained(
            model_path, torch_dtype=torch.bfloat16, device_map="auto",
            trust_remote_code=True,
        )

        messages = [{"role": "user", "content": prompt}]
        text = tokenizer.apply_chat_template(messages, tokenize=False, add_generation_prompt=True)
        inputs = tokenizer(text, return_tensors="pt").to(model.device)
        outputs = model.generate(**inputs, max_new_tokens=512, do_sample=False)
        response = tokenizer.decode(outputs[0][inputs.input_ids.shape[1]:], skip_special_tokens=True)
        return response

    elif model_name == "qwen3-base":
        # Load vanilla Qwen3-8B-Base (no fine-tuning)
        from transformers import AutoModelForCausalLM, AutoTokenizer
        import torch

        model_path = "Qwen/Qwen3-8B"  # or local path
        tokenizer = AutoTokenizer.from_pretrained(model_path, trust_remote_code=True)
        model = AutoModelForCausalLM.from_pretrained(
            model_path, torch_dtype=torch.bfloat16, device_map="auto",
            trust_remote_code=True,
        )

        messages = [{"role": "user", "content": prompt}]
        text = tokenizer.apply_chat_template(messages, tokenize=False, add_generation_prompt=True)
        inputs = tokenizer(text, return_tensors="pt").to(model.device)
        outputs = model.generate(**inputs, max_new_tokens=512, do_sample=False)
        response = tokenizer.decode(outputs[0][inputs.input_ids.shape[1]:], skip_special_tokens=True)
        return response

    elif model_name == "gemini":
        import google.generativeai as genai
        model = genai.GenerativeModel("gemini-2.0-flash")
        response = model.generate_content(prompt)
        return response.text

    else:
        raise ValueError(f"Unknown model: {model_name}")


def parse_response(response: str, k: int) -> dict:
    """Parse LLM response to extract selected indices."""
    # Try to find JSON in the response
    json_match = re.search(r'\{[^{}]*"selected"\s*:\s*\[[^\]]*\][^{}]*\}', response)
    if json_match:
        result = json.loads(json_match.group())
    else:
        # Fallback: try to find any list of numbers
        nums = re.findall(r'\b(\d+)\b', response)
        nums = [int(n) for n in nums[:k]]
        result = {"selected": nums, "reasoning": "parsed from raw output"}

    assert len(result["selected"]) == k, (
        f"Expected {k} selections, got {len(result['selected'])}"
    )
    return result


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--model", required=True, choices=["foodmolegpt", "qwen3-base", "gemini"])
    parser.add_argument("--candidates", default="data/candidates_grid.csv")
    parser.add_argument("--template", default="llm_priors/prompt_template.txt")
    parser.add_argument("--k", type=int, default=3)
    parser.add_argument("--output", default=None)
    parser.add_argument("--n-runs", type=int, default=1,
                        help="Number of inference runs (for robustness)")
    args = parser.parse_args()

    if args.output is None:
        args.output = f"llm_priors/{args.model}_init.json"

    candidates_df = load_candidates(args.candidates)
    prompt = format_prompt(candidates_df, args.k, args.template)

    print(f"Model: {args.model}")
    print(f"Candidates: {len(candidates_df)}")
    print(f"k: {args.k}")
    print(f"Prompt length: {len(prompt)} chars")
    print("=" * 50)
    print(prompt[:500] + "...")
    print("=" * 50)

    all_results = []
    for i in range(args.n_runs):
        print(f"\nRun {i+1}/{args.n_runs}...")
        response = run_inference(prompt, args.model)
        print(f"Response: {response[:300]}...")
        result = parse_response(response, args.k)
        result["run_idx"] = i
        all_results.append(result)
        print(f"Selected: {result['selected']}")

    output = {
        "model": args.model,
        "k": args.k,
        "n_candidates": len(candidates_df),
        "results": all_results,
        "selected": all_results[0]["selected"],  # primary result
        "reasoning": all_results[0].get("reasoning", ""),
    }

    Path(args.output).parent.mkdir(parents=True, exist_ok=True)
    with open(args.output, "w") as f:
        json.dump(output, f, indent=2)
    print(f"\nSaved: {args.output}")


if __name__ == "__main__":
    main()
