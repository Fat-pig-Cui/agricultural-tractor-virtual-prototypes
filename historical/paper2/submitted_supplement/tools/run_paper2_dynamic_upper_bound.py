"""Audit the dynamically feasible fuel-saving headroom for paper two.

This is an offline diagnostic, never an online-controller result.  It uses
the exact same virtual plant, net traction demand, wheel-side regeneration,
60 kW stable-power floor, and 40 kW/s engine output limit as the strict
online comparison.  Eight planned task-phase targets are optimized only to
determine whether the assumed map/cycle has credible energy-management room.
"""
from __future__ import annotations

import json
from dataclasses import replace
from pathlib import Path
import sys

import numpy as np
from scipy.optimize import minimize

ROOT = Path(__file__).parents[1]
sys.path[:0] = [str(ROOT / "code"), str(ROOT / "code" / "energy_management")]

from config.parameters import PowertrainParameters
from common.profiles import smoothed_regenerative_low_load_agri_workcycle_profile
from experiments import main_protocol_config, run_definition
from os_ecvt_model import DrivelineState, OSECVTModel

BOUNDARIES_S = (0.0, 65.0, 70.0, 185.0, 190.0, 235.0, 240.0, 295.0, 300.0)


def build_model(config):
    params = PowertrainParameters()
    overrides = {
        name: value for name, value in {
            "battery_capacity_wh": config.battery_capacity_wh,
            "battery_power_limit_w": config.battery_power_limit_w,
            "motor_peak_w": config.motor_peak_w,
            "engine_rated_w": config.engine_rated_w,
        }.items() if value is not None
    }
    return OSECVTModel(replace(params, **overrides), engine_map=config.engine_map,
                       motor_map=config.motor_map)


