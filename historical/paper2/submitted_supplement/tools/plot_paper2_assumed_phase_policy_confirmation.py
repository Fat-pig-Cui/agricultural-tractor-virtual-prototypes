"""Render the independent assumed-map phase-policy confirmation figure."""
from __future__ import annotations

import json
from pathlib import Path

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt

ROOT = Path(__file__).parents[1]
RESULT = ROOT / "results" / "paper2_assumed_phase_policy_multistart.json"
OUT = ROOT / "papers" / "figures" / "paper2_assumed_phase_policy_confirmation.png"


def main() -> None:
    data = json.loads(RESULT.read_text(encoding="utf-8"))
    confirmation = data["confirmation_frozen_finalist"]
    rows = confirmation["rows"]
    summary = confirmation["saving_pct"]
    seeds = [int(row["seed"]) for row in rows]
    savings = [float(row["saving_vs_same_seed_ool_pct"]) for row in rows]
    mean = float(summary["mean"])
    low = float(summary["ci95_low"])
    high = float(summary["ci95_high"])
    plt.rcParams.update({"font.family": "DejaVu Sans", "font.size": 9})
    fig, ax = plt.subplots(figsize=(6.4, 3.35))
    ax.scatter(seeds, savings, color="#2a9d8f", s=28, zorder=3,
               label="Same-seed paired saving")
    ax.axhline(0.0, color="#303030", linewidth=0.8)
    ax.axhline(mean, color="#e76f51", linewidth=1.2, label="Mean and 95% CI")
    ax.fill_between([min(seeds) - 0.5, max(seeds) + 0.5], low, high,
                    color="#e76f51", alpha=0.16)
    ax.set_xlim(min(seeds) - 0.5, max(seeds) + 0.5)
    ax.set_xlabel("Independent stochastic-cycle seed")
    ax.set_ylabel("Fuel saving vs. realistic OOL (%)")
    ax.set_title("Assumed-map causal phase-policy confirmation (n = 14)")
    ax.text(0.02, 0.04, f"Mean {mean:.2f}%  [95% CI {low:.2f}, {high:.2f}]",
            transform=ax.transAxes, va="bottom", fontsize=8)
    ax.grid(axis="y", alpha=0.2)
    ax.legend(frameon=False, fontsize=8, loc="upper left")
    OUT.parent.mkdir(parents=True, exist_ok=True)
    fig.tight_layout()
    fig.savefig(OUT, dpi=300, bbox_inches="tight")
    plt.close(fig)
    print(OUT)


if __name__ == "__main__":
    main()
