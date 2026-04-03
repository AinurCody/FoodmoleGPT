"""Generate a larger candidate pool on the mixture simplex.

The Sahraee 2022 paper defines a mixture design with:
  CE + GE + HS = 2.0 ml/100ml
  Each component in [0, 1] ml/100ml

We discretize this simplex at step=0.1 to create 66 candidate points,
then compute predicted DPPH using a quadratic Scheffe model fitted to
the 5 experimentally-reported DPPH values from the paper.

This gives a candidate pool large enough for meaningful BO vs Random comparison.
"""

import numpy as np
import pandas as pd

# --- Known experimental DPPH values ---
KNOWN_POINTS = {
    (0.83, 0.83, 0.34): 76.09,  # S5
    (0.83, 0.34, 0.83): 85.11,  # S9
    (0.50, 0.50, 1.00): 86.75,  # S10
    (0.34, 0.83, 0.83): 83.19,  # S12
    (0.50, 1.00, 0.50): 90.84,  # S14 (published best)
}


def generate_simplex_grid(step=0.1, total=2.0, bounds=(0.0, 1.0)):
    """Generate grid points on the mixture simplex CE+GE+HS=total.

    Each component is constrained to [bounds[0], bounds[1]].
    """
    lo, hi = bounds
    points = []
    ce_vals = np.arange(lo, hi + step / 2, step)
    for ce in ce_vals:
        ge_lo = max(lo, total - ce - hi)
        ge_hi = min(hi, total - ce - lo)
        if ge_lo > ge_hi + 1e-9:
            continue
        ge_vals = np.arange(ge_lo, ge_hi + step / 2, step)
        for ge in ge_vals:
            hs = total - ce - ge
            if lo - 1e-9 <= hs <= hi + 1e-9:
                points.append((round(ce, 4), round(ge, 4), round(hs, 4)))
    return points


def fit_quadratic_model(known_points):
    """Fit a quadratic Scheffe mixture model to known data points."""
    points = list(known_points.keys())
    values = list(known_points.values())

    def features(ce, ge, hs):
        return [ce, ge, hs, ce * ge, ce * hs, ge * hs]

    X = np.array([features(*p) for p in points])
    y = np.array(values)

    # Ridge regression (small lambda for stability with 6 params, 5 points)
    lam = 0.01
    beta = np.linalg.solve(X.T @ X + lam * np.eye(6), X.T @ y)
    return beta


def predict_dpph(ce, ge, hs, beta):
    """Predict DPPH using quadratic model."""
    x = np.array([ce, ge, hs, ce * ge, ce * hs, ge * hs])
    return float(x @ beta)


def main():
    # Fit model
    beta = fit_quadratic_model(KNOWN_POINTS)
    print(f"Fitted quadratic model coefficients:")
    names = ["CE", "GE", "HS", "CE*GE", "CE*HS", "GE*HS"]
    for name, b in zip(names, beta):
        print(f"  {name}: {b:.4f}")

    # Generate grid
    grid = generate_simplex_grid(step=0.1)
    print(f"\nGrid points: {len(grid)}")

    # Build DataFrame
    rows = []
    for i, (ce, ge, hs) in enumerate(grid):
        # Check if this is close to a known experimental point
        dpph = None
        source = "model_predicted"
        for known_pt, known_val in KNOWN_POINTS.items():
            if (abs(ce - known_pt[0]) < 0.05
                and abs(ge - known_pt[1]) < 0.05
                and abs(hs - known_pt[2]) < 0.05):
                dpph = known_val
                source = "paper_reported"
                break
        if dpph is None:
            dpph = predict_dpph(ce, ge, hs, beta)

        rows.append({
            "idx": i,
            "CE_ml_per_100ml": ce,
            "GE_ml_per_100ml": ge,
            "HS_ml_per_100ml": hs,
            "DPPH_inhibition_pct": round(dpph, 2),
            "source": source,
        })

    df = pd.DataFrame(rows)

    # Summary stats
    print(f"\nDPPH range: [{df['DPPH_inhibition_pct'].min():.2f}, "
          f"{df['DPPH_inhibition_pct'].max():.2f}]")
    print(f"Paper-reported points: {len(df[df['source'] == 'paper_reported'])}")
    print(f"Model-predicted points: {len(df[df['source'] == 'model_predicted'])}")

    # Top 10
    print("\nTop 10 candidates by DPPH:")
    top10 = df.nlargest(10, "DPPH_inhibition_pct")
    print(top10.to_string(index=False))

    # Bottom 5
    print("\nBottom 5 candidates by DPPH:")
    bot5 = df.nsmallest(5, "DPPH_inhibition_pct")
    print(bot5.to_string(index=False))

    # Save
    out_path = "data/candidates_grid.csv"
    df.to_csv(out_path, index=False)
    print(f"\nSaved: {out_path}")

    return df


if __name__ == "__main__":
    main()