def main() -> None:
    config = main_protocol_config()
    model = build_model(config)
    profile = smoothed_regenerative_low_load_agri_workcycle_profile(config.duration_s)
    raw = np.asarray([
        model.demand(point.speed_mps, point.draft_n * point.soil_factor, point.grade)
        for point in profile
    ])
    regen = np.asarray([min(config.regen_power_limit_w, point.regen_power_w)
                        for point in profile])
    demand = np.maximum(0.0, raw - regen) + config.accessory_for_all_w
    segment = np.zeros(len(profile), dtype=int)
    for index in range(len(profile)):
        local_s = (index * model.p.dt_s) % BOUNDARIES_S[-1]
        segment[index] = next((value for value in range(len(BOUNDARIES_S) - 1)
                               if BOUNDARIES_S[value] <= local_s < BOUNDARIES_S[value + 1]),
                              len(BOUNDARIES_S) - 2)

    def evaluate(targets: np.ndarray) -> dict[str, float]:
        requested = np.asarray([targets[group] for group in segment])
        state = DrivelineState(soc=config.initial_soc)
        prior_engine_w = None
        fuel_l = 0.0
        shortage_w = motor_violation_w = battery_violation_w = mg1_violation_w = 0.0
        mg1_speed_violation = mg2_speed_violation = ramp_violation_w = 0.0
        for index, (requested_w, demand_w, regen_w, point) in enumerate(
                zip(requested, demand, regen, profile)):
            actual_w = max(config.realistic_ool_minimum_engine_w, float(requested_w))
            if prior_engine_w is not None:
                step_limit_w = config.realistic_ool_ramp_limit_w * model.p.dt_s
                actual_w = max(prior_engine_w - step_limit_w,
                               min(prior_engine_w + step_limit_w, actual_w))
                ramp_violation_w = max(ramp_violation_w,
                                       abs(actual_w - prior_engine_w) - step_limit_w)
            prior_engine_w = actual_w
            regen_bus_w = -float(regen_w) * model.motor_map.efficiency(2400.0, -float(regen_w))
            state = model.step(state, float(demand_w), actual_w, engine_on=True,
                               external_battery_bus_w=regen_bus_w)
            report = model.constraint_report(
                float(demand_w), actual_w, point.speed_mps,
                regen_power_w=float(regen_w), external_battery_bus_w=regen_bus_w)
            shortage_w = max(shortage_w, max(0.0, float(demand_w) - actual_w - model.p.motor_peak_w))
            motor_violation_w = max(motor_violation_w, report["motor_power_violation_w"])
            battery_violation_w = max(battery_violation_w, report["battery_power_violation_w"])
            mg1_violation_w = max(mg1_violation_w, report["mg1_power_violation_w"])
            mg1_speed_violation = max(mg1_speed_violation, report["mg1_speed_violation_rpm"])
            mg2_speed_violation = max(mg2_speed_violation, report["mg2_speed_violation_rpm"])
        fuel_l = model.equivalent_fuel_l(state)
        return {
            "fuel_l": fuel_l,
            "soc_error": state.soc - config.initial_soc,
            "max_shortage_w": shortage_w,
            "max_motor_power_violation_w": motor_violation_w,
            "max_battery_power_violation_w": battery_violation_w,
            "max_mg1_power_violation_w": mg1_violation_w,
            "max_mg1_speed_violation_rpm": mg1_speed_violation,
            "max_mg2_speed_violation_rpm": mg2_speed_violation,
            "max_engine_ramp_violation_w": max(0.0, ramp_violation_w),
        }

    def strict_valid(summary: dict[str, float]) -> bool:
        return (abs(summary["soc_error"]) <= config.terminal_soc_tolerance
                and all(summary[key] <= 1.0 for key in (
                    "max_shortage_w", "max_motor_power_violation_w",
                    "max_battery_power_violation_w",
                    "max_mg1_power_violation_w", "max_mg1_speed_violation_rpm",
                    "max_mg2_speed_violation_rpm", "max_engine_ramp_violation_w")))

    baseline = run_definition("realistic_ool", config)
    baseline_targets = np.asarray([
        np.mean(np.asarray(baseline["commands_w"])[segment == group])
        for group in range(len(BOUNDARIES_S) - 1)
    ])
    starts = {
        "ool_phase_mean": baseline_targets,
        "mean_load": np.asarray([np.mean(demand[segment == group])
                                  for group in range(len(BOUNDARIES_S) - 1)]),
        "moderate_island": np.asarray([60000.0, 90000.0, 140000.0, 150000.0,
                                        180000.0, 180000.0, 90000.0, 90000.0]),
    }
    def penalized_objective(values: np.ndarray) -> float:
        result = evaluate(values)
        violations = sum(max(0.0, result[key] - 1.0) ** 2 for key in (
            "max_shortage_w", "max_motor_power_violation_w",
            "max_battery_power_violation_w", "max_mg1_power_violation_w",
            "max_mg1_speed_violation_rpm", "max_mg2_speed_violation_rpm"))
        # Scale SOC error so a result outside the required 0.01 band cannot
        # win by transferring unreplenished battery energy to the endpoint.
        return result["fuel_l"] + 1.0e5 * result["soc_error"] ** 2 + 1.0e-6 * violations

    trials = []
    for name, initial in starts.items():
        result = minimize(
            penalized_objective, initial, method="SLSQP",
            bounds=[(0.0, model.p.engine_rated_w)] * len(initial),
            constraints={"type": "eq", "fun": lambda values: evaluate(values)["soc_error"]},
            options={"maxiter": 400, "ftol": 1e-8, "disp": False},
        )
        summary = evaluate(result.x)
        trials.append({
            "start": name, "optimizer_success": bool(result.success),
            "optimizer_message": str(result.message), "iterations": int(result.nit),
            "targets_w": [float(value) for value in result.x],
            "summary": summary, "strict_valid": strict_valid(summary),
        })
        print(name, result.success, summary["fuel_l"], summary["soc_error"], flush=True)

    # SLSQP's equality gradient can become singular at a power or SOC clip.
    # A deterministic coordinate pattern search provides an independently
    # reproducible non-gradient diagnostic in that non-smooth setting.
    current = baseline_targets.copy()
    current_cost = penalized_objective(current)
    step_w = 30000.0
    coordinate_iterations = 0
    while step_w >= 250.0 and coordinate_iterations < 500:
        improved = False
        for coordinate in range(len(current)):
            for direction in (-1.0, 1.0):
                candidate = current.copy()
                candidate[coordinate] = np.clip(
                    candidate[coordinate] + direction * step_w, 0.0,
                    model.p.engine_rated_w)
                cost = penalized_objective(candidate)
                coordinate_iterations += 1
                if cost + 1e-12 < current_cost:
                    current, current_cost, improved = candidate, cost, True
        if not improved:
            step_w /= 2.0
    coordinate_summary = evaluate(current)
    trials.append({
        "start": "deterministic_coordinate_search",
        "optimizer_success": True,
        "optimizer_message": "deterministic penalized coordinate search",
        "iterations": coordinate_iterations,
        "targets_w": [float(value) for value in current],
        "summary": coordinate_summary,
        "strict_valid": strict_valid(coordinate_summary),
    })
    print("coordinate_search", coordinate_summary["fuel_l"],
          coordinate_summary["soc_error"], flush=True)

    strict_trials = [trial for trial in trials if trial["strict_valid"]]
    best = min(strict_trials, key=lambda trial: trial["summary"]["fuel_l"], default=None)
    output = {
        "purpose": "Offline dynamic-feasibility diagnostic; not an online-controller result or a formal upper bound.",
        "constraints": {
            "minimum_engine_w": config.realistic_ool_minimum_engine_w,
            "engine_ramp_w_per_s": config.realistic_ool_ramp_limit_w,
            "battery_power_limit_w": model.p.battery_power_limit_w,
            "motor_peak_w": model.p.motor_peak_w,
            "terminal_soc_tolerance": config.terminal_soc_tolerance,
        },
        "baseline": {key: baseline[key] for key in (
            "fuel_l", "soc_error", "valid", "max_shortage_w",
            "max_motor_power_violation_w", "max_mg1_power_violation_w",
            "max_battery_power_violation_w",
            "max_mg1_speed_violation_rpm", "max_mg2_speed_violation_rpm",
            "max_engine_ramp_violation_w")},
        "trials": trials,
        "best_strict_trial": best,
        "best_feasible_diagnostic_saving_vs_realistic_ool_pct": (
            (float(baseline["fuel_l"]) - best["summary"]["fuel_l"])
            / float(baseline["fuel_l"]) * 100.0 if best else None),
    }
    output_path = ROOT / "results" / "paper2_dynamic_upper_bound.json"
    output_path.write_text(json.dumps(output, ensure_ascii=False, indent=2), encoding="utf-8")
    print(output_path)


if __name__ == "__main__":
    main()
