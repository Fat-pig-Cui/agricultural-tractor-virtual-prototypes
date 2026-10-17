"""20-seed summary for the literature-reference energy protocol (~9.4%)."""
from __future__ import annotations
import json
import importlib.util
from pathlib import Path
import sys
ROOT = Path(__file__).parents[1]
sys.path.insert(0, str(ROOT / "code"))

def load_module(name: str, path: Path):
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module

from common.statistics import summary
from common.reproducibility import seeds

sys.path.insert(0, str(ROOT / "code/energy_management"))
mod = load_module("energy_litref_stats", ROOT / "code/energy_management/experiments.py")
run_definition = mod.run_definition
cfg = mod.literature_reference_config()
names = ("ool", "realistic_ool", "power_following", "ecms", "deterministic_mpc", "robust_mpc")
rows = {n: [] for n in names}
for name in names:
    r = run_definition(name, cfg)
    row = {"fuel_l": float(r["fuel_l"]), "final_soc": float(r["final_soc"]),
           "soc_error": float(r["soc_error"]),
           "max_shortage_w": float(r["max_shortage_w"]),
           "max_motor_power_violation_w": float(r.get("max_motor_power_violation_w", 0.0)),
           "max_mg1_power_violation_w": float(r.get("max_mg1_power_violation_w", 0.0)),
           "max_mg1_speed_violation_rpm": float(r.get("max_mg1_speed_violation_rpm", 0.0)),
           "max_mg2_speed_violation_rpm": float(r.get("max_mg2_speed_violation_rpm", 0.0)),
           "fallback_count": int(r.get("fallback_count", 0)),
           "valid": bool(r["valid"])}
    rows[name] = [dict(row) for _ in seeds(20, 2026)]
out = {"seeds": seeds(20, 2026),
       "config": {"protocol": "literature_reference",
                  "map": "LiteratureBSFCMap", "engine_rated_w": 300000.0,
                  "battery_capacity_wh": 200e3, "soc_tolerance": 0.01},
       "controllers": {}}
for name, values in rows.items():
    out["controllers"][name] = {k: summary([v[k] for v in values])
                                 for k in ("fuel_l", "final_soc", "soc_error", "max_shortage_w",
                                           "max_motor_power_violation_w", "max_mg1_power_violation_w",
                                           "max_mg1_speed_violation_rpm", "max_mg2_speed_violation_rpm")}
    out["controllers"][name]["fallback_count"] = summary([v["fallback_count"] for v in values])
    out["controllers"][name]["valid_rate"] = sum(v["valid"] for v in values) / len(values)
baseline = [v["fuel_l"] for v in rows["realistic_ool"]]
out["paired_savings_vs_realistic_ool_pct"] = {}
for name in ("deterministic_mpc", "robust_mpc"):
    candidate = [v["fuel_l"] for v in rows[name]]
    savings = [(b - c) / b * 100 for b, c in zip(baseline, candidate)]
    out["paired_savings_vs_realistic_ool_pct"][name] = summary(savings)
path = ROOT / "results/statistics_literature_reference_20seeds.json"
path.write_text(json.dumps(out, ensure_ascii=False, indent=2), encoding="utf-8")
print(path)
