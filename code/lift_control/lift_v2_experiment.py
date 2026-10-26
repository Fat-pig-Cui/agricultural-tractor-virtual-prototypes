"""End-to-end controller comparison on the Paper 1 two-chamber V2 plant."""
from __future__ import annotations

from dataclasses import dataclass, replace
from math import tanh
from random import Random

from hydraulic_v2 import (HydraulicV2Parameters, InterfaceObserver,
                          TwoChamberHydraulicPlant, noisy_measurement)


@dataclass(frozen=True)
class LiftV2Config:
    duration_s: float = 300.0
    seed: int = 4100
    post_step_load_n: float = 14_000.0
    load_step_time_s: float = 60.0
    leakage_scale: float = 1.0
    temperature_start_c: float = 25.0
    temperature_end_c: float = 50.0
    position_bias_m: float = 0.0
    pressure_bias_pa: float = 0.0
    position_noise_scale: float = 1.0
    pressure_noise_scale: float = 1.0
    accumulator_flow_scale: float = 1.0
    mode_dwell_s: float = 8.0
    lock_pressure_deficit_pa: float = 0.10e6
    accumulator_pressure_deficit_pa: float = 0.30e6
    lock_error_m: float = 0.0025
    accumulator_error_m: float = 0.004
    # Optional deterministic load schedule for the Reviewer 3 stress audit.
    # Each pair is (time in seconds, load in newtons); the last active pair
    # remains in force until the next pair. The empty tuple preserves the
    # submitted single-step protocol exactly.
    load_schedule: tuple[tuple[float, float], ...] = ()
    accumulator_enabled: bool = True
    # Explicit audit-only tuning interface. Defaults preserve all commands.
    tracking_gain_scale: float = 1.0
    accumulator_gain_scale: float = 1.0
    hold_main_valve_limit: float | None = None


@dataclass
class ControllerMemory:
    position_integral: float = 0.0
    pressure_integral: float = 0.0
    hold_counter: int = 0
    hold_started: bool = False
    hold_start_time_s: float | None = None
    mode: str = "TRACK"
    mode_dwell_steps: int = 0
    switches: int = 0


def smooth_reference(time_s: float) -> tuple[float, float, float]:
    duration = 8.0
    progress = max(0.0, min(1.0, time_s / duration))
    blend = 3.0 * progress ** 2 - 2.0 * progress ** 3
    position = 0.15 + 0.20 * blend
    if progress >= 1.0:
        return position, 0.0, 0.0
    velocity = 0.20 * (6.0 * progress - 6.0 * progress ** 2) / duration
    acceleration = 0.20 * (6.0 - 12.0 * progress) / duration ** 2
    return position, velocity, acceleration


def _pressure_command(target_delta_pa: float, measured_delta_pa: float,
                      memory: ControllerMemory, dt_s: float,
                      allow_integral: bool = True) -> float:
    error_mpa = (target_delta_pa - measured_delta_pa) / 1.0e6
    if allow_integral:
        memory.pressure_integral = max(-0.3, min(
            0.3, memory.pressure_integral + error_mpa * dt_s))
    return max(-1.0, min(1.0, 0.70 * error_mpa
                         + 0.05 * memory.pressure_integral))


