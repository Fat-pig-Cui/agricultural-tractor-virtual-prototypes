"""Quantify how realistic-OOL engineering limits affect baseline fuel."""
from __future__ import annotations
import json
from pathlib import Path
import sys
ROOT = Path(__file__).parents[1]
sys.path.insert(0, str(ROOT / "code")); sys.path.insert(0, str(ROOT / "code/energy_management"))
from experiments import run_definition, ExperimentConfig
from os_ecvt_model import RealisticDieselMap, RealisticMotorMap

common = dict(profile_name="agri_workcycle",
              engine_map=RealisticDieselMap(low_load_efficiency=0.22, power_width_w=90000.0),
              motor_map=RealisticMotorMap(), accessory_for_all_w=18000.0,
              mpc_terminal_weight=2000000.0)
cases = {
    "current_400kW_per_s": (40000.0, 60000.0),
    "40kW_per_s": (4000.0, 60000.0),
    "20kW_per_s": (2000.0, 60000.0),
    "40kW_per_s_min90": (4000.0, 90000.0),
    "40kW_per_s_min120": (4000.0, 120000.0),
}
out = {}
for name, (ramp, minimum) in cases.items():
    cfg = ExperimentConfig(realistic_ool_ramp_limit_w=ramp,
                           realistic_ool_minimum_engine_w=minimum, **common)
    r = run_definition("realistic_ool", cfg)
    out[name] = {"ramp_limit_w_per_s": ramp,
                 "ramp_limit_kw_per_s": ramp / 1000.0,
                 "minimum_engine_kw": minimum / 1000.0,
                 "fuel_l": float(r["fuel_l"]),
                 "final_soc": float(r["final_soc"]),
                 "valid": bool(r["valid"])}
path = ROOT / "results/ool_baseline_sensitivity.json"
path.write_text(json.dumps(out, ensure_ascii=False, indent=2), encoding="utf-8")
print(path)
