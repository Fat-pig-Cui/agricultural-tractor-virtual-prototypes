#!/usr/bin/env python3
"""Development and frozen stress audit for Paper 1 two-chamber V2."""
from __future__ import annotations

import json
import statistics
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path[:0] = [str(ROOT / "code"), str(ROOT / "code" / "lift_control")]

from lift_v2_experiment import LiftV2Config, run_lift_v2


CONTROLLERS = ("pid_lock", "smc_lock", "pid_accumulator", "observer_hybrid")


def summary(rows: list[dict[str, object]]) -> dict[str, object]:
    entered = [row for row in rows if bool(row["hold_started"])]
    drops = [float(row["hold_drop_mm"]) for row in entered
             if row["hold_drop_mm"] is not None]
    return {
        "count": len(rows),
        "hold_entry_count": len(entered),
        "pass_count": sum(
            bool(row["hold_started"])
            and float(row["hold_drop_mm"] or 1e9) <= 10.0
            and float(row["post_transition_max_abs_error_mm"]) <= 10.0
            and int(row["relief_activation_count"]) == 0
            for row in rows),
        "mean_hold_drop_mm": statistics.fmean(drops) if drops else None,
        "worst_hold_drop_mm": max(drops) if drops else None,
        "mean_post_transition_rmse_mm": statistics.fmean(
            float(row["post_transition_rmse_mm"]) for row in rows),
        "worst_post_transition_error_mm": max(
            float(row["post_transition_max_abs_error_mm"]) for row in rows),
        "mean_mode_switches": statistics.fmean(float(row["mode_switches"]) for row in rows),
        "mean_accumulator_oil_used_ml": statistics.fmean(
            float(row["accumulator_oil_used_ml"]) for row in rows),
        "peak_pressure_mpa": max(float(row["peak_pressure_mpa"]) for row in rows),
    }


def run_block(controller: str, seeds: range, config_overrides: dict[str, object]) -> dict[str, object]:
    rows = []
    for seed in seeds:
        row = run_lift_v2(controller, LiftV2Config(seed=seed, **config_overrides))
        rows.append(row)
    return {"summary": summary(rows), "rows": rows}


def main() -> None:
    development = {
        name: run_block(name, range(4100, 4105), {
            "duration_s": 300.0,
            "post_step_load_n": 14_000.0,
            "load_step_time_s": 60.0,
        }) for name in CONTROLLERS
    }
    holdout = {
        name: run_block(name, range(4120, 4140), {
            "duration_s": 1800.0,
            "post_step_load_n": 14_000.0,
            "load_step_time_s": 60.0,
        }) for name in CONTROLLERS
    }
    stress_cases = {
        "leakage_5x": {"leakage_scale": 5.0},
        "sensor_noise_2x": {"position_noise_scale": 2.0,
                            "pressure_noise_scale": 2.0},
        "accumulator_flow_0p5x": {"accumulator_flow_scale": 0.5},
        "position_bias_2mm": {"position_bias_m": 0.002},
        "pressure_bias_0p1mpa": {"pressure_bias_pa": 0.1e6},
    }
    stress = {
        case: run_block("observer_hybrid", range(4160, 4170), {
            "duration_s": 1800.0,
            "post_step_load_n": 14_000.0,
            "load_step_time_s": 60.0,
            **overrides,
        }) for case, overrides in stress_cases.items()
    }
    output = {
        "purpose": "Paper 1 two-chamber V2 end-to-end controller audit.",
        "boundary": "Parameterized theoretical plant; no hardware calibration claim.",
        "protocol": {
            "development_seeds": list(range(4100, 4105)),
            "holdout_seeds": list(range(4120, 4140)),
            "stress_seeds": list(range(4160, 4170)),
            "controller_access": "no true velocity, load, or leakage state",
        },
        "development": development,
        "holdout": holdout,
        "stress": stress,
    }
    path = ROOT / "results" / "paper1_two_chamber_v2.json"
    path.write_text(json.dumps(output, indent=2), encoding="utf-8")
    print(json.dumps({
        "development": {name: block["summary"] for name, block in development.items()},
        "holdout": {name: block["summary"] for name, block in holdout.items()},
        "stress": {name: block["summary"] for name, block in stress.items()},
        "output": str(path),
    }, indent=2))


if __name__ == "__main__":
    main()
