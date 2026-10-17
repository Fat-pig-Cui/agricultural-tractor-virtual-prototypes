"""Validate two causal demand-tracking phase-policy variants on holdout seeds.

The tracking gains were fixed before this screen. Each target schedule is
calibrated only on development seeds, then frozen. The policy observes current
demand, current SOC, and recurring public task phase; it does not see future
soil, grade, or traction samples.
"""
from __future__ import annotations

import json
from pathlib import Path

from run_paper2_phase_policy_screen import (
    DEVELOPMENT_SEEDS, HOLDOUT_SEEDS, evaluate, make_baselines, phase_means,
    score, search,
)

ROOT = Path(__file__).parents[1]
TRACKING_GAINS = (0.25, 0.75)


def main() -> None:
    development_baseline, development_raw = make_baselines(DEVELOPMENT_SEEDS)
    initial_targets = phase_means(development_raw)
    candidates = []
    for gain in TRACKING_GAINS:
        start = evaluate(initial_targets, DEVELOPMENT_SEEDS, development_baseline,
                         tracking_gain=gain)
        selected, trace = search(initial_targets, DEVELOPMENT_SEEDS,
                                 development_baseline, tracking_gain=gain)
        candidates.append({
            "tracking_gain": gain,
            "development_start": start,
            "development_selected": selected,
            "coordinate_search_trace": trace,
        })
        print("development", gain, selected["certified_rate"],
              selected["saving_pct"], flush=True)
    finalists = sorted(candidates, key=lambda item: score(item["development_selected"]))[:2]
    holdout_baseline, _ = make_baselines(HOLDOUT_SEEDS)
    holdout = []
    for finalist in finalists:
        selected = finalist["development_selected"]
        result = evaluate(tuple(selected["targets_w"]), HOLDOUT_SEEDS,
                          holdout_baseline,
                          tracking_gain=float(finalist["tracking_gain"]), emit=True)
        holdout.append({"tracking_gain": finalist["tracking_gain"], "result": result})
    output = {
        "purpose": (
            "Exploratory causal phase-policy tracking screen. The two tracking gains were "
            "fixed before schedule calibration; each schedule is frozen before holdout."),
        "protocol": {
            "online_information": "public recurring task phase, current demand, and current SOC only",
            "baseline": "unchanged same-seed realistic dynamic OOL",
            "shared_constraints": "60 kW stable floor, 40 kW/s applied engine ramp, 150 kW motor and battery-bus limits",
            "selection_rule": "hard-validity then mean-fuel coordinate search on six development seeds",
            "holdout_rule": "evaluate both fixed-gain development schedules on 14 disjoint seeds",
        },
        "development_seeds": list(DEVELOPMENT_SEEDS),
        "holdout_seeds": list(HOLDOUT_SEEDS),
        "development_candidates": candidates,
        "holdout_frozen_finalists": holdout,
    }
    path = ROOT / "results" / "paper2_phase_policy_tracking_screen.json"
    path.write_text(json.dumps(output, ensure_ascii=False, indent=2), encoding="utf-8")
    print(path)


if __name__ == "__main__":
    main()
