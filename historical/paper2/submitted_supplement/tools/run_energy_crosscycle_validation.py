"""Twenty-seed cross-cycle validation for the energy-management submission draft."""
from __future__ import annotations

import json
import math
from pathlib import Path
import sys

ROOT = Path(__file__).parents[1]
sys.path[:0] = [str(ROOT / "code"), str(ROOT / "code" / "energy_management")]

from experiments import ExperimentConfig, run_definition
from os_ecvt_model import LiteratureBSFCMap, RealisticDieselMap, RealisticMotorMap

SEEDS = tuple(range(2026, 2046))
CONTROLLERS = ("realistic_ool", "deterministic_mpc", "robust_mpc")


def mean_ci(values: list[float]) -> dict[str, float]:
    mean = sum(values) / len(values)
    std = (sum((value - mean) ** 2 for value in values) / (len(values) - 1)) ** 0.5
    half_width = 2.093 * std / math.sqrt(len(values))
    return {"n": len(values), "mean": mean, "std": std,
            "ci95_low": mean - half_width, "ci95_high": mean + half_width}


def run_protocol(name: str, engine_map, engine_rated_w: float) -> dict[str, object]:
    rows: dict[str, list[dict[str, object]]] = {controller: [] for controller in CONTROLLERS}
    base = dict(
        duration_s=600.0,
        profile_name="stochastic_agri_workcycle",
        engine_map=engine_map,
        motor_map=RealisticMotorMap(),
        accessory_for_all_w=18000.0,
        mpc_terminal_weight=2000000.0,
        stochastic_disturbance_scale=0.25,
        stochastic_smooth_disturbances=True,
        stochastic_offline_reference=False,
        engine_rated_w=engine_rated_w,
        battery_capacity_wh=200000.0,
        battery_power_limit_w=150000.0,
        motor_peak_w=150000.0,
    )
    for seed in SEEDS:
        for controller in CONTROLLERS:
            result = run_definition(controller, ExperimentConfig(seed=seed, **base))
            rows[controller].append({
                "seed": seed,
                "fuel_l": float(result["fuel_l"]),
                "soc_error": float(result["soc_error"]),
                "valid": bool(result["valid"]),
                "max_shortage_w": float(result["max_shortage_w"]),
                "max_motor_power_violation_w": float(result["max_motor_power_violation_w"]),
                "max_battery_power_violation_w": float(result["max_battery_power_violation_w"]),
                "max_mg1_power_violation_w": float(result["max_mg1_power_violation_w"]),
                "max_mg1_speed_violation_rpm": float(result["max_mg1_speed_violation_rpm"]),
                "max_mg2_speed_violation_rpm": float(result["max_mg2_speed_violation_rpm"]),
                "fallback_count": int(result["fallback_count"]),
                "ramp_envelope_infeasibility_count": int(result["ramp_envelope_infeasibility_count"]),
                "max_engine_ramp_violation_w": float(result["max_engine_ramp_violation_w"]),
            })
        print(name, seed, flush=True)

    baseline = rows["realistic_ool"]
    summaries: dict[str, object] = {}
    for controller, values in rows.items():
        summaries[controller] = {
            "valid_rate": sum(row["valid"] for row in values) / len(values),
            "fuel_l": mean_ci([float(row["fuel_l"]) for row in values]),
            "soc_error": mean_ci([float(row["soc_error"]) for row in values]),
            "fallback_count": mean_ci([float(row["fallback_count"]) for row in values]),
        }
    savings: dict[str, object] = {}
    for controller in ("deterministic_mpc", "robust_mpc"):
        values = [
            (float(base_row["fuel_l"]) - float(candidate_row["fuel_l"]))
            / float(base_row["fuel_l"]) * 100.0
            for base_row, candidate_row in zip(baseline, rows[controller])
            if base_row["valid"] and candidate_row["valid"]
        ]
        savings[controller] = {
            "valid_pairs": len(values),
            "valid_pair_rate": len(values) / len(SEEDS),
            "saving_pct": mean_ci(values) if values else None,
        }
    return {"rows": rows, "summaries": summaries, "paired_savings_vs_realistic_ool": savings}


def main() -> None:
    output = {
        "seeds": list(SEEDS),
        "protocol": {
            "cycle": "stochastic_agri_workcycle",
            "duration_s": 600.0,
            "disturbance_scale": 0.25,
            "disturbance_evolution": "continuous interpolation between the same 10 s random-walk targets",
            "offline_soc_reference": False,
            "terminal_soc_tolerance": 0.01,
            "certification_rule": "All hard validity conditions plus zero fallback and zero forecast ramp-envelope infeasibility.",
            "note": "Cross-cycle virtual-prototype validation; not hardware validation.",
        },
        "assumed_efficiency_island": run_protocol(
            "assumed_efficiency_island", RealisticDieselMap(low_load_efficiency=0.08, power_width_w=90000.0), 260000.0),
        "literature_shaped_bsfc": run_protocol("literature_shaped_bsfc", LiteratureBSFCMap(), 300000.0),
    }
    path = ROOT / "results" / "energy_crosscycle_validation.json"
    path.write_text(json.dumps(output, ensure_ascii=False, indent=2), encoding="utf-8")
    print(path)


if __name__ == "__main__":
    main()
