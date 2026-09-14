"""Create English, data-backed figures for the AgriEngineering submission drafts."""
from __future__ import annotations

import json
from pathlib import Path

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt


ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "papers" / "figures"
RESULTS = ROOT / "results"

plt.rcParams.update({"font.family": "DejaVu Sans", "font.size": 9})


def load(name: str):
    return json.loads((RESULTS / name).read_text())


def save(fig, name: str, *, tight_layout: bool = True):
    if tight_layout:
        fig.tight_layout()
    fig.savefig(OUT / name, dpi=300, bbox_inches="tight")
    plt.close(fig)
    print(OUT / name)


def lift_figures():
    hold = load("lift_hold_validation.json")
    keys = ["filtered_gate_lock_leak_0.5x", "filtered_gate_lock_leak_1x",
            "filtered_gate_lock_leak_2x", "filtered_gate_lock_leak_5x",
            "filtered_gate_lock_leak_10x"]
    scales = [0.5, 1, 2, 5, 10]
    means = [hold[key]["mean_hold_drop_mm"] for key in keys]
    fig, ax = plt.subplots(figsize=(6.0, 3.6))
    ax.plot(scales, means, "o-", color="#1f77b4", label="Hybrid controller")
    ax.set_xscale("log")
    ax.set_xlabel("Lock-valve leakage multiplier (-)")
    ax.set_ylabel("1800 s position drop (mm)")
    ax.set_title("Lock-valve micro-leakage sensitivity (n = 20)")
    ax.set_ylim(0, max(means) * 1.35)
    for scale, mean in zip(scales, means):
        ax.annotate(f"{mean:.3f}", (scale, mean), xytext=(0, 7),
                    textcoords="offset points", ha="center", fontsize=8)
    ax.text(0.03, 0.83, "10 mm numerical screen is outside this axis",
            transform=ax.transAxes, va="top", fontsize=8, color="#555555")
    ax.grid(alpha=0.25)
    ax.legend(frameon=False, loc="upper left")
    save(fig, "paper1_lock_leakage_sensitivity.png")

    ablation = load("lift_ablation.json")
    keys = ["load_step_14kn", "load_step_14kn_no_acc_closed_loop",
            "load_step_14kn_no_feedforward"]
    labels = ["Full hybrid", "Without accumulator\nclosed loop", "Without load\nfeedforward"]
    values = [ablation[key]["mean_hold_drop_mm"] for key in keys]
    fig, ax = plt.subplots(figsize=(6.0, 3.6))
    bars = ax.bar(labels, values, color=["#2a9d8f", "#e9c46a", "#e76f51"])
    ax.axhline(10, color="#c44e52", ls="--", label="30 min requirement")
    ax.set_ylabel("Mean position drop after 14 kN load step (mm)")
    ax.set_title("Load-step ablation (n = 20)")
    ax.bar_label(bars, fmt="%.1f", padding=2)
    ax.legend(frameon=False)
    save(fig, "paper1_load_step_ablation.png")

    robustness = load("lift_submission_robustness.json")
    envelope = robustness["temperature_load_envelope"]
    temperatures = [25, 40, 50]
    loads = [7, 10, 14]
    drops = [[envelope[f"temperature_{temp}c_load_{load}kn"]["hold_drop_mm"]["mean"]
              for load in loads] for temp in temperatures]
    gate = robustness["raw_velocity_gate_sensitivity"]
    raw_tolerances = [3, 5, 10]
    raw_rates = [100 * gate[f"raw_gate_{tol}mm_s"]["hold_entry_rate"]
                 for tol in raw_tolerances]
    fig, (ax_heat, ax_gate) = plt.subplots(1, 2, figsize=(7.4, 3.25),
                                           gridspec_kw={"width_ratios": [1.25, 1]})
    image = ax_heat.imshow(drops, cmap="YlGnBu", aspect="auto")
    ax_heat.set_xticks(range(len(loads)), [f"{load} kN" for load in loads])
    ax_heat.set_yticks(range(len(temperatures)), [f"{temp} C" for temp in temperatures])
    ax_heat.set_xlabel("Post-step load")
    ax_heat.set_ylabel("Oil temperature")
    ax_heat.set_title("Filtered-gate hold drop (mm)")
    for row, values in enumerate(drops):
        for column, value in enumerate(values):
            color = "white" if value > 1 else "black"
            ax_heat.text(column, row, f"{value:.3f}", ha="center", va="center", color=color)
    colorbar = fig.colorbar(image, ax=ax_heat, fraction=0.046, pad=0.04)
    colorbar.set_label("1800 s drop (mm)")

    bars = ax_gate.bar([f"{tol}" for tol in raw_tolerances], raw_rates,
                       color=["#e76f51", "#e9c46a", "#2a9d8f"])
    ax_gate.set_ylim(0, 115)
    ax_gate.set_xlabel("Raw velocity tolerance (mm/s)")
    ax_gate.set_ylabel("Hold-entry rate (%)")
    ax_gate.set_title("Unfiltered velocity gate (n = 20)")
    ax_gate.bar_label(bars, fmt="%.0f%%", padding=2, fontsize=8)
    save(fig, "paper1_operating_envelope.png")

    stress = load("lift_theoretical_stress.json")
    ranges = stress["one_at_a_time_ranges"]
    selected_ranges = [
        ("Nominal", "nominal"),
        ("m 0.7x", "mass_0p7x"),
        ("c 1.3x", "viscous_1p3x"),
        ("k 0.7x", "stiffness_0p7x"),
        ("noise 2x", "position_noise_2p0x"),
        ("C_l 5x", "leakage_5p0x"),
        ("K_acc 0.5x\n(14 kN)", "accumulator_flow_0p5x_14kn"),
        ("K_acc 1.5x\n(14 kN)", "accumulator_flow_1p5x_14kn"),
    ]
    labels = [label for label, _ in selected_ranges]
    range_drops = [ranges[key]["hold_drop_mm"]["mean"] for _, key in selected_ranges]
    step = stress["leakage_step_ablation"]
    observer_case = step["leakage_step_1x_to_8x_observer"]
    prior_case = step["leakage_step_1x_to_8x_nominal_prior"]
    coefficient_ratios = [
        observer_case["observer_coefficient_m3_s_pa"]["mean"] / 1.5e-12,
        prior_case["observer_coefficient_m3_s_pa"]["mean"] / 1.5e-12,
    ]

    fig, (ax_range, ax_proxy) = plt.subplots(1, 2, figsize=(7.4, 3.35),
                                              gridspec_kw={"width_ratios": [1.45, 1]})
    colors = ["#457b9d"] * 6 + ["#e9c46a", "#2a9d8f"]
    bars = ax_range.bar(range(len(labels)), range_drops, color=colors)
    ax_range.axhline(10, color="#c44e52", ls="--", linewidth=1, label="10 mm numerical screen")
    ax_range.set_xticks(range(len(labels)), labels, rotation=35, ha="right", fontsize=7.5)
    ax_range.set_ylabel("Mean 1800 s position drop (mm)")
    ax_range.set_title("Selected one-at-a-time assumptions (n = 5)")
    ax_range.set_ylim(0, max(11, max(range_drops) * 1.18))
    ax_range.grid(axis="y", alpha=0.2)
    ax_range.legend(frameon=False, fontsize=7.3, loc="upper left")
    for bar, value in zip(bars, range_drops):
        ax_range.text(bar.get_x() + bar.get_width() / 2, value + 0.22,
                      f"{value:.2f}", ha="center", va="bottom", fontsize=6.7)

    labels = ["Transition\nproxy", "Fixed\nnominal prior"]
    bars = ax_proxy.bar(labels, coefficient_ratios, color=["#2a9d8f", "#e76f51"])
    ax_proxy.axhline(8, color="#404040", ls="--", linewidth=1, label="Virtual step target")
    ax_proxy.set_ylim(0, 9.5)
    ax_proxy.set_ylabel("Final coefficient / nominal coefficient (-)")
    ax_proxy.set_title("Virtual 1x to 8x leakage step (n = 20)")
    ax_proxy.grid(axis="y", alpha=0.2)
    ax_proxy.legend(frameon=False, fontsize=7.3, loc="upper left")
    ax_proxy.bar_label(bars, fmt="%.1fx", padding=2, fontsize=8)
    delay = observer_case["observer_detection_delay_s"]["mean"]
    ax_proxy.text(0, 0.52, f"90% in {delay:.3f} s", ha="center", va="bottom", fontsize=7.5)
    ax_proxy.text(1, 0.52, "No adaptation", ha="center", va="bottom", fontsize=7.5)
    save(fig, "paper1_assumption_and_proxy_stress.png")


