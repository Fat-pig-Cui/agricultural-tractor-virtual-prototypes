"""Minimal ablations for the lift-control manuscript."""
from __future__ import annotations
import json
from pathlib import Path
import sys
ROOT = Path(__file__).parents[1]
sys.path.insert(0, str(ROOT / "code")); sys.path.insert(0, str(ROOT / "code/lift_control"))
from experiments import run_definition, ExperimentConfig

cases = {
    "full_hybrid": ExperimentConfig(),
    "no_pressure_feedforward": ExperimentConfig(pressure_feedforward_enabled=False),
    "no_leakage_observer": ExperimentConfig(leakage_observer_enabled=False),
    "raw_velocity_gate": ExperimentConfig(filtered_velocity_gate_enabled=False),
    "high_leakage_10x": ExperimentConfig(leakage_scale=10.0),
    "no_hysteresis": ExperimentConfig(hold_supervisor_hysteresis=0.0),
    "no_accumulator": ExperimentConfig(accumulator_enabled=False),
    "noise_2x": ExperimentConfig(noise_scale=2.0),
    "load_step_14kn": ExperimentConfig(load_after_step_n=14000.0),
    "load_step_14kn_no_feedforward": ExperimentConfig(load_after_step_n=14000.0, load_feedforward_enabled=False),
    "load_step_14kn_no_acc_closed_loop": ExperimentConfig(load_after_step_n=14000.0, accumulator_closed_loop=False),
    "no_hold_structure": ExperimentConfig(hold_enabled=False),
    "no_hold_structure_leak_10x": ExperimentConfig(hold_enabled=False, leakage_scale=10.0),
    "leak_lock_10x": ExperimentConfig(leakage_scale=10.0, lock_valve_leakage_scale=10.0),
}
out = {}
for case, cfg in cases.items():
    rows = []
    for seed in range(2026, 2046):
        r = run_definition("hybrid", cfg, seed=seed)
        rows.append({"seed": seed, "rmse_mm": r["rmse_m"] * 1000,
                     "settling_error_mm": r["settling_error_m"] * 1000,
                     "hold_started": bool(r["hold_started"]),
                     "hold_start_time_s": r["hold_start_time_s"],
                     "hold_drop_mm": (r["hold_drop_m"] or 0.0) * 1000,
                     "max_velocity_mps": r["max_velocity_mps"],
                     "command_energy": r["command_energy"]})
    out[case] = {
        "hold_trigger_rate": sum(x["hold_started"] for x in rows) / len(rows),
        "mean_rmse_mm": sum(x["rmse_mm"] for x in rows) / len(rows),
        "mean_settling_error_mm": sum(x["settling_error_mm"] for x in rows) / len(rows),
        "mean_hold_drop_mm": sum(x["hold_drop_mm"] for x in rows) / len(rows),
        "max_hold_drop_mm": max(x["hold_drop_mm"] for x in rows),
        "mean_hold_start_time_s": sum(x["hold_start_time_s"] or 1800 for x in rows) / len(rows),
        "mean_max_velocity_mps": sum(x["max_velocity_mps"] for x in rows) / len(rows),
        "mean_command_energy": sum(x["command_energy"] for x in rows) / len(rows),
        "rows": rows,
    }
path = ROOT / "results/lift_ablation.json"
path.write_text(json.dumps(out, ensure_ascii=False, indent=2), encoding="utf-8")
print(path)
