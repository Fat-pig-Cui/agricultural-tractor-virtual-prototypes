"""Scan physical premise changes while retaining SOC and power constraints."""
from __future__ import annotations
import json
from pathlib import Path
import sys
import numpy as np
ROOT = Path(__file__).parents[1]
sys.path.insert(0, str(ROOT / "code")); sys.path.insert(0, str(ROOT / "code/energy_management"))
from experiments import run_definition, ExperimentConfig
from os_ecvt_model import RealisticDieselMap, RealisticMotorMap

cases = {
    "baseline_lowload022": dict(engine_low_load_efficiency=0.22),
    "lowload018": dict(engine_low_load_efficiency=0.18),
    "lowload015": dict(engine_low_load_efficiency=0.15),
    "lowload012": dict(engine_low_load_efficiency=0.12),
    "battery150kWh": dict(engine_low_load_efficiency=0.18, battery_capacity_wh=150000.0),
    "battery150kW": dict(engine_low_load_efficiency=0.18, battery_capacity_wh=150000.0,
                           battery_power_limit_w=150000.0, motor_peak_w=150000.0),
    "lowload_cycle": dict(engine_low_load_efficiency=0.18, profile_name="low_load_agri_workcycle"),
    "lowload_cycle_strong": dict(engine_low_load_efficiency=0.12, profile_name="low_load_agri_workcycle"),
}
common = dict(duration_s=60.0, profile_name="agri_workcycle", accessory_for_all_w=18000.0,
              mpc_terminal_weight=2000000.0)
out = {}
for name, overrides in cases.items():
    engine = RealisticDieselMap(low_load_efficiency=overrides.pop("engine_low_load_efficiency", 0.22),
                                power_width_w=90000.0)
    motor = RealisticMotorMap()
    cfg_kw = dict(common, engine_map=engine, motor_map=motor, **overrides)
    baseline = run_definition("realistic_ool", ExperimentConfig(**cfg_kw))
    rows = {}
    for controller in ("deterministic_mpc", "robust_mpc"):
        r = run_definition(controller, ExperimentConfig(**cfg_kw))
        saving = (baseline["fuel_l"] - r["fuel_l"]) / baseline["fuel_l"] * 100.0
        rows[controller] = {"fuel_l": float(r["fuel_l"]), "valid": bool(r["valid"]),
                            "saving_vs_realistic_ool_pct": float(saving),
                            "soc_error": float(r["soc_error"]),
                            "max_shortage_w": float(r["max_shortage_w"]),
                            "max_motor_power_violation_w": float(r["max_motor_power_violation_w"]),
                            "max_mg1_power_violation_w": float(r["max_mg1_power_violation_w"])}
    out[name] = {"config": {k: v for k, v in cfg_kw.items() if k not in ("engine_map", "motor_map")},
                 "baseline_fuel_l": float(baseline["fuel_l"]), "controllers": rows}
path = ROOT / "results/physical_premise_scan.json"
path.write_text(json.dumps(out, ensure_ascii=False, indent=2), encoding="utf-8")
print(path)
