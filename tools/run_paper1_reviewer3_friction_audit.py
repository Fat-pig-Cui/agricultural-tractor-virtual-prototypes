"""Predeclared friction-mismatch audit for Paper 1 Reviewer 3 revision.

The true V2 plant friction is changed while the observer/controller retain
their nominal coefficients.  This directly addresses the reviewer request
for a plant/observer friction mismatch.  The protocol uses the same repeated
load schedule and fivefold virtual leakage arm as the Reviewer 3 stress audit
so the new screen is a combined, fixed-gain test rather than a retuned case.
"""
from __future__ import annotations

import json
import statistics
import sys
from concurrent.futures import ProcessPoolExecutor
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path[:0] = [str(ROOT / "code"), str(ROOT / "code" / "lift_control")]
from lift_v2_experiment import LiftV2Config, run_lift_v2

OUT = ROOT / "revisions/machines_major_revision/results"
SEEDS = tuple(range(4400, 4405))
SCHEDULE = ((0.0, 9000.0), (60.0, 14000.0), (300.0, 10000.0),
            (600.0, 16000.0), (900.0, 11000.0), (1200.0, 15000.0))

# The observer contains no friction coefficients; it retains the nominal
# pressure/force model.  Each arm changes all three true-plant friction terms
# by the same declared factor, which makes the mismatch explicit and
# reproducible without retuning the controller.
CASES = {
    "friction_0.7x": {"viscous_n_s_m": 2200.0 * 0.7,
                       "coulomb_n": 850.0 * 0.7,
                       "stribeck_n": 350.0 * 0.7},
    "friction_1.3x": {"viscous_n_s_m": 2200.0 * 1.3,
                       "coulomb_n": 850.0 * 1.3,
                       "stribeck_n": 350.0 * 1.3},
}


def run_one(item):
    case, seed = item
    result = run_lift_v2(
        "observer_hybrid",
        LiftV2Config(duration_s=1800.0, seed=seed, load_schedule=SCHEDULE,
                     leakage_scale=5.0),
        plant_overrides=CASES[case],
    )
    return case, result


def summarize(rows):
    def vals(key):
        return [r[key] for r in rows if r[key] is not None]

    def mean(key):
        v = vals(key)
        return None if not v else statistics.fmean(v)

    passed = [r for r in rows if r["hold_started"]
              and r["hold_drop_mm"] is not None
              and r["hold_drop_mm"] <= 10.0
              and r["post_transition_max_abs_error_mm"] <= 10.0
              and not r["relief_activation_count"]
              and not r["stroke_boundary_samples"]]
    return {
        "n": len(rows),
        "entered": sum(bool(r["hold_started"]) for r in rows),
        "passed": len(passed),
        "mean_hold_drop_mm": mean("hold_drop_mm"),
        "max_hold_drop_mm": max(vals("hold_drop_mm"), default=None),
        "mean_max_error_mm": mean("post_transition_max_abs_error_mm"),
        "max_error_mm": max(vals("post_transition_max_abs_error_mm"), default=None),
        "mean_oil_ml": mean("accumulator_oil_used_ml"),
        "mean_switches": mean("mode_switches"),
        "min_accumulator_pressure_mpa": min(
            vals("minimum_accumulator_pressure_mpa"), default=None),
        "relief_paths": sum(bool(r["relief_activation_count"]) for r in rows),
        "stroke_hit_paths": sum(bool(r["stroke_boundary_samples"]) for r in rows),
    }


def main():
    OUT.mkdir(parents=True, exist_ok=True)
    protocol = {
        "cases": CASES,
        "seeds": list(SEEDS),
        "load_schedule": SCHEDULE,
        "leakage_scale": 5.0,
        "duration_s": 1800.0,
        "controller": "observer_hybrid",
        "controller_period_s": 0.01,
        "selection": "predeclared friction-mismatch audit; no retuning or case selection",
        "mismatch_definition": "true plant viscous, Coulomb and Stribeck friction are scaled; observer/controller retain nominal coefficients",
    }
    (OUT / "reviewer3_friction_protocol.json").write_text(
        json.dumps(protocol, indent=2))
    rows = {case: [] for case in CASES}
    with ProcessPoolExecutor(max_workers=2) as pool:
        for case, result in pool.map(run_one,
                [(case, seed) for case in CASES for seed in SEEDS]):
            rows[case].append(result)
    output = dict(protocol=protocol, cases={})
    for case, values in rows.items():
        values.sort(key=lambda r: r["seed"])
        output["cases"][case] = {"summary": summarize(values), "rows": values}
        (OUT / ("reviewer3_" + case + ".json")).write_text(
            json.dumps(output["cases"][case], indent=2))
    (OUT / "reviewer3_friction_audit.json").write_text(json.dumps(output, indent=2))
    print(json.dumps({k: v["summary"] for k, v in output["cases"].items()}, indent=2))


if __name__ == "__main__":
    main()
