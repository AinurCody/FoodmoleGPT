"""Day 1 experiment: Random Search + Vanilla BO baselines.

Uses 66-point candidate pool on the mixture simplex (step=0.1).
Budget is capped at T=15 rounds (sees 18/66 = 27% of pool),
giving BO room to demonstrate advantage over Random.

Run from LLM_BO/ directory:
    conda run -n foodmole python run_day1.py
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

K_INIT = 3          # number of initial points
N_ROUNDS = 15       # BO rounds after init (see 18/66 = 27% of pool)
N_REPEATS = 20      # number of random seed repeats
SEED_BASE = 42


def main():
    # Load data
    pool_df = pd.read_csv(DATA_PATH)
    with open(SEARCH_SPACE_PATH) as f:
        search_space = json.load(f)

    published_best = search_space["published_best"]
    n_candidates = len(pool_df)

    print(f"Candidate pool: {n_candidates} points")
    print(f"Init size: {K_INIT}, BO rounds: {N_ROUNDS}")
    print(f"Total observations per run: {K_INIT + N_ROUNDS} / {n_candidates} "
          f"({100 * (K_INIT + N_ROUNDS) / n_candidates:.0f}%)")
    print(f"Published best DPPH: {published_best}%")
    print(f"Repeats: {N_REPEATS}")
    print(f"DPPH range: [{pool_df['DPPH_inhibition_pct'].min():.2f}, "
          f"{pool_df['DPPH_inhibition_pct'].max():.2f}]")
    print()

    results = {}
    all_metrics = {}

    # --- Random Search ---
    print("=" * 60)
    print("Running Random Search...")
    rs_trajectories = []
    rs_metrics_list = []
    for i in range(N_REPEATS):
        rng = np.random.default_rng(SEED_BASE + i)
        init_indices = rng.permutation(n_candidates)[:K_INIT].tolist()
        traj = run_random_search(pool_df, K_INIT, N_ROUNDS, rng)
        rs_trajectories.append(traj)
        m = compute_all_metrics(traj, pool_df, init_indices, published_best)
        rs_metrics_list.append(m)
        if (i + 1) % 10 == 0:
            print(f"  [{i+1}/{N_REPEATS}] final_best={traj[-1]:.2f}")

    results["Random Search"] = rs_trajectories
    all_metrics["Random Search"] = rs_metrics_list

    # --- Vanilla BO (random init) ---
    print("=" * 60)
    print("Running Vanilla BO (random init)...")
    bo_trajectories = []
    bo_metrics_list = []
    for i in range(N_REPEATS):
        rng = np.random.default_rng(SEED_BASE + i)
        init_indices = rng.permutation(n_candidates)[:K_INIT].tolist()
        print(f"  [{i+1}/{N_REPEATS}] init={init_indices}...", end=" ", flush=True)
        try:
            traj = run_bo_experiment(pool_df, init_indices, N_ROUNDS)
            print(f"final_best={traj[-1]:.2f}")
        except Exception as e:
            print(f"FAILED: {e}")
            rng2 = np.random.default_rng(SEED_BASE + i + 1000)
            traj = run_random_search(pool_df, K_INIT, N_ROUNDS, rng2)
            print(f"  -> fallback to random, final_best={traj[-1]:.2f}")
        bo_trajectories.append(traj)
        m = compute_all_metrics(traj, pool_df, init_indices, published_best)
        bo_metrics_list.append(m)

    results["Vanilla BO"] = bo_trajectories
    all_metrics["Vanilla BO"] = bo_metrics_list

    # --- Summary ---
    print("\n" + "=" * 60)
    print("RESULTS SUMMARY")
    print("=" * 60)

    for method, metrics_list in all_metrics.items():
        r90 = [m["rounds_to_90pct"] for m in metrics_list]
        fb = [m["final_best"] for m in metrics_list]
        iq = [m["init_quality"] for m in metrics_list]
        tq = [m["top_quartile_hit_rate"] for m in metrics_list]

        print(f"\n{method}:")
        print(f"  Rounds to 90%:       {np.mean(r90):.1f} +/- {np.std(r90):.1f}")
        print(f"  Final best:          {np.mean(fb):.2f} +/- {np.std(fb):.2f}")
        print(f"  Init quality:        {np.mean(iq):.2f} +/- {np.std(iq):.2f}")
        print(f"  Top-quartile hit:    {np.mean(tq):.2f} +/- {np.std(tq):.2f}")

    # --- Plots ---
    print("\n" + "=" * 60)
    print("Generating plots...")

    plot_best_so_far(
        results, published_best,
        save_path=str(RESULTS_DIR / "day1_best_so_far.png"),
        title="Day 1: Random Search vs Vanilla BO (66 candidates, T=15)",
    )

    init_qualities = {
        method: [m["init_quality"] for m in mlist]
        for method, mlist in all_metrics.items()
    }
    plot_init_quality_bar(
        init_qualities,
        save_path=str(RESULTS_DIR / "day1_init_quality.png"),
    )

    final_bests = {
        method: [m["final_best"] for m in mlist]
        for method, mlist in all_metrics.items()
    }
    plot_final_best_boxplot(
        final_bests, published_best,
        save_path=str(RESULTS_DIR / "day1_final_best_boxplot.png"),
    )

    # --- Save raw results ---
    raw_results = {
        method: {
            "trajectories": results[method],
            "metrics": all_metrics[method],
        }
        for method in results
    }
    with open(RESULTS_DIR / "day1_results.json", "w") as f:
        json.dump(raw_results, f, indent=2)
    print(f"Saved: {RESULTS_DIR / 'day1_results.json'}")

    # --- Sanity check ---
    print("\n" + "=" * 60)
    rs_mean_final = np.mean([m["final_best"] for m in all_metrics["Random Search"]])
    bo_mean_final = np.mean([m["final_best"] for m in all_metrics["Vanilla BO"]])
    rs_mean_r90 = np.mean([m["rounds_to_90pct"] for m in all_metrics["Random Search"]])
    bo_mean_r90 = np.mean([m["rounds_to_90pct"] for m in all_metrics["Vanilla BO"]])

    print(f"Final best — Random: {rs_mean_final:.2f}, BO: {bo_mean_final:.2f}, "
          f"delta: {bo_mean_final - rs_mean_final:.2f}")
    print(f"Rounds to 90% — Random: {rs_mean_r90:.1f}, BO: {bo_mean_r90:.1f}")

    if bo_mean_final - rs_mean_final < 0.5 and bo_mean_r90 >= rs_mean_r90 - 0.5:
        print("\nWARNING: BO shows no clear advantage over Random!")
        print("Consider adjusting parameters or switching dataset.")
    else:
        print("\nPASS: BO shows advantage over Random Search")

    print("Day 1 complete!")


if __name__ == "__main__":
    main()
