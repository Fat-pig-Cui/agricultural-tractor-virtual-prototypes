"""Coarse full-cycle dynamic-programming diagnostic for paper-two headroom.

This is deliberately labelled a diagnostic rather than a performance result:
it knows the complete nominal cycle and discretizes SOC and engine output. It
does, however, enforce the same applied 60 kW stable-power floor, 40 kW/s
engine ramp, combined regenerative MG2 path, battery bus, and terminal SOC
screen as the repaired virtual plant. It maps whether the withdrawn 20% point
is even plausible under those constraints.
"""
from __future__ import annotations

import json
from dataclasses import replace
from pathlib import Path
import sys

import numpy as np

ROOT = Path(__file__).parents[1]
sys.path[:0] = [str(ROOT / "code"), str(ROOT / "code" / "energy_management")]

from config.parameters import PowertrainParameters
from common.profiles import smoothed_regenerative_low_load_agri_workcycle_profile
from experiments import main_protocol_config, run_definition
from os_ecvt_model import DrivelineState, OSECVTModel


def solve(soc_step: float, engine_step_w: float = 4000.0,
          reconstruct_path: bool = False, config=None, profile=None,
          return_path: bool = False) -> dict[str, object]:
    config = main_protocol_config() if config is None else config
    parameters = replace(
        PowertrainParameters(), engine_rated_w=float(config.engine_rated_w),
        battery_capacity_wh=float(config.battery_capacity_wh),
        battery_power_limit_w=float(config.battery_power_limit_w),
        motor_peak_w=float(config.motor_peak_w))
    model = OSECVTModel(parameters, engine_map=config.engine_map,
                        motor_map=config.motor_map)
    profile = (smoothed_regenerative_low_load_agri_workcycle_profile(config.duration_s)
               if profile is None else profile)
    demand = []
    regen = []
    for point in profile:
        raw = model.demand(point.speed_mps, point.draft_n * point.soil_factor,
                           point.grade)
        recovery = min(config.regen_power_limit_w, point.regen_power_w)
        demand.append(max(0.0, raw - recovery) + config.accessory_for_all_w)
        regen.append(recovery)
    demand = np.asarray(demand)
    regen = np.asarray(regen)

    engine_w = np.arange(config.realistic_ool_minimum_engine_w,
                         model.p.engine_rated_w + 1.0, engine_step_w)
    ramp_grid_steps = int(round(
        config.realistic_ool_ramp_limit_w * model.p.dt_s / engine_step_w))
    if ramp_grid_steps <= 0:
        raise ValueError("engine grid is coarser than the applied ramp step")
    soc = np.arange(model.p.soc_min, model.p.soc_max + soc_step / 2.0, soc_step)
    initial_index = int(np.argmin(np.abs(soc - config.initial_soc)))
    cost = np.full((len(soc), len(engine_w)), np.inf)
    # The primary comparison treats the engine as already running at its
    # stable floor; there is no unconstrained start-up power jump.
    cost[initial_index, 0] = 0.0
    predecessor_soc = predecessor_engine = None
    if reconstruct_path:
        predecessor_soc = np.full(
            (len(profile), len(soc), len(engine_w)), -1, dtype=np.int16)
        predecessor_engine = np.full_like(predecessor_soc, -1)
    step_energy = model.p.dt_s / (model.p.battery_capacity_wh * 3600.0)
    fuel_increment_l = np.asarray([
        ((power + 12000.0) * model.p.dt_s
         / (model.engine_map.efficiency(1500.0, power) * 42.7e6) * 1000.0 / 832.0)
        for power in engine_w
    ])

    for time_index, (demand_w, regen_w) in enumerate(zip(demand, regen)):
        next_cost = np.full_like(cost, np.inf)
        regen_bus_w = -regen_w * model.motor_map.efficiency(2400.0, -regen_w)
        for engine_index, power_w in enumerate(engine_w):
            motor_w = demand_w - power_w
            combined_mg2_w = motor_w - regen_w
            if abs(combined_mg2_w) > model.p.motor_peak_w + 1e-9:
                continue
            efficiency = model.motor_map.efficiency(2400.0, motor_w)
            split_bus_w = (motor_w / max(efficiency, 1e-9)
                           if motor_w >= 0.0 else motor_w * efficiency)
            battery_bus_w = split_bus_w + regen_bus_w
            if abs(battery_bus_w) > model.p.battery_power_limit_w + 1e-9:
                continue
            next_soc = soc - battery_bus_w * step_energy
            next_index = np.rint((next_soc - model.p.soc_min) / soc_step).astype(int)
            valid = (next_index >= 0) & (next_index < len(soc))
            if not np.any(valid):
                continue
            low = max(0, engine_index - ramp_grid_steps)
            high = min(len(engine_w), engine_index + ramp_grid_steps + 1)
            predecessor_costs = cost[:, low:high]
            predecessor_engine_index = np.argmin(predecessor_costs, axis=1) + low
            candidate = (predecessor_costs[np.arange(len(soc)),
                                           predecessor_engine_index - low][valid]
                         + fuel_increment_l[engine_index])
            source_index = np.flatnonzero(valid)
            destination_index = next_index[valid]
            existing = next_cost[destination_index, engine_index]
            better = candidate < existing
            next_cost[destination_index[better], engine_index] = candidate[better]
            if reconstruct_path and np.any(better):
                assert predecessor_soc is not None and predecessor_engine is not None
                predecessor_soc[time_index, destination_index[better], engine_index] = source_index[better]
                predecessor_engine[time_index, destination_index[better], engine_index] = (
                    predecessor_engine_index[source_index[better]])
        cost = next_cost

    terminal = np.abs(soc - config.initial_soc) <= config.terminal_soc_tolerance
    if not np.any(np.isfinite(cost[terminal])):
        return {"soc_step": soc_step, "feasible": False}
    terminal_cost = cost.copy()
    terminal_cost[~terminal, :] = np.inf
    best_soc_index, best_engine_index = np.unravel_index(
        int(np.argmin(terminal_cost)), terminal_cost.shape)
    result: dict[str, object] = {
        "soc_step": soc_step,
        "feasible": True,
        "fuel_l": float(cost[best_soc_index, best_engine_index]),
        "terminal_soc_grid": float(soc[best_soc_index]),
        "terminal_soc_error_grid": float(soc[best_soc_index] - config.initial_soc),
        "terminal_engine_w": float(engine_w[best_engine_index]),
        "soc_grid_count": len(soc),
        "engine_grid_count": len(engine_w),
        "engine_grid_step_w": engine_step_w,
    }
    if reconstruct_path:
        assert predecessor_soc is not None and predecessor_engine is not None
        path = np.empty(len(profile))
        current_soc_index, current_engine_index = best_soc_index, best_engine_index
        for time_index in range(len(profile) - 1, -1, -1):
            path[time_index] = engine_w[current_engine_index]
            prior_soc_index = predecessor_soc[time_index, current_soc_index, current_engine_index]
            prior_engine_index = predecessor_engine[time_index, current_soc_index, current_engine_index]
            if prior_soc_index < 0 or prior_engine_index < 0:
                raise RuntimeError("dynamic-programming path reconstruction failed")
            current_soc_index, current_engine_index = int(prior_soc_index), int(prior_engine_index)

        state = DrivelineState(soc=config.initial_soc)
        min_soc = max_soc = state.soc
        exact = {
            "max_shortage_w": 0.0, "max_motor_power_violation_w": 0.0,
            "max_battery_power_violation_w": 0.0, "max_mg1_power_violation_w": 0.0,
            "max_mg1_speed_violation_rpm": 0.0, "max_mg2_speed_violation_rpm": 0.0,
            "max_engine_ramp_violation_w": 0.0,
        }
        prior_power_w = None
        for demand_w, regen_w, point, power_w in zip(demand, regen, profile, path):
            regen_bus_w = -regen_w * model.motor_map.efficiency(2400.0, -regen_w)
            if prior_power_w is not None:
                exact["max_engine_ramp_violation_w"] = max(
                    exact["max_engine_ramp_violation_w"],
                    abs(power_w - prior_power_w) - config.realistic_ool_ramp_limit_w * model.p.dt_s)
            prior_power_w = power_w
            state = model.step(state, float(demand_w), float(power_w), engine_on=True,
                               external_battery_bus_w=regen_bus_w)
            min_soc = min(min_soc, state.soc)
            max_soc = max(max_soc, state.soc)
            report = model.constraint_report(
                float(demand_w), float(power_w), point.speed_mps,
                regen_power_w=float(regen_w), external_battery_bus_w=regen_bus_w)
            exact["max_shortage_w"] = max(
                exact["max_shortage_w"], max(0.0, float(demand_w) - power_w - model.p.motor_peak_w))
            for key, value in report.items():
                exact[f"max_{key}"] = max(exact[f"max_{key}"], value)
        exact["fuel_l"] = model.equivalent_fuel_l(state)
        exact["soc_error"] = state.soc - config.initial_soc
        exact["min_soc"] = min_soc
        exact["max_soc"] = max_soc
        exact["strict_valid"] = (
            abs(exact["soc_error"]) <= config.terminal_soc_tolerance
            and all(exact[key] <= 1.0 for key in exact if key.startswith("max_")))
        result["continuous_rollout"] = exact
        if return_path:
            result["path_w"] = [float(value) for value in path]
    return result


