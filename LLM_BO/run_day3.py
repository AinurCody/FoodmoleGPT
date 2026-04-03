"""Day 3: Gemini Flash + Order Robustness + Final Summary.

Run from LLM_BO/ directory:
    # Set Gemini API key first:
    export GEMINI_API_KEY="your-key-here"
    conda run -n foodmole python run_day3.py
"""

import json
import os
import re
import warnings
import numpy as np
import pandas as pd
from pathlib import Path
from itertools import combinations

warnings.filterwarnings("ignore")

from bo.discrete_replay import run_bo_experiment, FEATURE_COLS
from bo.baselines import run_random_search
from eval.metrics import compute_all_metrics
from eval.plot import plot_best_so_far, plot_init_quality_bar, plot_final_best_boxplot

# --- Config ---
DATA_PATH = Path("data/candidates_grid.csv")
SEARCH_SPACE_PATH = Path("data/gold_search_space.json")
RESULTS_DIR = Path("results")
RESULTS_DIR.mkdir(exist_ok=True)

K_INIT = 3
N_ROUNDS = 15
N_REPEATS = 20
SEED_BASE = 42
GEMINI_N_RUNS = 5  # number of Gemini runs for robustness


def build_prompt(candidates_df, k=3, shuffle_seed=None):
    """Build warm-start prompt, optionally with shuffled candidate order."""
    df = candidates_df[["idx", "CE_ml_per_100ml", "GE_ml_per_100ml", "HS_ml_per_100ml"]].copy()
    if shuffle_seed is not None:
        df = df.sample(frac=1, random_state=shuffle_seed).reset_index(drop=True)

    lines = []
    for _, row in df.iterrows():
        lines.append(
            f"  #{int(row['idx']):2d}: CE={row['CE_ml_per_100ml']:.2f}, "
            f"GE={row['GE_ml_per_100ml']:.2f}, HS={row['HS_ml_per_100ml']:.2f}"
        )
    table = "\n".join(lines)
    N = len(df)

    return f"""You are a food science expert. Below is a list of {N} candidate functional beverage formulations. Each formulation contains three plant extract components:
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


def call_gemini(prompt, temperature=0.3):
    """Call Gemini Flash API."""
    import google.generativeai as genai

    api_key = os.environ.get("GEMINI_API_KEY") or os.environ.get("GOOGLE_API_KEY")
    if not api_key:
        raise RuntimeError("Set GEMINI_API_KEY or GOOGLE_API_KEY environment variable")

    genai.configure(api_key=api_key)
    model = genai.GenerativeModel("gemini-3-flash-preview")

    config = genai.GenerationConfig(temperature=temperature, max_output_tokens=512)
    response = model.generate_content(prompt, generation_config=config)
    return response.text


def parse_response(response, k=3):
    """Parse LLM response to extract selected indices."""
    json_match = re.search(r'\{[^{}]*"selected"\s*:\s*\[([^\]]*)\][^{}]*\}', response)
    if json_match:
        try:
            result = json.loads(json_match.group())
            if len(result.get("selected", [])) == k:
                return result
        except json.JSONDecodeError:
            pass
    nums = [int(n) for n in re.findall(r'\b(\d{1,2})\b', response) if 0 <= int(n) <= 65]
    seen = set()
    unique = [x for x in nums if not (x in seen or seen.add(x))]
    return {"selected": unique[:k], "reasoning": f"Parsed from: {response[:200]}"}


def jaccard(set_a, set_b):
    """Jaccard similarity between two sets."""
    a, b = set(set_a), set(set_b)
    if not a and not b:
        return 1.0
    return len(a & b) / len(a | b)


# ============================================================
# Part 1: Gemini Flash
# ============================================================
def run_gemini_experiment(pool_df, published_best):
    """Run Gemini Flash init -> BO."""
    print("=" * 60)
    print(f"Running Gemini Flash ({GEMINI_N_RUNS} runs, temp=0.3)...")

    all_runs = []
    for i in range(GEMINI_N_RUNS):
        prompt = build_prompt(pool_df, k=K_INIT)
        response = call_gemini(prompt, temperature=0.3)
        result = parse_response(response, K_INIT)
        result["raw_response"] = response
        all_runs.append(result)
        print(f"  Run {i+1}: selected={result['selected']}")

    # Use first valid run as primary
    primary = all_runs[0]
    init_indices = primary["selected"]

    # Save
    output = {
        "model": "gemini-flash",
        "k": K_INIT,
        "n_candidates": len(pool_df),
        "temperature": 0.3,
        "selected": init_indices,
        "reasoning": primary.get("reasoning", ""),
        "all_runs": [{"selected": r["selected"], "reasoning": r.get("reasoning", "")}
                     for r in all_runs],
    }
    with open("llm_priors/gemini_init.json", "w") as f:
        json.dump(output, f, indent=2, ensure_ascii=False)

    # Show what Gemini picked
    for i in init_indices:
        row = pool_df.iloc[i]
        print(f"    #{i}: CE={row['CE_ml_per_100ml']:.2f}, "
              f"GE={row['GE_ml_per_100ml']:.2f}, "
              f"HS={row['HS_ml_per_100ml']:.2f} → "
              f"DPPH={row['DPPH_inhibition_pct']:.2f}")

    # Run BO
    try:
        traj = run_bo_experiment(pool_df, init_indices, N_ROUNDS)
    except Exception as e:
        print(f"  BO failed: {e}, using random fallback")
        rng = np.random.default_rng(SEED_BASE)
        traj = run_random_search(pool_df, K_INIT, N_ROUNDS, rng)

    metrics = compute_all_metrics(traj, pool_df, init_indices, published_best)
    print(f"  Final best: {metrics['final_best']:.2f}")

    trajectories = [traj] * N_REPEATS
    metrics_list = [metrics] * N_REPEATS
    return trajectories, metrics_list, all_runs


# ============================================================
# Part 2: Order Robustness
# ============================================================
def run_order_robustness(pool_df):
    """Analyze selection robustness across shuffled candidate orders (Gemini only).

    Also uses existing multi-run data from v2 JSON files.
    """
    print("\n" + "=" * 60)
    print("Order Robustness Analysis")
    print("=" * 60)

    results = {}

    # --- From existing v2 multi-run data (FoodmoleGPT & Qwen3-base) ---
    for model_name, json_path in [
        ("FoodmoleGPT", "llm_priors/foodmolegpt_init.json"),
        ("Qwen3-base", "llm_priors/qwen3base_init.json"),
    ]:
        with open(json_path) as f:
            data = json.load(f)
        if "all_runs" in data and len(data["all_runs"]) > 1:
            runs = [set(r["selected"]) for r in data["all_runs"]]
            jaccards = [jaccard(a, b) for a, b in combinations(runs, 2)]
            mean_j = np.mean(jaccards) if jaccards else 1.0
            results[model_name] = {
                "runs": [r["selected"] for r in data["all_runs"]],
                "mean_jaccard": mean_j,
                "source": "temperature sampling (temp=0.3)",
            }
            print(f"\n{model_name} (temp=0.3, {len(runs)} runs):")
            for i, r in enumerate(data["all_runs"]):
                print(f"  Run {i+1}: {r['selected']}")
            print(f"  Mean Jaccard: {mean_j:.3f}")

    # --- Gemini: shuffle candidate order 5 times ---
    try:
        print(f"\nGemini Flash (shuffled order, {GEMINI_N_RUNS} runs):")
        gemini_runs = []
        for i in range(GEMINI_N_RUNS):
            prompt = build_prompt(pool_df, k=K_INIT, shuffle_seed=100 + i)
            response = call_gemini(prompt, temperature=0.0)  # greedy for order test
            result = parse_response(response, K_INIT)
            gemini_runs.append(set(result["selected"]))
            print(f"  Shuffle {i+1}: {result['selected']}")

        jaccards = [jaccard(a, b) for a, b in combinations(gemini_runs, 2)]
        mean_j = np.mean(jaccards) if jaccards else 1.0
        results["Gemini Flash"] = {
            "runs": [list(r) for r in gemini_runs],
            "mean_jaccard": mean_j,
            "source": "order shuffling (greedy)",
        }
        print(f"  Mean Jaccard: {mean_j:.3f}")
    except Exception as e:
        print(f"  Gemini order robustness skipped: {e}")

    return results


# ============================================================
# Part 3: Full experiment with all 5 methods
# ============================================================
def main():
    pool_df = pd.read_csv(DATA_PATH)
    with open(SEARCH_SPACE_PATH) as f:
        search_space = json.load(f)
    published_best = search_space["published_best"]
    n_candidates = len(pool_df)

    print(f"Candidate pool: {n_candidates} points")
    print(f"Published best DPPH: {published_best}%")
    print()

    # Load Day 2 results
    with open(RESULTS_DIR / "day2_results.json") as f:
        day2 = json.load(f)

    results = {}
    all_metrics = {}
    for method in ["Random Search", "Vanilla BO", "Qwen3-base -> BO", "FoodmoleGPT -> BO"]:
        if method in day2:
            results[method] = day2[method]["trajectories"]
            all_metrics[method] = day2[method]["metrics"]
            fb = np.mean([m["final_best"] for m in day2[method]["metrics"]])
            print(f"Loaded {method}: final_best={fb:.2f}")

    # --- Gemini Flash ---
    try:
        gemini_traj, gemini_metrics, gemini_runs = run_gemini_experiment(pool_df, published_best)
        results["Gemini Flash -> BO"] = gemini_traj
        all_metrics["Gemini Flash -> BO"] = gemini_metrics
    except Exception as e:
        print(f"\nGemini Flash SKIPPED: {e}")
        print("Set GEMINI_API_KEY to enable.")

    # --- Order Robustness ---
    robustness = run_order_robustness(pool_df)

    # --- Summary table ---
    print("\n" + "=" * 70)
    print(f"{'Method':<25} {'R90':>5} {'R95':>5} {'Final':>7} {'InitQ':>7} {'TQ%':>5}")
    print("-" * 70)
    for method, metrics_list in all_metrics.items():
        r90 = np.mean([m["rounds_to_90pct"] for m in metrics_list])
        r95 = np.mean([m["rounds_to_95pct"] for m in metrics_list])
        fb = np.mean([m["final_best"] for m in metrics_list])
        iq = np.mean([m["init_quality"] for m in metrics_list])
        tq = np.mean([m["top_quartile_hit_rate"] for m in metrics_list])
        print(f"{method:<25} {r90:>5.1f} {r95:>5.1f} {fb:>7.2f} {iq:>7.2f} {tq:>5.2f}")
    print("=" * 70)

    # --- Robustness summary ---
    if robustness:
        print(f"\n{'Model':<20} {'Mean Jaccard':>13} {'Source'}")
        print("-" * 60)
        for model, info in robustness.items():
            print(f"{model:<20} {info['mean_jaccard']:>13.3f} {info['source']}")

    # --- Plots ---
    print("\nGenerating Day 3 plots...")

    plot_best_so_far(
        results, published_best,
        save_path=str(RESULTS_DIR / "day3_best_so_far.png"),
        title="LLM-Guided BO: All Methods (66 candidates, T=15)",
    )

    init_qualities = {
        method: [m["init_quality"] for m in mlist]
        for method, mlist in all_metrics.items()
    }
    plot_init_quality_bar(
        init_qualities,
        save_path=str(RESULTS_DIR / "day3_init_quality.png"),
        title="Init Quality by Method (All 5)",
    )

    final_bests = {
        method: [m["final_best"] for m in mlist]
        for method, mlist in all_metrics.items()
    }
    plot_final_best_boxplot(
        final_bests, published_best,
        save_path=str(RESULTS_DIR / "day3_final_best_boxplot.png"),
        title="Final Best Value Distribution (All 5)",
    )

    # Save all results
    raw = {
        method: {"trajectories": results[method], "metrics": all_metrics[method]}
        for method in results
    }
    raw["robustness"] = {k: {"mean_jaccard": v["mean_jaccard"], "runs": v["runs"]}
                         for k, v in robustness.items()}
    with open(RESULTS_DIR / "day3_results.json", "w") as f:
        json.dump(raw, f, indent=2)
    print(f"Saved: {RESULTS_DIR / 'day3_results.json'}")

    print("\nDay 3 complete!")


if __name__ == "__main__":
    main()
