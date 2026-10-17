"""High-order plant-integration convergence audit for Machines Paper 1.

The controller, observer, measurements and commanded input remain on the
submitted 10 ms grid. Only the virtual plant update is replaced by the
event-clipped RK4 arm. This is an additional audit and never overwrites the
frozen Euler results.
"""
from __future__ import annotations
from concurrent.futures import ProcessPoolExecutor, as_completed
from pathlib import Path
import json, math, statistics, sys, time

ROOT = Path(__file__).resolve().parents[1]
sys.path[:0] = [str(ROOT / "code"), str(ROOT / "code" / "lift_control")]
from lift_v2_experiment import LiftV2Config, run_lift_v2

OUT = ROOT / "revisions" / "machines_major_revision" / "results"
SEEDS = list(range(4300, 4305))
SUBSTEPS = [10, 20]  # 1.0 and 0.5 ms plant steps


def stat(values):
    return {
        "n": len(values),
        "mean": statistics.fmean(values),
        "sd": statistics.stdev(values) if len(values) > 1 else 0.0,
        "min": min(values),
        "max": max(values),
    }


def passed(row):
    return bool(row["hold_started"] and row["hold_drop_mm"] <= 10.0
                and row["post_transition_max_abs_error_mm"] <= 10.0
                and row["relief_activation_count"] == 0
                and row["stroke_boundary_samples"] == 0)


def job(substeps, seed):
    row = run_lift_v2(
        "observer_hybrid",
        LiftV2Config(duration_s=1800.0, seed=seed),
        integration_substeps=substeps,
        integration_scheme="rk4",
    )
    return substeps, row


def main():
    OUT.mkdir(parents=True, exist_ok=True)
    tasks = [(sub, seed) for sub in SUBSTEPS for seed in SEEDS]
    rows = {sub: [] for sub in SUBSTEPS}
    start = time.time()
    with ProcessPoolExecutor(max_workers=min(4, len(tasks))) as pool:
        futures = [pool.submit(job, sub, seed) for sub, seed in tasks]
        for i, future in enumerate(as_completed(futures), 1):
            sub, row = future.result()
            rows[sub].append(row)
            print(f"{i}/{len(tasks)} rk4 substeps={sub} seed={row['seed']}", flush=True)
    summary = {}
    for sub in SUBSTEPS:
        values = rows[sub]
        values.sort(key=lambda r: r["seed"])
        summary[str(sub)] = {
            "plant_step_ms": 10.0 / sub,
            "n": len(values),
            "passed": sum(passed(r) for r in values),
            "hold_drop_mm": stat([r["hold_drop_mm"] for r in values]),
            "post_transition_rmse_mm": stat([r["post_transition_rmse_mm"] for r in values]),
            "post_transition_max_abs_error_mm": stat([r["post_transition_max_abs_error_mm"] for r in values]),
            "peak_pressure_mpa": stat([r["peak_pressure_mpa"] for r in values]),
            "stroke_boundary_samples": stat([r["stroke_boundary_samples"] for r in values]),
        }
        (OUT / f"rk4_integration_{sub}.json").write_text(
            json.dumps({"summary": summary[str(sub)], "rows": values}, indent=2)
        )
    fine = {r["seed"]: r for r in rows[20]}
    coarse = {r["seed"]: r for r in rows[10]}
    differences = []
    for seed in SEEDS:
        a, b = coarse[seed], fine[seed]
        differences.append({
            "seed": seed,
            "hold_drop_difference_mm": a["hold_drop_mm"] - b["hold_drop_mm"],
            "max_error_difference_mm": a["post_transition_max_abs_error_mm"] - b["post_transition_max_abs_error_mm"],
        })
    report = {
        "method": "event-clipped classical RK4 plant update; controller, observer and noise remain at 10 ms",
        "seeds": SEEDS,
        "substeps": SUBSTEPS,
        "summary": summary,
        "coarse_1ms_minus_fine_0_5ms": differences,
        "mean_absolute_hold_drop_difference_mm": statistics.fmean(abs(d["hold_drop_difference_mm"])
                                                                  for d in differences),
        "mean_absolute_max_error_difference_mm": statistics.fmean(abs(d["max_error_difference_mm"])
                                                                  for d in differences),
        "elapsed_s": time.time() - start,
        "interpretation": (
            "This audit tests numerical convergence of the refined plant arm. "
            "It does not change the primary 10 ms Euler comparison and does not "
            "establish physical-model validity or global switched stability."
        ),
    }
    (OUT / "rk4_convergence_audit.json").write_text(json.dumps(report, indent=2))
    print(json.dumps(report, indent=2))


if __name__ == "__main__":
    main()
