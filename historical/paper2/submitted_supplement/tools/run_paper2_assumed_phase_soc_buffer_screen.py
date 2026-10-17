"""Strict causal screen for public-phase SOC-buffer policies.

The policy uses only a recurring public work phase, present demand, and
present SOC.  SOC targets describe a predeclared buffer trajectory; they do
not use realized future disturbance data and the existing terminal-SOC hard
screen remains in force.  Candidate vectors are selected on development
seeds, then frozen through disjoint holdout and confirmation seeds.
"""
from __future__ import annotations

import json
from pathlib import Path

from run_paper2_assumed_phase_policy_tiered_screen import (
    BASE, baselines, compact, mean_ci,
)
from experiments import ExperimentConfig, run_definition

ROOT = Path(__file__).parents[1]
DEVELOPMENT_SEEDS = tuple(range(2163, 2169))
HOLDOUT_SEEDS = tuple(range(2169, 2183))
CONFIRMATION_SEEDS = tuple(range(2183, 2197))
TRACKING_GAIN = 0.35
SOC_TRACKING_TIME_S = 60.0
FROZEN_TARGETS_W = (174375.0, 168750.0, 202500.0, 181875.0,
                    176250.0, 123750.0, 140625.0, 151875.0)

# Phase order: idle, idle-to-transport, transport, transport-to-plough,
# plough, plough-to-turn, turn, turn-to-idle.  The first candidate is the
# exact frozen policy, so an SOC reference must beat it fairly to advance.
CANDIDATES: dict[str, tuple[float, ...] | None] = {
    "no_phase_soc_reference": None,
    "charge_before_plough_then_assist":
        (0.550, 0.552, 0.556, 0.558, 0.545, 0.545, 0.550, 0.550),
    "moderate_preplough_buffer":
        (0.550, 0.552, 0.555, 0.556, 0.550, 0.548, 0.550, 0.550),
    "transport_charge_turn_recovery":
        (0.550, 0.551, 0.555, 0.556, 0.547, 0.546, 0.553, 0.550),
}


def evaluate(name: str, targets: tuple[float, ...] | None, seeds: tuple[int, ...],
             baseline_rows: dict[int, dict[str, object]], emit: bool = False) -> dict[str, object]:
    rows = []
    for seed in seeds:
        result = run_definition(
            "phase_policy",
            ExperimentConfig(
                seed=seed,
                phase_policy_targets_w=FROZEN_TARGETS_W,
                phase_policy_tracking_gain=TRACKING_GAIN,
                phase_policy_soc_targets=targets,
                phase_policy_soc_tracking_time_s=SOC_TRACKING_TIME_S,
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
        "engine_targets_w": list(FROZEN_TARGETS_W),
        "tracking_gain": TRACKING_GAIN,
        "soc_targets": None if targets is None else list(targets),
        "soc_tracking_time_s": SOC_TRACKING_TIME_S,
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
        evaluate(name, targets, DEVELOPMENT_SEEDS, development_baseline, emit=True)
        for name, targets in CANDIDATES.items()
    ]
    finalist = min(development, key=score)
    print("selected_development", finalist["name"], finalist["hard_valid_rate"],
          finalist["saving_pct"], flush=True)

    holdout_baseline = baselines(HOLDOUT_SEEDS)
    targets = finalist["soc_targets"]
    holdout = evaluate(str(finalist["name"]), None if targets is None else tuple(targets),
                       HOLDOUT_SEEDS, holdout_baseline, emit=True)
    confirmation_baseline = baselines(CONFIRMATION_SEEDS)
    confirmation = evaluate(str(finalist["name"]), None if targets is None else tuple(targets),
                            CONFIRMATION_SEEDS, confirmation_baseline, emit=True)
    output = {
        "purpose": (
            "Predeclared public-phase SOC-buffer causal screen on the uncalibrated assumed map; "
            "not an MPC, calibrated-tractor, hardware, or 20-percent result."
        ),
        "protocol": {
            "online_information": "public recurring task phase, present demand, and present SOC only",
            "baseline": "unchanged same-seed realistic dynamic OOL",
            "shared_constraints": "60 kW stable floor, 40 kW/s applied engine ramp, 150 kW motor and battery-bus limits",
            "selection": "four predeclared SOC reference vectors, development selection, frozen holdout, and frozen independent confirmation",
            "map": "RealisticDieselMap low_load_efficiency=0.08, power_width_w=90000; uncalibrated sensitivity map",
        },
        "development_seeds": list(DEVELOPMENT_SEEDS),
        "holdout_seeds": list(HOLDOUT_SEEDS),
        "confirmation_seeds": list(CONFIRMATION_SEEDS),
        "frozen_engine_targets_w": list(FROZEN_TARGETS_W),
        "tracking_gain": TRACKING_GAIN,
        "soc_tracking_time_s": SOC_TRACKING_TIME_S,
        "predeclared_soc_candidates": {
            name: None if targets is None else list(targets)
            for name, targets in CANDIDATES.items()
        },
        "development_candidates": development,
        "selected_development_finalist": finalist,
        "holdout_frozen_finalist": holdout,
        "confirmation_frozen_finalist": confirmation,
    }
    path = ROOT / "results" / "paper2_assumed_phase_soc_buffer_screen.json"
    path.write_text(json.dumps(output, ensure_ascii=False, indent=2), encoding="utf-8")
    print(path)


if __name__ == "__main__":
    main()
