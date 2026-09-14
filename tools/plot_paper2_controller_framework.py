"""Plot the strict controller-framework comparison used in paper 2."""
from __future__ import annotations

import json
from pathlib import Path

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt


ROOT = Path(__file__).parents[1]
RESULT = ROOT / "results" / "paper2_controller_framework_benchmark.json"
OUTS = (ROOT / "papers" / "figures" / "paper2_controller_framework.png",
        ROOT / "MDPI_template_ACS" / "paper2_controller_framework.png")

plt.rcParams.update({"font.family": "DejaVu Sans", "font.size": 8.5})


def controller_rows(data: dict[str, object]) -> list[tuple[str, dict[str, object]]]:
    controllers = data["test_controllers"]
    return [
        ("ECMS", controllers["map_aware_ecms"]["summary"]),
        ("Phase\npolicy", controllers["nominal_phase_policy"]["summary"]),
        ("Det.\nMPC", controllers["deterministic_mpc"]["summary"]),
        ("Scenario\nMPC", controllers["scenario_mpc"]["summary"]),
        ("Terminal-set\nMPC",
         controllers["terminal_set_scenario_mpc"]["summary"]),
    ]


def panel(ax, title: str, data: dict[str, object], color: str, ylim: tuple[float, float]) -> None:
    rows = controller_rows(data)
    labels = [label for label, _ in rows]
    means = [float(summary["saving_pct"]["mean"]) for _, summary in rows]
    lower = [float(summary["saving_pct"]["ci95_low"]) for _, summary in rows]
    upper = [float(summary["saving_pct"]["ci95_high"]) for _, summary in rows]
    certified = [int(round(float(summary["certified_rate"]) * 20)) for _, summary in rows]
    x = list(range(len(rows)))
    bars = ax.bar(x, means, yerr=[[mean - low for mean, low in zip(means, lower)],
                                  [high - mean for mean, high in zip(means, upper)]],
                  capsize=2.8, width=0.64, color=color, edgecolor="#2f2f2f", linewidth=0.45)
    for bar, count in zip(bars, certified):
        if count < 20:
            bar.set_hatch("//")
    ax.axhline(0.0, color="#303030", linewidth=0.8)
    ax.set_xticks(x, labels)
    ax.set_ylim(*ylim)
    ax.set_title(title, fontsize=9.2, pad=7)
    ax.grid(axis="y", alpha=0.2)
    span = ylim[1] - ylim[0]
    for index, (mean, count) in enumerate(zip(means, certified)):
        if mean < 0.0:
            y, va = mean * 0.55, "center"
        else:
            y, va = mean + 0.025 * span, "bottom"
        ax.text(index, y, f"{mean:.3f}%\nn={count}/20", ha="center", va=va, fontsize=7.0)


def main() -> None:
    data = json.loads(RESULT.read_text(encoding="utf-8"))
    fig, axes = plt.subplots(1, 2, figsize=(7.9, 3.75))
    panel(axes[0], "Literature-shaped map", data["literature_shaped"], "#457b9d", (-0.92, 0.15))
    panel(axes[1], "Steep-island virtual sensitivity",
          data["steep_island_sensitivity"], "#d9903d", (-3.25, 11.65))
    axes[0].set_ylabel("Paired fuel saving vs. engineering OOL (%)")
    axes[1].set_ylabel("Paired fuel saving vs. engineering OOL (%)")
    fig.text(0.5, 0.01,
             "Error bars: 95% confidence intervals. Hatched bars: fewer than 20 zero-external-fallback certified pairs.",
             ha="center", fontsize=7.2)
    fig.subplots_adjust(left=0.085, right=0.995, top=0.88, bottom=0.28, wspace=0.28)
    for output in OUTS:
        output.parent.mkdir(parents=True, exist_ok=True)
        fig.savefig(output, dpi=300, bbox_inches="tight")
    plt.close(fig)
    for output in OUTS:
        print(output)


if __name__ == "__main__":
    main()
