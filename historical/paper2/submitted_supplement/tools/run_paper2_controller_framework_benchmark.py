"""Run the strict, causal controller-framework benchmark for paper 2.

The experiment deliberately does not search for a target fuel-saving number.
It compares controllers under one information set and one terminal-energy
rule.  ECMS equivalent factors are selected only on development seeds; the
selected factor and every other controller are evaluated unchanged on an
unseen test set.
"""
from __future__ import annotations

import json
import math
from pathlib import Path
import sys
from typing import Any

ROOT = Path(__file__).parents[1]
sys.path[:0] = [str(ROOT / "code"), str(ROOT / "code" / "energy_management")]

from experiments import (ExperimentConfig, _WORKCYCLE_SEGMENT_BOUNDARIES_S,
                         run_definition)
from os_ecvt_model import LiteratureBSFCMap, RealisticDieselMap, RealisticMotorMap


DEVELOPMENT_SEEDS = tuple(range(2200, 2206))
TEST_SEEDS = tuple(range(2220, 2240))
ECMS_FACTORS = (0.5, 0.75, 1.0, 1.25, 1.5, 2.0, 2.5, 3.0, 4.0, 5.0)
PHASE_TRACKING_GAIN = 0.75


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


def strict_valid(result: dict[str, object]) -> bool:
    """Require hard constraints and virtually identical terminal energy."""
    return bool(result["valid"]) and abs(float(result["soc_error"])) <= 1e-4


def compact(seed: int, result: dict[str, object], baseline: dict[str, object] | None) -> dict[str, object]:
    eligible = strict_valid(result)
    saving = None
    if baseline is not None and eligible and bool(baseline["strict_valid"]):
        saving = ((float(baseline["fuel_l"]) - float(result["fuel_l"]))
                  / float(baseline["fuel_l"]) * 100.0)
    return {
        "seed": seed,
        "fuel_l": float(result["fuel_l"]),
        "soc_error": float(result["soc_error"]),
        "strict_valid": eligible,
        "fallback_count": int(result["fallback_count"]),
        "ramp_envelope_infeasibility_count": int(result["ramp_envelope_infeasibility_count"]),
        "safety_filter_activation_count": int(result.get("safety_filter_activation_count", 0)),
        "terminal_set_violation_count": int(result.get("terminal_set_violation_count", 0)),
        "max_shortage_w": float(result["max_shortage_w"]),
        "max_motor_power_violation_w": float(result["max_motor_power_violation_w"]),
        "max_battery_power_violation_w": float(result["max_battery_power_violation_w"]),
        "max_mg1_power_violation_w": float(result["max_mg1_power_violation_w"]),
        "max_mg1_speed_violation_rpm": float(result["max_mg1_speed_violation_rpm"]),
        "max_mg2_speed_violation_rpm": float(result["max_mg2_speed_violation_rpm"]),
        "max_engine_ramp_violation_w": float(result["max_engine_ramp_violation_w"]),
        "saving_vs_same_seed_ool_pct": saving,
    }


def summarize(rows: list[dict[str, object]], requires_zero_fallback: bool = False) -> dict[str, object]:
    certified_rows = [
        row for row in rows
        if bool(row["strict_valid"])
        and (not requires_zero_fallback or (
            int(row["fallback_count"]) == 0
            and int(row["ramp_envelope_infeasibility_count"]) == 0))
    ]
    savings = [float(row["saving_vs_same_seed_ool_pct"]) for row in certified_rows
               if row["saving_vs_same_seed_ool_pct"] is not None]
    return {
        "strict_valid_rate": sum(bool(row["strict_valid"]) for row in rows) / len(rows),
        "certified_rate": len(certified_rows) / len(rows),
        "max_abs_terminal_soc_error": max(abs(float(row["soc_error"])) for row in rows),
        "mean_fuel_l": mean_ci([float(row["fuel_l"]) for row in rows]),
        "saving_pct": mean_ci(savings),
        "mean_fallback_count": sum(int(row["fallback_count"]) for row in rows) / len(rows),
        "mean_safety_filter_activation_count": (
            sum(int(row["safety_filter_activation_count"]) for row in rows) / len(rows)),
        "total_safety_filter_activation_count": sum(
            int(row["safety_filter_activation_count"]) for row in rows),
        "max_terminal_set_violation_count": max(
            int(row["terminal_set_violation_count"]) for row in rows),
    }


