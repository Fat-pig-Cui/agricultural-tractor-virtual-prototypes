"""Predeclared Reviewer 3 stress audit for the Paper 1 virtual plant.

The audit adds repeated load changes, sustained leakage, and accumulator
disablement while retaining the submitted controller, observer, 10 ms
measurement grid, and frozen gains. It is simulation evidence only.
"""
from __future__ import annotations

import json
from pathlib import Path
import statistics
import sys
from concurrent.futures import ProcessPoolExecutor

ROOT = Path(__file__).resolve().parents[1]
sys.path[:0] = [str(ROOT / "code"), str(ROOT / "code" / "lift_control")]
from lift_v2_experiment import LiftV2Config, run_lift_v2

OUT = ROOT / "revisions/machines_major_revision/results"
SEEDS = tuple(range(4400, 4405))
SCHEDULE = ((0.0, 9000.0), (60.0, 14000.0), (300.0, 10000.0),
            (600.0, 16000.0), (900.0, 11000.0), (1200.0, 15000.0))

CASES = {
    "repeated_load_nominal_leakage": dict(leakage_scale=1.0, accumulator_enabled=True),
    "repeated_load_sustained_5x_leakage": dict(leakage_scale=5.0, accumulator_enabled=True),
    "repeated_load_sustained_5x_leakage_accumulator_disabled": dict(
        leakage_scale=5.0, accumulator_enabled=False),
}


def run_one(item):
    case, seed = item
    config = LiftV2Config(duration_s=1800.0, seed=seed,
                          load_schedule=SCHEDULE, **CASES[case])
    result = run_lift_v2("observer_hybrid", config, trace_interval_s=0.5)
    return case, result


def summarize(rows):
    def values(key): return [r[key] for r in rows if r[key] is not None]
    def mean(key):
        vals = values(key)
        return None if not vals else statistics.fmean(vals)
    return dict(n=len(rows), entered=sum(bool(r["hold_started"]) for r in rows),
                passed=sum(bool(r["hold_started"] and r["hold_drop_mm"] is not None
                               and r["hold_drop_mm"] <= 10.0
                               and r["post_transition_max_abs_error_mm"] <= 10.0
                               and not r["relief_activation_count"]
                               and not r["stroke_boundary_samples"]) for r in rows),
                mean_hold_drop_mm=mean("hold_drop_mm"),
                max_hold_drop_mm=max(values("hold_drop_mm"), default=None),
                mean_max_error_mm=mean("post_transition_max_abs_error_mm"),
                max_error_mm=max(values("post_transition_max_abs_error_mm"), default=None),
                mean_oil_ml=mean("accumulator_oil_used_ml"),
                max_oil_ml=max(values("accumulator_oil_used_ml"), default=None),
                mean_switches=mean("mode_switches"),
                min_accumulator_pressure_mpa=min(values("minimum_accumulator_pressure_mpa"), default=None),
                relief_paths=sum(bool(r["relief_activation_count"]) for r in rows),
                stroke_hit_paths=sum(bool(r["stroke_boundary_samples"]) for r in rows))


def main():
    OUT.mkdir(parents=True, exist_ok=True)
    protocol = dict(cases=CASES, seeds=list(SEEDS), load_schedule=SCHEDULE,
                    duration_s=1800.0, controller="observer_hybrid",
                    controller_period_s=0.01,
                    selection="predeclared stress audit; no retuning or case selection",
                    leakage_note="5x multiplies the declared V2 internal leakage input; it is not a calibrated fault model")
    (OUT / "reviewer3_stress_protocol.json").write_text(json.dumps(protocol, indent=2))
    rows = {case: [] for case in CASES}
    with ProcessPoolExecutor(max_workers=4) as pool:
        for case, result in pool.map(run_one,
                [(case, seed) for case in CASES for seed in SEEDS]):
            rows[case].append(result)
    output = dict(protocol=protocol, cases={})
    for case, values in rows.items():
        values.sort(key=lambda r: r["seed"])
        output["cases"][case] = dict(summary=summarize(values), rows=values)
        (OUT / ("reviewer3_" + case + ".json")).write_text(
            json.dumps(output["cases"][case], indent=2))
    (OUT / "reviewer3_stress_audit.json").write_text(json.dumps(output, indent=2))
    print(json.dumps({k: v["summary"] for k, v in output["cases"].items()}, indent=2))


if __name__ == "__main__":
    main()
