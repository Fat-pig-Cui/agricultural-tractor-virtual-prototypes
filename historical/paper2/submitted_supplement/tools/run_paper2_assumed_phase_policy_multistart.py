"""Multi-start confirmation screen for the assumed-map causal phase policy.

This follows the initial tiered screen with a fixed 0.35 current-demand
tracking gain. Three physically interpretable schedules are optimized on new
development seeds. The selected schedule is then frozen through separate
holdout and confirmation seed sets. No run observes future disturbances.
"""
from __future__ import annotations

import json
from pathlib import Path

from run_paper2_assumed_phase_policy_tiered_screen import (
    BASE, baselines, evaluate, score,
)

ROOT = Path(__file__).parents[1]
DEVELOPMENT_SEEDS = tuple(range(2094, 2100))
HOLDOUT_SEEDS = tuple(range(2100, 2114))
CONFIRMATION_SEEDS = tuple(range(2114, 2128))
TRACKING_GAIN = 0.35
STARTS = {
    # Selected in the prior tiered screen, but not fitted to these seeds.
    "prior_tiered_schedule": (175000.0, 171250.0, 204375.0, 185625.0,
                              183125.0, 126875.0, 143125.0, 156250.0),
    # Hold each task segment close to the 180 kW assumed map island.
    "flat_efficiency_island": (180000.0, 180000.0, 180000.0, 180000.0,
                                180000.0, 180000.0, 180000.0, 180000.0),
    # Charge through lower-load transport, then assist the high-draft phase.
    "transport_charge_plough_assist": (200000.0, 200000.0, 220000.0, 200000.0,
                                        160000.0, 160000.0, 180000.0, 180000.0),
}


def coordinate_search(initial: tuple[float, ...], baseline_rows):
    current = initial
    current_summary = evaluate(current, TRACKING_GAIN, DEVELOPMENT_SEEDS, baseline_rows)
    trace = [{"step_w": None, "targets_w": list(current), "score": list(score(current_summary))}]
    for step_w in (60000.0, 30000.0, 15000.0, 7500.0, 3750.0, 1875.0):
        improved = True
        sweeps = 0
        while improved and sweeps < 3:
            improved = False
            sweeps += 1
            for coordinate in range(len(current)):
                for direction in (-1.0, 1.0):
                    candidate = list(current)
                    candidate[coordinate] = max(60000.0, min(260000.0,
                                                              candidate[coordinate] + direction * step_w))
                    candidate_tuple = tuple(candidate)
                    candidate_summary = evaluate(candidate_tuple, TRACKING_GAIN,
                                                 DEVELOPMENT_SEEDS, baseline_rows)
                    if score(candidate_summary) < score(current_summary):
                        current, current_summary = candidate_tuple, candidate_summary
                        improved = True
                        trace.append({"step_w": step_w, "targets_w": list(current),
                                      "score": list(score(current_summary))})
    return current_summary, trace


def main() -> None:
    development_baseline = baselines(DEVELOPMENT_SEEDS)
    development = []
    for name, start in STARTS.items():
        initial = evaluate(start, TRACKING_GAIN, DEVELOPMENT_SEEDS, development_baseline)
        selected, trace = coordinate_search(start, development_baseline)
        development.append({"name": name, "development_initial": initial,
                            "development_selected": selected, "trace": trace})
        print("development", name, selected["hard_valid_rate"],
              selected["saving_pct"], flush=True)

    holdout_baseline = baselines(HOLDOUT_SEEDS)
    holdout = []
    for candidate in development:
        selected = candidate["development_selected"]
        result = evaluate(tuple(selected["targets_w"]), TRACKING_GAIN,
                          HOLDOUT_SEEDS, holdout_baseline, emit=True)
        holdout.append({"name": candidate["name"], "result": result})
    finalist = min(holdout, key=lambda item: score(item["result"]))

    confirmation_baseline = baselines(CONFIRMATION_SEEDS)
    confirmation = evaluate(tuple(finalist["result"]["targets_w"]), TRACKING_GAIN,
                            CONFIRMATION_SEEDS, confirmation_baseline, emit=True)
    output = {
        "purpose": (
            "Multi-start assumed-efficiency-island causal phase-policy sensitivity; not a calibrated "
            "tractor, hardware, or MPC result."),
        "protocol": {
            "online_information": "public recurring task phase, present demand, and present SOC only",
            "baseline": "unchanged same-seed realistic dynamic OOL",
            "shared_constraints": "60 kW stable floor, 40 kW/s applied engine ramp, 150 kW motor and battery-bus limits",
            "selection": "three predeclared starts, development optimization, holdout selection, independent frozen confirmation",
            "tracking_gain": TRACKING_GAIN,
            "map": "RealisticDieselMap low_load_efficiency=0.08, power_width_w=90000; uncalibrated sensitivity map",
        },
        "development_seeds": list(DEVELOPMENT_SEEDS),
        "holdout_seeds": list(HOLDOUT_SEEDS),
        "confirmation_seeds": list(CONFIRMATION_SEEDS),
        "starts": {name: list(values) for name, values in STARTS.items()},
        "development_candidates": development,
        "holdout_candidates": holdout,
        "selected_holdout_finalist": finalist,
        "confirmation_frozen_finalist": confirmation,
    }
    path = ROOT / "results" / "paper2_assumed_phase_policy_multistart.json"
    path.write_text(json.dumps(output, ensure_ascii=False, indent=2), encoding="utf-8")
    print(path)


if __name__ == "__main__":
    main()
