"""Random Search baseline for comparison with BO."""

import numpy as np
import pandas as pd


OBJECTIVE_COL = "DPPH_inhibition_pct"


def run_random_search(
    pool_df: pd.DataFrame,
    k_init: int,
    n_rounds: int,
    rng: np.random.Generator,
) -> list[float]:
    """Random search: randomly select points one at a time.

    Args:
        pool_df: candidate pool DataFrame
        k_init: number of initial points
        n_rounds: number of additional rounds after init
        rng: numpy random generator

    Returns:
        best-so-far trajectory of length (n_rounds + 1)
    """
    objectives = pool_df[OBJECTIVE_COL].values
    n_total = len(pool_df)

    # Random permutation of all indices
    perm = rng.permutation(n_total).tolist()

    # First k_init are the init, rest are sequential "rounds"
    init_indices = perm[:k_init]
    remaining = perm[k_init:]

    best_so_far = [max(objectives[i] for i in init_indices)]

    for round_idx in range(n_rounds):
        if round_idx < len(remaining):
            val = objectives[remaining[round_idx]]
        else:
            val = best_so_far[-1]  # pool exhausted
        best_so_far.append(max(best_so_far[-1], val))

    return best_so_far
