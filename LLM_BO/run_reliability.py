"""Reliability analysis for LLM-guided BO.

Four reliability dimensions:
  1. Prior hit rate (top-quartile / top-10%)
  2. Order perturbation stability (Jaccard)
  3. Constraint consistency (valid indices, sum constraint)
  4. Low-confidence fallback mechanism

Run from LLM_BO/ directory:
    GEMINI_API_KEY="..." conda run -n foodmole python run_reliability.py
"""

import json
import os
import re
import warnings
import numpy as np
import pandas as pd
from pathlib import Path
from itertools import combinations
from collections import Counter

warnings.filterwarnings("ignore")

DATA_PATH = Path("data/candidates_grid.csv")
RESULTS_DIR = Path("results")
RESULTS_DIR.mkdir(exist_ok=True)

OBJECTIVE_COL = "DPPH_inhibition_pct"


def load_all_priors():
    """Load all LLM prior JSONs."""
    priors = {}
    for name, path in [
        ("FoodmoleGPT", "llm_priors/foodmolegpt_init.json"),
        ("Qwen3-base", "llm_priors/qwen3base_init.json"),
        ("Gemini 3 Flash", "llm_priors/gemini_init.json"),
    ]:
        p = Path(path)
        if p.exists():
            with open(p) as f:
                priors[name] = json.load(f)
    return priors


# ============================================================
# 1. Prior Hit Rate
# ============================================================
def analyze_prior_hit_rate(pool_df, priors):
    """Compute top-quartile and top-10% hit rates for each model."""
    objectives = pool_df[OBJECTIVE_COL].values
    q75 = np.percentile(objectives, 75)
    q90 = np.percentile(objectives, 90)
    published_best = objectives.max()

    print("=" * 70)
    print("1. PRIOR HIT RATE (先验命中率)")
    print("=" * 70)
    print(f"   Pool size: {len(objectives)}")
    print(f"   Top-25% threshold (Q75): {q75:.2f}")
    print(f"   Top-10% threshold (Q90): {q90:.2f}")
    print(f"   Published best: {published_best:.2f}")
    print()

    results = {}
    for model, data in priors.items():
        all_runs = data.get("all_runs", [{"selected": data["selected"]}])

        all_hit25 = []
        all_hit10 = []
        all_hit_best = []

        for run in all_runs:
            selected = run["selected"]
            vals = [objectives[i] for i in selected if i < len(objectives)]

            hit25 = sum(1 for v in vals if v >= q75) / len(vals)
            hit10 = sum(1 for v in vals if v >= q90) / len(vals)
            hit_best = int(published_best in vals)

            all_hit25.append(hit25)
            all_hit10.append(hit10)
            all_hit_best.append(hit_best)

        results[model] = {
            "top25_mean": np.mean(all_hit25),
            "top10_mean": np.mean(all_hit10),
            "hit_best_rate": np.mean(all_hit_best),
            "n_runs": len(all_runs),
        }

        print(f"   {model} ({len(all_runs)} runs):")
        print(f"     Top-25% hit rate: {np.mean(all_hit25):.2f}")
        print(f"     Top-10% hit rate: {np.mean(all_hit10):.2f}")
        print(f"     Published best hit: {np.mean(all_hit_best):.0%} ({sum(all_hit_best)}/{len(all_runs)} runs)")
        print()

    # Random baseline (analytical)
    n = len(objectives)
    k = 3
    n_top25 = sum(1 for v in objectives if v >= q75)
    expected_hit25 = k * n_top25 / n
    print(f"   Random baseline (expected):")
    print(f"     Top-25% hit rate: {expected_hit25 / k:.2f}")
    print()

    return results


# ============================================================
# 2. Order Perturbation Stability
# ============================================================
def analyze_order_stability(pool_df, priors):
    """Analyze selection stability across runs."""
    print("=" * 70)
    print("2. ORDER PERTURBATION STABILITY (顺序扰动稳定性)")
    print("=" * 70)

    results = {}
    for model, data in priors.items():
        all_runs = data.get("all_runs", [{"selected": data["selected"]}])
        if len(all_runs) < 2:
            print(f"   {model}: only 1 run, skipping")
            continue

        run_sets = [set(r["selected"]) for r in all_runs]

        # Pairwise Jaccard
        jaccards = [
            len(a & b) / len(a | b) if a | b else 1.0
            for a, b in combinations(run_sets, 2)
        ]
        mean_jaccard = np.mean(jaccards)

        # Repeat selection rate: fraction of indices selected in >50% of runs
        all_indices = [idx for r in all_runs for idx in r["selected"]]
        counts = Counter(all_indices)
        n_runs = len(all_runs)
        stable_picks = [idx for idx, cnt in counts.items() if cnt > n_runs / 2]

        results[model] = {
            "mean_jaccard": mean_jaccard,
            "stable_picks": stable_picks,
            "n_runs": n_runs,
            "source": data.get("source", "temperature sampling"),
        }

        print(f"   {model} ({n_runs} runs):")
        print(f"     Mean Jaccard: {mean_jaccard:.3f}")
        print(f"     Stable picks (>50% runs): {stable_picks}")
        for idx, cnt in counts.most_common():
            val = pool_df.iloc[idx][OBJECTIVE_COL]
            print(f"       #{idx} (DPPH={val:.2f}): {cnt}/{n_runs} runs")
        print()

    return results


