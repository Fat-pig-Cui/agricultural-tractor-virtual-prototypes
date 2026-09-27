#!/usr/bin/env python3
"""Generate V2 manuscript architecture and result figures from frozen JSON."""
from __future__ import annotations

import json
from pathlib import Path

import matplotlib.pyplot as plt
from matplotlib.patches import FancyArrowPatch, FancyBboxPatch


ROOT = Path(__file__).resolve().parents[1]
FIGURES = ROOT / "papers" / "figures"
RESULTS = ROOT / "results"
COLORS = {
    "navy": "#1F4E79",
    "blue": "#5B9BD5",
    "green": "#70AD47",
    "orange": "#ED7D31",
    "red": "#C00000",
    "gray": "#6B7280",
    "light": "#F4F6F8",
}


def box(ax, xy, width, height, text, color, fontsize=9.2):
    patch = FancyBboxPatch(
        xy, width, height, boxstyle="round,pad=0.012,rounding_size=0.012",
        facecolor=color, edgecolor="#263238", linewidth=1.1,
    )
    ax.add_patch(patch)
    ax.text(xy[0] + width / 2, xy[1] + height / 2, text,
            ha="center", va="center", fontsize=fontsize, color="white",
            linespacing=1.15)


def arrow(ax, start, end, color="#37474F", style="-"):
    ax.add_patch(FancyArrowPatch(
        start, end, arrowstyle="-|>", mutation_scale=13,
        linewidth=1.3, color=color, linestyle=style,
        connectionstyle="arc3,rad=0.0",
    ))


def architecture_paper1():
    fig, ax = plt.subplots(figsize=(12.4, 6.2), constrained_layout=True)
    ax.set_xlim(0, 1)
    ax.set_ylim(0, 1)
    ax.axis("off")
    box(ax, (0.02, 0.62), 0.15, 0.20, "Position and\nchamber-pressure\nmeasurements", COLORS["navy"], 13.0)
    box(ax, (0.22, 0.62), 0.15, 0.20, "Interface observer\n(position rate and\nload estimate)", COLORS["blue"], 13.0)
    box(ax, (0.42, 0.62), 0.15, 0.20, "Tracking and\npressure controller", COLORS["green"], 13.0)
    box(ax, (0.62, 0.62), 0.13, 0.20, "Spool valve\nand lock", COLORS["orange"], 13.0)
    box(ax, (0.81, 0.62), 0.16, 0.20, "Two-chamber plant\nwith leakage, friction,\nand relief limits", COLORS["navy"], 13.0)
    box(ax, (0.29, 0.18), 0.28, 0.20, "Hysteretic hold supervisor\nFINE TRIM / LOCK / ACCUMULATOR\n8 s minimum dwell", COLORS["gray"], 12.5)
    box(ax, (0.67, 0.18), 0.20, 0.20, "Finite gas-oil\naccumulator", COLORS["red"], 13.0)

    arrow(ax, (0.17, 0.72), (0.22, 0.72))
    arrow(ax, (0.37, 0.72), (0.42, 0.72))
    arrow(ax, (0.57, 0.72), (0.62, 0.72))
    arrow(ax, (0.75, 0.72), (0.81, 0.72))
    arrow(ax, (0.30, 0.62), (0.38, 0.38))
    arrow(ax, (0.50, 0.38), (0.50, 0.62))
    arrow(ax, (0.57, 0.28), (0.67, 0.28))
    arrow(ax, (0.87, 0.38), (0.89, 0.62))
    ax.plot([0.89, 0.89, 0.10], [0.82, 0.91, 0.91],
            color=COLORS["gray"], linestyle="--", linewidth=1.3)
    arrow(ax, (0.10, 0.91), (0.10, 0.82), color=COLORS["gray"], style="--")
    ax.text(0.50, 0.95, "measured feedback only", ha="center", va="center",
            fontsize=12.0, color=COLORS["gray"])
    fig.savefig(FIGURES / "paper1_v2_architecture.png", dpi=240,
                bbox_inches="tight", facecolor="white")
    plt.close(fig)


def architecture_paper2():
    fig, ax = plt.subplots(figsize=(12.4, 6.2), constrained_layout=True)
    ax.set_xlim(0, 1)
    ax.set_ylim(0, 1)
    ax.axis("off")
    box(ax, (0.02, 0.62), 0.15, 0.20, "Present demand,\nSOC, and public\ntask phase", COLORS["navy"], 17.0)
    box(ax, (0.21, 0.62), 0.15, 0.20, "Adaptive ECMS\neconomic proposal", COLORS["green"], 17.0)
    box(ax, (0.40, 0.62), 0.17, 0.20, "Finite engine-speed\nand power\ncandidates", COLORS["blue"], 17.0)
    box(ax, (0.61, 0.62), 0.16, 0.20, "Plant feasibility,\nelectric reserve,\nand action filter", COLORS["orange"], 17.0)
    box(ax, (0.81, 0.62), 0.16, 0.20, "Shrinking-SOC\nviability shield", COLORS["red"], 17.0)
    box(ax, (0.34, 0.18), 0.24, 0.20, "Applied engine /\nMG action\n1 s causal decision", COLORS["navy"], 17.0)
    box(ax, (0.68, 0.18), 0.23, 0.20, "Power-split virtual\nplant and constraint\naccounting", COLORS["gray"], 17.0)

    arrow(ax, (0.17, 0.72), (0.21, 0.72))
    arrow(ax, (0.36, 0.72), (0.40, 0.72))
    arrow(ax, (0.57, 0.72), (0.61, 0.72))
    arrow(ax, (0.77, 0.72), (0.81, 0.72))
    arrow(ax, (0.89, 0.62), (0.52, 0.38))
    arrow(ax, (0.58, 0.28), (0.68, 0.28))
    ax.plot([0.80, 0.80, 0.10], [0.18, 0.08, 0.08],
            color=COLORS["gray"], linestyle="--", linewidth=1.3)
    arrow(ax, (0.10, 0.08), (0.10, 0.62), color=COLORS["gray"], style="--")
    ax.text(0.43, 0.045, "SOC and applied-state feedback",
            ha="center", va="center", fontsize=14.5, color=COLORS["gray"])
    fig.savefig(FIGURES / "paper2_v2_architecture.png", dpi=240,
                bbox_inches="tight", facecolor="white")
    plt.close(fig)


