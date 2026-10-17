"""Quantify disturbance magnitude and its effect on stochastic-cycle validity."""
from __future__ import annotations
import json
from pathlib import Path
import sys
import numpy as np

ROOT = Path(__file__).parents[1]
sys.path.insert(0, str(ROOT / "code")); sys.path.insert(0, str(ROOT / "code/energy_management"))
from common.profiles import agri_workcycle_profile, stochastic_agri_workcycle_profile
from experiments import run_definition, ExperimentConfig
from os_ecvt_model import OSECVTModel, RealisticDieselMap, RealisticMotorMap
from config.parameters import PowertrainParameters


def disturbance_metrics(scales=(0.25, 0.5, 1.0, 1.5), seeds=range(2026, 2046)):
    model = OSECVTModel(PowertrainParameters())
    nominal = agri_workcycle_profile(600.0)
    nominal_d = np.asarray([model.demand(p.speed_mps, p.draft_n * p.soil_factor, p.grade)
                            for p in nominal])
    out = {}
    for scale in scales:
        rows = []
        for seed in seeds:
            profile = stochastic_agri_workcycle_profile(600.0, seed=seed,
                                                        disturbance_scale=scale)
            demand = np.asarray([model.demand(p.speed_mps, p.draft_n * p.soil_factor, p.grade)
                                 for p in profile])
            rel = np.abs(demand - nominal_d) / np.maximum(nominal_d, 1.0)
            rows.append({"seed": seed, "mean_abs_relative": float(rel.mean()),
                         "p95_abs_relative": float(np.percentile(rel, 95)),
                         "max_abs_relative": float(rel.max()),
                         "p95_abs_delta_w": float(np.percentile(np.abs(demand - nominal_d), 95)),
                         "max_abs_delta_w": float(np.max(np.abs(demand - nominal_d)))})
        out[str(scale)] = {
            "mean_abs_relative": float(np.mean([r["mean_abs_relative"] for r in rows])),
            "p95_abs_relative_mean": float(np.mean([r["p95_abs_relative"] for r in rows])),
            "max_abs_relative_mean": float(np.mean([r["max_abs_relative"] for r in rows])),
            "p95_abs_delta_w_mean": float(np.mean([r["p95_abs_delta_w"] for r in rows])),
            "max_abs_delta_w_mean": float(np.mean([r["max_abs_delta_w"] for r in rows])),
            "rows": rows,
        }
    return out


def controller_sensitivity(scales=(0.0, 0.25, 0.5, 1.0, 1.5), seeds=range(2026, 2046)):
    names = ("realistic_ool", "deterministic_mpc", "robust_mpc")
    common = dict(profile_name="stochastic_agri_workcycle",
                  engine_map=RealisticDieselMap(low_load_efficiency=0.22, power_width_w=90000.0),
                  motor_map=RealisticMotorMap(), accessory_for_all_w=18000.0,
                  mpc_terminal_weight=2000000.0)
    out = {}
    for scale in scales:
        out[str(scale)] = {}
        for name in names:
            rows = []
            for seed in seeds:
                result = run_definition(name, ExperimentConfig(
                    seed=seed, stochastic_disturbance_scale=scale, **common))
                rows.append({"fuel_l": float(result["fuel_l"]),
                             "soc_error": float(result["soc_error"]),
                             "valid": bool(result["valid"]),
                             "max_shortage_w": float(result["max_shortage_w"])})
            out[str(scale)][name] = {
                "valid_rate": float(np.mean([r["valid"] for r in rows])),
                "mean_fuel_l": float(np.mean([r["fuel_l"] for r in rows])),
                "mean_soc_error": float(np.mean([r["soc_error"] for r in rows])),
                "mean_max_shortage_w": float(np.mean([r["max_shortage_w"] for r in rows])),
                "rows": rows,
            }
    return out


if __name__ == "__main__":
    result = {"seeds": list(range(2026, 2046)),
              "disturbance": disturbance_metrics(),
              "controller_sensitivity": controller_sensitivity()}
    path = ROOT / "results/stochastic_disturbance_sensitivity.json"
    path.write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")
    print(path)
