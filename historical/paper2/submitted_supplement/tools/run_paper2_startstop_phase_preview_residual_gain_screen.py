"""Screen the causal present-residual persistence in strict scenario MPC."""
from __future__ import annotations

import json
from pathlib import Path
import sys
from typing import Any

ROOT = Path(__file__).parents[1]
sys.path[:0] = [str(ROOT / "code"), str(ROOT / "code" / "energy_management")]

from experiments import ExperimentConfig, run_definition
from run_paper2_startstop_phase_preview_scenario_screen import (
    BASE, DEVELOPMENT_SEEDS, HOLDOUT_SEEDS, compact, mean_ci,
)


CANDIDATES: tuple[dict[str, Any], ...] = tuple(
    {"name": f"H8_scenarios5_residual_{gain:g}",
     "overrides": {"scenario_count": 5, "stochastic_phase_residual_gain": gain}}
    for gain in (0.0, 0.25, 0.5, 0.75, 1.0)
)


def baseline(seeds: tuple[int, ...]) -> dict[int, dict[str, object]]:
    rows = {}
    for seed in seeds:
        row = compact(seed, run_definition("realistic_ool", ExperimentConfig(seed=seed, **BASE)))
        rows[seed] = row
        print("ool", seed, row["certified"], f"{row['fuel_l']:.6f}", flush=True)
    return rows


def evaluate(candidate: dict[str, Any], seeds: tuple[int, ...],
             baselines: dict[int, dict[str, object]]) -> dict[str, object]:
    rows = []
    for seed in seeds:
        values = dict(BASE)
        values.update(candidate["overrides"], seed=seed)
        row = compact(seed, run_definition("robust_mpc", ExperimentConfig(**values)))
        base = baselines[seed]
        row["saving_vs_same_seed_ool_pct"] = (
            (float(base["fuel_l"]) - float(row["fuel_l"])) / float(base["fuel_l"]) * 100.0
            if bool(base["certified"]) and bool(row["certified"]) else None)
        rows.append(row)
        print(candidate["name"], seed, row["certified"], f"{row['fuel_l']:.6f}", flush=True)
    savings = [float(row["saving_vs_same_seed_ool_pct"]) for row in rows
               if row["saving_vs_same_seed_ool_pct"] is not None]
    return {
        "name": candidate["name"], "overrides": candidate["overrides"], "rows": rows,
        "valid_rate": sum(bool(row["valid"]) for row in rows) / len(rows),
        "certified_rate": sum(bool(row["certified"]) for row in rows) / len(rows),
        "saving_pct": mean_ci(savings),
        "mean_fallback_count": sum(int(row["fallback_count"]) for row in rows) / len(rows),
    }


def rank(entry: dict[str, object]) -> float:
    summary = entry["saving_pct"]
    if entry["certified_rate"] != 1.0 or summary is None:
        return float("-inf")
    return float(summary["mean"])


def main() -> None:
    development_baseline = baseline(DEVELOPMENT_SEEDS)
    development = [evaluate(candidate, DEVELOPMENT_SEEDS, development_baseline)
                   for candidate in CANDIDATES]
    finalists = sorted(development, key=rank, reverse=True)[:2]
    holdout_baseline = baseline(HOLDOUT_SEEDS)
    holdout = [evaluate({"name": entry["name"], "overrides": entry["overrides"]},
                        HOLDOUT_SEEDS, holdout_baseline) for entry in finalists]
    output = {
        "protocol": {
            "cycle": "600 s continuous stochastic agricultural work cycle",
            "engine_map": "LiteratureBSFCMap",
            "online_information": "public nominal task phase plus present measured demand; no evaluated-seed future samples or offline reference",
            "fixed_mpc_setting": "scenario MPC, horizon 8, five scenarios, terminal weight 2M",
            "tuned_parameter": "causal present-residual persistence in the public phase preview",
            "shared_start_stop": "25 kW stop, 45 kW restart, 10 s minimum-on, 5 s minimum-off, 1.5 g/start proxy",
            "shared_constraints": "exact common initial-SOC closure for direct-fuel comparison; 40 kW/s running-engine ramp; 60 kW stable-power floor; 150 kW motor and battery-bus limits; terminal SOC validity tolerance 0.01",
            "certification_rule": "all hard validity conditions, zero fallback, and zero forecast ramp-envelope infeasibility",
            "selection_rule": "rank fully certified residual gains on six development seeds; evaluate the two finalists on 14 disjoint holdout seeds",
            "scope_limit": "Start/stop transitions are a shared modeled operating mode and are not ordinary running-engine ramp events; the result is not hardware validation.",
        },
        "development_seeds": list(DEVELOPMENT_SEEDS),
        "holdout_seeds": list(HOLDOUT_SEEDS),
        "development": development,
        "selected_finalists": [entry["name"] for entry in finalists],
        "holdout": holdout,
    }
    path = ROOT / "results" / "paper2_startstop_phase_preview_residual_gain_screen.json"
    path.write_text(json.dumps(output, ensure_ascii=False, indent=2), encoding="utf-8")
    print(path)


if __name__ == "__main__":
    main()
