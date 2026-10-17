"""Tiered strict screen of a causal phase policy on the assumed efficiency map.

The controller uses only the public recurring task phase, current demand, and
current SOC. It never reads an evaluated future sample. All engine, electrical,
SOC, traction, speed, and ramp constraints are supplied by ``run_definition``
and are shared with the realistic dynamic OOL baseline.

This is an explicitly labelled assumed-map virtual-prototype sensitivity. Its
development, holdout, and confirmation seeds are disjoint from the earlier
literature-shaped policy screens.
"""
from __future__ import annotations

import json
import math
from pathlib import Path
import sys
from typing import Any

ROOT = Path(__file__).parents[1]
sys.path[:0] = [str(ROOT / "code"), str(ROOT / "code" / "energy_management")]

from experiments import ExperimentConfig, run_definition
from os_ecvt_model import RealisticDieselMap, RealisticMotorMap

DEVELOPMENT_SEEDS = tuple(range(2060, 2066))
HOLDOUT_SEEDS = tuple(range(2066, 2080))
CONFIRMATION_SEEDS = tuple(range(2080, 2094))
TRACKING_GAINS = (0.15, 0.25, 0.35)
# This predeclared map-informed start keeps the engine around its 180 kW
# efficiency island when the battery path permits it. It is not fitted to an
# evaluated seed; coordinate search then uses development seeds only.
INITIAL_TARGETS_W = (160000.0, 160000.0, 180000.0, 180000.0,
                     200000.0, 200000.0, 160000.0, 160000.0)
BASE: dict[str, Any] = {
    "duration_s": 600.0,
    "profile_name": "stochastic_agri_workcycle",
    "engine_map": RealisticDieselMap(low_load_efficiency=0.08, power_width_w=90000.0),
    "motor_map": RealisticMotorMap(),
    "accessory_for_all_w": 18000.0,
    "stochastic_disturbance_scale": 0.25,
    "stochastic_smooth_disturbances": True,
    "engine_rated_w": 260000.0,
    "battery_capacity_wh": 200000.0,
    "battery_power_limit_w": 150000.0,
    "motor_peak_w": 150000.0,
}


def mean_ci(values: list[float]) -> dict[str, float] | None:
    if not values:
        return None
    mean = sum(values) / len(values)
    if len(values) == 1:
        return {"n": 1, "mean": mean, "std": 0.0,
                "ci95_low": mean, "ci95_high": mean}
    std = (sum((value - mean) ** 2 for value in values) / (len(values) - 1)) ** 0.5
    critical = {6: 2.571, 14: 2.160}.get(len(values), 1.960)
    half = critical * std / math.sqrt(len(values))
    return {"n": len(values), "mean": mean, "std": std,
            "ci95_low": mean - half, "ci95_high": mean + half}


def baselines(seeds: tuple[int, ...]) -> dict[int, dict[str, object]]:
    output = {}
    for seed in seeds:
        result = run_definition("realistic_ool", ExperimentConfig(seed=seed, **BASE))
        output[seed] = result
        print("ool", seed, result["valid"], f"{result['fuel_l']:.6f}", flush=True)
    return output


def compact(seed: int, result: dict[str, object], baseline: dict[str, object]) -> dict[str, object]:
    hard_valid = bool(result["valid"])
    saving = None
    if hard_valid and bool(baseline["valid"]):
        saving = ((float(baseline["fuel_l"]) - float(result["fuel_l"]))
                  / float(baseline["fuel_l"]) * 100.0)
    return {
        "seed": seed, "fuel_l": float(result["fuel_l"]),
        "soc_error": float(result["soc_error"]), "hard_valid": hard_valid,
        "max_shortage_w": float(result["max_shortage_w"]),
        "max_motor_power_violation_w": float(result["max_motor_power_violation_w"]),
        "max_battery_power_violation_w": float(result["max_battery_power_violation_w"]),
        "max_mg1_power_violation_w": float(result["max_mg1_power_violation_w"]),
        "max_mg1_speed_violation_rpm": float(result["max_mg1_speed_violation_rpm"]),
        "max_mg2_speed_violation_rpm": float(result["max_mg2_speed_violation_rpm"]),
        "max_engine_ramp_violation_w": float(result["max_engine_ramp_violation_w"]),
        "saving_vs_same_seed_ool_pct": saving,
    }


def evaluate(targets: tuple[float, ...], tracking_gain: float,
             seeds: tuple[int, ...], baseline_rows: dict[int, dict[str, object]],
             emit: bool = False) -> dict[str, object]:
    rows = []
    for seed in seeds:
        result = run_definition(
            "phase_policy",
            ExperimentConfig(seed=seed, phase_policy_targets_w=targets,
                             phase_policy_tracking_gain=tracking_gain, **BASE),
        )
        row = compact(seed, result, baseline_rows[seed])
        rows.append(row)
        if emit:
            print("policy", tracking_gain, seed, row["hard_valid"],
                  f"{row['fuel_l']:.6f}", flush=True)
    savings = [float(row["saving_vs_same_seed_ool_pct"]) for row in rows
               if row["saving_vs_same_seed_ool_pct"] is not None]
    return {
        "targets_w": list(targets), "tracking_gain": tracking_gain, "rows": rows,
        "hard_valid_rate": sum(bool(row["hard_valid"]) for row in rows) / len(rows),
        "mean_fuel_l": sum(float(row["fuel_l"]) for row in rows) / len(rows),
        "saving_pct": mean_ci(savings),
    }


