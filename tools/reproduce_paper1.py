"""Regenerate a short Paper 1 virtual-prototype result from source only."""
from __future__ import annotations

import argparse
import json
import sys
from dataclasses import replace
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path[:0] = [str(ROOT / "code"), str(ROOT / "code" / "lift_control")]

from lift_control import experiments  # noqa: E402
from config.parameters import LiftParameters  # noqa: E402


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--workspace", type=Path, required=True)
    parser.add_argument("--duration", type=float, default=60.0)
    parser.add_argument("--seed", type=int, default=2026)
    args = parser.parse_args()
    config = replace(experiments.ExperimentConfig(), duration_s=args.duration)
    rows = {controller: experiments.run_definition(controller, config, args.seed)
            for controller in ("hybrid", "pid")}
    output = {
        "scope": "Source-only virtual simulation; no frozen or hardware data are read.",
        "duration_s": args.duration,
        "seed": args.seed,
        "parameters": {k: getattr(LiftParameters(), k)
                       for k in ("dt_s", "cylinder_area_m2", "mass_kg", "stiffness_n_m")},
        "controllers": rows,
    }
    target = args.workspace / "results" / "paper1_summary.json"
    target.write_text(json.dumps(output, indent=2, ensure_ascii=False) + "\n")
    print(json.dumps({k: {"hold_started": v["hold_started"],
                          "hold_drop_m": v["hold_drop_m"],
                          "steady_max_abs_error_m": v["steady_max_abs_error_m"]}
                     for k, v in rows.items()}, ensure_ascii=False))


if __name__ == "__main__":
    main()
