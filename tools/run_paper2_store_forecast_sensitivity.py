"""Frozen storage and causal-forecast sensitivity audit for paper 2.

This is not a controller retuning study. It changes one declared virtual input
at a time while keeping the causal information set, terminal-SOC rule, maps,
and controller settings fixed.
"""
from __future__ import annotations

import json
import math
from pathlib import Path
import sys
from typing import Any

ROOT = Path(__file__).parents[1]
sys.path[:0] = [str(ROOT / "code"), str(ROOT / "code" / "energy_management")]

from experiments import ExperimentConfig, run_definition
from os_ecvt_model import LiteratureBSFCMap, RealisticMotorMap


SEEDS = tuple(range(2500, 2512))
BATTERY_CAPACITIES_WH = (120000.0, 200000.0, 280000.0)
PREDICTOR_RESIDUAL_GAINS = (0.0, 0.5, 1.0)
ECMS_FACTOR = 2.0


def mean_ci(values: list[float]) -> dict[str, float] | None:
    if not values:
        return None
    mean = sum(values) / len(values)
    std = (sum((value - mean) ** 2 for value in values) / (len(values) - 1)) ** 0.5 if len(values) > 1 else 0.0
    half = 2.201 * std / math.sqrt(len(values)) if len(values) > 1 else 0.0
    return {"n": len(values), "mean": mean, "std": std,
            "ci95_low": mean - half, "ci95_high": mean + half}


def base(**overrides: Any) -> dict[str, Any]:
    values: dict[str, Any] = {
        "duration_s": 600.0,
        "profile_name": "stochastic_agri_workcycle",
        "engine_map": LiteratureBSFCMap(),
        "motor_map": RealisticMotorMap(),
        "accessory_for_all_w": 18000.0,
        "terminal_soc_tolerance": 1e-4,
        "terminal_soc_correction_gain": 3.0,
        "stochastic_disturbance_scale": 0.25,
        "stochastic_smooth_disturbances": True,
        "stochastic_offline_reference": False,
        "stochastic_nominal_reference": False,
        "stochastic_nominal_phase_preview": True,
        "stochastic_phase_residual_gain": 0.0,
        "use_offline_soc_reference": False,
        "engine_rated_w": 300000.0,
        "battery_capacity_wh": 200000.0,
        "battery_power_limit_w": 150000.0,
        "motor_peak_w": 150000.0,
        "mpc_horizon": 8,
        "scenario_count": 5,
        "mpc_terminal_weight": 2000000.0,
    }
    values.update(overrides)
    return values


def strict_valid(result: dict[str, object]) -> bool:
    return bool(result["valid"]) and abs(float(result["soc_error"])) <= 1e-4


def certified(result: dict[str, object], controller: str) -> bool:
    return (strict_valid(result)
            and int(result["fallback_count"]) == 0
            and int(result["ramp_envelope_infeasibility_count"]) == 0
            and (controller != "recursive_feasible_mpc"
                 or int(result.get("terminal_set_violation_count", 0)) == 0))


def row(seed: int, result: dict[str, object], controller: str,
        baseline: dict[str, object] | None) -> dict[str, object]:
    saving = None
    if baseline is not None and strict_valid(result) and bool(baseline["strict_valid"]):
        saving = ((float(baseline["fuel_l"]) - float(result["fuel_l"]))
                  / float(baseline["fuel_l"]) * 100.0)
    return {
        "seed": seed, "fuel_l": float(result["fuel_l"]),
        "soc_error": float(result["soc_error"]), "strict_valid": strict_valid(result),
        "certified": certified(result, controller),
        "fallback_count": int(result["fallback_count"]),
        "terminal_set_violation_count": int(result.get("terminal_set_violation_count", 0)),
        "safety_filter_activation_count": int(result.get("safety_filter_activation_count", 0)),
        "decision_timing_ms": result.get("decision_timing_ms"),
        "saving_vs_same_seed_ool_pct": saving,
    }


def summarize(rows: list[dict[str, object]]) -> dict[str, object]:
    savings = [float(item["saving_vs_same_seed_ool_pct"]) for item in rows
               if item["saving_vs_same_seed_ool_pct"] is not None]
    timings = [item["decision_timing_ms"] for item in rows if item["decision_timing_ms"]]
    return {
        "strict_valid_rate": sum(bool(item["strict_valid"]) for item in rows) / len(rows),
        "certified_rate": sum(bool(item["certified"]) for item in rows) / len(rows),
        "saving_pct": mean_ci(savings),
        "mean_safety_filter_activations": sum(int(item["safety_filter_activation_count"]) for item in rows) / len(rows),
        "decision_time_ms": None if not timings else {
            "mean_of_run_means": sum(float(item["mean"]) for item in timings) / len(timings),
            "maximum_run_p95": max(float(item["p95"]) for item in timings),
            "maximum_step": max(float(item["maximum"]) for item in timings),
        },
    }


def evaluate_suite(label: str, config_overrides: dict[str, Any],
                   controllers: tuple[str, ...]) -> dict[str, object]:
    rows: dict[str, list[dict[str, object]]] = {name: [] for name in controllers}
    for seed in SEEDS:
        configuration = ExperimentConfig(seed=seed, **base(**config_overrides))
        baseline_result = run_definition("realistic_ool", configuration)
        baseline_row = row(seed, baseline_result, "realistic_ool", None)
        rows["realistic_ool"].append(baseline_row)
        for controller in controllers:
            if controller == "realistic_ool":
                continue
            overrides = {"adaptive_ecms_equivalence_factor": ECMS_FACTOR} if controller == "adaptive_ecms" else {}
            result = run_definition(controller, ExperimentConfig(
                seed=seed, **base(**config_overrides), **overrides))
            rows[controller].append(row(seed, result, controller, baseline_row))
        print(label, seed, flush=True)
    return {"overrides": config_overrides, "rows": rows,
            "summaries": {name: summarize(values) for name, values in rows.items()}}


def main() -> None:
    capacity = {
        str(int(value / 1000)): evaluate_suite(
            f"capacity_{int(value / 1000)}kWh", {"battery_capacity_wh": value},
            ("realistic_ool", "adaptive_ecms", "recursive_feasible_mpc"))
        for value in BATTERY_CAPACITIES_WH
    }
    forecast = {
        str(gain): evaluate_suite(
            f"residual_gain_{gain}", {"stochastic_phase_residual_gain": gain},
            ("realistic_ool", "recursive_feasible_mpc"))
        for gain in PREDICTOR_RESIDUAL_GAINS
    }
    output = {
        "purpose": (
            "Frozen component-input and causal-predictor sensitivity audit. No controller, horizon, "
            "map, or seed is selected from these outcomes."
        ),
        "seeds": list(SEEDS),
        "protocol": {
            "shared_platform": "300 kW engine, 150 kW motor/battery bus, literature-shaped virtual map, 600 s stochastic agricultural cycle",
            "terminal_rule": "abs(SOC_T - SOC_0) <= 1e-4 with common terminal-energy governor",
            "frozen_controllers": "ECMS lambda=2.0; terminal-set scenario MPC H=8 with five scenarios",
            "causality": "public nominal task phase and present demand/SOC only; no future realized seed sample",
        },
        "battery_capacity_sensitivity": capacity,
        "forecast_residual_gain_sensitivity": forecast,
    }
    path = ROOT / "results" / "paper2_store_forecast_sensitivity.json"
    path.write_text(json.dumps(output, ensure_ascii=False, indent=2), encoding="utf-8")
    print(path)


if __name__ == "__main__":
    main()