def energy_figures():
    main = load("statistics_20seeds.json")["energy"]["controllers"]
    reference = load("statistics_literature_reference_20seeds.json")["controllers"]
    labels = ["Deterministic\nMPC", "Scenario\nMPC"]
    main_savings = load("statistics_20seeds.json")["energy"]["paired_savings_vs_realistic_ool_pct"]
    reference_savings = load("statistics_literature_reference_20seeds.json")["paired_savings_vs_realistic_ool_pct"]
    main_values = [main_savings["deterministic_mpc"]["mean"],
                   main_savings["robust_mpc"]["mean"]]
    ref_values = [reference_savings["deterministic_mpc"]["mean"],
                  reference_savings["robust_mpc"]["mean"]]
    x = range(len(labels))
    fig, ax = plt.subplots(figsize=(6.25, 4.15))
    left = ax.bar([v - 0.18 for v in x], main_values, width=0.36, color="#457b9d",
                  label="Assumed efficiency island")
    right = ax.bar([v + 0.18 for v in x], ref_values, width=0.36, color="#f4a261",
                   label="Literature-shaped BSFC map")
    ax.set_xticks(list(x), labels)
    ax.set_ylabel("Valid fuel saving vs. realistic OOL (%)")
    ax.set_title("Fuel-saving result depends on the engine efficiency map", fontsize=10, pad=8)
    ax.bar_label(left, fmt="%.2f", padding=2, fontsize=8)
    ax.bar_label(right, fmt="%.2f", padding=2, fontsize=8)
    fig.legend([left, right], [left.get_label(), right.get_label()], frameon=False,
               fontsize=7.4, ncol=2, loc="lower center", bbox_to_anchor=(0.5, 0.02))
    fig.subplots_adjust(left=0.15, right=0.98, top=0.88, bottom=0.25)
    save(fig, "paper2_protocol_comparison.png", tight_layout=False)

    crosscycle = load("energy_crosscycle_validation.json")
    assumed = crosscycle["assumed_efficiency_island"]
    literature = crosscycle["literature_shaped_bsfc"]
    controller_keys = ["deterministic_mpc", "robust_mpc"]
    controller_labels = ["Deterministic\nMPC", "Scenario\nMPC"]
    map_sets = [
        ("Assumed island", assumed, "#457b9d"),
        ("Literature-shaped", literature, "#f4a261"),
    ]
    fig, (ax_valid, ax_saving) = plt.subplots(1, 2, figsize=(7.8, 3.9))
    x = list(range(len(controller_keys)))
    valid_handles = []
    for offset, (name, data, color) in zip((-0.18, 0.18), map_sets):
        values = [100 * data["summaries"][key]["valid_rate"] for key in controller_keys]
        bars = ax_valid.bar([value + offset for value in x], values, width=0.36,
                            color=color, label=name)
        valid_handles.append(bars)
        ax_valid.bar_label(bars, fmt="%.0f%%", padding=2, fontsize=8)
    ax_valid.set_xticks(x, controller_labels)
    ax_valid.set_ylim(0, 115)
    ax_valid.set_ylabel("Valid-run rate (%)")
    ax_valid.set_title("Hard-valid runs", fontsize=9.5, pad=7)

    literature_savings = literature["paired_savings_vs_realistic_ool"]
    saving_stats = [literature_savings[key]["saving_pct"] for key in controller_keys]
    valid_pairs = [literature_savings[key]["valid_pairs"] for key in controller_keys]
    saving_x = list(range(len(controller_keys)))
    ax_saving.bar(0, 0, color="#D9D9D9", edgecolor="#7A7A7A", hatch="//", width=0.62)
    ax_saving.text(0, 0.115, f"No valid pairs\n({valid_pairs[0]}/20)", ha="center",
                   va="center", fontsize=7.5, color="#555555")
    reportable = saving_stats[1]
    mean = reportable["mean"]
    lower = reportable["ci95_low"]
    upper = reportable["ci95_high"]
    ax_saving.bar(1, mean, yerr=[[mean - lower], [upper - mean]], capsize=3,
                  color="#e76f51", width=0.62)
    ax_saving.axhline(0, color="black", linewidth=0.8)
    ax_saving.set_xticks(saving_x, controller_labels)
    ax_saving.set_ylim(-0.43, 0.16)
    ax_saving.set_ylabel("Fuel saving vs. realistic OOL (%)")
    ax_saving.set_title("Literature-shaped map: reportable pairs", fontsize=9.5, pad=7)
    ax_saving.text(1, lower - 0.025, f"{mean:.3f}%", ha="center", va="top", fontsize=8)
    fig.legend(valid_handles, [item[0] for item in map_sets], frameon=False, fontsize=8,
               ncol=2, loc="lower center", bbox_to_anchor=(0.5, 0.02))
    fig.suptitle("Strictly causal cross-cycle validation", fontsize=11, y=0.98)
    fig.subplots_adjust(left=0.10, right=0.99, top=0.80, bottom=0.24, wspace=0.30)
    save(fig, "paper2_crosscycle_validation.png", tight_layout=False)

    # Keep parameter selection separate from confirmation: the development
    # seeds rank candidates, while the disjoint holdout seeds report them.
    # This figure makes the small attainable improvement visible rather than
    # treating a post-hoc setting change as a new primary result.
    optimization = load("paper2_controller_optimization.json")
    selected = set(optimization["selected_finalists"])
    development = optimization["development_candidates"]
    labels = {
        "default_H8_S5_W2M": "Default\nH8, S5",
        "horizon_4": "Horizon\n4",
        "horizon_12": "Horizon\n12",
        "horizon_20": "Horizon\n20",
        "scenarios_3": "Scenarios\n3",
        "scenarios_9": "Scenarios\n9",
        "terminal_weight_0p5M": "Weight\n0.5M",
        "terminal_weight_1M": "Weight\n1M",
        "terminal_weight_5M": "Weight\n5M",
        "terminal_weight_10M": "Weight\n10M",
        "common_nominal_reference": "Common\nSOC prior",
    }
    fig, (ax_dev, ax_hold) = plt.subplots(1, 2, figsize=(7.4, 3.35),
                                           gridspec_kw={"width_ratios": [1.55, 1]})
    for index, item in enumerate(development):
        stat = item["saving_pct"]
        mean = stat["mean"]
        low = stat["ci95_low"]
        high = stat["ci95_high"]
        color = "#2a9d8f" if item["name"] in selected else "#8d99ae"
        if item["name"] == "common_nominal_reference":
            color = "#e76f51"
        ax_dev.errorbar(mean, index, xerr=[[mean - low], [high - mean]], fmt="o",
                        color=color, capsize=3, markersize=5)
    ax_dev.axvline(0, color="#303030", linewidth=0.8)
    ax_dev.set_yticks(range(len(development)), [labels[item["name"]] for item in development], fontsize=7.4)
    ax_dev.invert_yaxis()
    ax_dev.set_xlim(-0.18, 0.52)
    ax_dev.set_xlabel("Paired fuel saving vs. OOL (%)")
    ax_dev.set_title("Development screen (n = 6)")
    ax_dev.grid(axis="x", alpha=0.2)

    finalists = optimization["holdout_finalists"]
    for index, item in enumerate(finalists):
        stat = item["saving_pct"]
        mean = stat["mean"]
        low = stat["ci95_low"]
        high = stat["ci95_high"]
        ax_hold.errorbar(mean, index, xerr=[[mean - low], [high - mean]], fmt="o",
                         color="#2a9d8f", capsize=3, markersize=5)
        ax_hold.text(high + 0.012, index, f"{mean:.3f}", va="center", fontsize=7.7)
    ax_hold.axvline(0, color="#303030", linewidth=0.8)
    ax_hold.set_yticks(range(len(finalists)), [labels[item["name"]] for item in finalists], fontsize=8)
    ax_hold.invert_yaxis()
    ax_hold.set_xlim(-0.02, 0.48)
    ax_hold.set_xlabel("Paired fuel saving vs. OOL (%)")
    ax_hold.set_title("Untouched holdout (n = 14)")
    ax_hold.grid(axis="x", alpha=0.2)
    save(fig, "paper2_controller_screen.png")

    phase_policy_confirmation_figure()
    startstop_phase_preview_confirmation_figure()


