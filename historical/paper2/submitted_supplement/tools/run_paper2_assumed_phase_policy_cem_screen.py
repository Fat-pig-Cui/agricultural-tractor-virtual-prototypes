"""Global CEM screen for the assumed-map causal phase policy.

This deliberately uses a fixed-seed, bounded cross-entropy search rather than
another local coordinate start.  It observes only the six development seeds.
The selected policy is frozen before its disjoint holdout and confirmation
sets.  Every evaluated policy uses only public phase, present demand, and
present SOC at run time; all plant constraints are enforced by the common
runner.
"""
from __future__ import annotations

import json
import random
from pathlib import Path

from run_paper2_assumed_phase_policy_tiered_screen import (
    BASE, baselines, compact, mean_ci,
)
from experiments import ExperimentConfig, run_definition

ROOT = Path(__file__).parents[1]
DEVELOPMENT_SEEDS = tuple(range(2198, 2204))
HOLDOUT_SEEDS = tuple(range(2204, 2218))
CONFIRMATION_SEEDS = tuple(range(2218, 2232))
RANDOM_SEED = 20260909
POPULATION = 16
GENERATIONS = 5
ELITE_COUNT = 4

# Frozen incumbent from the prior multi-start confirmation.  The global
# screen must beat this exact policy on development fuel before it advances.
INCUMBENT_TARGETS_W = (174375.0, 168750.0, 202500.0, 181875.0,
                       176250.0, 123750.0, 140625.0, 151875.0)
INCUMBENT_GAINS = (0.35,) * 8


def clip(value: float, lower: float, upper: float) -> float:
    return max(lower, min(upper, value))


def evaluate(name: str, targets: tuple[float, ...], gains: tuple[float, ...],
             seeds: tuple[int, ...], baseline_rows: dict[int, dict[str, object]],
             emit: bool = False) -> dict[str, object]:
    rows = []
    for seed in seeds:
        result = run_definition(
            "phase_policy",
            ExperimentConfig(
                seed=seed,
                phase_policy_targets_w=targets,
                phase_policy_tracking_gains=gains,
                **BASE,
            ),
        )
        row = compact(seed, result, baseline_rows[seed])
        rows.append(row)
        if emit:
            print("policy", name, seed, row["hard_valid"],
                  f"{row['fuel_l']:.6f}", flush=True)
    savings = [float(row["saving_vs_same_seed_ool_pct"]) for row in rows
               if row["saving_vs_same_seed_ool_pct"] is not None]
    return {
        "name": name,
        "targets_w": list(targets),
        "tracking_gains": list(gains),
        "rows": rows,
        "hard_valid_rate": sum(bool(row["hard_valid"]) for row in rows) / len(rows),
        "mean_fuel_l": sum(float(row["fuel_l"]) for row in rows) / len(rows),
        "saving_pct": mean_ci(savings),
    }


def score(summary: dict[str, object]) -> tuple[int, float]:
    invalid = len(summary["rows"]) - sum(bool(row["hard_valid"]) for row in summary["rows"])
    return invalid, float(summary["mean_fuel_l"])


def sample_policy(rng: random.Random, target_mean: list[float], target_sigma: list[float],
                  gain_mean: list[float], gain_sigma: list[float]) -> tuple[tuple[float, ...], tuple[float, ...]]:
    targets = tuple(clip(rng.gauss(mean, sigma), 60000.0, 260000.0)
                    for mean, sigma in zip(target_mean, target_sigma))
    gains = tuple(clip(rng.gauss(mean, sigma), 0.0, 1.0)
                  for mean, sigma in zip(gain_mean, gain_sigma))
    return targets, gains


def elite_moments(entries: list[dict[str, object]], key: str, floor: float) -> tuple[list[float], list[float]]:
    values = [list(map(float, entry[key])) for entry in entries]
    width = len(values[0])
    means = [sum(row[index] for row in values) / len(values) for index in range(width)]
    sigmas = []
    for index, mean in enumerate(means):
        variance = sum((row[index] - mean) ** 2 for row in values) / len(values)
        sigmas.append(max(floor, variance ** 0.5))
    return means, sigmas