def main() -> None:
    config = main_protocol_config()
    baseline = run_definition("realistic_ool", config)
    grids = [(0.005, 4000.0, True), (0.002, 4000.0, False),
             (0.002, 2000.0, False)]
    results = [solve(soc_step, engine_step_w, reconstruct_path)
               for soc_step, engine_step_w, reconstruct_path in grids]
    for result in results:
        if result["feasible"]:
            result["saving_vs_realistic_ool_pct"] = (
                (float(baseline["fuel_l"]) - float(result["fuel_l"]))
                / float(baseline["fuel_l"]) * 100.0)
    output = {
        "purpose": (
            "Offline full-cycle, grid-discretized diagnostic. It is not an "
            "online-MPC result, not a formal bound, and not manuscript performance evidence."),
        "constraints": {
            "stable_engine_floor_w": config.realistic_ool_minimum_engine_w,
            "engine_ramp_w_per_s": config.realistic_ool_ramp_limit_w,
            "motor_peak_w": config.motor_peak_w,
            "battery_bus_limit_w": config.battery_power_limit_w,
            "terminal_soc_tolerance": config.terminal_soc_tolerance,
        },
        "baseline": {key: baseline[key] for key in (
            "fuel_l", "soc_error", "valid", "max_shortage_w",
            "max_motor_power_violation_w", "max_battery_power_violation_w",
            "max_mg1_power_violation_w", "max_mg1_speed_violation_rpm",
            "max_mg2_speed_violation_rpm", "max_engine_ramp_violation_w")},
        "resolutions": results,
    }
    path = ROOT / "results" / "paper2_dynamic_dp_diagnostic.json"
    path.write_text(json.dumps(output, ensure_ascii=False, indent=2), encoding="utf-8")
    print(path)


if __name__ == "__main__":
    main()
