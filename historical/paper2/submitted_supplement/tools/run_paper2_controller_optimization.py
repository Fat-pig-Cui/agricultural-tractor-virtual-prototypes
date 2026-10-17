"""Two-stage, no-oracle controller search for the paper-2 strict protocol.

Candidate choices are ranked only on development seeds.  The selected three
settings are then evaluated on untouched holdout seeds against the same-seed
realistic OOL baseline.  The study intentionally uses the literature-shaped
engine map because it is the more defensible main-evidence case.
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
from os_ecvt_model import LiteratureBSFCMap, RealisticMotorMap

DEVELOPMENT_SEEDS = tuple(range(2026, 2032))
HOLDOUT_SEEDS = tuple(range(2032, 2046))
CONTROLLER = "robust_mpc"

# The default setting is retained as a candidate.  No candidate changes the
# demand, SOC screen, proxy constraint screen, hardware proxy, or OOL baseline.
CANDIDATES: tuple[dict[str, Any], ...] = (
    {"name": "default_H8_S5_W2M", "overrides": {}},
    {"name": "horizon_4", "overrides": {"mpc_horizon": 4}},
    {"name": "horizon_12", "overrides": {"mpc_horizon": 12}},
    {"name": "horizon_20", "overrides": {"mpc_horizon": 20}},
    {"name": "scenarios_3", "overrides": {"scenario_count": 3}},
    {"name": "scenarios_9", "overrides": {"scenario_count": 9}},
    {"name": "terminal_weight_0p5M", "overrides": {"mpc_terminal_weight": 500000.0}},
    {"name": "terminal_weight_1M", "overrides": {"mpc_terminal_weight": 1000000.0}},
    {"name": "terminal_weight_5M", "overrides": {"mpc_terminal_weight": 5000000.0}},
    {"name": "terminal_weight_10M", "overrides": {"mpc_terminal_weight": 10000000.0}},
    {"name": "common_nominal_reference", "overrides": {"stochastic_nominal_reference": True}},
)

BASE_PROTOCOL: dict[str, Any] = {
    "duration_s": 600.0,
    "profile_name": "stochastic_agri_workcycle",
    "engine_map": LiteratureBSFCMap(),
    "motor_map": RealisticMotorMap(),
    "accessory_for_all_w": 18000.0,
    "mpc_terminal_weight": 2000000.0,
    "stochastic_disturbance_scale": 0.25,
    "stochastic_offline_reference": False,
    "stochastic_nominal_reference": False,
    "stochastic_nominal_phase_preview": False,
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
        return {"n": 1, "mean": mean, "std": 0.0, "ci95_low": mean, "ci95_high": mean}
    std = (sum((value - mean) ** 2 for value in values) / (len(values) - 1)) ** 0.5
    # t_{0.975, n-1} for the only sample sizes used below (6 and 14).
    t_critical = {6: 2.571, 14: 2.160}.get(len(values), 1.960)
    half_width = t_critical * std / math.sqrt(len(values))
    return {"n": len(values), "mean": mean, "std": std,
            "ci95_low": mean - half_width, "ci95_high": mean + half_width}


def row(result: dict[str, object], seed: int) -> dict[str, object]:
    return {
        "seed": seed,
        "fuel_l": float(result["fuel_l"]),
        "soc_error": float(result["soc_error"]),
        "valid": bool(result["valid"]),
        "max_shortage_w": float(result["max_shortage_w"]),
        "max_motor_power_violation_w": float(result["max_motor_power_violation_w"]),
        "max_mg1_power_violation_w": float(result["max_mg1_power_violation_w"]),
        "max_mg1_speed_violation_rpm": float(result["max_mg1_speed_violation_rpm"]),
        "max_mg2_speed_violation_rpm": float(result["max_mg2_speed_violation_rpm"]),
        "fallback_count": int(result["fallback_count"]),
    }


def evaluate(candidate: dict[str, Any], seeds: tuple[int, ...],
             baseline_rows: dict[int, dict[str, object]]) -> dict[str, object]:
    rows: list[dict[str, object]] = []
    for seed in seeds:
        config_values = dict(BASE_PROTOCOL)
        config_values.update(candidate["overrides"])
        result = run_definition(CONTROLLER, ExperimentConfig(seed=seed, **config_values))
        candidate_row = row(result, seed)
        base_row = baseline_rows[seed]
        candidate_row["saving_vs_same_seed_ool_pct"] = (
            (float(base_row["fuel_l"]) - float(candidate_row["fuel_l"]))
            / float(base_row["fuel_l"]) * 100.0
            if bool(base_row["valid"]) and bool(candidate_row["valid"]) else None)
        rows.append(candidate_row)
        print(candidate["name"], seed, candidate_row["valid"],
              f"{candidate_row['fuel_l']:.6f}", flush=True)
    valid_savings = [float(item["saving_vs_same_seed_ool_pct"]) for item in rows
                     if item["saving_vs_same_seed_ool_pct"] is not None]
    return {
        "name": candidate["name"],
        "overrides": candidate["overrides"],
        "rows": rows,
        "valid_rate": sum(bool(item["valid"]) for item in rows) / len(rows),
        "valid_pair_rate": len(valid_savings) / len(rows),
        "saving_pct": mean_ci(valid_savings),
        "mean_fallback_count": sum(int(item["fallback_count"]) for item in rows) / len(rows),
    }


def baseline_for(seeds: tuple[int, ...]) -> dict[int, dict[str, object]]:
    baseline_rows: dict[int, dict[str, object]] = {}
    for seed in seeds:
        result = run_definition("realistic_ool", ExperimentConfig(seed=seed, **BASE_PROTOCOL))
        baseline_rows[seed] = row(result, seed)
        print("realistic_ool", seed, baseline_rows[seed]["valid"],
              f"{baseline_rows[seed]['fuel_l']:.6f}", flush=True)
    return baseline_rows


def rankable(entry: dict[str, object]) -> float:
    summary = entry["saving_pct"]
    if entry["valid_pair_rate"] != 1.0 or summary is None:
        return float("-inf")
    return float(summary["mean"])


def main() -> None:
    development_baseline = baseline_for(DEVELOPMENT_SEEDS)
    development = [evaluate(candidate, DEVELOPMENT_SEEDS, development_baseline)
                   for candidate in CANDIDATES]
    finalists = sorted(development, key=rankable, reverse=True)[:3]

    holdout_baseline = baseline_for(HOLDOUT_SEEDS)
    holdout = [evaluate({"name": item["name"], "overrides": item["overrides"]},
                        HOLDOUT_SEEDS, holdout_baseline)
               for item in finalists]
    output = {
        "protocol": {
            "engine_map": "LiteratureBSFCMap",
            "cycle": "stochastic_agri_workcycle",
            "duration_s": 600.0,
            "disturbance_scale": 0.25,
            "offline_reference": False,
            "nominal_phase_preview": False,
            "common_nominal_reference_definition": (
                "When enabled, the reference is solved once from the shared "
                "zero-disturbance task sequence; it never uses seed-specific future disturbances."),
            "selection_rule": (
                "Rank all-valid candidates by paired saving on development seeds; "
                "report finalists only on disjoint holdout seeds."),
            "validity_rule": "terminal SOC error <= 0.01, traction shortage <= 1 W, proxy violations <= 1 W/rpm",
            "baseline": "Unchanged same-seed realistic dynamic OOL baseline",
        },
        "development_seeds": list(DEVELOPMENT_SEEDS),
        "holdout_seeds": list(HOLDOUT_SEEDS),
        "development_baseline_rows": list(development_baseline.values()),
        "development_candidates": development,
        "selected_finalists": [item["name"] for item in finalists],
        "holdout_baseline_rows": list(holdout_baseline.values()),
        "holdout_finalists": holdout,
    }
    path = ROOT / "results" / "paper2_controller_optimization.json"
    path.write_text(json.dumps(output, ensure_ascii=False, indent=2), encoding="utf-8")
    print(path)


if __name__ == "__main__":
    main()
