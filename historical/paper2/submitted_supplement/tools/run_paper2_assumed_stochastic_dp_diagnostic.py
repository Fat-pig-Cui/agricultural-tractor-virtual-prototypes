"""Full-future DP headroom diagnostic on one strict stochastic assumed-map seed.

This is a deliberately non-online diagnostic. The selected seed is not used to
fit any controller, but its entire future demand trajectory is known to the
grid solver. It therefore cannot be reported as an online result or a formal
bound; it only helps distinguish information/parameterization limits from
physical feasibility under the shared constraints.
"""
from __future__ import annotations

import json
from dataclasses import replace
from pathlib import Path
import sys

ROOT = Path(__file__).parents[1]
sys.path[:0] = [str(ROOT / "code"), str(ROOT / "code" / "energy_management")]

from common.profiles import stochastic_agri_workcycle_profile
from experiments import ExperimentConfig, run_definition
from config.parameters import PowertrainParameters
from os_ecvt_model import DrivelineState, OSECVTModel, RealisticDieselMap, RealisticMotorMap
from run_paper2_dynamic_dp_diagnostic import solve

SEED = 2128
CONFIG = ExperimentConfig(
    duration_s=600.0,
    profile_name="stochastic_agri_workcycle",
    engine_map=RealisticDieselMap(low_load_efficiency=0.08, power_width_w=90000.0),
    motor_map=RealisticMotorMap(),
    accessory_for_all_w=18000.0,
    stochastic_disturbance_scale=0.25,
    stochastic_smooth_disturbances=True,
    engine_rated_w=260000.0,
    battery_capacity_wh=200000.0,
    battery_power_limit_w=150000.0,
    motor_peak_w=150000.0,
)


def json_default(value):
    """Convert NumPy scalar diagnostics without weakening their values."""
    if hasattr(value, "item"):
        return value.item()
    raise TypeError(f"not JSON serializable: {type(value).__name__}")


def model_for_config() -> OSECVTModel:
    parameters = replace(
        PowertrainParameters(), engine_rated_w=float(CONFIG.engine_rated_w),
        battery_capacity_wh=float(CONFIG.battery_capacity_wh),
        battery_power_limit_w=float(CONFIG.battery_power_limit_w),
        motor_peak_w=float(CONFIG.motor_peak_w))
    return OSECVTModel(parameters, engine_map=CONFIG.engine_map, motor_map=CONFIG.motor_map)


def motor_limits(model: OSECVTModel) -> tuple[float, float]:
    def largest(sign: float) -> float:
        low, high = 0.0, model.p.motor_peak_w
        for _ in range(32):
            middle = (low + high) / 2.0
            efficiency = model.motor_map.efficiency(2400.0, sign * middle)
            bus_w = (sign * middle / max(efficiency, 1e-9)
                     if sign > 0.0 else sign * middle * efficiency)
            if abs(bus_w) <= model.p.battery_power_limit_w:
                low = middle
            else:
                high = middle
        return low
    return largest(1.0), largest(-1.0)