def run_lift_v2(controller: str, config: LiftV2Config = LiftV2Config(), *,
                plant_overrides: dict | None = None, integration_substeps: int = 1,
                observer_variant: str = "shared", baseline_dwell_s: float = 0.0,
                trace_interval_s: float | None = None,
                integration_scheme: str = "euler") -> dict[str, object]:
    """Replay frozen control code with optional, explicitly labelled audit arms.

    The controller and Gaussian samples remain at 10 ms when only the plant
    integration is refined. Defaults preserve the submitted numerical path.
    """
    if integration_substeps < 1 or int(integration_substeps) != integration_substeps:
        raise ValueError("integration_substeps must be a positive integer")
    if integration_scheme not in ("euler", "rk4"):
        raise ValueError("integration_scheme must be euler or rk4")
    rng = Random(config.seed)
    control_params = HydraulicV2Parameters()
    base = replace(control_params, **(plant_overrides or {}))
    params = replace(
        base,
        sensor_position_std_m=base.sensor_position_std_m * config.position_noise_scale,
        sensor_pressure_std_pa=base.sensor_pressure_std_pa * config.pressure_noise_scale,
        accumulator_valve_coefficient_m3_s_pa_sqrt=(
            base.accumulator_valve_coefficient_m3_s_pa_sqrt
            * config.accumulator_flow_scale),
    )
    plant = TwoChamberHydraulicPlant(params)
    integration_plant = (plant if integration_substeps == 1 else
        TwoChamberHydraulicPlant(replace(params, dt_s=params.dt_s/integration_substeps)))
    state = plant.initial_state()
    observer = InterfaceObserver(params.dt_s, control_params.piston_area_m2,
                                 control_params.stiffness_n_m)
    observer.x_hat = state.x_m
    observer.p_a_hat_pa = state.p_a_pa
    observer.p_b_hat_pa = state.p_b_pa
    memory = ControllerMemory()
    step_count = int(config.duration_s / params.dt_s)
    required_hold_steps = int(1.0 / params.dt_s)
    minimum_dwell_steps = int(config.mode_dwell_s / params.dt_s)
    errors = []
    post_transition_errors = []
    hold_positions = []
    commands = []
    accumulator_commands = []
    pressure_peaks = []
    relief_count = 0
    accumulator_initial_oil = (params.accumulator_shell_volume_m3
                               - state.accumulator_gas_volume_m3)
    previous_command = 0.0
    previous_measured_x = state.x_m
    trace = []
    stroke_hits = 0
    minimum_accumulator_pressure = plant.accumulator_pressure(state)
    accumulator_active_samples = 0
    mode_samples = {}
    hold_confirmation_time_s = None
    hold_window_start_time_s = None

    for step in range(step_count):
        time_s = step * params.dt_s
        reference, reference_velocity, reference_acceleration = smooth_reference(time_s)
        if config.load_schedule:
            load_n = config.load_schedule[0][1]
            for schedule_time, scheduled_load in config.load_schedule:
                if time_s >= schedule_time:
                    load_n = scheduled_load
                else:
                    break
        else:
            load_n = 9000.0 if time_s < config.load_step_time_s else config.post_step_load_n
        temperature_c = (config.temperature_start_c
                         + (config.temperature_end_c - config.temperature_start_c)
                         * step / max(1, step_count - 1))
        measured_x, measured_p_a, measured_p_b = noisy_measurement(
            state, params, rng, config.pressure_bias_pa, config.position_bias_m)
        observer.update(measured_x, measured_p_a, measured_p_b,
                        previous_command, plant)
        if observer_variant == "raw":
            observer.x_hat = measured_x
            observer.v_hat = (measured_x - previous_measured_x) / params.dt_s
            observer.p_a_hat_pa, observer.p_b_hat_pa = measured_p_a, measured_p_b
            observer.load_hat_n = 9000.0
        elif observer_variant == "fixed_load":
            observer.load_hat_n = 9000.0
        elif observer_variant != "shared":
            raise ValueError("observer_variant must be shared, fixed_load, or raw")
        previous_measured_x = measured_x
        error = reference - observer.x_hat
        measured_delta = observer.p_a_hat_pa - observer.p_b_hat_pa
        velocity_error = reference_velocity - observer.v_hat
        memory.mode_dwell_steps += 1

        if (time_s >= 8.0 and not memory.hold_started
                and abs(error) <= 0.010 and abs(observer.v_hat) <= 0.003):
            memory.hold_counter += 1
        elif not memory.hold_started:
            memory.hold_counter = 0
        if not memory.hold_started and memory.hold_counter >= required_hold_steps:
            memory.hold_started = True
            memory.hold_start_time_s = time_s - 1.0
            hold_confirmation_time_s = time_s
            hold_window_start_time_s = time_s + params.dt_s
            memory.mode = "FINE_TRIM"
            memory.mode_dwell_steps = 0

        estimated_load = max(3000.0, min(20_000.0, observer.load_hat_n))
        if controller in ("pid_lock", "pid_accumulator"):
            memory.position_integral = max(-0.05, min(
                0.05, memory.position_integral + error * params.dt_s))
            desired_acceleration = (reference_acceleration + (650.0 * config.tracking_gain_scale) * error
                                    + (90.0 * config.tracking_gain_scale) * velocity_error
                                    + (20.0 * config.tracking_gain_scale) * memory.position_integral)
            target_force = (estimated_load + control_params.stiffness_n_m * reference
                            + control_params.viscous_n_s_m * reference_velocity
                            + control_params.mass_kg * desired_acceleration)
            target_delta = target_force / control_params.piston_area_m2
        elif controller in ("smc_lock", "smc_accumulator"):
            sliding = 18.0 * error + velocity_error
            desired_acceleration = (reference_acceleration + (650.0 * config.tracking_gain_scale) * error
                                    + (90.0 * config.tracking_gain_scale) * velocity_error)
            robust_force = 1200.0 * tanh(sliding / 0.006)
            target_force = (estimated_load + control_params.stiffness_n_m * reference
                            + control_params.viscous_n_s_m * reference_velocity
                            + control_params.mass_kg * desired_acceleration
                            + robust_force)
            target_delta = target_force / control_params.piston_area_m2
        elif controller == "observer_hybrid":
            desired_acceleration = (reference_acceleration + (650.0 * config.tracking_gain_scale) * error
                                    + (90.0 * config.tracking_gain_scale) * velocity_error)
            target_force = (estimated_load + control_params.stiffness_n_m * reference
                            + control_params.viscous_n_s_m * reference_velocity
                            + control_params.mass_kg * desired_acceleration)
            target_delta = target_force / control_params.piston_area_m2
        else:
            raise ValueError(f"unknown controller: {controller}")

        command = _pressure_command(target_delta, measured_delta, memory,
                                    params.dt_s)
        accumulator_valve = 0.0
        if memory.hold_started:
            if controller in ("pid_lock", "smc_lock"):
                command = 0.0
                new_mode = "LOCK"
            elif controller in ("pid_accumulator", "smc_accumulator"):
                new_mode = "ACCUMULATOR" if error > 0.002 else "LOCK"
                if baseline_dwell_s and memory.mode_dwell_steps * params.dt_s < baseline_dwell_s:
                    new_mode = memory.mode
                limit = 0.08 if config.hold_main_valve_limit is None else config.hold_main_valve_limit
                command = max(-limit, min(limit, command))
                accumulator_valve = max(0.0, min(1.0, (80.0 * config.accumulator_gain_scale) * max(error - 0.001, 0.0)))
                if baseline_dwell_s and new_mode != "ACCUMULATOR":
                    accumulator_valve = 0.0
            else:
                pressure_deficit = target_delta - measured_delta
                if memory.mode == "ACCUMULATOR":
                    request_accumulator = (pressure_deficit > config.lock_pressure_deficit_pa * 0.5
                                           or error > config.lock_error_m * 0.6)
                else:
                    request_accumulator = (pressure_deficit > config.accumulator_pressure_deficit_pa
                                           or error > config.accumulator_error_m)
                if memory.mode == "LOCK":
                    request_lock = (abs(error) < config.lock_error_m * 1.25
                                    and abs(observer.v_hat) < 0.0015
                                    and pressure_deficit < config.accumulator_pressure_deficit_pa * 1.15)
                else:
                    request_lock = (abs(error) < config.lock_error_m
                                    and abs(observer.v_hat) < 0.0015
                                    and pressure_deficit < config.lock_pressure_deficit_pa)
                new_mode = memory.mode
                if memory.mode_dwell_steps >= minimum_dwell_steps:
                    if request_accumulator:
                        new_mode = "ACCUMULATOR"
                    elif request_lock:
                        new_mode = "LOCK"
                    else:
                        new_mode = "FINE_TRIM"
                if new_mode == "LOCK":
                    command = 0.0
                else:
                    limit = 0.10 if config.hold_main_valve_limit is None else config.hold_main_valve_limit
                    command = max(-limit, min(limit, command))
                if new_mode == "ACCUMULATOR":
                    accumulator_valve = max(0.0, min(
                        1.0, (1.5 * config.accumulator_gain_scale) * max(pressure_deficit, 0.0) / 1.0e6
                        + (60.0 * config.accumulator_gain_scale) * max(error - 0.001, 0.0)))
            if not config.accumulator_enabled:
                accumulator_valve = 0.0
            if new_mode != memory.mode:
                memory.mode = new_mode
                memory.mode_dwell_steps = 0
                memory.switches += 1

        for _ in range(integration_substeps):
            if integration_scheme == "rk4":
                result = integration_plant.step_rk4(
                    state, command, load_n, temperature_c,
                    accumulator_valve=accumulator_valve,
                    leakage_scale=config.leakage_scale)
            else:
                result = integration_plant.step(
                    state, command, load_n, temperature_c,
                    accumulator_valve=accumulator_valve,
                    leakage_scale=config.leakage_scale)
            state = result.state
            relief_count += int(result.relief_active)
            stroke_hits += int(state.x_m <= 0.0 or state.x_m >= params.stroke_m)
        p_acc = plant.accumulator_pressure(state)
        minimum_accumulator_pressure = min(minimum_accumulator_pressure, p_acc)
        accumulator_active_samples += int(accumulator_valve > 0)
        mode_samples[memory.mode] = mode_samples.get(memory.mode, 0) + 1
        if trace_interval_s is not None and step % max(1, round(trace_interval_s/params.dt_s)) == 0:
            trace.append(dict(t_s=time_s, x_m=state.x_m, error_mm=(reference-state.x_m)*1000,
                state_time_s=time_s + params.dt_s,
                p_a_mpa=state.p_a_pa/1e6, p_b_mpa=state.p_b_pa/1e6,
                p_acc_mpa=p_acc/1e6, command=command, accumulator_valve=accumulator_valve,
                mode=memory.mode, load_estimate_n=observer.load_hat_n))
        previous_command = command
        errors.append(reference - state.x_m)
        if time_s >= 8.0:
            post_transition_errors.append(reference - state.x_m)
        if memory.hold_started:
            hold_positions.append(state.x_m)
        commands.append(command)
        accumulator_commands.append(accumulator_valve)
        pressure_peaks.append(max(state.p_a_pa, state.p_b_pa))

    hold_drop = None
    if hold_positions:
        hold_drop = max(0.0, hold_positions[0] - min(hold_positions))
    post_abs = [abs(value) for value in post_transition_errors]
    accumulator_final_oil = (params.accumulator_shell_volume_m3
                             - state.accumulator_gas_volume_m3)
    output = {
        "controller": controller,
        "seed": config.seed,
        "hold_started": memory.hold_started,
        "hold_start_time_s": hold_window_start_time_s,
        "hold_confirmation_time_s": hold_confirmation_time_s,
        "legacy_hold_start_time_s": memory.hold_start_time_s,
        "hold_start_position_m": hold_positions[0] if hold_positions else None,
        "hold_min_position_m": min(hold_positions) if hold_positions else None,
        "hold_sample_count": len(hold_positions),
        "metric_schema": "endpoint-hold-window-v2; legacy numeric drop unchanged",
        "final_mode": memory.mode,
        "mode_switches": memory.switches,
        "hold_drop_mm": None if hold_drop is None else hold_drop * 1000.0,
        "post_transition_rmse_mm": (
            (sum(value * value for value in post_transition_errors)
             / max(1, len(post_transition_errors))) ** 0.5 * 1000.0),
        "post_transition_max_abs_error_mm": max(post_abs, default=0.0) * 1000.0,
        "terminal_error_mm": errors[-1] * 1000.0,
        "command_energy": sum(value * value for value in commands) * params.dt_s,
        "command_total_variation": sum(abs(commands[index] - commands[index - 1])
                                       for index in range(1, len(commands))),
        "accumulator_valve_energy": sum(value * value for value in accumulator_commands) * params.dt_s,
        "accumulator_oil_used_ml": max(0.0, accumulator_initial_oil - accumulator_final_oil) * 1.0e6,
        "peak_pressure_mpa": max(pressure_peaks, default=0.0) / 1.0e6,
        "relief_activation_count": relief_count,
        "final_position_m": state.x_m,
        "observer_final_load_n": observer.load_hat_n,
        "observer_final_leakage_m3_s_pa": observer.leakage_hat_m3_s_pa,
        "stroke_boundary_samples": stroke_hits,
        "accumulator_active_time_s": accumulator_active_samples*params.dt_s,
        "minimum_accumulator_pressure_mpa": minimum_accumulator_pressure/1e6,
        "final_accumulator_pressure_mpa": plant.accumulator_pressure(state)/1e6,
        "mode_times_s": {k:v*params.dt_s for k,v in mode_samples.items()},
    }
    if trace_interval_s is not None:
        output["trace"] = trace
    return output
