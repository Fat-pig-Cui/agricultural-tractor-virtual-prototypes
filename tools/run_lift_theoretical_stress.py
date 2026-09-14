"""Reproducible assumption-range and leakage-step screens for paper 1.

All cases are virtual-prototype experiments.  The one-at-a-time ranges are
stress-test settings, not measured distributions or a probabilistic coverage
claim.
"""
from __future__ import annotations

import argparse
import json
import math
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path[:0] = [str(ROOT / "code"), str(ROOT / "code" / "lift_control")]

from experiments import ExperimentConfig, run_definition

FULL_SEEDS = tuple(range(2026, 2046))
RANGE_SEEDS = tuple(range(2026, 2031))


def summary(values: list[float]) -> dict[str, float]:
    mean = sum(values) / len(values)
    std = (sum((value - mean) ** 2 for value in values) / (len(values) - 1)) ** 0.5
    half_width = 2.093 * std / math.sqrt(len(values))
    return {"n": len(values), "mean": mean, "std": std,
            "ci95_low": mean - half_width, "ci95_high": mean + half_width}


def evaluate(config: ExperimentConfig, seeds: tuple[int, ...]) -> dict[str, object]:
    rows = []
    for seed in seeds:
        result = run_definition("hybrid", config, seed=seed)
        rows.append({
            "seed": seed,
            "hold_started": bool(result["hold_started"]),
            "hold_drop_mm": (result["hold_drop_m"] or 0.0) * 1000.0,
            "rmse_mm": result["rmse_m"] * 1000.0,
            "terminal_error_mm": result["settling_error_m"] * 1000.0,
            "command_energy": result["command_energy"],
            "accumulator_valve_energy": result["acc_valve_energy"],
            "observer_coefficient_m3_s_pa": result["observer_final_coefficient_m3_s_pa"],
            "observer_detection_delay_s": result["observer_detection_delay_s"],
            "observer_updates": result["observer_update_count"],
            "hold_mode_counts": result["hold_mode_counts"],
        })
    modes = ("fine_trim", "lock", "accumulator")
    total_mode_steps = sum(sum(row["hold_mode_counts"].values()) for row in rows)
    delays = [row["observer_detection_delay_s"] for row in rows
              if row["observer_detection_delay_s"] is not None]
    return {
        "hold_entry_rate": sum(row["hold_started"] for row in rows) / len(rows),
        "hold_drop_mm": summary([row["hold_drop_mm"] for row in rows]),
        "rmse_mm": summary([row["rmse_mm"] for row in rows]),
        "terminal_error_mm": summary([row["terminal_error_mm"] for row in rows]),
        "command_energy": summary([row["command_energy"] for row in rows]),
        "accumulator_valve_energy": summary([row["accumulator_valve_energy"] for row in rows]),
        "observer_coefficient_m3_s_pa": summary([row["observer_coefficient_m3_s_pa"] for row in rows]),
        "observer_detection_delay_s": None if not delays else summary(delays),
        "hold_mode_fraction": {
            mode: (sum(row["hold_mode_counts"][mode] for row in rows) / total_mode_steps
                   if total_mode_steps else 0.0)
            for mode in modes
        },
        "rows": rows,
    }


RANGE_CASES = {
    "nominal": ExperimentConfig(),
    "mass_0p7x": ExperimentConfig(mass_scale=0.7),
    "mass_1p3x": ExperimentConfig(mass_scale=1.3),
    "viscous_0p7x": ExperimentConfig(viscous_scale=0.7),
    "viscous_1p3x": ExperimentConfig(viscous_scale=1.3),
    "stiffness_0p7x": ExperimentConfig(stiffness_scale=0.7),
    "stiffness_1p3x": ExperimentConfig(stiffness_scale=1.3),
    "position_noise_0p5x": ExperimentConfig(noise_scale=0.5),
    "position_noise_2p0x": ExperimentConfig(noise_scale=2.0),
    "leakage_0p5x": ExperimentConfig(leakage_scale=0.5),
    "leakage_2p0x": ExperimentConfig(leakage_scale=2.0),
    "leakage_5p0x": ExperimentConfig(leakage_scale=5.0),
    "accumulator_flow_0p5x_14kn": ExperimentConfig(accumulator_flow_scale=0.5, load_after_step_n=14000.0),
    "accumulator_flow_1p5x_14kn": ExperimentConfig(accumulator_flow_scale=1.5, load_after_step_n=14000.0),
}

STEP_CASES = {
    "leakage_step_1x_to_8x_observer": ExperimentConfig(
        leakage_step_time_s=60.0, leakage_step_multiplier=8.0),
    "leakage_step_1x_to_8x_nominal_prior": ExperimentConfig(
        leakage_step_time_s=60.0, leakage_step_multiplier=8.0,
        leakage_observer_enabled=False),
}


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--section", choices=("all", "ranges", "leakage-step"), default="all")
    args = parser.parse_args()
    output = ROOT / "results" / "lift_theoretical_stress.json"
    out = json.loads(output.read_text(encoding="utf-8")) if output.exists() else {
        "seeds": {
            "leakage_step_ablation": list(FULL_SEEDS),
            "one_at_a_time_ranges": list(RANGE_SEEDS),
        },
        "protocol": {
            "duration_s": 1800.0,
            "controller": "hybrid",
            "integration_step_s": 0.01,
            "range_interpretation": "One-at-a-time virtual stress settings over five fixed noise seeds; not calibrated uncertainty distributions or a probabilistic coverage claim.",
            "leakage_step_interpretation": "The pressure-transition estimator is evaluated only against the same virtual model used to generate the state transition.",
        },
    }
    if args.section in ("all", "ranges"):
        out["one_at_a_time_ranges"] = {}
        for name, config in RANGE_CASES.items():
            print(name, flush=True)
            out["one_at_a_time_ranges"][name] = evaluate(config, RANGE_SEEDS)
            output.write_text(json.dumps(out, ensure_ascii=False, indent=2), encoding="utf-8")
    if args.section in ("all", "leakage-step"):
        out["leakage_step_ablation"] = {}
        for name, config in STEP_CASES.items():
            print(name, flush=True)
            out["leakage_step_ablation"][name] = evaluate(config, FULL_SEEDS)
            output.write_text(json.dumps(out, ensure_ascii=False, indent=2), encoding="utf-8")
    output.write_text(json.dumps(out, ensure_ascii=False, indent=2), encoding="utf-8")
    print(output)


if __name__ == "__main__":
    main()