# ============================================================
# 3. Constraint Consistency
# ============================================================
def analyze_constraint_consistency(pool_df, priors):
    """Check if LLM outputs satisfy all constraints."""
    print("=" * 70)
    print("3. CONSTRAINT CONSISTENCY (约束一致性)")
    print("=" * 70)

    n_candidates = len(pool_df)
    results = {}

    for model, data in priors.items():
        all_runs = data.get("all_runs", [{"selected": data["selected"]}])
        k = data.get("k", 3)

        violations = {
            "out_of_range": 0,      # index outside [0, N-1]
            "wrong_count": 0,        # not exactly k selections
            "duplicates": 0,         # duplicate indices
            "total_runs": len(all_runs),
        }

        for run in all_runs:
            selected = run["selected"]

            # Check count
            if len(selected) != k:
                violations["wrong_count"] += 1

            # Check range
            for idx in selected:
                if idx < 0 or idx >= n_candidates:
                    violations["out_of_range"] += 1

            # Check duplicates
            if len(selected) != len(set(selected)):
                violations["duplicates"] += 1

        total_violations = sum(v for k_, v in violations.items() if k_ != "total_runs")
        violation_rate = total_violations / violations["total_runs"] if violations["total_runs"] > 0 else 0

        # Check reasoning for invalid claims
        reasoning = data.get("reasoning", "")
        raw = data.get("raw_response", "")

        results[model] = {
            "violations": violations,
            "violation_rate": violation_rate,
        }

        status = "PASS" if total_violations == 0 else f"FAIL ({total_violations} violations)"
        print(f"   {model}: {status}")
        print(f"     Out-of-range indices: {violations['out_of_range']}")
        print(f"     Wrong selection count: {violations['wrong_count']}")
        print(f"     Duplicate indices: {violations['duplicates']}")
        print(f"     Violation rate: {violation_rate:.0%}")
        print()

    return results


# ============================================================
# 4. Low-Confidence Fallback
# ============================================================
def build_confidence_prompt(pool_df, k=3):
    """Build prompt that also asks for confidence score."""
    candidates = pool_df[["idx", "CE_ml_per_100ml", "GE_ml_per_100ml", "HS_ml_per_100ml"]]
    lines = []
    for _, row in candidates.iterrows():
        lines.append(
            f"  #{int(row['idx']):2d}: CE={row['CE_ml_per_100ml']:.2f}, "
            f"GE={row['GE_ml_per_100ml']:.2f}, HS={row['HS_ml_per_100ml']:.2f}"
        )
    table = "\n".join(lines)
    N = len(candidates)

    return f"""You are a food science expert. Below is a list of {N} candidate functional beverage formulations. Each formulation contains three plant extract components:
- CE (Cardamom Essential oil, ml/100ml)
- GE (Ginger Extract, ml/100ml)
- HS (Hibiscus Solution, ml/100ml)

The three components satisfy the constraint: CE + GE + HS = 2.0 ml/100ml.

Candidate formulations:
{table}

The goal is to maximize DPPH free radical scavenging activity (antioxidant activity, measured as % inhibition).

Please select the {k} formulations that are most worth testing first. Also rate your confidence in each selection on a scale of 1-5:
  1 = pure guess, no domain basis
  2 = weak intuition
  3 = moderate confidence based on general knowledge
  4 = confident based on specific domain knowledge
  5 = very confident, strong literature evidence

Output ONLY valid JSON:
{{
  "selections": [
    {{"index": <int>, "confidence": <1-5>, "reason": "<brief>"}},
    ...
  ],
  "overall_confidence": <1-5>
}}"""


