"""Technical holdout check for conservative, development-certified MPC weights."""
from __future__ import annotations

import json
from pathlib import Path
import sys

ROOT = Path(__file__).parents[1]
sys.path[:0] = [str(ROOT / "code"), str(ROOT / "code" / "energy_management")]

from experiments import ExperimentConfig, run_definition
from run_paper2_startstop_phase_preview_terminal_weight_screen import (
    BASE, HOLDOUT_SEEDS, compact, mean_ci,
)


WEIGHTS = (5000000.0, 10000000.0)


def main() -> None:
    baseline_rows = {}
    for seed in HOLDOUT_SEEDS:
        baseline_rows[seed] = compact(
            seed, run_definition("realistic_ool", ExperimentConfig(seed=seed, **BASE)))
    checks = []
    for weight in WEIGHTS:
        rows = []
        for seed in HOLDOUT_SEEDS:
            values = dict(BASE, mpc_terminal_weight=weight, seed=seed)
            row = compact(seed, run_definition("robust_mpc", ExperimentConfig(**values)))
            base = baseline_rows[seed]
            row["saving_vs_same_seed_ool_pct"] = (
                (float(base["fuel_l"]) - float(row["fuel_l"])) / float(base["fuel_l"]) * 100.0
                if bool(base["certified"]) and bool(row["certified"]) else None)
            rows.append(row)
            print(weight, seed, row["certified"], f"{row['fuel_l']:.6f}", flush=True)
        savings = [float(row["saving_vs_same_seed_ool_pct"]) for row in rows
                   if row["saving_vs_same_seed_ool_pct"] is not None]
        checks.append({
            "name": f"H8_weight_{weight / 1e6:g}M",
            "overrides": {"mpc_terminal_weight": weight},
            "rows": rows,
            "certified_rate": sum(bool(row["certified"]) for row in rows) / len(rows),
            "saving_pct": mean_ci(savings),
            "mean_fallback_count": sum(int(row["fallback_count"]) for row in rows) / len(rows),
        })
    output = {
        "purpose": "Technical feasibility check of conservative weights after the initial terminal-weight holdout exposed fallback events. This is not an independent confirmation set.",
        "seeds": list(HOLDOUT_SEEDS),
        "selection_rule_for_next_stage": "freeze the lowest tested weight with zero fallback on all 14 technical holdout seeds, then use new seeds for independent confirmation",
        "checks": checks,
    }
    path = ROOT / "results" / "paper2_startstop_phase_preview_conservative_holdout.json"
    path.write_text(json.dumps(output, ensure_ascii=False, indent=2), encoding="utf-8")
    print(path)


if __name__ == "__main__":
    main()
