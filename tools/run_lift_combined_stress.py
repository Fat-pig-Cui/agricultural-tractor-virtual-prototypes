"""Cartesian virtual stress surface for the paper-1 hitch controller.

The factors are deliberately researcher-defined virtual perturbations.  This
screen is a deterministic coverage exercise, not a probability distribution or
an uncertainty estimate for a physical hitch.
"""
from __future__ import annotations

import itertools
import json
import math
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path[:0] = [str(ROOT / "code"), str(ROOT / "code" / "lift_control")]

from experiments import ExperimentConfig, run_definition

SEEDS = tuple(range(2026, 2046))
T_975_BY_N = {2: 12.706, 3: 4.303, 4: 3.182, 5: 2.776, 6: 2.571,
              10: 2.262, 15: 2.145, 20: 2.093, 30: 2.045}
FACTORS = {
    "mass_scale": (0.7, 1.3),
    "leakage_scale": (1.0, 5.0),
    "temperature_c": (25.0, 50.0),
    "load_after_step_n": (7000.0, 14000.0),
    "accumulator_flow_scale": (0.5, 1.0),
}


def ci(values: list[float]) -> dict[str, float]:
    mean = sum(values) / len(values)
    std = (sum((value - mean) ** 2 for value in values) / max(1, len(values) - 1)) ** 0.5
    if len(values) not in T_975_BY_N:
        raise ValueError(f"Add a 95% two-sided t critical value for n={len(values)}")
    half = T_975_BY_N[len(values)] * std / math.sqrt(len(values)) if len(values) > 1 else 0.0
    return {"n": len(values), "mean": mean, "std": std,
            "ci95_low": mean - half, "ci95_high": mean + half}


def evaluate(values: tuple[float, ...]) -> dict[str, object]:
    mass, leakage, temperature, load, accumulator = values
    config = ExperimentConfig(
        mass_scale=mass,
        leakage_scale=leakage,
        temperature_start_c=temperature,
        temperature_end_c=temperature,
        load_after_step_n=load,
        accumulator_flow_scale=accumulator,
    )
    rows = []
    for seed in SEEDS:
        result = run_definition("hybrid", config, seed=seed)
        drop_mm = (result["hold_drop_m"] or 0.0) * 1000.0
        rows.append({
            "seed": seed,
            "hold_started": bool(result["hold_started"]),
            "hold_drop_mm": drop_mm,
            "rmse_mm": result["rmse_m"] * 1000.0,
            "terminal_error_mm": result["settling_error_m"] * 1000.0,
            "pass_10mm_screen": bool(result["hold_started"]) and drop_mm <= 10.0,
        })
    drops = [float(row["hold_drop_mm"]) for row in rows]
    rmses = [float(row["rmse_mm"]) for row in rows]
    return {
        "factors": {
            "mass_scale": mass,
            "leakage_scale": leakage,
            "temperature_c": temperature,
            "load_after_step_n": load,
            "accumulator_flow_scale": accumulator,
        },
        "screen_pass_rate": sum(bool(row["pass_10mm_screen"]) for row in rows) / len(rows),
        "hold_entry_rate": sum(bool(row["hold_started"]) for row in rows) / len(rows),
        "hold_drop_mm": ci(drops),
        "rmse_mm": ci(rmses),
        "rows": rows,
    }


def main() -> None:
    keys = tuple(FACTORS)
    cases = []
    for values in itertools.product(*(FACTORS[key] for key in keys)):
        cases.append(evaluate(tuple(float(value) for value in values)))
        print("case", len(cases), values, flush=True)
    worst = max(cases, key=lambda case: float(case["hold_drop_mm"]["mean"]))
    output = {
        "purpose": "Cartesian virtual stress surface for the dual-mode hitch controller; not calibrated uncertainty coverage.",
        "seeds": list(SEEDS),
        "factor_order": list(keys),
        "factor_levels": {key: list(levels) for key, levels in FACTORS.items()},
        "screen": "hold entry required and mean per-seed drop no larger than 10 mm over 1800 s",
        "case_count": len(cases),
        "cases": cases,
        "worst_case": worst,
    }
    path = ROOT / "results" / "lift_combined_stress.json"
    path.write_text(json.dumps(output, ensure_ascii=False, indent=2), encoding="utf-8")
    print(path)


if __name__ == "__main__":
    main()
