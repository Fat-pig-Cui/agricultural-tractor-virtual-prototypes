"""Causal task-phase forecast screen for the strict paper-2 protocol.

The planned agricultural task phase is common knowledge across all seeds.  A
candidate may persist only a bounded fraction of the presently observed
soil/grade residual; it never receives a future demand sample.  Development
and holdout seeds remain disjoint.
"""
from __future__ import annotations

import json
import math
from pathlib import Path
import sys

ROOT = Path(__file__).parents[1]
sys.path[:0] = [str(ROOT / "code"), str(ROOT / "code" / "energy_management")]

from experiments import ExperimentConfig, run_definition
from os_ecvt_model import LiteratureBSFCMap, RealisticMotorMap

DEVELOPMENT_SEEDS = tuple(range(2026, 2032))
HOLDOUT_SEEDS = tuple(range(2032, 2046))
# ``None`` is the causal history-only control; numeric values enable the
# common task-phase preview with the stated residual persistence gain.
GAINS = (None, 0.0, 0.25, 0.5, 0.75, 1.0)
BASE = {
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
}


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


def result_row(seed: int, result: dict[str, object], baseline: dict[str, object]) -> dict[str, object]:
    valid = bool(result["valid"])
    base_valid = bool(baseline["valid"])
    certified = (valid and int(result["fallback_count"]) == 0
                 and int(result["ramp_envelope_infeasibility_count"]) == 0)
    saving = None
    if certified and base_valid:
        saving = (float(baseline["fuel_l"]) - float(result["fuel_l"])) / float(baseline["fuel_l"]) * 100.0
    return {
        "seed": seed, "fuel_l": float(result["fuel_l"]),
        "soc_error": float(result["soc_error"]), "valid": valid,
        "certified": certified,
        "fallback_count": int(result["fallback_count"]),
        "ramp_envelope_infeasibility_count": int(result["ramp_envelope_infeasibility_count"]),
        "max_engine_ramp_violation_w": float(result["max_engine_ramp_violation_w"]),
        "max_shortage_w": float(result["max_shortage_w"]),
        "max_motor_power_violation_w": float(result["max_motor_power_violation_w"]),
        "max_battery_power_violation_w": float(result["max_battery_power_violation_w"]),
        "max_mg1_power_violation_w": float(result["max_mg1_power_violation_w"]),
        "max_mg1_speed_violation_rpm": float(result["max_mg1_speed_violation_rpm"]),
        "max_mg2_speed_violation_rpm": float(result["max_mg2_speed_violation_rpm"]),
        "saving_vs_same_seed_ool_pct": saving,
    }


def baselines(seeds: tuple[int, ...]) -> dict[int, dict[str, object]]:
    rows = {}
    for seed in seeds:
        result = run_definition("realistic_ool", ExperimentConfig(seed=seed, **BASE))
        rows[seed] = {"fuel_l": float(result["fuel_l"]), "valid": bool(result["valid"])}
        print("ool", seed, rows[seed]["valid"], f"{rows[seed]['fuel_l']:.6f}", flush=True)
    return rows


def evaluate(gain: float | None, seeds: tuple[int, ...], baseline: dict[int, dict[str, object]]) -> dict[str, object]:
    rows = []
    for seed in seeds:
        config_values = dict(BASE)
        config_values.update(
            seed=seed,
            stochastic_nominal_phase_preview=(gain is not None),
            stochastic_phase_residual_gain=(1.0 if gain is None else gain),
        )
        result = run_definition("robust_mpc", ExperimentConfig(**config_values))
        row = result_row(seed, result, baseline[seed])
        rows.append(row)
        label = "history_only" if gain is None else f"gain_{gain:g}"
        print(label, seed, row["valid"], f"{row['fuel_l']:.6f}", flush=True)
    savings = [float(row["saving_vs_same_seed_ool_pct"]) for row in rows
               if row["saving_vs_same_seed_ool_pct"] is not None]
    return {
        "residual_gain": gain, "rows": rows,
        "valid_rate": sum(bool(row["valid"]) for row in rows) / len(rows),
        "certified_rate": sum(bool(row["certified"]) for row in rows) / len(rows),
        "valid_pair_rate": len(savings) / len(rows),
        "saving_pct": mean_ci(savings),
        "mean_fallback_count": sum(int(row["fallback_count"]) for row in rows) / len(rows),
    }


def rank(entry: dict[str, object]) -> float:
    if entry["certified_rate"] != 1.0 or entry["valid_pair_rate"] != 1.0 or entry["saving_pct"] is None:
        return float("-inf")
    return float(entry["saving_pct"]["mean"])


def main() -> None:
    development_baseline = baselines(DEVELOPMENT_SEEDS)
    development = [evaluate(gain, DEVELOPMENT_SEEDS, development_baseline) for gain in GAINS]
    finalists = sorted(development, key=rank, reverse=True)[:2]
    holdout_baseline = baselines(HOLDOUT_SEEDS)
    holdout = [evaluate(entry["residual_gain"], HOLDOUT_SEEDS, holdout_baseline)
               for entry in finalists]
    output = {
        "protocol": {
            "engine_map": "LiteratureBSFCMap",
            "cycle": "stochastic_agri_workcycle",
            "duration_s": 600.0,
            "disturbance_scale": 0.25,
            "online_information": (
                "A shared zero-disturbance task phase and current measured demand only; "
                "the residual persistence gain is bounded to [0, 1]."),
            "baseline": "Unchanged same-seed realistic dynamic OOL",
            "shared_engine_constraints": "60 kW stable-power floor and 40 kW/s output ramp for OOL and MPC; theoretical OOL excluded.",
            "validity_rule": "terminal SOC error <= 0.01, traction shortage <= 1 W, motor/battery/MG violations <= 1 W or rpm, output-ramp violation <= 1 W.",
            "certification_rule": "All validity conditions plus zero MPC fallback and zero forecast ramp-envelope infeasibility.",
            "selection_rule": "Rank all-valid candidates on six development seeds; test two finalists on 14 disjoint holdout seeds.",
        },
        "development_seeds": list(DEVELOPMENT_SEEDS),
        "holdout_seeds": list(HOLDOUT_SEEDS),
        "development": development,
        "selected_residual_gains": [entry["residual_gain"] for entry in finalists],
        "holdout": holdout,
    }
    path = ROOT / "results" / "paper2_phase_preview_scan.json"
    path.write_text(json.dumps(output, ensure_ascii=False, indent=2), encoding="utf-8")
    print(path)


if __name__ == "__main__":
    main()
