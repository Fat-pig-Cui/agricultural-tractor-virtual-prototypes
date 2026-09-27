#!/usr/bin/env python3
"""Independent nominal and stress audit for the frozen Paper 1 V2 controller."""
from __future__ import annotations

import json
import statistics
import sys
from dataclasses import asdict
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path[:0] = [str(ROOT / "code"), str(ROOT / "code" / "lift_control")]

from lift_v2_experiment import LiftV2Config, run_lift_v2


def summarize(rows: list[dict[str, object]]) -> dict[str, object]:
    passed = [row for row in rows if bool(row["pass_screen"])]
    drops = [float(row["hold_drop_mm"]) for row in rows]
    errors = [float(row["post_transition_max_abs_error_mm"]) for row in rows]
    return {
        "count": len(rows),
        "pass_count": len(passed),
        "pass_rate": len(passed) / max(1, len(rows)),
        "mean_hold_drop_mm": statistics.fmean(drops),
        "worst_hold_drop_mm": max(drops),
        "mean_post_transition_max_abs_error_mm": statistics.fmean(errors),
        "worst_post_transition_max_abs_error_mm": max(errors),
        "mean_mode_switches": statistics.fmean(float(row["mode_switches"]) for row in rows),
        "mean_accumulator_oil_used_ml": statistics.fmean(
            float(row["accumulator_oil_used_ml"]) for row in rows),
    }


def run_group(label: str, seeds: range, **config_overrides: object) -> dict[str, object]:
    rows = []
    for seed in seeds:
        config = LiftV2Config(seed=seed, duration_s=1800.0, **config_overrides)
        result = run_lift_v2("observer_hybrid", config)
        result["pass_screen"] = bool(
            result["hold_started"]
            and float(result["hold_drop_mm"]) <= 10.0
            and float(result["post_transition_max_abs_error_mm"]) <= 10.0
            and int(result["relief_activation_count"]) == 0
        )
        result["group"] = label
        rows.append(result)
    return {"summary": summarize(rows), "rows": rows}


def main() -> None:
    groups = {
        "nominal_new_seeds": run_group("nominal_new_seeds", range(4200, 4220)),
        "five_times_leakage": run_group(
            "five_times_leakage", range(4220, 4230), leakage_scale=5.0),
        "doubled_sensor_noise": run_group(
            "doubled_sensor_noise", range(4230, 4240),
            position_noise_scale=2.0, pressure_noise_scale=2.0),
        "half_accumulator_flow": run_group(
            "half_accumulator_flow", range(4240, 4250),
            accumulator_flow_scale=0.5),
    }
    output = {
        "purpose": "Independent post-freeze audit; seeds and groups were not used for supervisor selection.",
        "model_boundary": "Parameterized theoretical two-chamber virtual prototype; no hardware calibration.",
        "pass_screen": "hold entry, <=10 mm hold drop, <=10 mm post-transition error, zero relief activation",
        "controller": "observer_hybrid",
        "config": asdict(LiftV2Config()),
        "groups": groups,
    }
    path = ROOT / "results" / "paper1_v2_independent_audit.json"
    path.write_text(json.dumps(output, indent=2), encoding="utf-8")
    print(json.dumps({label: group["summary"] for label, group in groups.items()}, indent=2))
    print(path)


if __name__ == "__main__":
    main()
