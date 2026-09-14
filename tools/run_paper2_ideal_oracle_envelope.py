"""Evaluate a declared full-information upper-bound case for paper two.

This script is deliberately separate from the strictly causal benchmark.  It
uses the same 300 kW virtual platform, traction/recovery profile generation,
engine floor, applied ramp, motor/bus limits, physical SOC bounds, and dynamic
OOL baseline, but assumes that the entire nominal smooth task is known.  A
task-level terminal SOC band of +/-0.01 is permitted.  Raw engine fuel and a
predeclared terminal-energy-normalized value are both reported.
"""
from __future__ import annotations

import json
from dataclasses import replace
from pathlib import Path
import sys

ROOT = Path(__file__).parents[1]
sys.path[:0] = [str(ROOT / "code"), str(ROOT / "code" / "energy_management")]

from common.profiles import smoothed_regenerative_low_load_agri_workcycle_profile
from experiments import ExperimentConfig, run_definition
from os_ecvt_model import LiteratureBSFCMap, RealisticDieselMap, RealisticMotorMap
from run_paper2_dynamic_dp_diagnostic import solve


TASK_SOC_TOLERANCE = 0.01
REFERENCE_FUEL_CONVERSION_EFFICIENCY = 0.42
FUEL_LOWER_HEATING_VALUE_J_KG = 42.7e6
FUEL_DENSITY_KG_L = 0.832
GRID_RESOLUTIONS = ((0.005, 4000.0, True), (0.002, 2000.0, False))


def json_default(value: object) -> object:
    """Convert NumPy scalar diagnostics while preserving their numeric values."""
    if hasattr(value, "item"):
        return value.item()
    raise TypeError(f"not JSON serializable: {type(value).__name__}")


def ideal_config(map_kind: str) -> ExperimentConfig:
    if map_kind == "literature_shaped":
        engine_map = LiteratureBSFCMap()
    elif map_kind == "steep_low_load_sensitivity":
        engine_map = RealisticDieselMap(low_load_efficiency=0.08, power_width_w=90000.0)
    else:
        raise ValueError(map_kind)
    return ExperimentConfig(
        duration_s=600.0,
        profile_name="smoothed_regenerative_low_load_agri_workcycle",
        engine_map=engine_map,
        motor_map=RealisticMotorMap(),
        accessory_for_all_w=18000.0,
        terminal_soc_tolerance=TASK_SOC_TOLERANCE,
        terminal_soc_correction_gain=1.0,
        regenerative_braking=True,
        regen_power_limit_w=45000.0,
        engine_rated_w=300000.0,
        battery_capacity_wh=200000.0,
        battery_power_limit_w=150000.0,
        motor_peak_w=150000.0,
        realistic_ool_minimum_engine_w=60000.0,
        realistic_ool_ramp_limit_w=40000.0,
    )


def saving_pct(baseline_l: float, candidate_l: float) -> float:
    return (baseline_l - candidate_l) / baseline_l * 100.0


def terminal_energy_correction_l(baseline_soc_error: float, candidate_soc_error: float,
                                 capacity_wh: float) -> dict[str, float]:
    """Charge a lower-energy candidate back to the paired OOL end energy.

    A positive correction is added to candidate fuel.  This fixed, declared
    conversion is not a second optimizer; it prevents raw fuel from being
    interpreted as a fair saving when the two trajectories end with different
    battery energy inside the allowed task-level SOC band.
    """
    delta_kwh = (baseline_soc_error - candidate_soc_error) * capacity_wh / 1000.0
    liters_per_kwh = (3.6e6 / (REFERENCE_FUEL_CONVERSION_EFFICIENCY
                                * FUEL_LOWER_HEATING_VALUE_J_KG
                                * FUEL_DENSITY_KG_L))
    return {
        "candidate_energy_deficit_vs_ool_kwh": delta_kwh,
        "reference_l_per_kwh": liters_per_kwh,
        "fuel_correction_l": delta_kwh * liters_per_kwh,
    }


