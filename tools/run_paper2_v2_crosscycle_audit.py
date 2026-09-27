#!/usr/bin/env python3
"""Cross-cycle and action-grid audit for the frozen V2 energy manager."""
from __future__ import annotations

import json
import statistics
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path[:0] = [str(ROOT / "code"), str(ROOT / "code" / "energy_management")]

from common.profiles import (agri_workcycle_profile, high_variability_profile,
                             low_load_agri_workcycle_profile,
                             stochastic_agri_workcycle_profile)
from viability_ecms_v2 import ECMSSettings, PowerSplitParameters, run_cycle


SETTINGS = ECMSSettings(
    base_equivalence_factor=1.0,
    proportional_gain=60.0,
    viability_band_soc=0.045,
    terminal_soc_tolerance=1e-4,
)


def paired(points, params: PowerSplitParameters) -> dict[str, object]:
    try:
        baseline = run_cycle(points, "load_following", SETTINGS, params)
        proposed = run_cycle(points, "viability_ecms", SETTINGS, params)
    except RuntimeError as error:
        return {"valid": False, "reason": str(error)}
    raw = ((float(baseline["fuel_l"]) - float(proposed["fuel_l"]))
           / float(baseline["fuel_l"]) * 100.0)
    normalized = ((float(baseline["energy_normalized_fuel_l"])
                   - float(proposed["energy_normalized_fuel_l"]))
                  / float(baseline["energy_normalized_fuel_l"]) * 100.0)
    return {
        "valid": bool(baseline["strict_valid"] and proposed["strict_valid"]),
        "raw_saving_pct": raw,
        "energy_normalized_saving_pct": normalized,
        "baseline": baseline,
        "proposed": proposed,
    }


def compact(rows: list[dict[str, object]]) -> dict[str, object]:
    valid = [row for row in rows if bool(row.get("valid"))]
    savings = [float(row["energy_normalized_saving_pct"]) for row in valid]
    return {
        "count": len(rows),
        "valid_count": len(valid),
        "mean_energy_normalized_saving_pct": (
            statistics.fmean(savings) if savings else None),
        "minimum_energy_normalized_saving_pct": min(savings) if savings else None,
        "maximum_energy_normalized_saving_pct": max(savings) if savings else None,
    }


def main() -> None:
    params = PowerSplitParameters(engine_power_step_w=5000.0)
    deterministic = paired(agri_workcycle_profile(600.0, 1.0), params)
    low_load = paired(low_load_agri_workcycle_profile(600.0, 1.0), params)
    high_variability = paired(high_variability_profile(300.0, 1.0), params)
    stochastic_rows = []
    for seed in range(3160, 3180):
        row = paired(stochastic_agri_workcycle_profile(
            600.0, 1.0, seed=seed, disturbance_scale=1.0,
            smooth_disturbances=True), params)
        row["seed"] = seed
        stochastic_rows.append(row)

    grid_rows = []
    for spacing_w in (10_000.0, 5_000.0, 2_500.0):
        grid_params = PowerSplitParameters(engine_power_step_w=spacing_w)
        rows = []
        for seed in range(3180, 3186):
            row = paired(stochastic_agri_workcycle_profile(
                600.0, 1.0, seed=seed, disturbance_scale=1.0,
                smooth_disturbances=True), grid_params)
            row["seed"] = seed
            rows.append(row)
        grid_rows.append({
            "engine_power_step_w": spacing_w,
            "summary": compact(rows),
            "rows": rows,
        })

    output = {
        "purpose": "Frozen V2 cross-cycle and action-grid audit; no retuning.",
        "settings": SETTINGS.__dict__,
        "platform": params.__dict__,
        "crosscycle": {
            "deterministic_agri_workcycle": deterministic,
            "low_load_agri_workcycle": low_load,
            "high_variability": high_variability,
            "stochastic_new_seeds": {
                "summary": compact(stochastic_rows),
                "rows": stochastic_rows,
            },
        },
        "action_grid_convergence": grid_rows,
    }
    path = ROOT / "results" / "paper2_v2_crosscycle_audit.json"
    path.write_text(json.dumps(output, indent=2), encoding="utf-8")
    print(json.dumps({
        "deterministic": {key: deterministic.get(key) for key in (
            "valid", "energy_normalized_saving_pct")},
        "low_load": {key: low_load.get(key) for key in (
            "valid", "energy_normalized_saving_pct")},
        "high_variability": {key: high_variability.get(key) for key in (
            "valid", "energy_normalized_saving_pct", "reason")},
        "stochastic": compact(stochastic_rows),
        "grid": [{"step_w": row["engine_power_step_w"], **row["summary"]}
                 for row in grid_rows],
        "output": str(path),
    }, indent=2))


if __name__ == "__main__":
    main()
