"""Map the causal-MPC feasibility--fuel trade-off for paper two.

This is a predeclared mechanism screen, not a search for a headline saving.
It varies only horizon and the information source used by terminal-set scenario
MPC.  Every candidate retains the main paper's strict terminal-SOC rule,
hardware limits, same-seed dynamic OOL comparison, and virtual engine maps.
Development and holdout seed sets are disjoint from the main benchmark.
"""
from __future__ import annotations

import json
import math
from pathlib import Path
import sys
from time import perf_counter
from typing import Any

ROOT = Path(__file__).parents[1]
sys.path[:0] = [str(ROOT / "code"), str(ROOT / "code" / "energy_management")]

from experiments import ExperimentConfig, run_definition
from os_ecvt_model import LiteratureBSFCMap, RealisticDieselMap, RealisticMotorMap


DEVELOPMENT_SEEDS = tuple(range(2400, 2406))
HOLDOUT_SEEDS = tuple(range(2420, 2440))
CANDIDATES: tuple[dict[str, object], ...] = (
    {"id": "H4_history", "label": "H4 history-only", "mpc_horizon": 4,
     "stochastic_nominal_phase_preview": False, "stochastic_phase_residual_gain": 0.0},
    {"id": "H4_phase", "label": "H4 public phase", "mpc_horizon": 4,
     "stochastic_nominal_phase_preview": True, "stochastic_phase_residual_gain": 0.0},
    {"id": "H8_history", "label": "H8 history-only", "mpc_horizon": 8,
     "stochastic_nominal_phase_preview": False, "stochastic_phase_residual_gain": 0.0},
    {"id": "H8_phase", "label": "H8 public phase", "mpc_horizon": 8,
     "stochastic_nominal_phase_preview": True, "stochastic_phase_residual_gain": 0.0},
    {"id": "H12_history", "label": "H12 history-only", "mpc_horizon": 12,
     "stochastic_nominal_phase_preview": False, "stochastic_phase_residual_gain": 0.0},
    {"id": "H12_phase", "label": "H12 public phase", "mpc_horizon": 12,
     "stochastic_nominal_phase_preview": True, "stochastic_phase_residual_gain": 0.0},
)


def mean_ci(values: list[float]) -> dict[str, float] | None:
    if not values:
        return None
    mean = sum(values) / len(values)
    if len(values) == 1:
        return {"n": 1, "mean": mean, "std": 0.0,
                "ci95_low": mean, "ci95_high": mean}
    std = (sum((value - mean) ** 2 for value in values) / (len(values) - 1)) ** 0.5
    critical = {6: 2.571, 20: 2.093}.get(len(values), 1.960)
    half = critical * std / math.sqrt(len(values))
    return {"n": len(values), "mean": mean, "std": std,
            "ci95_low": mean - half, "ci95_high": mean + half}


def map_protocol(map_kind: str) -> dict[str, Any]:
    if map_kind == "literature_shaped":
        engine_map = LiteratureBSFCMap()
        map_note = "Literature-shaped efficiency reference, rescaled to the common 300 kW virtual platform."
    elif map_kind == "steep_island_sensitivity":
        engine_map = RealisticDieselMap(low_load_efficiency=0.08, power_width_w=90000.0)
        map_note = "Declared steep low-load virtual efficiency island on the same 300 kW platform."
    else:
        raise ValueError(map_kind)
    return {
        "duration_s": 600.0,
        "profile_name": "stochastic_agri_workcycle",
        "engine_map": engine_map,
        "motor_map": RealisticMotorMap(),
        "accessory_for_all_w": 18000.0,
        "terminal_soc_tolerance": 1e-4,
        "terminal_soc_correction_gain": 3.0,
        "stochastic_disturbance_scale": 0.25,
        "stochastic_smooth_disturbances": True,
        "stochastic_offline_reference": False,
        "stochastic_nominal_reference": False,
        "scenario_count": 5,
        "mpc_terminal_weight": 2000000.0,
        "engine_rated_w": 300000.0,
        "battery_capacity_wh": 200000.0,
        "battery_power_limit_w": 150000.0,
        "motor_peak_w": 150000.0,
        "realistic_ool_minimum_engine_w": 60000.0,
        "realistic_ool_ramp_limit_w": 40000.0,
        "map_note": map_note,
    }


