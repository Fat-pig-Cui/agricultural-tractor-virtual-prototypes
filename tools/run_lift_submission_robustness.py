"""Operating-envelope and raw-velocity tests for the hitch submission draft."""
from __future__ import annotations

import json
import math
from pathlib import Path
import sys
import argparse

ROOT = Path(__file__).parents[1]
sys.path[:0] = [str(ROOT / "code"), str(ROOT / "code" / "lift_control")]

from experiments import ExperimentConfig, run_definition

SEEDS = tuple(range(2026, 2046))


def summary(values: list[float]) -> dict[str, float]:
    mean = sum(values) / len(values)
    std = (sum((value - mean) ** 2 for value in values) / (len(values) - 1)) ** 0.5
    half_width = 2.093 * std / math.sqrt(len(values))
    return {"n": len(values), "mean": mean, "std": std,
            "ci95_low": mean - half_width, "ci95_high": mean + half_width}


def evaluate(config: ExperimentConfig) -> dict[str, object]:
    rows = []
    for seed in SEEDS:
        result = run_definition("hybrid", config, seed=seed)
        rows.append({
            "seed": seed,
            "hold_started": bool(result["hold_started"]),
            "hold_start_s": result["hold_start_time_s"],
            "hold_drop_mm": (result["hold_drop_m"] or 0.0) * 1000.0,
            "settling_error_mm": result["settling_error_m"] * 1000.0,
            "rmse_mm": result["rmse_m"] * 1000.0,
            "max_velocity_mps": result["max_velocity_mps"],
        })
    return {
        "hold_entry_rate": sum(row["hold_started"] for row in rows) / len(rows),
        "hold_drop_mm": summary([row["hold_drop_mm"] for row in rows]),
        "settling_error_mm": summary([row["settling_error_mm"] for row in rows]),
        "rmse_mm": summary([row["rmse_mm"] for row in rows]),
        "rows": rows,
    }


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--section", choices=("all", "envelope", "raw-gate"), default="all")
    args = parser.parse_args()
    temperature_c = (25.0, 40.0, 50.0)
    post_step_load_n = (7000.0, 10000.0, 14000.0)
    output = ROOT / "results" / "lift_submission_robustness.json"
    out = json.loads(output.read_text(encoding="utf-8")) if output.exists() else {
        "seeds": list(SEEDS),
        "protocol": {
            "duration_s": 1800.0,
            "controller": "hybrid",
            "temperature_c": list(temperature_c),
            "post_step_load_n": list(post_step_load_n),
            "raw_gate_tolerance_mm_s": [3.0, 5.0, 10.0],
            "note": "All parameters remain virtual-prototype engineering assumptions.",
        },
    }
    if args.section in ("all", "envelope"):
        envelope: dict[str, object] = {}
        for temperature in temperature_c:
            for load in post_step_load_n:
                key = f"temperature_{int(temperature)}c_load_{int(load / 1000)}kn"
                envelope[key] = evaluate(ExperimentConfig(
                    temperature_start_c=temperature,
                    temperature_end_c=temperature,
                    load_after_step_n=load,
                ))
                print(key, flush=True)
        out["temperature_load_envelope"] = envelope
        output.write_text(json.dumps(out, ensure_ascii=False, indent=2), encoding="utf-8")
    if args.section in ("all", "raw-gate"):
        raw_gate: dict[str, object] = {}
        for tolerance_mm_s in (3.0, 5.0, 10.0):
            key = f"raw_gate_{int(tolerance_mm_s)}mm_s"
            raw_gate[key] = evaluate(ExperimentConfig(
                filtered_velocity_gate_enabled=False,
                velocity_gate_mode="raw",
                velocity_gate_tolerance_mps=tolerance_mm_s / 1000.0,
            ))
            print(key, flush=True)
        out["raw_velocity_gate_sensitivity"] = raw_gate
    output.write_text(json.dumps(out, ensure_ascii=False, indent=2), encoding="utf-8")
    print(output)


if __name__ == "__main__":
    main()
