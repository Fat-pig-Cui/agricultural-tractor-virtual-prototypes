"""Screen the admissible electrical-power boundary of the high-variability cycle.

This is a predeclared platform-capability audit, not a controller-tuning
experiment.  The cycle, map, information set, terminal-SOC rule, and seed set
are frozen; only the paired motor and battery-bus power limit is changed.
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

SEEDS = tuple(range(2300, 2312))
POWER_LIMITS_W = (150000.0, 175000.0, 200000.0, 225000.0)
CONTROLLERS = ("realistic_ool", "adaptive_ecms", "recursive_feasible_mpc")


def mean_ci(values: list[float]) -> dict[str, float] | None:
    if not values:
        return None
    mean = sum(values) / len(values)
    if len(values) == 1:
        return {"n": 1, "mean": mean, "std": 0.0,
                "ci95_low": mean, "ci95_high": mean}
    std = (sum((value - mean) ** 2 for value in values) / (len(values) - 1)) ** 0.5
    half = 2.201 * std / math.sqrt(len(values))
    return {"n": len(values), "mean": mean, "std": std,
            "ci95_low": mean - half, "ci95_high": mean + half}


def base(power_limit_w: float) -> dict[str, object]:
    return {
        "duration_s": 300.0,
        "profile_name": "high_variability",
        "engine_map": LiteratureBSFCMap(),
        "motor_map": RealisticMotorMap(),
        "accessory_for_all_w": 18000.0,
        "terminal_soc_tolerance": 1e-4,
        "terminal_soc_correction_gain": 3.0,
        "stochastic_offline_reference": False,
        "stochastic_nominal_reference": False,
        "stochastic_nominal_phase_preview": False,
        "stochastic_phase_residual_gain": 0.0,
        "use_offline_soc_reference": False,
        "engine_rated_w": 300000.0,
        "battery_capacity_wh": 200000.0,
        "battery_power_limit_w": power_limit_w,
        "motor_peak_w": power_limit_w,
        "mpc_horizon": 8,
        "scenario_count": 5,
        "mpc_terminal_weight": 2000000.0,
    }


def strict_valid(result: dict[str, object]) -> bool:
    return bool(result["valid"]) and abs(float(result["soc_error"])) <= 1e-4


def run_limit(power_limit_w: float) -> dict[str, object]:
    rows: dict[str, list[dict[str, object]]] = {name: [] for name in CONTROLLERS}
    configs = base(power_limit_w)
    for seed in SEEDS:
        baseline = None
        for controller in CONTROLLERS:
            result = run_definition(controller, ExperimentConfig(seed=seed, **configs))
            valid = strict_valid(result)
            row = {
                "seed": seed,
                "fuel_l": float(result["fuel_l"]),
                "strict_valid": valid,
                "soc_error": float(result["soc_error"]),
                "max_battery_power_violation_w": float(result["max_battery_power_violation_w"]),
                "max_motor_power_violation_w": float(result["max_motor_power_violation_w"]),
                "max_shortage_w": float(result["max_shortage_w"]),
                "fallback_count": int(result["fallback_count"]),
                "terminal_set_violation_count": int(result.get("terminal_set_violation_count", 0)),
            }
            if controller == "realistic_ool":
                baseline = row
            else:
                row["saving_vs_ool_pct"] = (
                    (float(baseline["fuel_l"]) - float(row["fuel_l"]))
                    / float(baseline["fuel_l"]) * 100.0)
            rows[controller].append(row)
        print(int(power_limit_w / 1000), seed, flush=True)
    summaries = {}
    for controller, values in rows.items():
        savings = [float(row["saving_vs_ool_pct"]) for row in values
                   if "saving_vs_ool_pct" in row and row["strict_valid"]]
        summaries[controller] = {
            "strict_valid_rate": sum(bool(row["strict_valid"]) for row in values) / len(values),
            "mean_max_battery_power_violation_kw": mean_ci(
                [float(row["max_battery_power_violation_w"]) / 1000.0 for row in values]),
            "worst_max_battery_power_violation_kw": max(
                float(row["max_battery_power_violation_w"]) for row in values) / 1000.0,
            "mean_max_motor_power_violation_kw": mean_ci(
                [float(row["max_motor_power_violation_w"]) / 1000.0 for row in values]),
            "mean_max_shortage_kw": mean_ci(
                [float(row["max_shortage_w"]) / 1000.0 for row in values]),
            "saving_pct_on_strict_valid_pairs": mean_ci(savings),
        }
    return {"power_limit_w": power_limit_w, "rows": rows, "summaries": summaries}


def main() -> None:
    output = {
        "seeds": list(SEEDS),
        "protocol": {
            "profile": "high_variability",
            "duration_s": 300.0,
            "map": "LiteratureBSFCMap",
            "paired_motor_and_battery_bus_limit_w": list(POWER_LIMITS_W),
            "terminal_soc_tolerance": 1e-4,
            "information_set": "causal present demand and current SOC; no offline reference",
            "selection_rule": "No controller or power limit is selected from the results; this is an admissible-demand boundary screen.",
            "note": "Changing power limits changes virtual platform capability and is not evidence for a target tractor.",
        },
        "limits": {str(int(limit / 1000)): run_limit(limit) for limit in POWER_LIMITS_W},
    }
    path = ROOT / "results" / "paper2_high_variability_power_boundary.json"
    path.write_text(json.dumps(output, ensure_ascii=False, indent=2), encoding="utf-8")
    print(path)


if __name__ == "__main__":
    main()
