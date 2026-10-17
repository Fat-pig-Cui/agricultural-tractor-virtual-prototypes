"""Twenty-seed stochastic agricultural-cycle robustness and timing report."""
from __future__ import annotations
import json
import time
from pathlib import Path
import sys
ROOT = Path(__file__).parents[1]
sys.path.insert(0, str(ROOT / "code")); sys.path.insert(0, str(ROOT / "code/energy_management"))
from experiments import run_definition, ExperimentConfig
from os_ecvt_model import RealisticDieselMap, RealisticMotorMap

def main():
    names = ("realistic_ool", "deterministic_mpc", "robust_mpc")
    rows = {n: [] for n in names}
    cfg_base = dict(profile_name="stochastic_agri_workcycle",
                    engine_map=RealisticDieselMap(low_load_efficiency=0.22, power_width_w=90000.0),
                    motor_map=RealisticMotorMap(), accessory_for_all_w=18000.0,
                    mpc_terminal_weight=2000000.0)
    for seed in range(2026, 2046):
        for name in names:
            t0 = time.perf_counter()
            r = run_definition(name, ExperimentConfig(seed=seed, **cfg_base))
            elapsed = time.perf_counter() - t0
            rows[name].append({"fuel_l": float(r["fuel_l"]), "soc_error": float(r["soc_error"]),
                               "valid": bool(r["valid"]), "max_shortage_w": float(r["max_shortage_w"]),
                               "max_mg1_power_violation_w": float(r["max_mg1_power_violation_w"]),
                               "max_mg1_speed_violation_rpm": float(r["max_mg1_speed_violation_rpm"]),
                               "max_mg2_speed_violation_rpm": float(r["max_mg2_speed_violation_rpm"]),
                               "runtime_s": elapsed,
                               "sample_period_s": 0.1})
    out = {"seeds": list(range(2026, 2046)), "controllers": rows}
    path = ROOT / "results/stochastic_energy_20seeds.json"
    path.write_text(json.dumps(out, ensure_ascii=False, indent=2), encoding="utf-8")
    print(path)
if __name__ == "__main__": main()
