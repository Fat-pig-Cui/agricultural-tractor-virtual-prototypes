"""Plot the predeclared causal-MPC mechanism map for paper two."""
from __future__ import annotations

import json
from pathlib import Path

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt


ROOT = Path(__file__).parents[1]
RESULT = ROOT / "results" / "paper2_mpc_mechanism_map.json"
OUTS = (ROOT / "papers" / "figures" / "paper2_mpc_mechanism_map.png",
        ROOT / "MDPI_template_ACS" / "paper2_mpc_mechanism_map.png")

plt.rcParams.update({"font.family": "DejaVu Sans", "font.size": 8.2})


def finite_summary(entry: dict[str, object]) -> dict[str, float] | None:
    summary = entry["summary"]["saving_pct"]
    return None if summary is None else {key: float(value) for key, value in summary.items()}


def panel(ax, title: str, data: dict[str, object], color: str) -> None:
    entries = data["development"]
    labels = [str(entry["id"]).split("_")[0].upper() + "\n"
              + ("Hist." if str(entry["id"]).endswith("history") else "Phase")
              for entry in entries]
    x = list(range(len(entries)))
    summaries = [finite_summary(entry) for entry in entries]
    values = [summary["mean"] if summary is not None else 0.0 for summary in summaries]
    lower = [summary["ci95_low"] if summary is not None else 0.0 for summary in summaries]
    upper = [summary["ci95_high"] if summary is not None else 0.0 for summary in summaries]
    errors = [[value - low for value, low, summary in zip(values, lower, summaries)
               if summary is not None],
              [high - value for value, high, summary in zip(values, upper, summaries)
               if summary is not None]]
    bars = ax.bar(x, values, width=0.68, color=color, edgecolor="#2f2f2f", linewidth=0.45)
    for index, (bar, entry, summary) in enumerate(zip(bars, entries, summaries)):
        certified = int(round(float(entry["summary"]["certified_rate"]) * 6))
        if certified < 6:
            bar.set_hatch("//")
        if summary is not None:
            ax.errorbar(index, summary["mean"],
                        yerr=[[summary["mean"] - summary["ci95_low"]],
                              [summary["ci95_high"] - summary["mean"]]],
                        color="#242424", capsize=2.4, linewidth=0.7)
        else:
            ax.text(index, 0.06, "not\ncertified", ha="center", va="bottom", fontsize=6.7)
        ax.text(index, -0.05, f"n={certified}/6", ha="center", va="top", fontsize=6.6)

    holdout = data["holdout"]
    selected_id = data["selected_by_development"]
    if holdout is not None:
        summary = finite_summary(holdout)
        selected_index = next(index for index, entry in enumerate(entries)
                              if entry["id"] == selected_id)
        if summary is not None:
            ax.errorbar(selected_index, summary["mean"],
                        yerr=[[summary["mean"] - summary["ci95_low"]],
                              [summary["ci95_high"] - summary["mean"]]],
                        fmt="D", markersize=4.6, color="#111111", mfc="#ffffff",
                        capsize=2.6, zorder=4)
            holdout_n = int(round(float(holdout["summary"]["certified_rate"]) * 20))
            ax.annotate(f"holdout n={holdout_n}/20", (selected_index, summary["mean"]),
                        xytext=(0, 7), textcoords="offset points", ha="center", fontsize=6.4)

    extent = max(1.0, max(abs(value) for value in values) + 0.8)
    ax.set_ylim(-extent, extent)
    ax.axhline(0.0, color="#303030", linewidth=0.8)
    ax.set_xticks(x, labels, fontsize=7.4)
    ax.set_title(title, fontsize=9.0, pad=7)
    ax.grid(axis="y", alpha=0.2)


def main() -> None:
    data = json.loads(RESULT.read_text(encoding="utf-8"))
    fig, axes = plt.subplots(1, 2, figsize=(7.9, 3.85))
    panel(axes[0], "Literature-shaped map", data["maps"]["literature_shaped"], "#457b9d")
    panel(axes[1], "Steep-island virtual sensitivity",
          data["maps"]["steep_island_sensitivity"], "#d9903d")
    axes[0].set_ylabel("Paired fuel saving vs. engineering OOL (%)")
    axes[1].set_ylabel("Paired fuel saving vs. engineering OOL (%)")
    fig.text(0.5, 0.01,
             "Bars: development mean with 95% CI. Hatched: fewer than 6 certified paths. "
             "Diamond: development-selected setting on 20 disjoint holdout paths. "
             "Hist.: causal history-only; Phase: public task phase plus present measurement.",
             ha="center", fontsize=7.0)
    fig.subplots_adjust(left=0.09, right=0.995, top=0.86, bottom=0.28, wspace=0.25)
    for output in OUTS:
        output.parent.mkdir(parents=True, exist_ok=True)
        fig.savefig(output, dpi=300, bbox_inches="tight")
    plt.close(fig)
    for output in OUTS:
        print(output)


if __name__ == "__main__":
    main()