def phase_policy_confirmation_figure():
    """Plot only the independently confirmed phase-policy result."""
    # This is a separate confirmation set. It is plotted independently from
    # the gain/schedule screen so an exploratory choice is not mistaken for a
    # pre-registered controller comparison.
    confirmation = load("paper2_phase_policy_tracking_confirmation.json")
    rows = confirmation["test_result"]["rows"]
    seeds = [int(row["seed"]) for row in rows]
    savings = [float(row["saving_vs_same_seed_ool_pct"]) for row in rows]
    summary = confirmation["test_result"]["saving_pct"]
    mean = float(summary["mean"])
    ci_low = float(summary["ci95_low"])
    ci_high = float(summary["ci95_high"])
    fig, ax = plt.subplots(figsize=(6.4, 4.0))
    ax.scatter(seeds, savings, color="#2a9d8f", s=28, zorder=3,
               label="Same-seed paired saving")
    ax.axhline(0.0, color="#303030", linewidth=0.8)
    ax.axhline(mean, color="#e76f51", linewidth=1.2,
               label="Mean and 95% CI")
    ax.fill_between([min(seeds) - 0.5, max(seeds) + 0.5], ci_low, ci_high,
                    color="#e76f51", alpha=0.16)
    ax.set_xlim(min(seeds) - 0.5, max(seeds) + 0.5)
    ax.set_xlabel("Independent stochastic-cycle seed")
    ax.set_ylabel("Fuel saving vs. realistic OOL (%)")
    ax.set_title("Causal phase-policy confirmation (n = 14)", fontsize=10, pad=8)
    ax.text(0.02, 0.04, f"Mean {mean:.3f}%  [95% CI {ci_low:.3f}, {ci_high:.3f}]",
            transform=ax.transAxes, fontsize=8, va="bottom",
            bbox={"boxstyle": "round,pad=0.14", "fc": "white", "ec": "none", "alpha": 0.92})
    ax.grid(axis="y", alpha=0.2)
    ax.legend(frameon=False, fontsize=8, ncol=2, loc="upper center",
              bbox_to_anchor=(0.5, -0.27))
    fig.subplots_adjust(left=0.14, right=0.98, top=0.88, bottom=0.28)
    save(fig, "paper2_phase_policy_confirmation.png", tight_layout=False)


