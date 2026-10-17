"""Strict causal cross-cycle audit for the paper-2 virtual prototype.

The audit keeps the same terminal-energy rule and controller information set
used by the manuscript benchmark, then changes only the public work-cycle
profile.  It is an independent robustness check, not a search for a favorable
fuel-saving value.
"""
from __future__ import annotations

import json
import math
from pathlib import Path
import sys

ROOT = Path(__file__).parents[1]
sys.path[:0] = [str(ROOT / "code"), str(ROOT / "code" / "energy_management")]

from experiments import ExperimentConfig, run_definition
from os_ecvt_model import LiteratureBSFCMap, RealisticMotorMap

SEEDS = tuple(range(2026, 2046))
PROFILES = ("agri_workcycle", "high_variability", "stochastic_agri_workcycle")
CONTROLLERS = ("realistic_ool", "adaptive_ecms", "recursive_feasible_mpc")


def mean_ci(values: list[float]) -> dict[str, float] | None:
    if not values:
        return None
    mean = sum(values) / len(values)
    if len(values) == 1:
        return {"n": 1, "mean": mean, "std": 0.0,
                "ci95_low": mean, "ci95_high": mean}
    std = (sum((value - mean) ** 2 for value in values) / (len(values) - 1)) ** 0.5
    half = 2.093 * std / math.sqrt(len(values))
    return {"n": len(values), "mean": mean, "std": std,
            "ci95_low": mean - half, "ci95_high": mean + half}


def strict_valid(result: dict[str, object]) -> bool:
    return bool(result["valid"]) and abs(float(result["soc_error"])) <= 1e-4


def certified(result: dict[str, object], controller: str) -> bool:
    if not strict_valid(result):
        return False
    if int(result["fallback_count"]) != 0:
        return False
    if int(result["ramp_envelope_infeasibility_count"]) != 0:
        return False
    if controller == "recursive_feasible_mpc" and int(result.get("terminal_set_violation_count", 0)) != 0:
        return False
    return True


def compact(seed: int, result: dict[str, object], controller: str,
            baseline: dict[str, object] | None) -> dict[str, object]:
    valid = strict_valid(result)
    cert = certified(result, controller)
    saving = None
    if baseline is not None and valid and bool(baseline["strict_valid"]):
        saving = ((float(baseline["fuel_l"]) - float(result["fuel_l"]))
                  / float(baseline["fuel_l"]) * 100.0)
    return {
        "seed": seed,
        "fuel_l": float(result["fuel_l"]),
        "soc_error": float(result["soc_error"]),
        "strict_valid": valid,
        "certified": cert,
        "fallback_count": int(result["fallback_count"]),
        "ramp_envelope_infeasibility_count": int(result["ramp_envelope_infeasibility_count"]),
        "terminal_set_violation_count": int(result.get("terminal_set_violation_count", 0)),
        "max_shortage_w": float(result["max_shortage_w"]),
        "max_battery_power_violation_w": float(result["max_battery_power_violation_w"]),
        "max_engine_ramp_violation_w": float(result["max_engine_ramp_violation_w"]),
        "saving_vs_same_seed_ool_pct": saving,
    }


def base_config(profile: str) -> dict[str, object]:
    return {
        "duration_s": 600.0,
        "profile_name": profile,
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


def summarize(rows: list[dict[str, object]], controller: str) -> dict[str, object]:
    savings = [float(row["saving_vs_same_seed_ool_pct"]) for row in rows
               if row["saving_vs_same_seed_ool_pct"] is not None]
    return {
        "strict_valid_rate": sum(bool(row["strict_valid"]) for row in rows) / len(rows),
        "certified_rate": sum(bool(row["certified"]) for row in rows) / len(rows),
        "max_abs_terminal_soc_error": max(abs(float(row["soc_error"])) for row in rows),
        "fuel_l": mean_ci([float(row["fuel_l"]) for row in rows]),
        "saving_pct": mean_ci(savings),
        "mean_fallback_count": sum(int(row["fallback_count"]) for row in rows) / len(rows),
        "mean_ramp_envelope_infeasibility_count": (
            sum(int(row["ramp_envelope_infeasibility_count"]) for row in rows) / len(rows)),
        "controller": controller,
    }


def run_profile(profile: str) -> dict[str, object]:
    base = base_config(profile)
    rows = {name: [] for name in CONTROLLERS}
    for seed in SEEDS:
        baseline_result = run_definition("realistic_ool", ExperimentConfig(seed=seed, **base))
        baseline_row = compact(seed, baseline_result, "realistic_ool", None)
        rows["realistic_ool"].append(baseline_row)
        for controller in ("adaptive_ecms", "recursive_feasible_mpc"):
            result = run_definition(controller, ExperimentConfig(seed=seed, **base))
            row = compact(seed, result, controller, baseline_row)
            rows[controller].append(row)
        print(profile, seed, flush=True)
    return {
        "profile": profile,
        "rows": rows,
        "summaries": {
            controller: summarize(values, controller)
            for controller, values in rows.items()
        },
    }


def main() -> None:
    output = {
        "seeds": list(SEEDS),
        "protocol": {
            "profiles": list(PROFILES),
            "duration_s": 600.0,
            "engine_map": "LiteratureBSFCMap: literature-shaped sensitivity, not platform calibration",
            "accessory_for_all_w": 18000.0,
            "terminal_soc_tolerance": 1e-4,
            "certification_rule": "strict validity, zero fallback, zero forecast ramp-envelope infeasibility, and zero terminal-set violation for recursive MPC",
            "information_set": "causal present demand/SOC and public cycle phase only; no realized future samples or offline SOC reference",
            "note": "Cross-cycle virtual-prototype audit; not hardware validation and not a target-saving optimization. The offline SOC reference is disabled for every profile.",
        },
        "profiles": {profile: run_profile(profile) for profile in PROFILES},
    }
    path = ROOT / "results" / "paper2_crosscycle_strict_scan.json"
    path.write_text(json.dumps(output, ensure_ascii=False, indent=2), encoding="utf-8")
    print(path)


if __name__ == "__main__":
    main()