def main() -> None:
    rng = random.Random(RANDOM_SEED)
    development_baseline = baselines(DEVELOPMENT_SEEDS)
    target_mean = list(INCUMBENT_TARGETS_W)
    target_sigma = [35000.0] * 8
    gain_mean = list(INCUMBENT_GAINS)
    gain_sigma = [0.25] * 8
    generations = []
    all_candidates = []

    for generation in range(GENERATIONS):
        policies: list[tuple[str, tuple[float, ...], tuple[float, ...]]] = []
        if generation == 0:
            policies.append(("incumbent", INCUMBENT_TARGETS_W, INCUMBENT_GAINS))
        while len(policies) < POPULATION:
            targets, gains = sample_policy(rng, target_mean, target_sigma, gain_mean, gain_sigma)
            policies.append((f"g{generation}_p{len(policies):02d}", targets, gains))
        summaries = [evaluate(name, targets, gains, DEVELOPMENT_SEEDS, development_baseline)
                     for name, targets, gains in policies]
        ranked = sorted(summaries, key=score)
        elite = ranked[:ELITE_COUNT]
        target_mean, target_sigma = elite_moments(elite, "targets_w", 6000.0)
        gain_mean, gain_sigma = elite_moments(elite, "tracking_gains", 0.05)
        generations.append({
            "generation": generation,
            "target_mean_w": target_mean,
            "target_sigma_w": target_sigma,
            "gain_mean": gain_mean,
            "gain_sigma": gain_sigma,
            "candidates": summaries,
            "elite_names": [str(entry["name"]) for entry in elite],
        })
        all_candidates.extend(summaries)
        print("generation", generation, "best", ranked[0]["name"],
              ranked[0]["hard_valid_rate"], ranked[0]["saving_pct"], flush=True)

    finalist = min(all_candidates, key=score)
    print("selected_development", finalist["name"], finalist["hard_valid_rate"],
          finalist["saving_pct"], flush=True)
    holdout_baseline = baselines(HOLDOUT_SEEDS)
    holdout = evaluate("frozen_" + str(finalist["name"]),
                       tuple(finalist["targets_w"]), tuple(finalist["tracking_gains"]),
                       HOLDOUT_SEEDS, holdout_baseline, emit=True)
    confirmation_baseline = baselines(CONFIRMATION_SEEDS)
    confirmation = evaluate("frozen_" + str(finalist["name"]),
                            tuple(finalist["targets_w"]), tuple(finalist["tracking_gains"]),
                            CONFIRMATION_SEEDS, confirmation_baseline, emit=True)
    output = {
        "purpose": (
            "Fixed-seed global CEM exploration of a causal public-phase policy on an uncalibrated "
            "assumed map; not an MPC, calibrated tractor, hardware, or 20-percent result."
        ),
        "protocol": {
            "online_information": "public recurring task phase, present demand, and present SOC only",
            "baseline": "unchanged same-seed realistic dynamic OOL",
            "shared_constraints": "60 kW stable floor, 40 kW/s applied engine ramp, 150 kW motor and battery-bus limits",
            "selection": "fixed-seed CEM on development only; frozen disjoint holdout and confirmation",
            "map": "RealisticDieselMap low_load_efficiency=0.08, power_width_w=90000; uncalibrated sensitivity map",
        },
        "random_seed": RANDOM_SEED,
        "population": POPULATION,
        "generations": GENERATIONS,
        "elite_count": ELITE_COUNT,
        "development_seeds": list(DEVELOPMENT_SEEDS),
        "holdout_seeds": list(HOLDOUT_SEEDS),
        "confirmation_seeds": list(CONFIRMATION_SEEDS),
        "incumbent": {"targets_w": list(INCUMBENT_TARGETS_W), "tracking_gains": list(INCUMBENT_GAINS)},
        "search_generations": generations,
        "selected_development_finalist": finalist,
        "holdout_frozen_finalist": holdout,
        "confirmation_frozen_finalist": confirmation,
    }
    path = ROOT / "results" / "paper2_assumed_phase_policy_cem_screen.json"
    path.write_text(json.dumps(output, ensure_ascii=False, indent=2), encoding="utf-8")
    print(path)


if __name__ == "__main__":
    main()
