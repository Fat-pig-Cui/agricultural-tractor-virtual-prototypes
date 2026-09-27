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


def run_lift_v2(controller: str, config: LiftV2Config = LiftV2Config()) -> dict[str, object]:
    rng = Random(config.seed)
    base = HydraulicV2Parameters()
    params = replace(
        base,
        sensor_position_std_m=base.sensor_position_std_m * config.position_noise_scale,
        sensor_pressure_std_pa=base.sensor_pressure_std_pa * config.pressure_noise_scale,
        accumulator_valve_coefficient_m3_s_pa_sqrt=(
            base.accumulator_valve_coefficient_m3_s_pa_sqrt
            * config.accumulator_flow_scale),
    )
    plant = TwoChamberHydraulicPlant(params)
    state = plant.initial_state()
    observer = InterfaceObserver(params.dt_s, params.piston_area_m2,
                                 params.stiffness_n_m)
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

    for step in range(step_count):
        time_s = step * params.dt_s
        reference, reference_velocity, reference_acceleration = smooth_reference(time_s)
        load_n = 9000.0 if time_s < config.load_step_time_s else config.post_step_load_n
        temperature_c = (config.temperature_start_c
                         + (config.temperature_end_c - config.temperature_start_c)
                         * step / max(1, step_count - 1))
        measured_x, measured_p_a, measured_p_b = noisy_measurement(
            state, params, rng, config.pressure_bias_pa, config.position_bias_m)
        observer.update(measured_x, measured_p_a, measured_p_b,
                        previous_command, plant)
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
            memory.mode = "FINE_TRIM"
            memory.mode_dwell_steps = 0

        estimated_load = max(3000.0, min(20_000.0, observer.load_hat_n))
        if controller in ("pid_lock", "pid_accumulator"):
            memory.position_integral = max(-0.05, min(
                0.05, memory.position_integral + error * params.dt_s))
            desired_acceleration = (reference_acceleration + 650.0 * error
                                    + 90.0 * velocity_error
                                    + 20.0 * memory.position_integral)
            target_force = (estimated_load + params.stiffness_n_m * reference
                            + params.viscous_n_s_m * reference_velocity
                            + params.mass_kg * desired_acceleration)
            target_delta = target_force / params.piston_area_m2
        elif controller == "smc_lock":
            sliding = 18.0 * error + velocity_error
            desired_acceleration = (reference_acceleration + 650.0 * error
                                    + 90.0 * velocity_error)
            robust_force = 1200.0 * tanh(sliding / 0.006)
            target_force = (estimated_load + params.stiffness_n_m * reference
                            + params.viscous_n_s_m * reference_velocity
                            + params.mass_kg * desired_acceleration
                            + robust_force)
            target_delta = target_force / params.piston_area_m2
        elif controller == "observer_hybrid":
            desired_acceleration = (reference_acceleration + 650.0 * error
                                    + 90.0 * velocity_error)
            target_force = (estimated_load + params.stiffness_n_m * reference
                            + params.viscous_n_s_m * reference_velocity
                            + params.mass_kg * desired_acceleration)
            target_delta = target_force / params.piston_area_m2
        else:
            raise ValueError(f"unknown controller: {controller}")

        command = _pressure_command(target_delta, measured_delta, memory,
                                    params.dt_s)
        accumulator_valve = 0.0
        if memory.hold_started:
            if controller in ("pid_lock", "smc_lock"):
                command = 0.0
                new_mode = "LOCK"
            elif controller == "pid_accumulator":
                new_mode = "ACCUMULATOR" if error > 0.002 else "LOCK"
                command = max(-0.08, min(0.08, command))
                accumulator_valve = max(0.0, min(1.0, 80.0 * max(error - 0.001, 0.0)))
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
                    command = max(-0.10, min(0.10, command))
                if new_mode == "ACCUMULATOR":
                    accumulator_valve = max(0.0, min(
                        1.0, 1.5 * max(pressure_deficit, 0.0) / 1.0e6
                        + 60.0 * max(error - 0.001, 0.0)))
            if new_mode != memory.mode:
                memory.mode = new_mode
                memory.mode_dwell_steps = 0
                memory.switches += 1

        result = plant.step(state, command, load_n, temperature_c,
                            accumulator_valve=accumulator_valve,
                            leakage_scale=config.leakage_scale)
        state = result.state
        previous_command = command
        relief_count += int(result.relief_active)
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
    return {
        "controller": controller,
        "seed": config.seed,
        "hold_started": memory.hold_started,
        "hold_start_time_s": memory.hold_start_time_s,
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
    }
