"""Visualization for BO experiments."""

import numpy as np
import matplotlib.pyplot as plt
import matplotlib
matplotlib.use("Agg")


def plot_best_so_far(
    results: dict[str, list[list[float]]],
    published_best: float,
    save_path: str,
    title: str = "Best-so-far Curve",
):
    """Plot best-so-far curves for multiple methods.

    Args:
        results: {method_name: list of best-so-far trajectories (one per repeat)}
        published_best: the best value from the published study
        save_path: path to save the figure
        title: plot title
    """
    colors = {
        "Random Search": "#888888",
        "Vanilla BO": "#2196F3",
        "Qwen3-base -> BO": "#FF9800",
        "FoodmoleGPT -> BO": "#E91E63",
        "Gemini Flash -> BO": "#4CAF50",
    }

    fig, ax = plt.subplots(figsize=(10, 6))

    for method_name, trajectories in results.items():
        arr = np.array(trajectories)
        mean = arr.mean(axis=0)
        std = arr.std(axis=0)
        x = np.arange(len(mean))

        color = colors.get(method_name, "#333333")
        ax.plot(x, mean, label=method_name, color=color, linewidth=2)
        ax.fill_between(x, mean - std, mean + std, alpha=0.15, color=color)

    # Published best reference line
    ax.axhline(
        y=published_best, color="red", linestyle="--", linewidth=1.5,
        label=f"Published best ({published_best:.1f}%)", alpha=0.7,
    )
    # 90% threshold
    ax.axhline(
        y=published_best * 0.9, color="orange", linestyle=":",
        linewidth=1, label=f"90% threshold ({published_best * 0.9:.1f}%)", alpha=0.5,
    )

    ax.set_xlabel("Round (0 = after init)", fontsize=12)
    ax.set_ylabel("Best Observed DPPH Inhibition (%)", fontsize=12)
    ax.set_title(title, fontsize=14)
    ax.legend(loc="lower right", fontsize=10)
    ax.grid(True, alpha=0.3)

    fig.tight_layout()
    fig.savefig(save_path, dpi=150, bbox_inches="tight")
    plt.close(fig)
    print(f"Saved: {save_path}")


def plot_init_quality_bar(
    init_qualities: dict[str, list[float]],
    save_path: str,
    title: str = "Init Quality (Mean DPPH of k Initial Points)",
):
    """Bar chart of init quality across methods.

    Args:
        init_qualities: {method_name: list of init_quality values (one per repeat)}
        save_path: path to save the figure
    """
    colors = {
        "Random Search": "#888888",
        "Vanilla BO": "#2196F3",
        "Qwen3-base -> BO": "#FF9800",
        "FoodmoleGPT -> BO": "#E91E63",
        "Gemini Flash -> BO": "#4CAF50",
    }

    fig, ax = plt.subplots(figsize=(8, 5))

    names = list(init_qualities.keys())
    means = [np.mean(v) for v in init_qualities.values()]
    stds = [np.std(v) for v in init_qualities.values()]
    bar_colors = [colors.get(n, "#333333") for n in names]

    bars = ax.bar(names, means, yerr=stds, capsize=5, color=bar_colors, alpha=0.8)
    ax.set_ylabel("Mean DPPH Inhibition (%)", fontsize=12)
    ax.set_title(title, fontsize=14)
    ax.grid(True, axis="y", alpha=0.3)

    # Add value labels
    for bar, mean in zip(bars, means):
        ax.text(
            bar.get_x() + bar.get_width() / 2, bar.get_height() + 0.5,
            f"{mean:.1f}", ha="center", va="bottom", fontsize=10,
        )

    fig.tight_layout()
    fig.savefig(save_path, dpi=150, bbox_inches="tight")
    plt.close(fig)
    print(f"Saved: {save_path}")


def plot_final_best_boxplot(
    final_bests: dict[str, list[float]],
    published_best: float,
    save_path: str,
    title: str = "Final Best Value Distribution",
):
    """Box plot of final best values across methods."""
    colors = {
        "Random Search": "#888888",
        "Vanilla BO": "#2196F3",
        "Qwen3-base -> BO": "#FF9800",
        "FoodmoleGPT -> BO": "#E91E63",
        "Gemini Flash -> BO": "#4CAF50",
    }

    fig, ax = plt.subplots(figsize=(8, 5))

    names = list(final_bests.keys())
    data = [final_bests[n] for n in names]
    bar_colors = [colors.get(n, "#333333") for n in names]

    bp = ax.boxplot(data, labels=names, patch_artist=True)
    for patch, color in zip(bp["boxes"], bar_colors):
        patch.set_facecolor(color)
        patch.set_alpha(0.6)

    ax.axhline(y=published_best, color="red", linestyle="--", linewidth=1.5, alpha=0.7)
    ax.set_ylabel("Best Observed DPPH Inhibition (%)", fontsize=12)
    ax.set_title(title, fontsize=14)
    ax.grid(True, axis="y", alpha=0.3)

    fig.tight_layout()
    fig.savefig(save_path, dpi=150, bbox_inches="tight")
    plt.close(fig)
    print(f"Saved: {save_path}")