def run_case(map_kind: str) -> dict[str, object]:
    config = ideal_config(map_kind)
    profile = smoothed_regenerative_low_load_agri_workcycle_profile(config.duration_s)
    baseline = run_definition("realistic_ool", config)
    grids: list[dict[str, object]] = []
    continuous: dict[str, object] | None = None

    for soc_step, engine_step_w, reconstruct_path in GRID_RESOLUTIONS:
        result = solve(soc_step, engine_step_w, reconstruct_path=reconstruct_path,
                       config=config, profile=profile)
        if result.get("feasible"):
            result["grid_saving_vs_ool_raw_fuel_pct"] = saving_pct(
                float(baseline["fuel_l"]), float(result["fuel_l"]))
        grids.append(result)
        if reconstruct_path:
            continuous = result.get("continuous_rollout")

    if continuous is None:
        raise RuntimeError("the declared coarse-grid run did not produce a continuous replay")
    continuous_fuel_l = float(continuous["fuel_l"])
    correction = terminal_energy_correction_l(
        float(baseline["soc_error"]), float(continuous["soc_error"]),
        float(config.battery_capacity_wh or 0.0))
    corrected_fuel_l = continuous_fuel_l + float(correction["fuel_correction_l"])
    hard_limits = (
        "max_shortage_w",
        "max_motor_power_violation_w",
        "max_battery_power_violation_w",
        "max_mg1_power_violation_w",
        "max_mg1_speed_violation_rpm",
        "max_mg2_speed_violation_rpm",
        "max_engine_ramp_violation_w",
    )
    return {
        "map_kind": map_kind,
        "baseline": {
            key: baseline[key] for key in (
                "fuel_l", "soc_error", "valid", "max_shortage_w",
                "max_motor_power_violation_w", "max_battery_power_violation_w",
                "max_mg1_power_violation_w", "max_mg1_speed_violation_rpm",
                "max_mg2_speed_violation_rpm", "max_engine_ramp_violation_w",
            )
        },
        "grid_resolutions": grids,
        "continuous_replay": continuous,
        "continuous_raw_saving_vs_ool_pct": saving_pct(
            float(baseline["fuel_l"]), continuous_fuel_l),
        "terminal_energy_normalization": {
            **correction,
            "candidate_energy_normalized_fuel_l": corrected_fuel_l,
            "energy_normalized_saving_vs_ool_pct": saving_pct(
                float(baseline["fuel_l"]), corrected_fuel_l),
        },
        "validity": {
            "ool_within_task_soc_band": bool(baseline["valid"]),
            "oracle_within_task_soc_band": bool(continuous["strict_valid"]),
            "all_continuous_hard_limit_violations_at_most_1": all(
                float(continuous[key]) <= 1.0 for key in hard_limits),
        },
    }


def validate_envelope(output: dict[str, object]) -> None:
    """Fail loudly if the reported idealized case loses its declared basis."""
    literature = output["literature_shaped"]
    steep = output["steep_low_load_sensitivity"]
    assert isinstance(literature, dict)
    assert isinstance(steep, dict)
    steep_normalized = steep["terminal_energy_normalization"]
    assert isinstance(steep_normalized, dict)

    checks = {
        "both_ool_baselines_within_task_soc_band": bool(
            literature["validity"]["ool_within_task_soc_band"]
            and steep["validity"]["ool_within_task_soc_band"]),
        "literature_shaped_oracle_rejected_by_continuous_soc": not bool(
            literature["validity"]["oracle_within_task_soc_band"]),
        "steep_oracle_within_task_soc_band": bool(
            steep["validity"]["oracle_within_task_soc_band"]),
        "steep_oracle_hard_limits_satisfied": bool(
            steep["validity"]["all_continuous_hard_limit_violations_at_most_1"]),
        "steep_continuous_raw_saving_at_least_20_pct": float(
            steep["continuous_raw_saving_vs_ool_pct"]) >= 20.0,
        "terminal_energy_normalization_is_conservative": (
            float(steep_normalized["fuel_correction_l"]) >= 0.0
            and float(steep_normalized["energy_normalized_saving_vs_ool_pct"])
            <= float(steep["continuous_raw_saving_vs_ool_pct"]))
    }
    output["acceptance_checks"] = checks
    failed = [name for name, passed in checks.items() if not passed]
    if failed:
        raise RuntimeError("idealized-envelope acceptance check failed: " + ", ".join(failed))


def main() -> None:
    output = {
        "purpose": (
            "Declared idealized full-information envelope. It is a non-causal "
            "virtual upper-bound diagnostic, not an online controller result, "
            "not an MPC fuel-saving result, and not a tractor-performance estimate."
        ),
        "protocol": {
            "common_with_main_platform": (
                "300 kW virtual platform; 200 kWh battery; 150 kW motor and battery bus; "
                "60 kW stable engine floor; 40 kW/s applied ramp; wheel-side regeneration; "
                "physical SOC bounds; common dynamic realistic-OOL baseline."
            ),
            "intentional_idealizations": (
                "Complete future nominal smooth-cycle demand is known to the offline DP; "
                "terminal SOC is a task-level +/-0.01 band rather than the strict causal "
                "benchmark's 1e-4 direct-fuel threshold."
            ),
            "energy_accounting": (
                "Raw engine fuel is reported separately from terminal-energy-normalized fuel. "
                "The latter returns a lower-energy oracle trajectory to its paired OOL end energy "
                "using a predeclared 0.42 conversion efficiency."
            ),
            "grid_resolutions": [
                {"soc_step": soc_step, "engine_step_w": engine_step_w}
                for soc_step, engine_step_w, _ in GRID_RESOLUTIONS
            ],
        },
        "literature_shaped": run_case("literature_shaped"),
        "steep_low_load_sensitivity": run_case("steep_low_load_sensitivity"),
    }
    validate_envelope(output)
    path = ROOT / "results" / "paper2_ideal_oracle_envelope.json"
    path.write_text(json.dumps(output, ensure_ascii=False, indent=2,
                               default=json_default), encoding="utf-8")
    print(path)


if __name__ == "__main__":
    main()
