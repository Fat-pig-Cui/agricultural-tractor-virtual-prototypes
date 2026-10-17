"""Select terminal-SOC MPC weight after fixing the causal phase-preview horizon."""
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
    "mpc_horizon": 8,
    "scenario_count": 5,
    "stochastic_disturbance_scale": 0.25,
    "stochastic_smooth_disturbances": True,
    "stochastic_offline_reference": False,
    "stochastic_nominal_reference": False,
    "stochastic_nominal_phase_preview": True,
    "stochastic_phase_residual_gain": 0.0,
    "engine_rated_w": 300000.0,
    "battery_capacity_wh": 200000.0,
    "battery_power_limit_w": 150000.0,
    "motor_peak_w": 150000.0,
    "engine_start_stop": True,
    "engine_stop_threshold_w": 25000.0,
    "engine_restart_threshold_w": 45000.0,
    "engine_minimum_on_s": 10.0,
    "engine_minimum_off_s": 5.0,
    "engine_start_fuel_g": 1.5,
}
CANDIDATES: tuple[dict[str, Any], ...] = tuple(
    {"name": f"H8_weight_{weight / 1e6:g}M",
     "overrides": {"mpc_terminal_weight": weight}}
    for weight in (500000.0, 1000000.0, 2000000.0, 5000000.0, 10000000.0)
)


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


def compact(seed: int, result: dict[str, object]) -> dict[str, object]:
    certified = (bool(result["valid"])
                 and int(result["fallback_count"]) == 0
                 and int(result["ramp_envelope_infeasibility_count"]) == 0)
    return {
        "seed": seed, "fuel_l": float(result["fuel_l"]),
        "soc_error": float(result["soc_error"]), "valid": bool(result["valid"]),
        "certified": certified, "fallback_count": int(result["fallback_count"]),
        "ramp_envelope_infeasibility_count": int(result["ramp_envelope_infeasibility_count"]),
        "max_shortage_w": float(result["max_shortage_w"]),
        "max_motor_power_violation_w": float(result["max_motor_power_violation_w"]),
        "max_battery_power_violation_w": float(result["max_battery_power_violation_w"]),
        "max_mg1_power_violation_w": float(result["max_mg1_power_violation_w"]),
        "max_mg1_speed_violation_rpm": float(result["max_mg1_speed_violation_rpm"]),
        "max_mg2_speed_violation_rpm": float(result["max_mg2_speed_violation_rpm"]),
        "max_engine_ramp_violation_w": float(result["max_engine_ramp_violation_w"]),
        "engine_starts": int(result["engine_starts"]),
        "start_stop_transition_count": int(result["start_stop_transition_count"]),
    }


def baseline(seeds: tuple[int, ...]) -> dict[int, dict[str, object]]:
    rows = {}
    for seed in seeds:
        row = compact(seed, run_definition("realistic_ool", ExperimentConfig(seed=seed, **BASE)))
        rows[seed] = row
        print("ool", seed, row["certified"], f"{row['fuel_l']:.6f}", flush=True)
    return rows


def evaluate(candidate: dict[str, Any], seeds: tuple[int, ...],
             baselines: dict[int, dict[str, object]]) -> dict[str, object]:
    rows = []
    for seed in seeds:
        values = dict(BASE)
        values.update(candidate["overrides"], seed=seed)
        row = compact(seed, run_definition("robust_mpc", ExperimentConfig(**values)))
        base = baselines[seed]
        row["saving_vs_same_seed_ool_pct"] = (
            (float(base["fuel_l"]) - float(row["fuel_l"])) / float(base["fuel_l"]) * 100.0
            if bool(base["certified"]) and bool(row["certified"]) else None)
        rows.append(row)
        print(candidate["name"], seed, row["certified"], f"{row['fuel_l']:.6f}", flush=True)
    savings = [float(row["saving_vs_same_seed_ool_pct"]) for row in rows
               if row["saving_vs_same_seed_ool_pct"] is not None]
    return {
        "name": candidate["name"], "overrides": candidate["overrides"], "rows": rows,
        "valid_rate": sum(bool(row["valid"]) for row in rows) / len(rows),
        "certified_rate": sum(bool(row["certified"]) for row in rows) / len(rows),
        "saving_pct": mean_ci(savings),
        "mean_fallback_count": sum(int(row["fallback_count"]) for row in rows) / len(rows),
    }


def rank(entry: dict[str, object]) -> float:
    summary = entry["saving_pct"]
    if entry["certified_rate"] != 1.0 or summary is None:
        return float("-inf")
    return float(summary["mean"])


def main() -> None:
    development_baseline = baseline(DEVELOPMENT_SEEDS)
    development = [evaluate(candidate, DEVELOPMENT_SEEDS, development_baseline)
                   for candidate in CANDIDATES]
    finalists = sorted(development, key=rank, reverse=True)[:2]
    holdout_baseline = baseline(HOLDOUT_SEEDS)
    holdout = [evaluate({"name": entry["name"], "overrides": entry["overrides"]},
                        HOLDOUT_SEEDS, holdout_baseline) for entry in finalists]
    output = {
        "protocol": {
            "cycle": "600 s continuous stochastic agricultural work cycle",
            "engine_map": "LiteratureBSFCMap",
            "online_information": "public nominal task phase plus present measured demand; no evaluated-seed future samples or offline reference",
            "fixed_mpc_setting": "scenario MPC, horizon 8, five scenarios, nominal phase preview, residual gain 0",
            "shared_start_stop": "25 kW stop, 45 kW restart, 10 s minimum-on, 5 s minimum-off, 1.5 g/start proxy",
            "shared_constraints": "exact common initial-SOC closure for direct-fuel comparison; 40 kW/s running-engine ramp; 60 kW stable-power floor; 150 kW motor and battery-bus limits; terminal SOC validity tolerance 0.01",
            "certification_rule": "all hard validity conditions, zero fallback, and zero forecast ramp-envelope infeasibility",
            "selection_rule": "rank fully certified terminal weights on six development seeds; evaluate the two finalists on 14 disjoint holdout seeds",
            "scope_limit": "Start/stop transitions are a shared modeled operating mode and are not ordinary running-engine ramp events; the result is not hardware validation.",
        },
        "development_seeds": list(DEVELOPMENT_SEEDS),
        "holdout_seeds": list(HOLDOUT_SEEDS),
        "development": development,
        "selected_finalists": [entry["name"] for entry in finalists],
        "holdout": holdout,
    }
    path = ROOT / "results" / "paper2_startstop_phase_preview_terminal_weight_screen.json"
    path.write_text(json.dumps(output, ensure_ascii=False, indent=2), encoding="utf-8")
    print(path)


if __name__ == "__main__":
    main()
