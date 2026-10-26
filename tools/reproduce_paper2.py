"""Regenerate a short Paper 2 virtual power-split result from source only."""
from __future__ import annotations

import argparse
import json
import sys
from dataclasses import replace
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path[:0] = [str(ROOT / "code"), str(ROOT / "code" / "energy_management")]

from energy_management import experiments  # noqa: E402


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--workspace", type=Path, required=True)
    parser.add_argument("--duration", type=float, default=60.0)
    parser.add_argument("--seed", type=int, default=5120)
    args = parser.parse_args()
    config = replace(experiments.main_protocol_config(),
                     duration_s=args.duration,
                     profile_name="stochastic_agri_workcycle",
                     seed=args.seed,
                     terminal_soc_tolerance=1e-4)
    rows = {controller: experiments.run_definition(controller, config)
            for controller in ("adaptive_ecms", "realistic_ool")}
    output = {
        "scope": "Source-only virtual simulation; no frozen or hardware data are read.",
        "duration_s": args.duration,
        "seed": args.seed,
        "terminal_soc_tolerance": config.terminal_soc_tolerance,
        "controllers": rows,
    }
    target = args.workspace / "results" / "paper2_summary.json"
    target.write_text(json.dumps(output, indent=2, ensure_ascii=False) + "\n")
    print(json.dumps({k: {"fuel_l": v["fuel_l"], "final_soc": v["final_soc"],
                          "valid": v["valid"]} for k, v in rows.items()}, ensure_ascii=False))


if __name__ == "__main__":
    main()