def startstop_phase_preview_confirmation_figure():
    """Plot the frozen causal MPC confirmation separately from all screens."""
    confirmation = load("paper2_startstop_phase_preview_confirmation.json")
    rows = confirmation["scenario_mpc_rows"]
    seeds = [int(row["seed"]) for row in rows]
    savings = [float(row["saving_vs_same_seed_ool_pct"]) for row in rows]
    summary = confirmation["paired_saving_pct"]
    mean = float(summary["mean"])
    ci_low = float(summary["ci95_low"])
    ci_high = float(summary["ci95_high"])
    fig, ax = plt.subplots(figsize=(6.4, 4.0))
    ax.scatter(seeds, savings, color="#277da1", s=30, zorder=3,
               label="Same-seed paired saving")
    ax.axhline(0.0, color="#303030", linewidth=0.8)
    ax.axhline(mean, color="#d1495b", linewidth=1.2, label="Mean and 95% CI")
    ax.fill_between([min(seeds) - 0.5, max(seeds) + 0.5], ci_low, ci_high,
                    color="#d1495b", alpha=0.16)
    ax.set_xlim(min(seeds) - 0.5, max(seeds) + 0.5)
    ax.set_xlabel("Independent stochastic-cycle seed")
    ax.set_ylabel("Fuel saving vs. realistic OOL (%)")
    ax.set_title("Causal scenario-MPC confirmation (n = 14)", fontsize=10, pad=8)
    ax.text(0.02, 0.04, f"Mean {mean:.3f}%  [95% CI {ci_low:.3f}, {ci_high:.3f}]",
            transform=ax.transAxes, fontsize=8, va="bottom")
    ax.grid(axis="y", alpha=0.2)
    ax.legend(frameon=False, fontsize=8, ncol=2, loc="upper center",
              bbox_to_anchor=(0.5, -0.27))
    fig.subplots_adjust(left=0.14, right=0.98, top=0.88, bottom=0.28)
    save(fig, "paper2_startstop_phase_preview_confirmation.png", tight_layout=False)


if __name__ == "__main__":
    OUT.mkdir(parents=True, exist_ok=True)
    lift_figures()
    energy_figures()