def protocol(map_kind: str) -> dict[str, Any]:
    if map_kind == "literature_shaped":
        engine_map = LiteratureBSFCMap()
        rated_power_w = 300000.0
        map_note = "LiteratureBSFCMap: literature-shaped efficiency sensitivity, not a target-platform calibration."
    elif map_kind == "steep_island_sensitivity":
        engine_map = RealisticDieselMap(low_load_efficiency=0.08, power_width_w=90000.0)
        # Keep the hardware platform identical to the literature-shaped arm.
        # Otherwise a high-demand seed can turn a map sensitivity into an
        # engine-rating sensitivity before controller performance is compared.
        rated_power_w = 300000.0
        map_note = "RealisticDieselMap with a deliberately steep low-load island on the same 300 kW virtual platform; uncalibrated sensitivity only."
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
        "engine_rated_w": rated_power_w,
        "battery_capacity_wh": 200000.0,
        "battery_power_limit_w": 150000.0,
        "motor_peak_w": 150000.0,
        "mpc_horizon": 8,
        "scenario_count": 5,
        "mpc_terminal_weight": 2000000.0,
        "stochastic_nominal_phase_preview": True,
        "stochastic_phase_residual_gain": 0.0,
        "map_note": map_note,
    }


def config_for(base: dict[str, Any], seed: int, **overrides: Any) -> ExperimentConfig:
    values = dict(base)
    values.pop("map_note")
    values.update(overrides, seed=seed)
    return ExperimentConfig(**values)


def baseline_rows(base: dict[str, Any], seeds: tuple[int, ...]) -> tuple[dict[int, dict[str, object]], dict[int, dict[str, object]]]:
    raw, rows = {}, {}
    for seed in seeds:
        result = run_definition("realistic_ool", config_for(base, seed))
        raw[seed] = result
        rows[seed] = compact(seed, result, None)
        print("ool", seed, rows[seed]["strict_valid"], f"{rows[seed]['fuel_l']:.6f}", flush=True)
    return raw, rows


def nominal_phase_targets(base: dict[str, Any]) -> tuple[float, ...]:
    """Derive a public nominal schedule without inspecting any random seed."""
    nominal = dict(base)
    nominal["stochastic_disturbance_scale"] = 0.0
    result = run_definition("realistic_ool", config_for(nominal, seed=0))
    targets = []
    for segment in range(len(_WORKCYCLE_SEGMENT_BOUNDARIES_S) - 1):
        commands = []
        for index, command_w in enumerate(result["commands_w"]):
            local_s = (index * 0.1) % _WORKCYCLE_SEGMENT_BOUNDARIES_S[-1]
            if (_WORKCYCLE_SEGMENT_BOUNDARIES_S[segment] <= local_s
                    < _WORKCYCLE_SEGMENT_BOUNDARIES_S[segment + 1]):
                commands.append(float(command_w))
        targets.append(sum(commands) / len(commands))
    return tuple(targets)


def evaluate(name: str, base: dict[str, Any], seeds: tuple[int, ...],
             baseline: dict[int, dict[str, object]], **overrides: Any) -> dict[str, object]:
    rows = []
    for seed in seeds:
        result = run_definition(name, config_for(base, seed, **overrides))
        row = compact(seed, result, baseline[seed])
        rows.append(row)
        print(name, seed, row["strict_valid"], row["fallback_count"],
              row["safety_filter_activation_count"],
              f"{row['fuel_l']:.6f}", flush=True)
    return {"controller": name, "overrides": overrides, "rows": rows,
            "summary": summarize(rows, requires_zero_fallback=name.endswith("mpc"))}


