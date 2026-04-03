"""Discrete retrospective replay BO on a fixed candidate pool."""

import numpy as np
import pandas as pd
import torch
from bo.gp_model import fit_gp_and_get_ei


FEATURE_COLS = ["CE_ml_per_100ml", "GE_ml_per_100ml", "HS_ml_per_100ml"]
OBJECTIVE_COL = "DPPH_inhibition_pct"


class DiscreteReplayBO:
    """Bayesian Optimization via retrospective replay on a fixed candidate pool.

    At each step:
      1. Fit GP to observed points
      2. Compute EI on unobserved candidates
      3. Select argmax EI, move to observed, return its true objective value
    """

    def __init__(self, candidate_pool_df: pd.DataFrame, init_indices: list[int]):
        self.pool = candidate_pool_df.reset_index(drop=True)
        self.features = torch.tensor(
            self.pool[FEATURE_COLS].values, dtype=torch.double
        )
        self.objectives = torch.tensor(
            self.pool[OBJECTIVE_COL].values, dtype=torch.double
        )
        self.observed = list(init_indices)
        self.unobserved = [
            i for i in range(len(self.pool)) if i not in init_indices
        ]

    def _get_observed_data(self):
        idx = self.observed
        train_X = self.features[idx]
        train_Y = self.objectives[idx].unsqueeze(-1)
        return train_X, train_Y

    def step(self) -> float:
        """Run one BO iteration. Returns the objective value of the selected point."""
        if not self.unobserved:
            return self.objectives[self.observed].max().item()

        train_X, train_Y = self._get_observed_data()
        best_f = train_Y.max().item()

        candidate_X = self.features[self.unobserved]

        ei_values = fit_gp_and_get_ei(train_X, train_Y, candidate_X, best_f)

        # Select candidate with highest EI
        best_candidate_idx = ei_values.argmax().item()
        selected_pool_idx = self.unobserved[best_candidate_idx]

        # Move to observed
        self.observed.append(selected_pool_idx)
        self.unobserved.remove(selected_pool_idx)

        return self.objectives[selected_pool_idx].item()

    def run(self, n_rounds: int) -> list[float]:
        """Run n_rounds of BO, return best-so-far trajectory.

        Returns list of length (n_rounds + 1): initial best, then best after each round.
        """
        init_vals = self.objectives[self.observed]
        best_so_far = [init_vals.max().item()]

        for _ in range(n_rounds):
            val = self.step()
            best_so_far.append(max(best_so_far[-1], val))

        return best_so_far


def run_bo_experiment(
    pool_df: pd.DataFrame,
    init_indices: list[int],
    n_rounds: int,
) -> list[float]:
    """Convenience wrapper: run one BO experiment and return best-so-far."""
    bo = DiscreteReplayBO(pool_df, init_indices)
    return bo.run(n_rounds)