def config_for(base: dict[str, Any], seed: int, candidate: dict[str, object] | None = None) -> ExperimentConfig:
    values = dict(base)
    values.pop("map_note")
    if candidate is not None:
        values.update({
            "mpc_horizon": int(candidate["mpc_horizon"]),
            "stochastic_nominal_phase_preview": bool(candidate["stochastic_nominal_phase_preview"]),
            "stochastic_phase_residual_gain": float(candidate["stochastic_phase_residual_gain"]),
        })
    values["seed"] = seed
    return ExperimentConfig(**values)


def strict_valid(result: dict[str, object]) -> bool:
    return bool(result["valid"]) and abs(float(result["soc_error"])) <= 1e-4


def compact(seed: int, result: dict[str, object], elapsed_s: float,
            baseline: dict[str, object] | None = None) -> dict[str, object]:
    valid = strict_valid(result)
    certified = (
        valid
        and int(result["fallback_count"]) == 0
        and int(result["ramp_envelope_infeasibility_count"]) == 0
        and int(result.get("terminal_set_violation_count", 0)) == 0
    )
    saving = None
    if baseline is not None and certified and bool(baseline["strict_valid"]):
        saving = ((float(baseline["fuel_l"]) - float(result["fuel_l"]))
                  / float(baseline["fuel_l"]) * 100.0)
    return {
        "seed": seed,
        "fuel_l": float(result["fuel_l"]),
        "soc_error": float(result["soc_error"]),
        "strict_valid": valid,
        "certified": certified,
        "fallback_count": int(result["fallback_count"]),
        "ramp_envelope_infeasibility_count": int(result["ramp_envelope_infeasibility_count"]),
        "safety_filter_activation_count": int(result.get("safety_filter_activation_count", 0)),
        "terminal_set_violation_count": int(result.get("terminal_set_violation_count", 0)),
        "elapsed_s": elapsed_s,
        "saving_vs_same_seed_ool_pct": saving,
    }


def evaluate_ool(base: dict[str, Any], seeds: tuple[int, ...]) -> dict[int, dict[str, object]]:
    rows: dict[int, dict[str, object]] = {}
    for seed in seeds:
        started = perf_counter()
        result = run_definition("realistic_ool", config_for(base, seed))
        row = compact(seed, result, perf_counter() - started)
        rows[seed] = row
        print("ool", seed, row["strict_valid"], f"{row['fuel_l']:.6f}", flush=True)
    return rows


def summarize(rows: list[dict[str, object]]) -> dict[str, object]:
    savings = [float(row["saving_vs_same_seed_ool_pct"]) for row in rows
               if row["saving_vs_same_seed_ool_pct"] is not None]
    return {
        "strict_valid_rate": sum(bool(row["strict_valid"]) for row in rows) / len(rows),
        "certified_rate": sum(bool(row["certified"]) for row in rows) / len(rows),
        "saving_pct": mean_ci(savings),
        "mean_safety_filter_activations": (
            sum(int(row["safety_filter_activation_count"]) for row in rows) / len(rows)),
        "mean_elapsed_s": sum(float(row["elapsed_s"]) for row in rows) / len(rows),
    }


def evaluate_candidate(candidate: dict[str, object], base: dict[str, Any],
                       seeds: tuple[int, ...], baseline: dict[int, dict[str, object]]) -> dict[str, object]:
    rows: list[dict[str, object]] = []
    for seed in seeds:
        started = perf_counter()
        result = run_definition("recursive_feasible_mpc", config_for(base, seed, candidate))
        row = compact(seed, result, perf_counter() - started, baseline[seed])
        rows.append(row)
        print(str(candidate["id"]), seed, row["certified"],
              row["safety_filter_activation_count"], f"{row['fuel_l']:.6f}", flush=True)
    return {
        "id": candidate["id"],
        "label": candidate["label"],
        "overrides": {
            "mpc_horizon": candidate["mpc_horizon"],
            "stochastic_nominal_phase_preview": candidate["stochastic_nominal_phase_preview"],
            "stochastic_phase_residual_gain": candidate["stochastic_phase_residual_gain"],
        },
        "rows": rows,
        "summary": summarize(rows),
    }


