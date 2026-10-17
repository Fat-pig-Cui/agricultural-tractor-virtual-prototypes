"""Plot fixed-controller low-load efficiency-map sensitivity for paper 2."""
from __future__ import annotations

import json
from pathlib import Path

import matplotlib.pyplot as plt

ROOT = Path(__file__).resolve().parents[1]
data = json.loads((ROOT / "results" / "paper2_map_sensitivity_grid.json").read_text())
levels = [case["low_load_efficiency"] for case in data["cases"]]

fig, ax = plt.subplots(figsize=(7.0, 4.1), dpi=180)
styles = {
    "adaptive_ecms": ("#1f5a85", "Map-aware ECMS"),
    "recursive_feasible_mpc": ("#b36b2c", "Terminal-set scenario MPC"),
}
for key, (color, label) in styles.items():
    summary = [case["controllers"][key]["saving_pct"] for case in data["cases"]]
    means = [entry["mean"] for entry in summary]
    low = [entry["mean"] - entry["ci95_low"] for entry in summary]
    high = [entry["ci95_high"] - entry["mean"] for entry in summary]
    ax.errorbar(levels, means, yerr=[low, high], marker="o", ms=4.5,
                color=color, capsize=2, lw=1.2, label=label)
ax.axhline(0.0, color="#444444", lw=0.8)
ax.set_xlabel("Virtual low-load efficiency parameter")
ax.set_ylabel("Saving vs. same-seed OOL (%)")
ax.set_xlim(min(levels) - 0.01, max(levels) + 0.01)
ax.grid(alpha=0.25)
ax.legend(frameon=False)
ax.set_title("Fixed-controller sensitivity to the virtual engine-map shape")
fig.tight_layout()
output = ROOT / "papers" / "figures" / "paper2_map_sensitivity_grid.png"
fig.savefig(output, bbox_inches="tight")
print(output)
