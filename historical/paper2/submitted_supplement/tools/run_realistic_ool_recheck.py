"""Long-horizon recheck of a less-ideal tractor OOL baseline.

This is a premise/sensitivity experiment, not a replacement for the nominal
benchmark.  It keeps the fair accessory load and all existing validity checks
and varies only the baseline's minimum stable engine power and low-load map.
"""
from __future__ import annotations
import json
from pathlib import Path
import sys

ROOT = Path(__file__).parents[1]
sys.path[:0] = [str(ROOT / "code"), str(ROOT / "code/energy_management")]
from experiments import ExperimentConfig, run_definition
from os_ecvt_model import RealisticDieselMap, RealisticMotorMap


def main() -> None:
    rows = []
    for minimum in (60_000.0, 80_000.0, 100_000.0, 120_000.0):
        for low_load_eff in (0.22, 0.18):
            cfg = ExperimentConfig(
                duration_s=600.0,
                profile_name="low_load_agri_workcycle",
                accessory_for_all_w=18_000.0,
                mpc_terminal_weight=2_000_000.0,
                realistic_ool_minimum_engine_w=minimum,
                realistic_ool_ramp_limit_w=40_000.0,
                engine_map=RealisticDieselMap(
                    low_load_efficiency=low_load_eff, power_width_w=90_000.0),
                motor_map=RealisticMotorMap(),
            )
            baseline = run_definition("realistic_ool", cfg)
            result = {"minimum_engine_kw": minimum / 1000.0,
                      "low_load_efficiency": low_load_eff,
                      "baseline_fuel_l": baseline["fuel_l"],
                      "baseline_valid": baseline["valid"]}
            for name in ("deterministic_mpc", "robust_mpc"):
                r = run_definition(name, cfg)
                result[name] = {
                    "fuel_l": r["fuel_l"], "valid": r["valid"],
                    "saving_pct": (baseline["fuel_l"] - r["fuel_l"])
                    / baseline["fuel_l"] * 100.0,
                    "soc_error": r["soc_error"],
                    "max_shortage_w": r["max_shortage_w"],
                    "max_motor_power_violation_w": r["max_motor_power_violation_w"],
                    "max_mg1_power_violation_w": r["max_mg1_power_violation_w"],
                    "max_mg1_speed_violation_rpm": r["max_mg1_speed_violation_rpm"],
                    "max_mg2_speed_violation_rpm": r["max_mg2_speed_violation_rpm"],
                }
            rows.append(result)
            print(json.dumps(result, ensure_ascii=False), flush=True)
    out = ROOT / "results/realistic_ool_recheck.json"
    out.write_text(json.dumps(rows, ensure_ascii=False, indent=2), encoding="utf-8")
    print(out)


if __name__ == "__main__":
    main()