def results_paper1():
    data = json.loads((RESULTS / "paper1_two_chamber_v2.json").read_text())
    holdout = data["holdout"]
    keys = ["pid_lock", "smc_lock", "pid_accumulator", "observer_hybrid"]
    labels = ["PID-lock", "SMC-lock", "PID-accumulator", "Observer hybrid"]
    means = [holdout[key]["summary"]["mean_hold_drop_mm"] for key in keys]
    worst = [holdout[key]["summary"]["worst_hold_drop_mm"] for key in keys]
    errors = [holdout[key]["summary"]["worst_post_transition_error_mm"] for key in keys]
    colors = [COLORS["gray"], COLORS["blue"], COLORS["orange"], COLORS["green"]]

    fig, axes = plt.subplots(1, 2, figsize=(12.2, 4.8), constrained_layout=True)
    x = range(len(keys))
    axes[0].bar(x, means, color=colors, edgecolor="#263238", linewidth=0.8)
    axes[0].scatter(x, worst, marker="D", s=42, color="#202124", label="Worst path", zorder=3)
    axes[0].axhline(10.0, color=COLORS["red"], linestyle="--", linewidth=1.3,
                    label="10 mm screen")
    axes[0].set_ylabel("Hold drop (mm)")
    axes[0].set_xticks(list(x), labels, rotation=17, ha="right")
    axes[0].set_title("30 min frozen holdout")
    axes[0].legend(frameon=False, fontsize=8.5)
    axes[0].grid(axis="y", alpha=0.25)

    axes[1].bar(x, errors, color=colors, edgecolor="#263238", linewidth=0.8)
    axes[1].axhline(10.0, color=COLORS["red"], linestyle="--", linewidth=1.3)
    axes[1].set_ylabel("Worst post-transition error (mm)")
    axes[1].set_xticks(list(x), labels, rotation=17, ha="right")
    axes[1].set_title("Accuracy boundary")
    axes[1].grid(axis="y", alpha=0.25)
    fig.savefig(FIGURES / "paper1_v2_results.png", dpi=240,
                bbox_inches="tight", facecolor="white")
    plt.close(fig)


def results_paper2():
    main = json.loads((RESULTS / "paper2_viability_ecms_v2.json").read_text())
    cross = json.loads((RESULTS / "paper2_v2_crosscycle_audit.json").read_text())
    sensitivity = json.loads((RESULTS / "paper2_v2_map_capacity_audit.json").read_text())
    main_value = main["holdout"]["viability_ecms"]["summary"]["mean_energy_normalized_saving_pct"]
    cycle_labels = ["Frozen\nholdout", "Deterministic", "Low load", "New stochastic"]
    cycle = cross["crosscycle"]
    cycle_values = [
        main_value,
        cycle["deterministic_agri_workcycle"]["energy_normalized_saving_pct"],
        cycle["low_load_agri_workcycle"]["energy_normalized_saving_pct"],
        cycle["stochastic_new_seeds"]["summary"]["mean_energy_normalized_saving_pct"],
    ]
    map_labels = ["Literature", "Low-load\n0.15", "Low-load\n0.25", "Low-load\n0.35"]
    map_values = [row["mean_saving_pct"] for row in sensitivity["map_sensitivity"]]

    fig, axes = plt.subplots(1, 2, figsize=(12.2, 4.8), constrained_layout=True)
    axes[0].bar(range(4), cycle_values,
                color=[COLORS["navy"], COLORS["blue"], COLORS["orange"], COLORS["green"]],
                edgecolor="#263238", linewidth=0.8)
    axes[0].axhline(0.0, color="#202124", linewidth=0.9)
    axes[0].set_ylabel("Energy-normalized fuel saving (%)")
    axes[0].set_xticks(range(4), cycle_labels)
    axes[0].set_title("Causal V2 cross-cycle results")
    axes[0].grid(axis="y", alpha=0.25)

    axes[1].bar(range(4), map_values,
                color=[COLORS["navy"], COLORS["orange"], COLORS["blue"], COLORS["gray"]],
                edgecolor="#263238", linewidth=0.8)
    axes[1].axhline(0.0, color="#202124", linewidth=0.9)
    axes[1].set_ylabel("Mean saving on valid pairs (%)")
    axes[1].set_xticks(range(4), map_labels)
    axes[1].set_title("Frozen map sensitivity (19/20 valid)")
    axes[1].grid(axis="y", alpha=0.25)
    fig.savefig(FIGURES / "paper2_v2_results.png", dpi=240,
                bbox_inches="tight", facecolor="white")
    plt.close(fig)


def main():
    FIGURES.mkdir(parents=True, exist_ok=True)
    architecture_paper1()
    architecture_paper2()
    results_paper1()
    results_paper2()
    for name in ("paper1_v2_architecture.png", "paper2_v2_architecture.png",
                 "paper1_v2_results.png", "paper2_v2_results.png"):
        print(FIGURES / name)


if __name__ == "__main__":
    main()
