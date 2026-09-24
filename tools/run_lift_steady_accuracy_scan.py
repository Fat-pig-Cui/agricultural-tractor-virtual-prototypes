"""Report transition-separated accuracy metrics for the lift virtual prototype."""
from __future__ import annotations

import json
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path[:0] = [str(ROOT / "code"), str(ROOT / "code" / "lift_control")]

from experiments import ExperimentConfig, run_definition

SEEDS = tuple(range(2026, 2046))
CASES = {
    "hybrid_nominal": ExperimentConfig(),
    "hybrid_14kn_step": ExperimentConfig(load_after_step_n=14000.0),
    "hybrid_2x_sensor_noise": ExperimentConfig(noise_scale=2.0),
    "hybrid_raw_gate_10mm_s": ExperimentConfig(
        filtered_velocity_gate_enabled=False, velocity_gate_tolerance_mps=0.010),
}


def summary(rows: list[dict[str, object]]) -> dict[str, object]:
    def mean(key: str) -> float:
        return sum(float(row[key]) for row in rows) / len(rows)

    return {
        "n": len(rows),
        "hold_entry_rate": sum(bool(row["hold_started"]) for row in rows) / len(rows),
        "mean_rmse_mm_all_time": mean("rmse_mm"),
        "mean_rmse_mm_after_8s": mean("steady_rmse_mm"),
        "mean_max_abs_error_mm_after_8s": mean("steady_max_abs_error_mm"),
        "max_max_abs_error_mm_after_8s": max(float(row["steady_max_abs_error_mm"]) for row in rows),
        "mean_p95_abs_error_mm_after_8s": mean("steady_p95_abs_error_mm"),
        "mean_hold_drop_mm": mean("hold_drop_mm"),
        "max_hold_drop_mm": max(float(row["hold_drop_mm"]) for row in rows),
        "rows": rows,
    }


def main() -> None:
    output = {}
    for name, config in CASES.items():
        rows = []
        for seed in SEEDS:
            result = run_definition("hybrid", config, seed=seed)
            rows.append({
                "seed": seed,
                "hold_started": bool(result["hold_started"]),
                "rmse_mm": float(result["rmse_m"]) * 1000.0,
                "steady_rmse_mm": float(result["steady_rmse_m"]) * 1000.0,
                "steady_max_abs_error_mm": float(result["steady_max_abs_error_m"]) * 1000.0,
                "steady_p95_abs_error_mm": float(result["steady_p95_abs_error_m"]) * 1000.0,
                "hold_drop_mm": float(result["hold_drop_m"] or 0.0) * 1000.0,
                "hold_start_time_s": result["hold_start_time_s"],
            })
        output[name] = summary(rows)
    path = ROOT / "results" / "lift_steady_accuracy_scan.json"
    path.write_text(json.dumps(output, ensure_ascii=False, indent=2), encoding="utf-8")
    print(path)


if __name__ == "__main__":
    main()
