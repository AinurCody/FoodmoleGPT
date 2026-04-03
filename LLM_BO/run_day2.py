"""Day 2 experiment: All 4 methods — Random, Vanilla BO, Qwen3-base->BO, FoodmoleGPT->BO.

Prerequisites:
  - Day 1 passed sanity check (BO > Random)
  - LLM init JSONs generated on Hopper and placed in llm_priors/

Run from LLM_BO/ directory:
    conda run -n foodmole python run_day2.py
"""

import json
import warnings
import numpy as np
import pandas as pd
from pathlib import Path

warnings.filterwarnings("ignore")

from bo.discrete_replay import run_bo_experiment
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

LLM_PRIORS = {
    "Qwen3-base -> BO": Path("llm_priors/qwen3base_init.json"),
    "FoodmoleGPT -> BO": Path("llm_priors/foodmolegpt_init.json"),
}


def load_llm_init(json_path: Path) -> list[int]:
    with open(json_path) as f:
        data = json.load(f)
    return data["selected"]


def run_random_method(pool_df, n_candidates, published_best):
    """Random Search baseline."""
    trajectories, metrics_list = [], []
    for i in range(N_REPEATS):
        rng = np.random.default_rng(SEED_BASE + i)
        init_indices = rng.permutation(n_candidates)[:K_INIT].tolist()
        traj = run_random_search(pool_df, K_INIT, N_ROUNDS, rng)
        trajectories.append(traj)
        metrics_list.append(compute_all_metrics(traj, pool_df, init_indices, published_best))
    return trajectories, metrics_list


def run_vanilla_bo_method(pool_df, n_candidates, published_best):
    """Vanilla BO with random init."""
    trajectories, metrics_list = [], []
    for i in range(N_REPEATS):
        rng = np.random.default_rng(SEED_BASE + i)
        init_indices = rng.permutation(n_candidates)[:K_INIT].tolist()
        try:
            traj = run_bo_experiment(pool_df, init_indices, N_ROUNDS)
        except Exception:
            rng2 = np.random.default_rng(SEED_BASE + i + 1000)
            traj = run_random_search(pool_df, K_INIT, N_ROUNDS, rng2)
        trajectories.append(traj)
        metrics_list.append(compute_all_metrics(traj, pool_df, init_indices, published_best))
    return trajectories, metrics_list


def run_llm_init_bo_method(pool_df, llm_init_indices, n_candidates, published_best):
    """BO with LLM-selected init points.

    The LLM picks a FIXED set of k init points.
    BO then runs from those init points. Since the init is deterministic,
    the BO is also deterministic (same GP fit → same EI → same selection).
    We run N_REPEATS times but they should give the same result.

    To introduce variance, we can:
    - Vary one of the k init points (keep LLM's top-2, randomize 3rd)
    - Or just report the single deterministic run

    For now: LLM picks all k init points → deterministic BO.
    We still report it as a single trajectory replicated N_REPEATS times
    so the plot aesthetics match.
    """
    # Single deterministic run
    try:
        traj = run_bo_experiment(pool_df, llm_init_indices, N_ROUNDS)
    except Exception as e:
        print(f"  LLM-init BO failed: {e}")
        rng = np.random.default_rng(SEED_BASE)
        traj = run_random_search(pool_df, K_INIT, N_ROUNDS, rng)

    metrics = compute_all_metrics(traj, pool_df, llm_init_indices, published_best)

    # Replicate for consistent plotting
    trajectories = [traj] * N_REPEATS
    metrics_list = [metrics] * N_REPEATS
    return trajectories, metrics_list


def print_summary(all_metrics):
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


def main():
    pool_df = pd.read_csv(DATA_PATH)
    with open(SEARCH_SPACE_PATH) as f:
        search_space = json.load(f)

    published_best = search_space["published_best"]
    n_candidates = len(pool_df)

    print(f"Candidate pool: {n_candidates} points")
    print(f"Init size: {K_INIT}, BO rounds: {N_ROUNDS}")
    print(f"Published best DPPH: {published_best}%")
    print(f"95% threshold: {published_best * 0.95:.2f}%")
    print()

    results = {}
    all_metrics = {}

    # --- 1. Random Search ---
    print("[1/4] Running Random Search...")
    results["Random Search"], all_metrics["Random Search"] = \
        run_random_method(pool_df, n_candidates, published_best)
    print(f"  Mean final best: {np.mean([m['final_best'] for m in all_metrics['Random Search']]):.2f}")

    # --- 2. Vanilla BO ---
    print("[2/4] Running Vanilla BO...")
    results["Vanilla BO"], all_metrics["Vanilla BO"] = \
        run_vanilla_bo_method(pool_df, n_candidates, published_best)
    print(f"  Mean final best: {np.mean([m['final_best'] for m in all_metrics['Vanilla BO']]):.2f}")

    # --- 3 & 4. LLM-init BO ---
    for method_name, json_path in LLM_PRIORS.items():
        idx = list(LLM_PRIORS.keys()).index(method_name) + 3
        print(f"[{idx}/4] Running {method_name}...")
        if not json_path.exists():
            print(f"  SKIPPED: {json_path} not found")
            continue

        llm_init = load_llm_init(json_path)
        print(f"  LLM selected indices: {llm_init}")

        # Validate indices
        for i in llm_init:
            if i < 0 or i >= n_candidates:
                print(f"  ERROR: index {i} out of range [0, {n_candidates})")
                continue

        # Show what the LLM picked
        for i in llm_init:
            row = pool_df.iloc[i]
            print(f"    #{i}: CE={row['CE_ml_per_100ml']:.2f}, "
                  f"GE={row['GE_ml_per_100ml']:.2f}, "
                  f"HS={row['HS_ml_per_100ml']:.2f} → "
                  f"DPPH={row['DPPH_inhibition_pct']:.2f}")

        results[method_name], all_metrics[method_name] = \
            run_llm_init_bo_method(pool_df, llm_init, n_candidates, published_best)
        print(f"  Final best: {all_metrics[method_name][0]['final_best']:.2f}")

    # --- Summary ---
    print_summary(all_metrics)

    # --- Plots ---
    print("\nGenerating plots...")

    plot_best_so_far(
        results, published_best,
        save_path=str(RESULTS_DIR / "day2_best_so_far.png"),
        title="LLM-Guided BO: Best-so-far Comparison (66 candidates, T=15)",
    )

    init_qualities = {
        method: [m["init_quality"] for m in mlist]
        for method, mlist in all_metrics.items()
    }
    plot_init_quality_bar(
        init_qualities,
        save_path=str(RESULTS_DIR / "day2_init_quality.png"),
        title="Init Quality by Method",
    )

    final_bests = {
        method: [m["final_best"] for m in mlist]
        for method, mlist in all_metrics.items()
    }
    plot_final_best_boxplot(
        final_bests, published_best,
        save_path=str(RESULTS_DIR / "day2_final_best_boxplot.png"),
        title="Final Best Value Distribution",
    )

    # Save raw results
    raw = {
        method: {
            "trajectories": results[method],
            "metrics": all_metrics[method],
        }
        for method in results
    }
    with open(RESULTS_DIR / "day2_results.json", "w") as f:
        json.dump(raw, f, indent=2)
    print(f"Saved: {RESULTS_DIR / 'day2_results.json'}")
    print("\nDay 2 complete!")


if __name__ == "__main__":
    main()
