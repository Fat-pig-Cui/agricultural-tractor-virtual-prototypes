#!/usr/bin/env python3
"""Scan mode dwell/hysteresis settings on development seeds only."""
from __future__ import annotations

import json
import statistics
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path[:0] = [str(ROOT / "code"), str(ROOT / "code" / "lift_control")]

from lift_v2_experiment import LiftV2Config, run_lift_v2


def main() -> None:
    candidates = []
    for dwell in (4.0, 8.0, 12.0):
        for accumulator_error in (0.0025, 0.004, 0.006):
            for pressure_deficit in (0.18e6, 0.30e6, 0.45e6):
                rows = [run_lift_v2("observer_hybrid", LiftV2Config(
                    seed=seed, duration_s=300.0, post_step_load_n=14_000.0,
                    load_step_time_s=60.0, mode_dwell_s=dwell,
                    accumulator_error_m=accumulator_error,
                    accumulator_pressure_deficit_pa=pressure_deficit,
                )) for seed in range(4100, 4105)]
                passed = [row for row in rows
                          if row["hold_started"]
                          and float(row["hold_drop_mm"] or 1e9) <= 10.0
                          and float(row["post_transition_max_abs_error_mm"]) <= 10.0
                          and int(row["relief_activation_count"]) == 0]
                candidates.append({
                    "dwell_s": dwell,
                    "accumulator_error_m": accumulator_error,
                    "accumulator_pressure_deficit_pa": pressure_deficit,
                    "pass_count": len(passed),
                    "mean_accumulator_oil_used_ml": statistics.fmean(
                        float(row["accumulator_oil_used_ml"]) for row in rows),
                    "mean_mode_switches": statistics.fmean(
                        float(row["mode_switches"]) for row in rows),
                    "mean_hold_drop_mm": statistics.fmean(
                        float(row["hold_drop_mm"] or 999.0) for row in rows),
                    "worst_post_transition_error_mm": max(
                        float(row["post_transition_max_abs_error_mm"]) for row in rows),
                })
    selected = min(candidates, key=lambda row: (
        -row["pass_count"], row["mean_accumulator_oil_used_ml"],
        row["mean_mode_switches"], row["mean_hold_drop_mm"]))
    output = {"purpose": "Development-only V2 mode-switch scan.",
              "candidates": candidates, "selected": selected}
    path = ROOT / "results" / "paper1_v2_mode_scan.json"
    path.write_text(json.dumps(output, indent=2), encoding="utf-8")
    print(json.dumps(output, indent=2))


if __name__ == "__main__":
    main()
