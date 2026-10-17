"""Fair shared-start/stop sensitivity screen for the strict paper-2 protocol.

Every candidate applies the identical start/stop supervisor to realistic OOL
and scenario MPC.  The start-fuel proxy is fixed across candidates; the screen
therefore tests controller response to a common operational constraint rather
than worsening the baseline selectively.
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
BASE: dict[str, Any] = {
    "duration_s": 600.0,
    "profile_name": "stochastic_agri_workcycle",
    "engine_map": LiteratureBSFCMap(),
    "motor_map": RealisticMotorMap(),
    "accessory_for_all_w": 18000.0,
    "mpc_terminal_weight": 2000000.0,
    "scenario_count": 5,
    "stochastic_disturbance_scale": 0.25,
    "stochastic_smooth_disturbances": True,
    "stochastic_offline_reference": False,
    "stochastic_nominal_reference": False,
    "stochastic_nominal_phase_preview": False,
    "engine_rated_w": 300000.0,
    "battery_capacity_wh": 200000.0,
    "battery_power_limit_w": 150000.0,
    "motor_peak_w": 150000.0,
    "engine_start_fuel_g": 1.5,
}

# This is an operating-assumption sensitivity, not a target-machine claim.
# Every enabled setting uses the same stable-speed floor, restart threshold,
# dwell accounting, and fixed start-fuel proxy for both controllers.
CANDIDATES: tuple[dict[str, Any], ...] = (
    {"name": "disabled", "overrides": {"engine_start_stop": False}},
    {"name": "stop20_restart45_on5_off5", "overrides": {
        "engine_start_stop": True, "engine_stop_threshold_w": 20000.0,
        "engine_restart_threshold_w": 45000.0, "engine_minimum_on_s": 5.0,
        "engine_minimum_off_s": 5.0}},
    {"name": "stop25_restart45_on5_off5", "overrides": {
        "engine_start_stop": True, "engine_stop_threshold_w": 25000.0,
        "engine_restart_threshold_w": 45000.0, "engine_minimum_on_s": 5.0,
        "engine_minimum_off_s": 5.0}},
    {"name": "stop30_restart45_on5_off5", "overrides": {
        "engine_start_stop": True, "engine_stop_threshold_w": 30000.0,
        "engine_restart_threshold_w": 45000.0, "engine_minimum_on_s": 5.0,
        "engine_minimum_off_s": 5.0}},
    {"name": "stop35_restart45_on5_off5", "overrides": {
        "engine_start_stop": True, "engine_stop_threshold_w": 35000.0,
        "engine_restart_threshold_w": 45000.0, "engine_minimum_on_s": 5.0,
        "engine_minimum_off_s": 5.0}},
    {"name": "stop25_restart45_on5_off10", "overrides": {
        "engine_start_stop": True, "engine_stop_threshold_w": 25000.0,
        "engine_restart_threshold_w": 45000.0, "engine_minimum_on_s": 5.0,
        "engine_minimum_off_s": 10.0}},
    {"name": "stop25_restart45_on10_off5", "overrides": {
        "engine_start_stop": True, "engine_stop_threshold_w": 25000.0,
        "engine_restart_threshold_w": 45000.0, "engine_minimum_on_s": 10.0,
        "engine_minimum_off_s": 5.0}},
)


def mean_ci(values: list[float]) -> dict[str, float] | None:
    if not values:
        return None
    value_mean = sum(values) / len(values)
    if len(values) == 1:
        return {"n": 1, "mean": value_mean, "std": 0.0,
                "ci95_low": value_mean, "ci95_high": value_mean}
    std = (sum((item - value_mean) ** 2 for item in values) / (len(values) - 1)) ** 0.5
    t_critical = {6: 2.571, 14: 2.160}.get(len(values), 1.960)
    half_width = t_critical * std / math.sqrt(len(values))
    return {"n": len(values), "mean": value_mean, "std": std,
            "ci95_low": value_mean - half_width,
            "ci95_high": value_mean + half_width}


def compact(result: dict[str, object], seed: int) -> dict[str, object]:
    certified = (bool(result["valid"])
                 and int(result["fallback_count"]) == 0
                 and int(result["ramp_envelope_infeasibility_count"]) == 0)
    return {
        "seed": seed, "fuel_l": float(result["fuel_l"]),
        "soc_error": float(result["soc_error"]), "valid": bool(result["valid"]),
        "certified": certified,
        "fallback_count": int(result["fallback_count"]),
        "ramp_envelope_infeasibility_count": int(result["ramp_envelope_infeasibility_count"]),
        "engine_starts": int(result["engine_starts"]),
        "start_stop_transition_count": int(result["start_stop_transition_count"]),
        "max_shortage_w": float(result["max_shortage_w"]),
        "max_motor_power_violation_w": float(result["max_motor_power_violation_w"]),
        "max_battery_power_violation_w": float(result["max_battery_power_violation_w"]),
        "max_mg1_power_violation_w": float(result["max_mg1_power_violation_w"]),
        "max_mg1_speed_violation_rpm": float(result["max_mg1_speed_violation_rpm"]),
        "max_mg2_speed_violation_rpm": float(result["max_mg2_speed_violation_rpm"]),
        "max_engine_ramp_violation_w": float(result["max_engine_ramp_violation_w"]),
    }


def evaluate(candidate: dict[str, Any], seeds: tuple[int, ...]) -> dict[str, object]:
    baseline_rows, mpc_rows = [], []
    for seed in seeds:
        config_values = dict(BASE)
        config_values.update(candidate["overrides"], seed=seed)
        config = ExperimentConfig(**config_values)
        baseline = compact(run_definition("realistic_ool", config), seed)
        mpc = compact(run_definition("robust_mpc", config), seed)
        saving = None
        if baseline["certified"] and mpc["certified"]:
            saving = (float(baseline["fuel_l"]) - float(mpc["fuel_l"])) / float(baseline["fuel_l"]) * 100.0
        mpc["saving_vs_same_seed_ool_pct"] = saving
        baseline_rows.append(baseline)
        mpc_rows.append(mpc)
        print(candidate["name"], seed, baseline["valid"], mpc["valid"],
              f"{baseline['fuel_l']:.6f}", f"{mpc['fuel_l']:.6f}", flush=True)
    savings = [float(row["saving_vs_same_seed_ool_pct"]) for row in mpc_rows
               if row["saving_vs_same_seed_ool_pct"] is not None]
    return {
        "name": candidate["name"], "overrides": candidate["overrides"],
        "baseline_rows": baseline_rows, "scenario_mpc_rows": mpc_rows,
        "baseline_valid_rate": sum(bool(row["valid"]) for row in baseline_rows) / len(baseline_rows),
        "baseline_certified_rate": sum(bool(row["certified"]) for row in baseline_rows) / len(baseline_rows),
        "valid_rate": sum(bool(row["valid"]) for row in mpc_rows) / len(mpc_rows),
        "certified_rate": sum(bool(row["certified"]) for row in mpc_rows) / len(mpc_rows),
        "certified_pair_rate": len(savings) / len(mpc_rows),
        "saving_pct": mean_ci(savings),
        "mean_baseline_engine_starts": sum(int(row["engine_starts"]) for row in baseline_rows) / len(baseline_rows),
        "mean_mpc_engine_starts": sum(int(row["engine_starts"]) for row in mpc_rows) / len(mpc_rows),
        "mean_mpc_fallback_count": sum(int(row["fallback_count"]) for row in mpc_rows) / len(mpc_rows),
    }


def rank(entry: dict[str, object]) -> float:
    if (entry["baseline_certified_rate"] != 1.0
            or entry["certified_pair_rate"] != 1.0
            or entry["saving_pct"] is None):
        return float("-inf")
    return float(entry["saving_pct"]["mean"])


def main() -> None:
    development = [evaluate(candidate, DEVELOPMENT_SEEDS) for candidate in CANDIDATES]
    finalists = sorted(development, key=rank, reverse=True)[:2]
    holdout = [evaluate({"name": entry["name"], "overrides": entry["overrides"]}, HOLDOUT_SEEDS)
               for entry in finalists]
    output = {
        "protocol": {
            "engine_map": "LiteratureBSFCMap",
            "cycle": "stochastic_agri_workcycle",
            "duration_s": 600.0,
            "disturbance_scale": 0.25,
            "shared_start_stop": "Identical supervisor, 60 kW stable-power floor, and 1.5 g/start proxy for OOL and scenario MPC.",
            "baseline": "Candidate-specific same-seed realistic dynamic OOL; no baseline is carried across a start/stop setting.",
            "validity_rule": "terminal SOC error <= 0.01, traction shortage <= 1 W, proxy violations <= 1 W/rpm, zero fallback, and zero forecast ramp-envelope infeasibility",
            "selection_rule": "Rank fully certified candidates on six development seeds; test two finalists on 14 disjoint holdout seeds.",
        },
        "development_seeds": list(DEVELOPMENT_SEEDS),
        "holdout_seeds": list(HOLDOUT_SEEDS),
        "development": development,
        "selected_finalists": [entry["name"] for entry in finalists],
        "holdout": holdout,
    }
    path = ROOT / "results" / "paper2_startstop_screen.json"
    path.write_text(json.dumps(output, ensure_ascii=False, indent=2), encoding="utf-8")
    print(path)


if __name__ == "__main__":
    main()
