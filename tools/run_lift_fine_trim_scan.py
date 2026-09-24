"""Scan post-transition fine-trim gains for steady virtual position accuracy."""
from __future__ import annotations

import json
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path[:0] = [str(ROOT / "code"), str(ROOT / "code" / "lift_control")]

from experiments import ExperimentConfig, run_definition

SEEDS = tuple(range(2026, 2046))
GAINS = {
    "baseline": (80.0, 12.0, 0.08),
    "trim_1p5": (120.0, 18.0, 0.10),
    "trim_2x": (160.0, 24.0, 0.12),
    "trim_2p5": (200.0, 30.0, 0.14),
}
CONDITIONS = {
    "nominal": {},
    "load_step_14kn": {"load_after_step_n": 14000.0},
    "sensor_noise_2x": {"noise_scale": 2.0},
}


def summarize(rows: list[dict[str, object]]) -> dict[str, object]:
    mean = lambda key: sum(float(row[key]) for row in rows) / len(rows)
    return {
        "n": len(rows),
        "hold_entry_rate": sum(bool(row["hold_started"]) for row in rows) / len(rows),
        "mean_steady_rmse_mm": mean("steady_rmse_mm"),
        "mean_steady_max_abs_error_mm": mean("steady_max_abs_error_mm"),
        "worst_steady_max_abs_error_mm": max(float(row["steady_max_abs_error_mm"]) for row in rows),
        "mean_hold_drop_mm": mean("hold_drop_mm"),
        "worst_hold_drop_mm": max(float(row["hold_drop_mm"]) for row in rows),
        "rows": rows,
    }


def main() -> None:
    output = {"gains": GAINS, "conditions": {}}
    for condition, overrides in CONDITIONS.items():
        output["conditions"][condition] = {}
        for name, (position_gain, velocity_gain, scale) in GAINS.items():
            rows = []
            for seed in SEEDS:
                config = ExperimentConfig(
                    **overrides,
                    hold_fine_trim_position_gain=position_gain,
                    hold_fine_trim_velocity_gain=velocity_gain,
                    hold_fine_trim_scale=scale,
                )
                result = run_definition("hybrid", config, seed=seed)
                rows.append({
                    "seed": seed,
                    "hold_started": bool(result["hold_started"]),
                    "steady_rmse_mm": float(result["steady_rmse_m"]) * 1000.0,
                    "steady_max_abs_error_mm": float(result["steady_max_abs_error_m"]) * 1000.0,
                    "hold_drop_mm": float(result["hold_drop_m"] or 0.0) * 1000.0,
                })
            output["conditions"][condition][name] = summarize(rows)
    path = ROOT / "results" / "lift_fine_trim_scan.json"
    path.write_text(json.dumps(output, ensure_ascii=False, indent=2), encoding="utf-8")
    print(path)


if __name__ == "__main__":
    main()
