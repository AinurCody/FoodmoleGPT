"""GP surrogate + EI acquisition for discrete candidate pool."""

import torch
from botorch.models import SingleTaskGP
from botorch.fit import fit_gpytorch_mll
from botorch.acquisition import LogExpectedImprovement
from gpytorch.mlls import ExactMarginalLogLikelihood


def fit_gp_and_get_ei(
    train_X: torch.Tensor,
    train_Y: torch.Tensor,
    candidate_X: torch.Tensor,
    best_f: float,
) -> torch.Tensor:
    """Fit GP to observed data and compute EI on candidate points.

    Args:
        train_X: (n_observed, d) observed input features
        train_Y: (n_observed, 1) observed objective values
        candidate_X: (n_candidates, d) unobserved candidate features
        best_f: best observed value so far

    Returns:
        ei_values: (n_candidates,) EI at each candidate point
    """
    model = SingleTaskGP(train_X, train_Y)
    mll = ExactMarginalLogLikelihood(model.likelihood, model)
    fit_gpytorch_mll(mll)

    log_ei = LogExpectedImprovement(model=model, best_f=best_f)
    # LogEI expects (batch, q, d) shape; q=1 for single-point acquisition
    ei_values = log_ei(candidate_X.unsqueeze(1))
    return ei_values