def select_ecms_factor(base: dict[str, Any], baseline: dict[int, dict[str, object]]) -> tuple[float, list[dict[str, object]]]:
    candidates = []
    for factor in ECMS_FACTORS:
        outcome = evaluate("adaptive_ecms", base, DEVELOPMENT_SEEDS, baseline,
                           adaptive_ecms_equivalence_factor=factor)
        outcome["equivalence_factor"] = factor
        candidates.append(outcome)
    eligible = [entry for entry in candidates
                if float(entry["summary"]["certified_rate"]) == 1.0]
    if not eligible:
        raise RuntimeError("No ECMS factor was strictly valid on every development seed")
    winner = min(eligible, key=lambda entry: float(entry["summary"]["mean_fuel_l"]["mean"]))
    return float(winner["equivalence_factor"]), candidates


def run_map(map_kind: str) -> dict[str, object]:
    base = protocol(map_kind)
    dev_raw, dev_baseline = baseline_rows(base, DEVELOPMENT_SEEDS)
    factor, ecms_development = select_ecms_factor(base, dev_baseline)
    phase_targets = nominal_phase_targets(base)
    test_raw, test_baseline = baseline_rows(base, TEST_SEEDS)
    del dev_raw, test_raw
    test_controllers = {
        "map_aware_ecms": evaluate("adaptive_ecms", base, TEST_SEEDS, test_baseline,
                                    adaptive_ecms_equivalence_factor=factor),
        "nominal_phase_policy": evaluate(
            "phase_policy", base, TEST_SEEDS, test_baseline,
            phase_policy_targets_w=phase_targets,
            phase_policy_tracking_gain=PHASE_TRACKING_GAIN),
        "deterministic_mpc": evaluate("deterministic_mpc", base, TEST_SEEDS, test_baseline),
        "scenario_mpc": evaluate("robust_mpc", base, TEST_SEEDS, test_baseline),
        "terminal_set_scenario_mpc": evaluate(
            "recursive_feasible_mpc", base, TEST_SEEDS, test_baseline),
    }
    ool_rows = list(test_baseline.values())
    return {
        "map_note": base["map_note"],
        "selected_ecms_equivalence_factor": factor,
        "ecms_development_candidates": ecms_development,
        "frozen_nominal_phase_targets_w": list(phase_targets),
        "test_ool": {"rows": ool_rows, "summary": summarize(ool_rows)},
        "test_controllers": test_controllers,
    }


def main() -> None:
    output = {
        "purpose": (
            "Strict causal controller-framework comparison for a parameterized hybrid-agricultural "
            "virtual prototype. It is a simulation sensitivity study, not tractor hardware validation."
        ),
        "protocol": {
            "development_seeds": list(DEVELOPMENT_SEEDS),
            "test_seeds": list(TEST_SEEDS),
            "online_information": "Current demand and SOC for ECMS; public zero-disturbance task phase plus current demand and SOC for the nominal phase policy; no evaluated-seed future samples for any online controller.",
            "common_constraints": "60 kW stable engine floor, 40 kW/s applied engine ramp, 150 kW motor and battery-bus limits, MG proxy limits, zero traction shortage, and terminal SOC tolerance 1e-4.",
            "energy_accounting": "Direct-fuel paired comparisons require each result to satisfy the 1e-4 terminal-SOC threshold. The terminal-energy governor gain of 3 is identical for all online methods.",
            "selection": "Ten predeclared ECMS equivalent factors are ranked by mean fuel only after every development run is strictly valid. The selected factor is frozen before testing. The phase-policy schedule comes only from the public zero-disturbance nominal task, and MPC settings are fixed before either split.",
            "mpc_certification": "MPC additionally requires zero experiment-runner finite-candidate fallback and zero forecast ramp-envelope infeasibility. The terminal-set MPC separately reports every internal safety-filter intervention and requires zero terminal-set violations.",
        },
        "literature_shaped": run_map("literature_shaped"),
        "steep_island_sensitivity": run_map("steep_island_sensitivity"),
    }
    path = ROOT / "results" / "paper2_controller_framework_benchmark.json"
    path.write_text(json.dumps(output, ensure_ascii=False, indent=2), encoding="utf-8")
    print(path)


if __name__ == "__main__":
    main()
