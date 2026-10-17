"""Cross-cycle terminal-SOC reserve scan without an offline cycle oracle.

This script evaluates a conservative online terminal-SOC target.  Validity is
always checked against the original initial SOC, so the reserve cannot mask a
battery-depletion result by changing the reported accounting criterion.
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

SEEDS = tuple(range(2026, 2046))
CONTROLLERS = ("deterministic_mpc", "robust_mpc")
RESERVES = (0.0, 0.0025, 0.0050, 0.0075, 0.0100)


def mean_ci(values: list[float]) -> dict[str, float]:
    mean = sum(values) / len(values)
    std = (sum((value - mean) ** 2 for value in values) / (len(values) - 1)) ** 0.5
    half_width = 2.093 * std / math.sqrt(len(values))
    return {"n": len(values), "mean": mean, "std": std,
            "ci95_low": mean - half_width, "ci95_high": mean + half_width}


def run_reserve(reserve: float) -> dict[str, object]:
    base = dict(
        duration_s=600.0,
        profile_name="stochastic_agri_workcycle",
        engine_map=LiteratureBSFCMap(),
        motor_map=RealisticMotorMap(),
        accessory_for_all_w=18000.0,
        mpc_terminal_weight=2000000.0,
        stochastic_disturbance_scale=0.25,
        stochastic_offline_reference=False,
        engine_rated_w=300000.0,
        battery_capacity_wh=200000.0,
        battery_power_limit_w=150000.0,
        motor_peak_w=150000.0,
        online_terminal_soc_reserve=reserve,
    )
    rows: dict[str, list[dict[str, object]]] = {name: [] for name in CONTROLLERS}
    baseline_rows = []
    for seed in SEEDS:
        baseline = run_definition("realistic_ool", ExperimentConfig(seed=seed, **base))
        baseline_rows.append(baseline)
        for controller in CONTROLLERS:
            result = run_definition(controller, ExperimentConfig(seed=seed, **base))
            rows[controller].append({
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
            })
        print(f"reserve={reserve:.4f}, seed={seed}", flush=True)
    summaries: dict[str, object] = {}
    for controller, values in rows.items():
        valid_savings = [
            (float(baseline["fuel_l"]) - float(row["fuel_l"])) / float(baseline["fuel_l"]) * 100.0
            for baseline, row in zip(baseline_rows, values)
            if baseline["valid"] and row["valid"]
        ]
        summaries[controller] = {
            "valid_rate": sum(row["valid"] for row in values) / len(values),
            "valid_runs": sum(row["valid"] for row in values),
            "fuel_l": mean_ci([float(row["fuel_l"]) for row in values]),
            "soc_error": mean_ci([float(row["soc_error"]) for row in values]),
            "fallback_count": mean_ci([float(row["fallback_count"]) for row in values]),
            "paired_saving_vs_realistic_ool_pct": mean_ci(valid_savings) if valid_savings else None,
        }
    return {"reserve_soc": reserve, "rows": rows, "summaries": summaries}


def main() -> None:
    output = {
        "seeds": list(SEEDS),
        "protocol": {
            "cycle": "stochastic_agri_workcycle",
            "duration_s": 600.0,
            "disturbance_scale": 0.25,
            "offline_soc_reference": False,
            "terminal_soc_tolerance": 0.01,
            "validity_target_soc": 0.55,
            "note": "The reserve alters online targeting only; validity remains relative to the initial SOC. Virtual-prototype result only.",
        },
        "reserves": [run_reserve(reserve) for reserve in RESERVES],
    }
    path = ROOT / "results" / "energy_terminal_reserve_scan.json"
    path.write_text(json.dumps(output, ensure_ascii=False, indent=2), encoding="utf-8")
    print(path)


if __name__ == "__main__":
    main()
