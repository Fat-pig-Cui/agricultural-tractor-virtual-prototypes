"""Fixed-controller efficiency-map sensitivity grid for paper 2.

The low-load efficiency is swept as a virtual model parameter.  Controller
settings and seeds are frozen; no result is used to tune a controller.
"""
from __future__ import annotations

import json
import math
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path[:0] = [str(ROOT / "code"), str(ROOT / "code" / "energy_management")]

from experiments import ExperimentConfig, run_definition
from os_ecvt_model import RealisticDieselMap, RealisticMotorMap

SEEDS = tuple(range(2260, 2280))
LOW_LOAD_LEVELS = (0.08, 0.12, 0.16, 0.20, 0.25, 0.30, 0.35)
ECMS_FACTOR = 2.0
T_975_BY_N = {2: 12.706, 3: 4.303, 4: 3.182, 5: 2.776, 6: 2.571,
              10: 2.262, 15: 2.145, 20: 2.093, 30: 2.045}


def mean_ci(values: list[float]) -> dict[str, float] | None:
    if not values:
        return None
    mean = sum(values) / len(values)
    std = (sum((value - mean) ** 2 for value in values) / max(1, len(values) - 1)) ** 0.5
    if len(values) not in T_975_BY_N:
        raise ValueError(f"Add a 95% two-sided t critical value for n={len(values)}")
    half = T_975_BY_N[len(values)] * std / math.sqrt(len(values)) if len(values) > 1 else 0.0
    return {"n": len(values), "mean": mean, "std": std,
            "ci95_low": mean - half, "ci95_high": mean + half}


def base(low_load_efficiency: float) -> dict[str, object]:
    return {
        "duration_s": 600.0,
        "profile_name": "stochastic_agri_workcycle",
        "engine_map": RealisticDieselMap(low_load_efficiency=low_load_efficiency,
                                          power_width_w=90000.0),
        "motor_map": RealisticMotorMap(),
        "accessory_for_all_w": 18000.0,
        "terminal_soc_tolerance": 1e-4,
        "terminal_soc_correction_gain": 3.0,
        "stochastic_disturbance_scale": 0.25,
        "stochastic_smooth_disturbances": True,
        "engine_rated_w": 300000.0,
        "battery_capacity_wh": 200000.0,
        "battery_power_limit_w": 150000.0,
        "motor_peak_w": 150000.0,
        "mpc_horizon": 8,
        "scenario_count": 5,
        "mpc_terminal_weight": 2000000.0,
        "stochastic_nominal_phase_preview": True,
        "stochastic_phase_residual_gain": 0.0,
    }


def run_case(low_load_efficiency: float, controller: str, seed: int,
             baseline: dict[str, object]) -> dict[str, object]:
    config = ExperimentConfig(seed=seed, **base(low_load_efficiency))
    overrides = {}
    if controller == "adaptive_ecms":
        overrides["adaptive_ecms_equivalence_factor"] = ECMS_FACTOR
    result = run_definition(controller, config if not overrides else
                            ExperimentConfig(seed=seed, **base(low_load_efficiency), **overrides))
    valid = bool(result["valid"]) and abs(float(result["soc_error"])) <= 1e-4
    certified = valid and int(result["fallback_count"]) == 0 and int(result["ramp_envelope_infeasibility_count"]) == 0
    saving = None
    if valid and bool(baseline["valid"]):
        saving = ((float(baseline["fuel_l"]) - float(result["fuel_l"]))
                  / float(baseline["fuel_l"]) * 100.0)
    return {
        "seed": seed,
        "fuel_l": float(result["fuel_l"]),
        "soc_error": float(result["soc_error"]),
        "strict_valid": valid,
        "certified": certified,
        "fallback_count": int(result["fallback_count"]),
        "ramp_envelope_infeasibility_count": int(result["ramp_envelope_infeasibility_count"]),
        "safety_filter_activation_count": int(result.get("safety_filter_activation_count", 0)),
        "saving_vs_same_seed_ool_pct": saving,
    }


def evaluate(low_load_efficiency: float) -> dict[str, object]:
    baselines = {}
    for seed in SEEDS:
        baselines[seed] = run_definition("realistic_ool",
                                         ExperimentConfig(seed=seed, **base(low_load_efficiency)))
    controllers = {}
    for controller in ("adaptive_ecms", "recursive_feasible_mpc"):
        rows = [run_case(low_load_efficiency, controller, seed, baselines[seed])
                for seed in SEEDS]
        savings = [float(row["saving_vs_same_seed_ool_pct"]) for row in rows
                    if row["saving_vs_same_seed_ool_pct"] is not None]
        controllers[controller] = {
            "strict_valid_rate": sum(bool(row["strict_valid"]) for row in rows) / len(rows),
            "certified_rate": sum(bool(row["certified"]) for row in rows) / len(rows),
            "saving_pct": mean_ci(savings),
            "mean_safety_filter_activation_count": sum(
                int(row["safety_filter_activation_count"]) for row in rows) / len(rows),
            "rows": rows,
        }
    return {"low_load_efficiency": low_load_efficiency, "controllers": controllers}


def main() -> None:
    cases = []
    for level in LOW_LOAD_LEVELS:
        cases.append(evaluate(level))
        print("map", level, flush=True)
    output = {
        "purpose": "Fixed-controller low-load efficiency-map sensitivity; theoretical virtual model only.",
        "seeds": list(SEEDS),
        "low_load_efficiency_levels": list(LOW_LOAD_LEVELS),
        "fixed_ecms_factor": ECMS_FACTOR,
        "controller_settings": "H=8, five scenarios, public nominal phase preview, terminal SOC 1e-4, shared 300 kW platform",
        "cases": cases,
    }
    path = ROOT / "results" / "paper2_map_sensitivity_grid.json"
    path.write_text(json.dumps(output, ensure_ascii=False, indent=2), encoding="utf-8")
    print(path)


if __name__ == "__main__":
    main()
