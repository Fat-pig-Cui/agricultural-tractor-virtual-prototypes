"""Record a development-only pilot for the causal map-aware ECMS ablation."""
from __future__ import annotations

import json
import math
from pathlib import Path
import sys

ROOT = Path(__file__).parents[1]
sys.path[:0] = [str(ROOT / "code"), str(ROOT / "code" / "energy_management")]

from experiments import ExperimentConfig, run_definition
from os_ecvt_model import RealisticDieselMap, RealisticMotorMap

SEEDS = tuple(range(2060, 2066))
FACTORS = (1.5, 2.0, 2.5, 3.0, 3.5, 4.0, 4.5, 5.0)
BASE = {
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
        return {"n": 1, "mean": mean, "std": 0.0, "ci95_low": mean, "ci95_high": mean}
    std = (sum((value - mean) ** 2 for value in values) / (len(values) - 1)) ** 0.5
    half = 2.571 * std / math.sqrt(len(values))
    return {"n": len(values), "mean": mean, "std": std,
            "ci95_low": mean - half, "ci95_high": mean + half}


def main() -> None:
    baseline = {seed: run_definition("realistic_ool", ExperimentConfig(seed=seed, **BASE))
                for seed in SEEDS}
    output = []
    for factor in FACTORS:
        rows = []
        for seed in SEEDS:
            result = run_definition(
                "adaptive_ecms",
                ExperimentConfig(seed=seed, adaptive_ecms_equivalence_factor=factor, **BASE),
            )
            saving = None
            if result["valid"] and baseline[seed]["valid"]:
                saving = ((float(baseline[seed]["fuel_l"]) - float(result["fuel_l"]))
                          / float(baseline[seed]["fuel_l"]) * 100.0)
            rows.append({"seed": seed, "fuel_l": float(result["fuel_l"]),
                         "hard_valid": bool(result["valid"]),
                         "soc_error": float(result["soc_error"]),
                         "saving_pct": saving,
                         "max_shortage_w": float(result["max_shortage_w"]),
                         "max_battery_power_violation_w": float(result["max_battery_power_violation_w"]),
                         "max_engine_ramp_violation_w": float(result["max_engine_ramp_violation_w"])})
            print("ecms", factor, seed, result["valid"], f"{result['fuel_l']:.6f}", flush=True)
        savings = [float(row["saving_pct"]) for row in rows if row["saving_pct"] is not None]
        output.append({"equivalence_factor": factor, "rows": rows,
                       "hard_valid_rate": sum(bool(row["hard_valid"]) for row in rows) / len(rows),
                       "saving_pct": mean_ci(savings)})
    path = ROOT / "results" / "paper2_assumed_adaptive_ecms_pilot.json"
    path.write_text(json.dumps({
        "purpose": "Development-only causal map-aware ECMS pilot; no future demand information and no confirmatory claim.",
        "seeds": list(SEEDS), "factors": list(FACTORS),
        "shared_constraints": "Unchanged realistic OOL, 60 kW floor, 40 kW/s output ramp, SOC, traction, motor, battery-bus, MG, and speed screens.",
        "results": output,
    }, ensure_ascii=False, indent=2), encoding="utf-8")
    print(path)


if __name__ == "__main__":
    main()
