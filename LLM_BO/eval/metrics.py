"""Evaluation metrics for BO experiments."""

import numpy as np
import pandas as pd


OBJECTIVE_COL = "DPPH_inhibition_pct"


def rounds_to_threshold(
    best_so_far: list[float],
    threshold: float,
) -> int | None:
    """Number of rounds to reach a given threshold.

    Returns the round index (0-based, where 0 = after init) at which
    best_so_far first reaches the threshold, or None if never reached.
    """
    for i, val in enumerate(best_so_far):
        if val >= threshold:
            return i
    return None


def rounds_to_90pct(
    best_so_far: list[float],
    published_best: float,
) -> int | None:
    """Rounds to reach 90% of published best."""
    return rounds_to_threshold(best_so_far, published_best * 0.9)


def rounds_to_95pct(
    best_so_far: list[float],
    published_best: float,
) -> int | None:
    """Rounds to reach 95% of published best."""
    return rounds_to_threshold(best_so_far, published_best * 0.95)


def final_best(best_so_far: list[float]) -> float:
    """Final best value at budget T."""
    return best_so_far[-1]


def init_quality(
    pool_df: pd.DataFrame,
    init_indices: list[int],
) -> float:
    """Mean objective value of the initial k points."""
    return pool_df.iloc[init_indices][OBJECTIVE_COL].mean()


def top_quartile_hit_rate(
    pool_df: pd.DataFrame,
    init_indices: list[int],
) -> float:
    """Fraction of init points that fall in the top 25% of all candidates."""
    objectives = pool_df[OBJECTIVE_COL].values
    q75 = np.percentile(objectives, 75)
    init_vals = objectives[init_indices]
    return np.mean(init_vals >= q75)


def compute_all_metrics(
    best_so_far: list[float],
    pool_df: pd.DataFrame,
    init_indices: list[int],
    published_best: float,
) -> dict:
    """Compute all P0 metrics for one experiment run."""
    r90 = rounds_to_90pct(best_so_far, published_best)
    r95 = rounds_to_95pct(best_so_far, published_best)
    n = len(best_so_far)
    return {
        "rounds_to_90pct": r90 if r90 is not None else n,
        "rounds_to_95pct": r95 if r95 is not None else n,
        "final_best": final_best(best_so_far),
        "init_quality": init_quality(pool_df, init_indices),
        "top_quartile_hit_rate": top_quartile_hit_rate(pool_df, init_indices),
    }
