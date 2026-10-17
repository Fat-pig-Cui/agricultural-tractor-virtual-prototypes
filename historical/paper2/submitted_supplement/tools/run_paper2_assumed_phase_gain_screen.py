"""Strict screen for a phase-dependent causal tracking policy.

The fixed targets are the frozen multi-start assumed-map schedule.  This
screen changes only how each public work phase responds to the *current*
measured demand.  Three gain vectors are predeclared before the development
seeds are evaluated; the selected vector is then frozen through disjoint
holdout and confirmation seeds.  It observes no realized future disturbance.
"""
from __future__ import annotations

import json
from pathlib import Path

from run_paper2_assumed_phase_policy_tiered_screen import (
    BASE, baselines, compact, mean_ci,
)
from experiments import ExperimentConfig, run_definition

ROOT = Path(__file__).parents[1]
DEVELOPMENT_SEEDS = tuple(range(2129, 2135))
HOLDOUT_SEEDS = tuple(range(2135, 2149))
CONFIRMATION_SEEDS = tuple(range(2149, 2163))

# Frozen from the prior multi-start study before any seed below was used.
FROZEN_TARGETS_W = (174375.0, 168750.0, 202500.0, 181875.0,
                    176250.0, 123750.0, 140625.0, 151875.0)

# Phase order: idle, idle-to-transport, transport, transport-to-plough,
# plough, plough-to-turn, turn, turn-to-idle.  All gains remain in [0, 1].
CANDIDATES = {
    "uniform_0p35": (0.35, 0.35, 0.35, 0.35, 0.35, 0.35, 0.35, 0.35),
    "stationary_island_with_transition_tracking":
        (0.00, 0.75, 0.05, 0.75, 0.35, 0.75, 0.00, 0.75),
    "demand_tracking_with_transition_priority":
        (0.10, 0.90, 0.35, 0.90, 0.45, 0.90, 0.10, 0.90),
}


def evaluate(name: str, gains: tuple[float, ...], seeds: tuple[int, ...],
             baseline_rows: dict[int, dict[str, object]], emit: bool = False) -> dict[str, object]:
    rows = []
    for seed in seeds:
        result = run_definition(
            "phase_policy",
            ExperimentConfig(
                seed=seed,
                phase_policy_targets_w=FROZEN_TARGETS_W,
                phase_policy_tracking_gains=gains,
                **BASE,
            ),
        )
        row = compact(seed, result, baseline_rows[seed])
        rows.append(row)
        if emit:
            print("policy", name, seed, row["hard_valid"],
                  f"{row['fuel_l']:.6f}", flush=True)
    savings = [float(row["saving_vs_same_seed_ool_pct"]) for row in rows
               if row["saving_vs_same_seed_ool_pct"] is not None]
    return {
        "name": name,
        "targets_w": list(FROZEN_TARGETS_W),
        "tracking_gains": list(gains),
        "rows": rows,
        "hard_valid_rate": sum(bool(row["hard_valid"]) for row in rows) / len(rows),
        "mean_fuel_l": sum(float(row["fuel_l"]) for row in rows) / len(rows),
        "saving_pct": mean_ci(savings),
    }


def score(summary: dict[str, object]) -> tuple[int, float]:
    invalid = len(summary["rows"]) - sum(bool(row["hard_valid"]) for row in summary["rows"])
    return invalid, float(summary["mean_fuel_l"])


def main() -> None:
    development_baseline = baselines(DEVELOPMENT_SEEDS)
    development = [
        evaluate(name, gains, DEVELOPMENT_SEEDS, development_baseline, emit=True)
        for name, gains in CANDIDATES.items()
    ]
    finalist = min(development, key=score)
    print("selected_development", finalist["name"], finalist["hard_valid_rate"],
          finalist["saving_pct"], flush=True)

    holdout_baseline = baselines(HOLDOUT_SEEDS)
    holdout = evaluate(str(finalist["name"]), tuple(finalist["tracking_gains"]),
                       HOLDOUT_SEEDS, holdout_baseline, emit=True)
    confirmation_baseline = baselines(CONFIRMATION_SEEDS)
    confirmation = evaluate(str(finalist["name"]), tuple(finalist["tracking_gains"]),
                            CONFIRMATION_SEEDS, confirmation_baseline, emit=True)
    output = {
        "purpose": (
            "Predeclared phase-dependent causal-gain screen on the uncalibrated assumed map; "
            "not an MPC, calibrated-tractor, hardware, or 20-percent result."
        ),
        "protocol": {
            "online_information": "public recurring task phase, present demand, and present SOC only",
            "baseline": "unchanged same-seed realistic dynamic OOL",
            "shared_constraints": "60 kW stable floor, 40 kW/s applied engine ramp, 150 kW motor and battery-bus limits",
            "selection": "three predeclared gain vectors, development selection, frozen holdout, and frozen independent confirmation",
            "map": "RealisticDieselMap low_load_efficiency=0.08, power_width_w=90000; uncalibrated sensitivity map",
        },
        "development_seeds": list(DEVELOPMENT_SEEDS),
        "holdout_seeds": list(HOLDOUT_SEEDS),
        "confirmation_seeds": list(CONFIRMATION_SEEDS),
        "frozen_targets_w": list(FROZEN_TARGETS_W),
        "predeclared_gain_candidates": {name: list(gains) for name, gains in CANDIDATES.items()},
        "development_candidates": development,
        "selected_development_finalist": finalist,
        "holdout_frozen_finalist": holdout,
        "confirmation_frozen_finalist": confirmation,
    }
    path = ROOT / "results" / "paper2_assumed_phase_gain_screen.json"
    path.write_text(json.dumps(output, ensure_ascii=False, indent=2), encoding="utf-8")
    print(path)


if __name__ == "__main__":
    main()
