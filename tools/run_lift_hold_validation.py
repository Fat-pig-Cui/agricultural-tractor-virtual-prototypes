"""Validate lift hold entry with raw/filtered velocity and lock leakage."""
from __future__ import annotations
import json
from pathlib import Path
import sys
ROOT = Path(__file__).parents[1]
sys.path.insert(0, str(ROOT / "code")); sys.path.insert(0, str(ROOT / "code/lift_control"))
from experiments import run_definition, ExperimentConfig

cases = {
    "filtered_gate_no_lock_leak": ExperimentConfig(),
    "raw_gate_no_lock_leak": ExperimentConfig(filtered_velocity_gate_enabled=False),
    "filtered_gate_lock_leak_0.5x": ExperimentConfig(lock_valve_leakage_scale=0.5),
    "filtered_gate_lock_leak_1x": ExperimentConfig(lock_valve_leakage_scale=1.0),
    "filtered_gate_lock_leak_2x": ExperimentConfig(lock_valve_leakage_scale=2.0),
    "filtered_gate_lock_leak_5x": ExperimentConfig(lock_valve_leakage_scale=5.0),
    "filtered_gate_lock_leak_10x": ExperimentConfig(lock_valve_leakage_scale=10.0),
}
out = {}
for name, cfg in cases.items():
    rows = []
    for seed in range(2026, 2046):
        r = run_definition("hybrid", cfg, seed=seed)
        rows.append({"seed": seed, "hold_started": bool(r["hold_started"]),
                     "hold_start_time_s": r["hold_start_time_s"],
                     "hold_drop_mm": (r["hold_drop_m"] or 0.0) * 1000,
                     "settling_error_mm": r["settling_error_m"] * 1000,
                     "max_velocity_mps": r["max_velocity_mps"]})
    out[name] = {
        "hold_trigger_rate": sum(r["hold_started"] for r in rows) / len(rows),
        "mean_hold_drop_mm": sum(r["hold_drop_mm"] for r in rows) / len(rows),
        "max_hold_drop_mm": max(r["hold_drop_mm"] for r in rows),
        "mean_settling_error_mm": sum(r["settling_error_mm"] for r in rows) / len(rows),
        "rows": rows,
    }
path = ROOT / "results/lift_hold_validation.json"
path.write_text(json.dumps(out, ensure_ascii=False, indent=2), encoding="utf-8")
print(path)
