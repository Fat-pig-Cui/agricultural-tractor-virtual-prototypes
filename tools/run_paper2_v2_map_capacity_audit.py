#!/usr/bin/env python3
"""Frozen V2 sensitivity to engine-map shape and battery capacity."""
from __future__ import annotations

import json
import statistics
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path[:0] = [str(ROOT / "code"), str(ROOT / "code" / "energy_management")]

from common.profiles import stochastic_agri_workcycle_profile
from os_ecvt_model import LiteratureBSFCMap, RealisticDieselMap, RealisticMotorMap
from viability_ecms_v2 import ECMSSettings, PowerSplitParameters, run_cycle


SEEDS = tuple(range(3200, 3220))
SETTINGS = ECMSSettings(
    base_equivalence_factor=1.0,
    proportional_gain=60.0,
    viability_band_soc=0.045,
    terminal_soc_tolerance=1e-4,
)


def points(seed: int):
    return stochastic_agri_workcycle_profile(
        600.0, 1.0, seed=seed, disturbance_scale=1.0,
        smooth_disturbances=True)


def evaluate(label: str, params: PowerSplitParameters, engine_map) -> dict[str, object]:
    rows = []
    for seed in SEEDS:
        try:
            baseline = run_cycle(points(seed), "load_following", SETTINGS, params,
                                 engine_map=engine_map, motor_map=RealisticMotorMap())
            proposed = run_cycle(points(seed), "viability_ecms", SETTINGS, params,
                                 engine_map=engine_map, motor_map=RealisticMotorMap())
        except RuntimeError as error:
            rows.append({"seed": seed, "valid": False,
                         "reason": str(error)})
            continue
        valid = bool(baseline["strict_valid"] and proposed["strict_valid"])
        normalized = ((float(baseline["energy_normalized_fuel_l"])
                       - float(proposed["energy_normalized_fuel_l"]))
                      / float(baseline["energy_normalized_fuel_l"]) * 100.0)
        rows.append({"seed": seed, "valid": valid,
                     "saving_pct": normalized,
                     "proposed": proposed, "baseline": baseline})
    valid_rows = [row for row in rows if row["valid"]]
    savings = [float(row["saving_pct"]) for row in valid_rows]
    return {
        "label": label,
        "valid_count": len(valid_rows),
        "count": len(rows),
        "mean_saving_pct": statistics.fmean(savings) if savings else None,
        "minimum_saving_pct": min(savings) if savings else None,
        "maximum_saving_pct": max(savings) if savings else None,
        "mean_shield_activations": statistics.fmean(
            float(row["proposed"]["shield_activations"]) for row in valid_rows)
            if valid_rows else None,
        "rows": rows,
    }


def main() -> None:
    base_params = PowerSplitParameters(engine_power_step_w=5000.0)
    maps = {
        "literature_shape": LiteratureBSFCMap(
            peak=0.42, rated_power_w=base_params.engine_rated_w),
        "low_load_015": RealisticDieselMap(
            low_load_efficiency=0.15),
        "low_load_025": RealisticDieselMap(
            low_load_efficiency=0.25),
        "low_load_035": RealisticDieselMap(
            low_load_efficiency=0.35),
    }
    map_rows = [evaluate(label, base_params, engine_map)
                for label, engine_map in maps.items()]
    capacity_rows = []
    for capacity in (120_000.0, 200_000.0, 280_000.0):
        params = PowerSplitParameters(engine_power_step_w=5000.0,
                                      battery_capacity_wh=capacity)
        capacity_rows.append(evaluate(f"capacity_{int(capacity / 1000)}kWh",
                                      params, maps["literature_shape"]))
    output = {
        "purpose": "Frozen V2 map and battery-capacity audit; no retuning.",
        "seeds": list(SEEDS),
        "settings": SETTINGS.__dict__,
        "map_sensitivity": map_rows,
        "capacity_sensitivity": capacity_rows,
    }
    path = ROOT / "results" / "paper2_v2_map_capacity_audit.json"
    path.write_text(json.dumps(output, indent=2), encoding="utf-8")
    print(json.dumps({
        "map_sensitivity": [{key: row[key] for key in (
            "label", "valid_count", "mean_saving_pct", "minimum_saving_pct", "maximum_saving_pct")}
            for row in map_rows],
        "capacity_sensitivity": [{key: row[key] for key in (
            "label", "valid_count", "mean_saving_pct", "minimum_saving_pct", "maximum_saving_pct")}
            for row in capacity_rows],
        "output": str(path),
    }, indent=2))


if __name__ == "__main__":
    main()
