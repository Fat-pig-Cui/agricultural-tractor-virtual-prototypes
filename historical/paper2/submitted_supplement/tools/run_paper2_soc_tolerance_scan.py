"""Sensitivity of strict causal energy-management results to terminal SOC tolerance."""
from __future__ import annotations

import json
import math
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path[:0] = [str(ROOT / "code"), str(ROOT / "code" / "energy_management")]

from experiments import ExperimentConfig, run_definition
from os_ecvt_model import LiteratureBSFCMap, RealisticMotorMap

SEEDS = tuple(range(2280, 2300))
TOLERANCES = (1e-4, 5e-4, 1e-3)
CONTROLLERS = ("adaptive_ecms", "recursive_feasible_mpc")
T_975_19 = 2.093


def mean_ci(values: list[float]) -> dict[str, float] | None:
    if not values:
        return None
    mean = sum(values) / len(values)
    std = (sum((value - mean) ** 2 for value in values) / max(1, len(values) - 1)) ** 0.5
    half = T_975_19 * std / math.sqrt(len(values)) if len(values) > 1 else 0.0
    return {"n": len(values), "mean": mean, "std": std,
            "ci95_low": mean - half, "ci95_high": mean + half}


def base(tolerance: float) -> dict[str, object]:
    return {
        "duration_s": 600.0,
        "profile_name": "stochastic_agri_workcycle",
        "engine_map": LiteratureBSFCMap(),
        "motor_map": RealisticMotorMap(),
        "accessory_for_all_w": 18000.0,
        "terminal_soc_tolerance": tolerance,
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


def evaluate(tolerance: float) -> dict[str, object]:
    configs = {seed: ExperimentConfig(seed=seed, **base(tolerance)) for seed in SEEDS}
    baselines = {seed: run_definition("realistic_ool", config)
                 for seed, config in configs.items()}
    output: dict[str, object] = {"terminal_soc_tolerance": tolerance,
                                 "controllers": {}}
    for controller in CONTROLLERS:
        rows = []
        for seed in SEEDS:
            config = configs[seed]
            overrides = {"adaptive_ecms_equivalence_factor": 2.0} if controller == "adaptive_ecms" else {}
            result = run_definition(controller,
                                    ExperimentConfig(**{**base(tolerance), "seed": seed, **overrides}))
            baseline = baselines[seed]
            valid = bool(result["valid"]) and abs(float(result["soc_error"])) <= tolerance
            certified = (valid and int(result["fallback_count"]) == 0
                         and int(result["ramp_envelope_infeasibility_count"]) == 0)
            rows.append({
                "seed": seed,
                "fuel_l": float(result["fuel_l"]),
                "soc_error": float(result["soc_error"]),
                "strict_valid": valid,
                "certified": certified,
                "fallback_count": int(result["fallback_count"]),
                "ramp_envelope_infeasibility_count": int(result["ramp_envelope_infeasibility_count"]),
                "saving_vs_same_seed_ool_pct": (
                    (float(baseline["fuel_l"]) - float(result["fuel_l"]))
                    / float(baseline["fuel_l"]) * 100.0
                    if bool(baseline["valid"]) and valid else None),
            })
        savings = [float(row["saving_vs_same_seed_ool_pct"]) for row in rows
                   if row["saving_vs_same_seed_ool_pct"] is not None]
        output["controllers"][controller] = {
            "strict_valid_rate": sum(bool(row["strict_valid"]) for row in rows) / len(rows),
            "certified_rate": sum(bool(row["certified"]) for row in rows) / len(rows),
            "saving_pct": mean_ci(savings),
            "rows": rows,
        }
    return output


def main() -> None:
    result = {
        "purpose": "Terminal-SOC tolerance sensitivity under a fixed strictly causal virtual protocol.",
        "seeds": list(SEEDS),
        "tolerances": list(TOLERANCES),
        "controller_settings": "LiteratureBSFCMap, H=8, five scenarios, public nominal phase preview, shared 300 kW platform",
        "cases": [evaluate(tolerance) for tolerance in TOLERANCES],
    }
    path = ROOT / "results" / "paper2_soc_tolerance_scan.json"
    path.write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")
    print(path)


if __name__ == "__main__":
    main()