def run_confidence_fallback(pool_df):
    """Demonstrate the low-confidence fallback mechanism."""
    print("=" * 70)
    print("4. LOW-CONFIDENCE FALLBACK (低置信回退)")
    print("=" * 70)

    CONFIDENCE_THRESHOLD = 2  # fall back if overall_confidence <= 2

    try:
        import google.generativeai as genai
        api_key = os.environ.get("GEMINI_API_KEY") or os.environ.get("GOOGLE_API_KEY")
        if not api_key:
            raise RuntimeError("No API key")
        genai.configure(api_key=api_key)
        model = genai.GenerativeModel("gemini-3-flash-preview")
    except Exception as e:
        print(f"   Gemini not available: {e}")
        print("   Demonstrating fallback logic with mock data...")

        # Mock demonstration
        mock_result = {
            "selections": [
                {"index": 20, "confidence": 4, "reason": "High GE known for antioxidant"},
                {"index": 0, "confidence": 3, "reason": "Max GE+HS combination"},
                {"index": 12, "confidence": 3, "reason": "Balanced moderate ratios"},
            ],
            "overall_confidence": 3,
        }
        _demonstrate_fallback(mock_result, CONFIDENCE_THRESHOLD, is_mock=True)
        return {"source": "mock", "result": mock_result}

    # Real Gemini call
    prompt = build_confidence_prompt(pool_df)
    config = genai.GenerationConfig(temperature=0.0, max_output_tokens=512)
    response = model.generate_content(prompt, generation_config=config)
    raw = response.text
    print(f"   Raw response: {raw[:300]}...")

    # Parse
    json_match = re.search(r'\{[\s\S]*"selections"[\s\S]*\}', raw)
    if json_match:
        try:
            result = json.loads(json_match.group())
        except json.JSONDecodeError:
            result = {"selections": [], "overall_confidence": 1}
    else:
        result = {"selections": [], "overall_confidence": 1}

    _demonstrate_fallback(result, CONFIDENCE_THRESHOLD, is_mock=False)

    return {"source": "gemini", "result": result, "raw": raw}


def _demonstrate_fallback(result, threshold, is_mock=False):
    """Show the fallback decision logic."""
    prefix = "[MOCK] " if is_mock else ""

    overall = result.get("overall_confidence", 0)
    selections = result.get("selections", [])

    print(f"\n   {prefix}Confidence analysis:")
    for s in selections:
        idx = s.get("index", "?")
        conf = s.get("confidence", 0)
        reason = s.get("reason", "")
        print(f"     #{idx}: confidence={conf}/5 — {reason}")
    print(f"     Overall confidence: {overall}/5")

    if overall <= threshold:
        print(f"\n   DECISION: FALLBACK to random init (overall_confidence={overall} <= threshold={threshold})")
        print(f"   Reason: LLM is not confident enough in its domain knowledge for this task.")
        print(f"   Action: Use random k=3 init → standard Vanilla BO")
    else:
        print(f"\n   DECISION: ACCEPT LLM prior (overall_confidence={overall} > threshold={threshold})")
        print(f"   Action: Use LLM-selected init → BO with warm start")


# ============================================================
# Main
# ============================================================
def main():
    pool_df = pd.read_csv(DATA_PATH)
    priors = load_all_priors()

    print(f"Loaded priors: {list(priors.keys())}")
    print()

    # 1. Prior hit rate
    hit_results = analyze_prior_hit_rate(pool_df, priors)

    # 2. Order stability
    stability_results = analyze_order_stability(pool_df, priors)

    # 3. Constraint consistency
    constraint_results = analyze_constraint_consistency(pool_df, priors)

    # 4. Low-confidence fallback
    fallback_results = run_confidence_fallback(pool_df)

    # --- Save ---
    report = {
        "prior_hit_rate": hit_results,
        "order_stability": {k: {"mean_jaccard": v["mean_jaccard"], "stable_picks": v["stable_picks"]}
                           for k, v in stability_results.items()},
        "constraint_consistency": {k: {"violation_rate": v["violation_rate"]}
                                  for k, v in constraint_results.items()},
        "fallback": {"threshold": 2, "source": fallback_results.get("source", "unknown")},
    }
    with open(RESULTS_DIR / "reliability_report.json", "w") as f:
        json.dump(report, f, indent=2)
    print(f"\nSaved: {RESULTS_DIR / 'reliability_report.json'}")

    # --- Summary ---
    print("\n" + "=" * 70)
    print("RELIABILITY SUMMARY")
    print("=" * 70)
    print(f"\n{'Model':<18} {'Top25%':>7} {'Top10%':>7} {'BestHit':>8} {'Jaccard':>8} {'Violations':>11}")
    print("-" * 70)
    for model in priors:
        h = hit_results.get(model, {})
        s = stability_results.get(model, {})
        c = constraint_results.get(model, {})
        print(f"{model:<18} {h.get('top25_mean',0):>7.2f} {h.get('top10_mean',0):>7.2f} "
              f"{h.get('hit_best_rate',0):>7.0%} {s.get('mean_jaccard',0):>8.3f} "
              f"{c.get('violation_rate',0):>10.0%}")
    print()


if __name__ == "__main__":
    main()