def continuous_correction(path_w: list[float], profile) -> dict[str, object]:
    """Close SOC with a scalar full-future correction inside every hard bound."""
    model = model_for_config()
    max_assist_w, max_charge_w = motor_limits(model)
    demands = [model.demand(point.speed_mps, point.draft_n * point.soil_factor,
                           point.grade) + CONFIG.accessory_for_all_w
               for point in profile]

    def replay(bias_w: float) -> dict[str, object]:
        state = DrivelineState(soc=CONFIG.initial_soc)
        prior = None
        min_soc = max_soc = state.soc
        maximums = {
            "max_shortage_w": 0.0, "max_motor_power_violation_w": 0.0,
            "max_battery_power_violation_w": 0.0, "max_mg1_power_violation_w": 0.0,
            "max_mg1_speed_violation_rpm": 0.0, "max_mg2_speed_violation_rpm": 0.0,
            "max_engine_ramp_violation_w": 0.0,
        }
        feasible = True
        for requested_w, demand_w, point in zip(path_w, demands, profile):
            low = max(CONFIG.realistic_ool_minimum_engine_w, demand_w - max_assist_w)
            high = min(model.p.engine_rated_w, demand_w + max_charge_w)
            target = max(low, min(high, requested_w + bias_w))
            if prior is not None:
                ramp = CONFIG.realistic_ool_ramp_limit_w * model.p.dt_s
                reachable_low = max(low, prior - ramp)
                reachable_high = min(high, prior + ramp)
                if reachable_low > reachable_high + 1e-9:
                    feasible = False
                    break
                target = max(reachable_low, min(reachable_high, target))
                maximums["max_engine_ramp_violation_w"] = max(
                    maximums["max_engine_ramp_violation_w"], abs(target - prior) - ramp)
            prior = target
            state = model.step(state, demand_w, target, engine_on=True)
            min_soc = min(min_soc, state.soc)
            max_soc = max(max_soc, state.soc)
            report = model.constraint_report(demand_w, target, point.speed_mps)
            maximums["max_shortage_w"] = max(
                maximums["max_shortage_w"], max(0.0, demand_w - target - model.p.motor_peak_w))
            for key, value in report.items():
                maximums[f"max_{key}"] = max(maximums[f"max_{key}"], value)
        output: dict[str, object] = {
            "bias_w": bias_w, "fuel_l": model.equivalent_fuel_l(state),
            "soc_error": state.soc - CONFIG.initial_soc, "min_soc": min_soc,
            "max_soc": max_soc, "ramp_path_feasible": feasible, **maximums,
        }
        output["strict_valid"] = (
            feasible and abs(float(output["soc_error"])) <= CONFIG.terminal_soc_tolerance
            and all(float(output[key]) <= 1.0 for key in maximums))
        return output

    low, high = 0.0, 200000.0
    low_result, high_result = replay(low), replay(high)
    if float(high_result["soc_error"]) < 0.0:
        return {"available": False, "zero_bias": low_result, "high_bias": high_result}
    for _ in range(32):
        middle = (low + high) / 2.0
        middle_result = replay(middle)
        if float(middle_result["soc_error"]) < 0.0:
            low = middle
        else:
            high = middle
    corrected = replay(high)
    return {"available": True, "zero_bias": low_result, "corrected": corrected}


def main() -> None:
    profile = stochastic_agri_workcycle_profile(
        CONFIG.duration_s, seed=SEED,
        disturbance_scale=CONFIG.stochastic_disturbance_scale,
        smooth_disturbances=CONFIG.stochastic_smooth_disturbances)
    baseline = run_definition("realistic_ool", replace(CONFIG, seed=SEED))
    # The coarse 0.005 grid accumulated a continuous terminal-SOC drift.
    # Use a finer grid and rely on the replay screen rather than the grid
    # terminal state alone.
    result = solve(0.001, 4000.0, reconstruct_path=True, config=CONFIG, profile=profile,
                   return_path=True)
    path_w = result.pop("path_w", [])
    correction = continuous_correction(path_w, profile) if path_w else None
    if result.get("feasible"):
        result["saving_vs_realistic_ool_pct"] = (
            (float(baseline["fuel_l"]) - float(result["fuel_l"]))
            / float(baseline["fuel_l"]) * 100.0)
    output = {
        "purpose": (
            "Offline complete-future dynamic-programming diagnostic on one stochastic assumed-map seed; "
            "not an online controller result, formal bound, or manuscript performance result."),
        "seed": SEED,
        "constraints": {
            "stable_engine_floor_w": CONFIG.realistic_ool_minimum_engine_w,
            "engine_ramp_w_per_s": CONFIG.realistic_ool_ramp_limit_w,
            "battery_bus_limit_w": CONFIG.battery_power_limit_w,
            "motor_peak_w": CONFIG.motor_peak_w,
            "terminal_soc_tolerance": CONFIG.terminal_soc_tolerance,
        },
        "baseline": {key: baseline[key] for key in (
            "fuel_l", "soc_error", "valid", "max_shortage_w",
            "max_motor_power_violation_w", "max_battery_power_violation_w",
            "max_mg1_power_violation_w", "max_mg1_speed_violation_rpm",
            "max_mg2_speed_violation_rpm", "max_engine_ramp_violation_w")},
        "dp_result": result,
        "continuous_terminal_correction": correction,
    }
    path = ROOT / "results" / "paper2_assumed_stochastic_dp_diagnostic.json"
    path.write_text(json.dumps(output, ensure_ascii=False, indent=2,
                               default=json_default), encoding="utf-8")
    print(path)


if __name__ == "__main__":
    main()
