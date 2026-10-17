"""Explore a frozen public-task-phase policy under the strict paper-2 protocol.

The policy receives only the recurring 270 s task phase and present SOC.  Its
eight requested engine-power targets are selected on six development seeds,
then frozen and evaluated on fourteen disjoint holdout seeds.  This is an
exploratory controller search, not a replacement for the causal-MPC result.
"""
from __future__ import annotations

import json
import math
from pathlib import Path
import sys
from typing import Any

ROOT = Path(__file__).parents[1]
sys.path[:0] = [str(ROOT / "code"), str(ROOT / "code" / "energy_management")]

from experiments import ExperimentConfig, _WORKCYCLE_SEGMENT_BOUNDARIES_S, run_definition
from os_ecvt_model import LiteratureBSFCMap, RealisticMotorMap

DEVELOPMENT_SEEDS = tuple(range(2026, 2032))
HOLDOUT_SEEDS = tuple(range(2032, 2046))
BASE: dict[str, Any] = {
    "duration_s": 600.0,
    "profile_name": "stochastic_agri_workcycle",
    "engine_map": LiteratureBSFCMap(),
    "motor_map": RealisticMotorMap(),
    "accessory_for_all_w": 18000.0,
    "stochastic_disturbance_scale": 0.25,
    "stochastic_smooth_disturbances": True,
    "engine_rated_w": 300000.0,
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


def compact(seed: int, result: dict[str, object], baseline: dict[str, object]) -> dict[str, object]:
    certified = bool(result["valid"])
    saving = None
    if certified and bool(baseline["certified"]):
        saving = ((float(baseline["fuel_l"]) - float(result["fuel_l"]))
                  / float(baseline["fuel_l"]) * 100.0)
    return {
        "seed": seed,
        "fuel_l": float(result["fuel_l"]),
        "soc_error": float(result["soc_error"]),
        "valid": bool(result["valid"]),
        "certified": certified,
        "max_shortage_w": float(result["max_shortage_w"]),
        "max_motor_power_violation_w": float(result["max_motor_power_violation_w"]),
        "max_battery_power_violation_w": float(result["max_battery_power_violation_w"]),
        "max_mg1_power_violation_w": float(result["max_mg1_power_violation_w"]),
        "max_mg1_speed_violation_rpm": float(result["max_mg1_speed_violation_rpm"]),
        "max_mg2_speed_violation_rpm": float(result["max_mg2_speed_violation_rpm"]),
        "max_engine_ramp_violation_w": float(result["max_engine_ramp_violation_w"]),
        "saving_vs_same_seed_ool_pct": saving,
    }


def make_baselines(seeds: tuple[int, ...]) -> tuple[dict[int, dict[str, object]], dict[int, dict[str, object]]]:
    rows: dict[int, dict[str, object]] = {}
    raw: dict[int, dict[str, object]] = {}
    for seed in seeds:
        result = run_definition("realistic_ool", ExperimentConfig(seed=seed, **BASE))
        raw[seed] = result
        rows[seed] = {"fuel_l": float(result["fuel_l"]), "certified": bool(result["valid"])}
        print("ool", seed, rows[seed]["certified"], f"{rows[seed]['fuel_l']:.6f}", flush=True)
    return rows, raw


def phase_means(raw_baselines: dict[int, dict[str, object]]) -> tuple[float, ...]:
    means = []
    for segment in range(len(_WORKCYCLE_SEGMENT_BOUNDARIES_S) - 1):
        values = []
        for result in raw_baselines.values():
            for index, command_w in enumerate(result["commands_w"]):
                local_s = (index * 0.1) % _WORKCYCLE_SEGMENT_BOUNDARIES_S[-1]
                if (_WORKCYCLE_SEGMENT_BOUNDARIES_S[segment] <= local_s
                        < _WORKCYCLE_SEGMENT_BOUNDARIES_S[segment + 1]):
                    values.append(float(command_w))
        means.append(sum(values) / len(values))
    return tuple(means)


def evaluate(targets: tuple[float, ...], seeds: tuple[int, ...],
             baselines: dict[int, dict[str, object]], tracking_gain: float = 0.0,
             emit: bool = False) -> dict[str, object]:
    rows = []
    for seed in seeds:
        result = run_definition(
            "phase_policy",
            ExperimentConfig(seed=seed, phase_policy_targets_w=targets,
                             phase_policy_tracking_gain=tracking_gain, **BASE),
        )
        row = compact(seed, result, baselines[seed])
        rows.append(row)
        if emit:
            print("phase_policy", seed, row["certified"], f"{row['fuel_l']:.6f}", flush=True)
    savings = [float(row["saving_vs_same_seed_ool_pct"]) for row in rows
               if row["saving_vs_same_seed_ool_pct"] is not None]
    return {
        "targets_w": list(targets), "tracking_gain": tracking_gain,
        "rows": rows,
        "valid_rate": sum(bool(row["valid"]) for row in rows) / len(rows),
        "certified_rate": sum(bool(row["certified"]) for row in rows) / len(rows),
        "saving_pct": mean_ci(savings),
        "mean_fuel_l": sum(float(row["fuel_l"]) for row in rows) / len(rows),
    }


def score(summary: dict[str, object]) -> tuple[int, float]:
    """Hard validity is lexicographically prior to fuel consumption."""
    invalid = len(summary["rows"]) - sum(bool(row["certified"]) for row in summary["rows"])
    return invalid, float(summary["mean_fuel_l"])


def search(initial: tuple[float, ...], seeds: tuple[int, ...],
           baselines: dict[int, dict[str, object]], tracking_gain: float = 0.0) -> tuple[dict[str, object], list[dict[str, object]]]:
    current = tuple(initial)
    current_summary = evaluate(current, seeds, baselines, tracking_gain=tracking_gain)
    trace = [{"step_w": None, "targets_w": list(current), "score": list(score(current_summary))}]
    for step_w in (60000.0, 30000.0, 15000.0, 7500.0, 3750.0, 1875.0):
        improved = True
        sweep = 0
        while improved and sweep < 3:
            improved = False
            sweep += 1
            for coordinate in range(len(current)):
                for direction in (-1.0, 1.0):
                    proposal = list(current)
                    proposal[coordinate] = max(60000.0, min(300000.0,
                                                            proposal[coordinate] + direction * step_w))
                    proposal_tuple = tuple(proposal)
                    proposal_summary = evaluate(proposal_tuple, seeds, baselines,
                                                tracking_gain=tracking_gain)
                    if score(proposal_summary) < score(current_summary):
                        current, current_summary = proposal_tuple, proposal_summary
                        improved = True
                        trace.append({"step_w": step_w, "targets_w": list(current),
                                      "score": list(score(current_summary))})
    return current_summary, trace


def main() -> None:
    development_baseline, development_raw = make_baselines(DEVELOPMENT_SEEDS)
    baseline_targets = phase_means(development_raw)
    development_start = evaluate(baseline_targets, DEVELOPMENT_SEEDS, development_baseline)
    development_selected, trace = search(baseline_targets, DEVELOPMENT_SEEDS, development_baseline)
    holdout_baseline, _ = make_baselines(HOLDOUT_SEEDS)
    holdout_selected = evaluate(tuple(development_selected["targets_w"]), HOLDOUT_SEEDS,
                                holdout_baseline, emit=True)
    output = {
        "purpose": (
            "Exploratory public-task-phase policy screen. Targets are selected on development "
            "seeds and frozen before holdout evaluation; this is not an online-MPC result."),
        "protocol": {
            "cycle": "600 s continuous stochastic agricultural cycle",
            "online_information": "public 270 s task phase plus present SOC; no future disturbance samples",
            "engine_map": "LiteratureBSFCMap",
            "baseline": "unchanged same-seed realistic dynamic OOL",
            "shared_constraints": "60 kW stable floor, 40 kW/s applied engine ramp, 150 kW motor and battery-bus limits",
            "certification_rule": "all existing hard run-validity conditions; no MPC candidate fallback exists in this policy",
            "selection_rule": "lexicographic hard-validity then mean fuel coordinate search on six development seeds",
        },
        "development_seeds": list(DEVELOPMENT_SEEDS),
        "holdout_seeds": list(HOLDOUT_SEEDS),
        "development_ool_phase_mean_start": development_start,
        "development_selected": development_selected,
        "coordinate_search_trace": trace,
        "holdout_frozen_selected": holdout_selected,
    }
    path = ROOT / "results" / "paper2_phase_policy_screen.json"
    path.write_text(json.dumps(output, ensure_ascii=False, indent=2), encoding="utf-8")
    print(path)


if __name__ == "__main__":
    main()