def select_candidate(development: list[dict[str, object]]) -> dict[str, object] | None:
    eligible = [entry for entry in development
                if float(entry["summary"]["certified_rate"]) == 1.0
                and entry["summary"]["saving_pct"] is not None]
    if not eligible:
        return None
    return max(eligible, key=lambda entry: float(entry["summary"]["saving_pct"]["mean"]))


def run_map(map_kind: str) -> dict[str, object]:
    base = map_protocol(map_kind)
    development_ool = evaluate_ool(base, DEVELOPMENT_SEEDS)
    development = [evaluate_candidate(candidate, base, DEVELOPMENT_SEEDS, development_ool)
                   for candidate in CANDIDATES]
    selected = select_candidate(development)
    holdout_ool = evaluate_ool(base, HOLDOUT_SEEDS)
    holdout = None
    if selected is not None:
        selected_candidate = next(candidate for candidate in CANDIDATES
                                  if candidate["id"] == selected["id"])
        holdout = evaluate_candidate(selected_candidate, base, HOLDOUT_SEEDS, holdout_ool)
    return {
        "map_note": base["map_note"],
        "development_ool": list(development_ool.values()),
        "development": development,
        "selected_by_development": None if selected is None else selected["id"],
        "holdout_ool": list(holdout_ool.values()),
        "holdout": holdout,
    }


def validate_output(output: dict[str, object]) -> None:
    checks: dict[str, bool] = {}
    maps = output["maps"]
    assert isinstance(maps, dict)
    for map_kind, result in maps.items():
        assert isinstance(result, dict)
        development_ool = result["development_ool"]
        holdout_ool = result["holdout_ool"]
        checks[f"{map_kind}_all_ool_paths_strict_valid"] = all(
            bool(row["strict_valid"]) for row in [*development_ool, *holdout_ool])
        checks[f"{map_kind}_development_selection_exists"] = result["selected_by_development"] is not None
        holdout = result["holdout"]
        checks[f"{map_kind}_holdout_result_exists"] = isinstance(holdout, dict)
    output["acceptance_checks"] = checks
    failed = [name for name, passed in checks.items() if not passed]
    if failed:
        raise RuntimeError("mechanism-map acceptance check failed: " + ", ".join(failed))


def main() -> None:
    output: dict[str, object] = {
        "purpose": (
            "Predeclared causal-MPC mechanism map. It identifies the joint role of "
            "horizon and public task-phase preview under the strict paper-2 protocol; "
            "it is not a search for a positive MPC fuel result."),
        "protocol": {
            "development_seeds": list(DEVELOPMENT_SEEDS),
            "holdout_seeds": list(HOLDOUT_SEEDS),
            "candidates": CANDIDATES,
            "online_information": (
                "History-only candidates use the causal predictor and current measured demand. "
                "Public-phase candidates additionally use the zero-disturbance scheduled task "
                "phase and current measured demand; neither observes a future realized seed sample."),
            "shared_constraints": (
                "300 kW engine, 200 kWh battery, 150 kW motor and battery-bus limits, "
                "60 kW stable engine floor, 40 kW/s applied ramp, zero traction shortage, "
                "and terminal SOC error no larger than 1e-4."),
            "certification_rule": (
                "Strict terminal SOC and hard constraints, zero experiment-runner fallback, "
                "zero forecast ramp-envelope infeasibility, and zero terminal-set violations. "
                "Internal safety-filter interventions remain reported rather than excluded."),
            "selection_rule": (
                "Within each map, select the highest mean direct-fuel saving only among 6/6 "
                "development-certified candidates, then evaluate that frozen candidate on 20 "
                "disjoint holdout seeds. All development cells remain reported."),
        },
        "maps": {
            "literature_shaped": run_map("literature_shaped"),
            "steep_island_sensitivity": run_map("steep_island_sensitivity"),
        },
    }
    validate_output(output)
    path = ROOT / "results" / "paper2_mpc_mechanism_map.json"
    path.write_text(json.dumps(output, ensure_ascii=False, indent=2), encoding="utf-8")
    print(path)


if __name__ == "__main__":
    main()