def score(summary: dict[str, object]) -> tuple[int, float]:
    invalid = len(summary["rows"]) - sum(bool(row["hard_valid"]) for row in summary["rows"])
    return invalid, float(summary["mean_fuel_l"])


def coordinate_search(tracking_gain: float, seeds: tuple[int, ...],
                      baseline_rows: dict[int, dict[str, object]]) -> tuple[dict[str, object], list[dict[str, object]]]:
    current = tuple(INITIAL_TARGETS_W)
    current_summary = evaluate(current, tracking_gain, seeds, baseline_rows)
    trace = [{"step_w": None, "targets_w": list(current), "score": list(score(current_summary))}]
    for step_w in (60000.0, 30000.0, 15000.0, 7500.0, 3750.0, 1875.0):
        improved = True
        sweeps = 0
        while improved and sweeps < 3:
            improved = False
            sweeps += 1
            for coordinate in range(len(current)):
                for direction in (-1.0, 1.0):
                    proposal = list(current)
                    proposal[coordinate] = max(60000.0, min(260000.0,
                                                            proposal[coordinate] + direction * step_w))
                    candidate = tuple(proposal)
                    candidate_summary = evaluate(candidate, tracking_gain, seeds, baseline_rows)
                    if score(candidate_summary) < score(current_summary):
                        current, current_summary = candidate, candidate_summary
                        improved = True
                        trace.append({"step_w": step_w, "targets_w": list(current),
                                      "score": list(score(current_summary))})
    return current_summary, trace


def main() -> None:
    development_baseline = baselines(DEVELOPMENT_SEEDS)
    candidates = []
    for gain in TRACKING_GAINS:
        initial = evaluate(tuple(INITIAL_TARGETS_W), gain, DEVELOPMENT_SEEDS,
                           development_baseline)
        selected, trace = coordinate_search(gain, DEVELOPMENT_SEEDS, development_baseline)
        candidates.append({"tracking_gain": gain, "development_initial": initial,
                           "development_selected": selected, "trace": trace})
        print("development", gain, selected["hard_valid_rate"],
              selected["saving_pct"], flush=True)

    holdout_baseline = baselines(HOLDOUT_SEEDS)
    holdout = []
    for candidate in candidates:
        selected = candidate["development_selected"]
        result = evaluate(tuple(selected["targets_w"]), float(candidate["tracking_gain"]),
                          HOLDOUT_SEEDS, holdout_baseline, emit=True)
        holdout.append({"tracking_gain": candidate["tracking_gain"], "result": result})
    finalist = min(holdout, key=lambda item: score(item["result"]))

    confirmation_baseline = baselines(CONFIRMATION_SEEDS)
    confirmation = evaluate(tuple(finalist["result"]["targets_w"]),
                            float(finalist["tracking_gain"]),
                            CONFIRMATION_SEEDS, confirmation_baseline, emit=True)
    output = {
        "purpose": (
            "Tiered causal phase-policy sensitivity on the uncalibrated assumed efficiency island; "
            "not a hardware result, a calibrated-tractor result, or an MPC result."),
        "protocol": {
            "online_information": "public recurring task phase, present demand, and present SOC only",
            "baseline": "unchanged same-seed realistic dynamic OOL",
            "shared_constraints": "60 kW stable floor, 40 kW/s applied engine ramp, 150 kW motor and battery-bus limits",
            "selection": "three fixed tracking gains; development coordinate search; holdout finalist selection; frozen independent confirmation",
            "map": "RealisticDieselMap low_load_efficiency=0.08, power_width_w=90000; uncalibrated sensitivity map",
        },
        "development_seeds": list(DEVELOPMENT_SEEDS),
        "holdout_seeds": list(HOLDOUT_SEEDS),
        "confirmation_seeds": list(CONFIRMATION_SEEDS),
        "tracking_gains": list(TRACKING_GAINS),
        "initial_targets_w": list(INITIAL_TARGETS_W),
        "development_candidates": candidates,
        "holdout_candidates": holdout,
        "selected_holdout_finalist": finalist,
        "confirmation_frozen_finalist": confirmation,
    }
    path = ROOT / "results" / "paper2_assumed_phase_policy_tiered_screen.json"
    path.write_text(json.dumps(output, ensure_ascii=False, indent=2), encoding="utf-8")
    print(path)


if __name__ == "__main__":
    main()
