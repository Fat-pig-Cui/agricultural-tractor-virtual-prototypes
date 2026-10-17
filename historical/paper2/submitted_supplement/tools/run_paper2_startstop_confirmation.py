"""Independent confirmation of the frozen shared start/stop MPC sensitivity.

The candidate was selected in ``run_paper2_startstop_screen.py`` using its
development split and evaluated once on that script's holdout split.  This
script does not screen alternatives: it uses a further, disjoint seed set to
check whether the selected setting remains feasible and fuel-positive under
the same causal information, plant, and constraints.
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


# These seeds are disjoint from the screen's 2026--2045 development/holdout
# splits and the existing phase-policy confirmation split (2218--2231).
CONFIRMATION_SEEDS = tuple(range(2232, 2246))

BASE: dict[str, Any] = {
    "duration_s": 600.0,
    "profile_name": "stochastic_agri_workcycle",
    "engine_map": LiteratureBSFCMap(),
    "motor_map": RealisticMotorMap(),
    "accessory_for_all_w": 18000.0,
    "mpc_terminal_weight": 2000000.0,
    "scenario_count": 5,
    "stochastic_disturbance_scale": 0.25,
    "stochastic_smooth_disturbances": True,
    "stochastic_offline_reference": False,
    "stochastic_nominal_reference": False,
    "stochastic_nominal_phase_preview": False,
    "engine_rated_w": 300000.0,
    "battery_capacity_wh": 200000.0,
    "battery_power_limit_w": 150000.0,
    "motor_peak_w": 150000.0,
    "engine_start_stop": True,
    "engine_stop_threshold_w": 25000.0,
    "engine_restart_threshold_w": 45000.0,
    "engine_minimum_on_s": 10.0,
    "engine_minimum_off_s": 5.0,
    "engine_start_fuel_g": 1.5,
}


def mean_ci(values: list[float]) -> dict[str, float] | None:
    if not values:
        return None
    mean = sum(values) / len(values)
    if len(values) == 1:
        return {"n": 1, "mean": mean, "std": 0.0,
                "ci95_low": mean, "ci95_high": mean}
    std = (sum((value - mean) ** 2 for value in values) / (len(values) - 1)) ** 0.5
    critical = {14: 2.160}.get(len(values), 1.960)
    half_width = critical * std / math.sqrt(len(values))
    return {"n": len(values), "mean": mean, "std": std,
            "ci95_low": mean - half_width, "ci95_high": mean + half_width}


def compact(seed: int, result: dict[str, object]) -> dict[str, object]:
    certified = (bool(result["valid"])
                 and int(result["fallback_count"]) == 0
                 and int(result["ramp_envelope_infeasibility_count"]) == 0)
    return {
        "seed": seed,
        "fuel_l": float(result["fuel_l"]),
        "soc_error": float(result["soc_error"]),
        "valid": bool(result["valid"]),
        "certified": certified,
        "fallback_count": int(result["fallback_count"]),
        "ramp_envelope_infeasibility_count": int(result["ramp_envelope_infeasibility_count"]),
        "max_shortage_w": float(result["max_shortage_w"]),
        "max_motor_power_violation_w": float(result["max_motor_power_violation_w"]),
        "max_battery_power_violation_w": float(result["max_battery_power_violation_w"]),
        "max_mg1_power_violation_w": float(result["max_mg1_power_violation_w"]),
        "max_mg1_speed_violation_rpm": float(result["max_mg1_speed_violation_rpm"]),
        "max_mg2_speed_violation_rpm": float(result["max_mg2_speed_violation_rpm"]),
        "max_engine_ramp_violation_w": float(result["max_engine_ramp_violation_w"]),
        "engine_starts": int(result["engine_starts"]),
        "start_stop_transition_count": int(result["start_stop_transition_count"]),
    }


def main() -> None:
    baseline_rows: list[dict[str, object]] = []
    mpc_rows: list[dict[str, object]] = []
    for seed in CONFIRMATION_SEEDS:
        config = ExperimentConfig(seed=seed, **BASE)
        baseline = compact(seed, run_definition("realistic_ool", config))
        mpc = compact(seed, run_definition("robust_mpc", config))
        saving = None
        if bool(baseline["certified"]) and bool(mpc["certified"]):
            saving = ((float(baseline["fuel_l"]) - float(mpc["fuel_l"]))
                      / float(baseline["fuel_l"]) * 100.0)
        mpc["saving_vs_same_seed_ool_pct"] = saving
        baseline_rows.append(baseline)
        mpc_rows.append(mpc)
        print(seed, baseline["certified"], mpc["certified"],
              f"{baseline['fuel_l']:.6f}", f"{mpc['fuel_l']:.6f}", flush=True)

    savings = [float(row["saving_vs_same_seed_ool_pct"]) for row in mpc_rows
               if row["saving_vs_same_seed_ool_pct"] is not None]
    summary = mean_ci(savings)
    all_pairs_certified = len(savings) == len(CONFIRMATION_SEEDS)
    positive_with_lower_ci = summary is not None and float(summary["ci95_low"]) > 0.0
    output = {
        "purpose": "Independent confirmation of the frozen top-ranked shared start/stop sensitivity.",
        "source_screen": "results/paper2_startstop_screen.json",
        "confirmation_seeds": list(CONFIRMATION_SEEDS),
        "protocol": {
            "cycle": "600 s continuous stochastic agricultural work cycle",
            "engine_map": "LiteratureBSFCMap",
            "online_information": "present measured demand only; no evaluated-seed future samples or offline reference",
            "baseline": "same-seed realistic dynamic OOL with the identical start/stop supervisor",
            "frozen_start_stop_setting": "25 kW stop, 45 kW restart, 10 s minimum-on, 5 s minimum-off, 1.5 g/start proxy",
            "shared_constraints": "40 kW/s running-engine ramp, 60 kW stable-power floor, 150 kW motor and battery-bus limits, terminal SOC tolerance 0.01",
            "certification_rule": "all hard validity conditions, zero controller fallback, and zero forecast ramp-envelope infeasibility",
            "predeclared_success_rule": "all 14 pairs certified and paired 95% CI lower bound above zero",
            "scope_limit": "Start/stop transitions are operating-mode changes and are not treated as ordinary running-engine 40 kW/s ramp events. This is a shared modeled sensitivity, not hardware validation.",
        },
        "baseline_rows": baseline_rows,
        "scenario_mpc_rows": mpc_rows,
        "baseline_certified_rate": sum(bool(row["certified"]) for row in baseline_rows) / len(baseline_rows),
        "scenario_mpc_certified_rate": sum(bool(row["certified"]) for row in mpc_rows) / len(mpc_rows),
        "paired_saving_pct": summary,
        "predeclared_success": bool(all_pairs_certified and positive_with_lower_ci),
    }
    path = ROOT / "results" / "paper2_startstop_confirmation.json"
    path.write_text(json.dumps(output, ensure_ascii=False, indent=2), encoding="utf-8")
    print(path)


if __name__ == "__main__":
    main()
