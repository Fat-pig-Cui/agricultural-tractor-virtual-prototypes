"""Predeclared measurement and observer mismatch audit for paper 1.

Only controller-facing measurements and observer coefficients are changed. The
virtual plant is fixed, so the result is an observability boundary rather than
hardware validation or parameter calibration.
"""
from __future__ import annotations

import json
import math
from pathlib import Path
import sys

ROOT = Path(__file__).parents[1]
sys.path[:0] = [str(ROOT / "code"), str(ROOT / "code" / "lift_control")]

from experiments import ExperimentConfig, run_definition


SEEDS = tuple(range(2060, 2080))
CASES: tuple[tuple[str, dict[str, float]], ...] = (
    ("nominal", {}),
    ("position_bias_plus_2mm", {"position_sensor_bias_m": 0.002}),
    ("pressure_bias_plus_0p1MPa", {"pressure_measurement_bias_pa": 0.1e6}),
    ("pressure_noise_0p1MPa_raw", {"pressure_measurement_noise_std_pa": 0.1e6}),
    ("pressure_noise_0p05MPa_filtered_200ms", {
        "pressure_measurement_noise_std_pa": 0.05e6,
        "pressure_measurement_filter_time_s": 0.2,
    }),
    ("observer_valve_gain_minus_15pct", {"observer_valve_gain_scale": 0.85}),
    ("observer_valve_gain_plus_15pct", {"observer_valve_gain_scale": 1.15}),
    ("observer_rates_minus_20pct", {
        "observer_tracking_rate_scale": 0.8,
        "observer_hold_rate_scale": 0.8,
        "observer_temperature_gain_scale": 0.8,
    }),
    ("combined_mismatch_filtered_200ms", {
        "position_sensor_bias_m": 0.002,
        "pressure_measurement_bias_pa": 0.1e6,
        "pressure_measurement_noise_std_pa": 0.05e6,
        "pressure_measurement_filter_time_s": 0.2,
        "load_measurement_bias_n": 500.0,
        "observer_valve_gain_scale": 0.85,
        "observer_tracking_rate_scale": 0.8,
        "observer_hold_rate_scale": 0.8,
        "observer_temperature_gain_scale": 0.8,
    }),
)


def summary(values: list[float]) -> dict[str, float]:
    mean = sum(values) / len(values)
    std = (sum((value - mean) ** 2 for value in values) / (len(values) - 1)) ** 0.5
    return {
        "n": len(values), "mean": mean, "std": std,
        "ci95_low": mean - 2.093 * std / math.sqrt(len(values)),
        "ci95_high": mean + 2.093 * std / math.sqrt(len(values)),
        "maximum": max(values),
    }


def evaluate(case_id: str, overrides: dict[str, float]) -> dict[str, object]:
    rows: list[dict[str, object]] = []
    for seed in SEEDS:
        result = run_definition("hybrid", ExperimentConfig(**overrides), seed=seed)
        rows.append({
            "seed": seed,
            "hold_started": bool(result["hold_started"]),
            "hold_drop_mm": None if result["hold_drop_m"] is None else result["hold_drop_m"] * 1000.0,
            "steady_rmse_mm": result["steady_rmse_m"] * 1000.0,
            "steady_p95_abs_error_mm": result["steady_p95_abs_error_m"] * 1000.0,
            "steady_max_abs_error_mm": result["steady_max_abs_error_m"] * 1000.0,
            "settling_error_mm": result["settling_error_m"] * 1000.0,
        })
    hold_drops = [float(row["hold_drop_mm"]) for row in rows if row["hold_drop_mm"] is not None]
    return {
        "case": case_id, "overrides": overrides,
        "hold_entry_rate": sum(bool(row["hold_started"]) for row in rows) / len(rows),
        "hold_drop_mm": summary(hold_drops) if hold_drops else None,
        "steady_rmse_mm": summary([float(row["steady_rmse_mm"]) for row in rows]),
        "steady_p95_abs_error_mm": summary([float(row["steady_p95_abs_error_mm"]) for row in rows]),
        "steady_max_abs_error_mm": summary([float(row["steady_max_abs_error_mm"]) for row in rows]),
        "settling_error_mm": summary([float(row["settling_error_mm"]) for row in rows]),
        "rows": rows,
    }


def main() -> None:
    cases: dict[str, object] = {}
    for case_id, overrides in CASES:
        print(case_id, flush=True)
        cases[case_id] = evaluate(case_id, overrides)
    output = {
        "purpose": (
            "Frozen virtual measurement and observer-mismatch audit. The plant remains unchanged; "
            "the unfiltered noise case is retained as a failure boundary, not excluded from reporting."
        ),
        "seeds": list(SEEDS), "cases": cases,
        "acceptance_checks": {
            "all_cases_have_20_rows": all(len(case["rows"]) == len(SEEDS) for case in cases.values()),
            "filtered_combined_case_enters_hold": (
                cases["combined_mismatch_filtered_200ms"]["hold_entry_rate"] == 1.0),
        },
    }
    path = ROOT / "results" / "paper1_measurement_observer_audit.json"
    path.write_text(json.dumps(output, ensure_ascii=False, indent=2), encoding="utf-8")
    print(path)


if __name__ == "__main__":
    main()
