"""Plot the fixed Cartesian virtual stress surface for paper 1."""
from __future__ import annotations

import json
from pathlib import Path

import matplotlib.pyplot as plt

ROOT = Path(__file__).resolve().parents[1]
data = json.loads((ROOT / "results" / "lift_combined_stress.json").read_text())
cases = data["cases"]

# Use four small multiples so every predeclared case remains legible at print scale.
masses = (0.7, 1.3)
leakages = (1.0, 5.0)
temperatures = (25.0, 50.0)
accumulator_flows = (0.5, 1.0)
loads = (7000.0, 14000.0)

fig, axes = plt.subplots(2, 2, figsize=(8.8, 6.2), dpi=180, sharex=True, sharey=True,
                         layout="constrained")
im = None
for row, mass in enumerate(masses):
    for col, leakage in enumerate(leakages):
        ax = axes[row, col]
        grid = []
        row_labels = []
        for temperature in temperatures:
            for flow in accumulator_flows:
                row_labels.append(f"{temperature:.0f} C, Q={flow:.1f}")
                values = []
                for load in loads:
                    match = next(
                        case for case in cases
                        if case["factors"] == {
                            "mass_scale": mass,
                            "leakage_scale": leakage,
                            "temperature_c": temperature,
                            "load_after_step_n": load,
                            "accumulator_flow_scale": flow,
                        }
                    )
                    values.append(match["hold_drop_mm"]["mean"])
                grid.append(values)
        im = ax.imshow(grid, cmap="YlGnBu", vmin=0.0, vmax=10.0, aspect="auto")
        for r, values in enumerate(grid):
            for c, value in enumerate(values):
                color = "white" if value >= 5.5 else "#143d59"
                ax.text(c, r, f"{value:.2f}", ha="center", va="center", fontsize=7, color=color)
        ax.set_title(f"m={mass:.1f}, L={leakage:.0f}", fontsize=9)
        ax.set_yticks(range(len(row_labels)))
        ax.set_yticklabels(row_labels, fontsize=7)
        ax.set_xticks(range(len(loads)))
        ax.set_xticklabels(("7 kN", "14 kN"), fontsize=8)
        ax.tick_params(length=0)
        for spine in ax.spines.values():
            spine.set_visible(False)

axes[1, 0].set_xlabel("Post-step load")
axes[1, 1].set_xlabel("Post-step load")
axes[0, 0].set_ylabel("Temperature and accumulator flow")
axes[1, 0].set_ylabel("Temperature and accumulator flow")
fig.suptitle("Cartesian virtual stress surface: mean 1800 s hold drop", fontsize=12)
cbar = fig.colorbar(im, ax=axes.ravel().tolist(), fraction=0.035, pad=0.03)
cbar.set_label("Hold drop (mm; 20-seed mean)")
output = ROOT / "papers" / "figures" / "paper1_combined_stress_surface.png"
fig.savefig(output, bbox_inches="tight")
print(output)
