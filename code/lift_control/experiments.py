"""Unified benchmark definitions for lift-control algorithms."""
from __future__ import annotations
from dataclasses import dataclass, replace
from random import Random
from config.parameters import LiftParameters
from hydraulic_model import ElectroHydraulicLift, LiftState
from controllers import AntiWindupPID, PressureObserver, BoundaryLayerSMC, DI_SMACKernel
from leakage_compensation import HybridHoldSupervisor, HoldMode

@dataclass(frozen=True)
class ExperimentConfig:
    duration_s: float = 1800.0
    repeats: int = 20
    reference_m: float = 0.35
    noise_scale: float = 1.0
    leakage_scale: float = 1.0
    leakage_step_time_s: float | None = None
    leakage_step_multiplier: float = 1.0
    mass_scale: float = 1.0
    viscous_scale: float = 1.0
    stiffness_scale: float = 1.0
    accumulator_flow_scale: float = 1.0
    pressure_feedforward_enabled: bool = True
    leakage_observer_enabled: bool = True
    filtered_velocity_gate_enabled: bool = True
    velocity_gate_mode: str = "filtered"  # filtered, raw, or dual
    lock_valve_leakage_scale: float = 0.0
    hold_enabled: bool = True
    hold_supervisor_hysteresis: float = 0.15
    accumulator_enabled: bool = True
    accumulator_closed_loop: bool = True
    accumulator_pressure_deficit_threshold_pa: float = 0.08e6
    load_after_step_n: float = 7000.0
    load_feedforward_enabled: bool = True
    temperature_start_c: float = 25.0
    temperature_end_c: float = 40.0
    velocity_gate_tolerance_mps: float = 0.003


def run_definition(controller_name: str, config: ExperimentConfig = ExperimentConfig(), seed: int = 2026) -> dict[str, float]:
    """Define one reproducible run; the caller explicitly invokes it after review."""
    rng = Random(seed)
    base_parameters = LiftParameters()
    parameters = replace(
        base_parameters,
        sensor_std_m=base_parameters.sensor_std_m * config.noise_scale,
        leakage_m3_s_pa=base_parameters.leakage_m3_s_pa * config.leakage_scale,
        mass_kg=base_parameters.mass_kg * config.mass_scale,
        viscous_n_s_m=base_parameters.viscous_n_s_m * config.viscous_scale,
        stiffness_n_m=base_parameters.stiffness_n_m * config.stiffness_scale,
        acc_flow_m3_s_pa=base_parameters.acc_flow_m3_s_pa * config.accumulator_flow_scale,
    )
    load_peak = 9000.0
    spring_force = parameters.stiffness_n_m * config.reference_m
    friction_margin = parameters.coulomb_n + 500.0
    required_pressure_pa = (load_peak + spring_force + friction_margin) / parameters.cylinder_area_m2
    initial_load = 9000.0
    initial_equilibrium = (initial_load + parameters.stiffness_n_m * 0.15 + parameters.coulomb_n) / parameters.cylinder_area_m2
    initial_pressure_difference = initial_equilibrium
    state = LiftState(
        x_m=0.15,
        p_a_pa=initial_pressure_difference + 3.0e6,
        p_b_pa=3.0e6,
        p_acc_pa=parameters.acc_precharge_pa if parameters.acc_precharge_pa > 0.0 else 0.0,
        acc_oil_m3=parameters.acc_volume_m3,
    )
    model = ElectroHydraulicLift(parameters)
    # The observer prior deliberately remains at the nominal coefficient even
    # in a leakage stress test.  Otherwise the ablation would disclose the
    # plant's hidden leakage multiplier to the controller.
    observer = PressureObserver(
        nominal_leakage_m3_s_pa=base_parameters.leakage_m3_s_pa,
        temperature_leakage_gain_per_c=parameters.temperature_leakage_gain_per_c,
        valve_pressure_gain_pa=parameters.valve_pressure_gain_pa,
        tracking_pressure_rate_s=parameters.tracking_pressure_rate_s,
        hold_pressure_rate_s=parameters.hold_pressure_rate_s,
        hold_leakage_retention=parameters.hold_leakage_retention)
    supervisor = HybridHoldSupervisor(hysteresis=config.hold_supervisor_hysteresis,
                                      accumulator_enabled=config.accumulator_enabled)
    pid = AntiWindupPID(); smc = BoundaryLayerSMC(); dismac = DI_SMACKernel()
    errors, commands = [], []
    velocities = []
    acc_valve_energy = 0.0
    acc_valve_integral = 0.0
    nominal_load = initial_load
    hold_start_position = None
    hold_start_step = None
    in_hold_steps = 0
    trajectory_time_s = 8.0
    hold_tolerance_m = 0.01
    velocity_tolerance_mps = config.velocity_gate_tolerance_mps
    pressure_tolerance_pa = 0.15e6
    required_hold_steps = int(1.0 / model.p.dt_s)
    min_hold_position = None
    filtered_velocity = 0.0
    hold_state = "TRACK"
    hold_mode_counts = {mode.value: 0 for mode in HoldMode}
    observer_confidence_min = 1.0
    observer_leakage_max = 0.0
    observer_detection_delay_s = None
    for step in range(int(config.duration_s / model.p.dt_s)):
        temperature = (config.temperature_start_c
                       + (config.temperature_end_c - config.temperature_start_c)
                       * step / max(config.duration_s / model.p.dt_s, 1.0))
        measured_x = state.x_m + rng.gauss(0.0, model.p.sensor_std_m)
        x_hat = measured_x
        pressure_delta = max(state.p_a_pa - state.p_b_pa, 0.0)
        leak_hat = observer.flow_estimate(pressure_delta, temperature)
        observer_confidence_min = min(observer_confidence_min, observer.confidence)
        observer_leakage_max = max(observer_leakage_max, abs(leak_hat))
        if not config.leakage_observer_enabled:
            leak_hat = (base_parameters.leakage_m3_s_pa
                        * observer.temperature_factor(temperature) * pressure_delta)
        time_s = step * model.p.dt_s
        progress = min(1.0, time_s / trajectory_time_s)
        blend = 3.0 * progress * progress - 2.0 * progress * progress * progress
        smooth_reference = 0.15 + (config.reference_m - 0.15) * blend
        if progress < 1.0:
            dblend = (6.0 * progress - 6.0 * progress * progress) / trajectory_time_s
            ddblend = (6.0 - 12.0 * progress) / (trajectory_time_s * trajectory_time_s)
            reference_velocity = (config.reference_m - 0.15) * dblend
            reference_acceleration = (config.reference_m - 0.15) * ddblend
        else:
            reference_velocity = 0.0
            reference_acceleration = 0.0
        load = 9000.0 if time_s < 10.0 else config.load_after_step_n
        desired_pressure = (load + parameters.stiffness_n_m * smooth_reference
                            + parameters.coulomb_n + parameters.mass_kg * reference_acceleration
                            + parameters.viscous_n_s_m * (reference_velocity - state.v_mps)) / parameters.cylinder_area_m2
        pressure_error = desired_pressure - (state.p_a_pa - state.p_b_pa)
        pressure_feedforward = (pressure_error / parameters.valve_pressure_gain_pa
                                if config.pressure_feedforward_enabled else 0.0)
        if controller_name == "pid":
            feedback = pid.update(smooth_reference, x_hat, model.p.dt_s)
        elif controller_name == "dismac":
            feedback = dismac.update(smooth_reference, x_hat, state.v_mps)
        elif controller_name == "smc":
            feedback = smc.update(smooth_reference, x_hat, state.v_mps, -leak_hat)
        elif controller_name == "hybrid":
            feedback = dismac.update(smooth_reference, x_hat, state.v_mps)
            feedback += supervisor.command(leak_hat) if step > int(5.0 / model.p.dt_s) else 0.0
        else:
            raise ValueError(f"unknown controller: {controller_name}")
        # Use a strong robust correction only while moving.  Once the
        # reference has arrived, reduce the outer-loop bandwidth so that the
        # pressure loop can dissipate velocity and satisfy the hold gate.
        # After the planned motion, use a common damped fine-trim law.  This
        # prevents controller-specific switching chatter from blocking the
        # hold-entry gate.
        if progress >= 1.0:
            feedback = 80.0 * (smooth_reference - x_hat) - 12.0 * state.v_mps
        feedback_scale = 0.18 if progress < 1.0 else 0.08
        command = pressure_feedforward + feedback_scale * feedback
        hold_mode = hold_start_step is not None and config.hold_enabled
        hold_policy = None
        hydraulic_hold_mode = False
        hold_compensation = 0.0
        acc_valve = 0.0
        # Load feedforward: the implement load is treated as a measurable
        # disturbance (e.g. a draft-force or load sensor), so the hold
        # pressure target uses the load signal directly instead of waiting
        # for the pressure loop to re-converge after a step.  Without
        # feedforward the controller keeps the pre-step nominal load, so the
        # pressure loop must recover the new equilibrium on its own.
        hold_load = load if config.load_feedforward_enabled else nominal_load
        if hold_mode:
            required_pressure = (hold_load + parameters.stiffness_n_m * state.x_m
                                 + parameters.coulomb_n) / parameters.cylinder_area_m2
            pressure_deficit = max(required_pressure - (state.p_a_pa - state.p_b_pa), 0.0)
            hold_policy = supervisor.update(leak_hat)
            # Stored fluid is also a fast response path for a measured load
            # step.  A leakage-only mode trigger left the accumulator idle
            # during exactly the pressure deficit it is meant to cover.
            if (config.accumulator_enabled
                    and pressure_deficit >= config.accumulator_pressure_deficit_threshold_pa):
                supervisor.mode = HoldMode.ACCUMULATOR
                hold_policy = HoldMode.ACCUMULATOR
            hold_state = hold_policy.name
            hold_mode_counts[hold_policy.value] += 1
            hydraulic_hold_mode = hold_policy in (HoldMode.LOCK, HoldMode.ACCUMULATOR)
            hold_compensation = 0.8 if hold_policy is HoldMode.ACCUMULATOR else 0.0
            hold_pressure = (hold_load + parameters.stiffness_n_m * config.reference_m
                             + parameters.coulomb_n) / parameters.cylinder_area_m2
            # All hold modes retain a bounded pressure correction so a load
            # step does not create an artificial position jump.  The mode
            # distinction is the structural leakage path and compensation
            # policy, not permission to abandon pressure balance.  The
            # accumulator discharge (below) is the dedicated compensation
            # path; the main valve stays on fine-trim in every mode.
            command = ((hold_pressure - (state.p_a_pa - state.p_b_pa))
                       / parameters.valve_pressure_gain_pa)
            command += 0.04 * max(-1.0, min(1.0, config.reference_m - state.x_m) / hold_tolerance_m)
            # Closed-loop accumulator discharge: the discharge valve opens on
            # the differential-pressure deficit (feedforward, with a deadband
            # that keeps the accumulator idle at the nominal steady state) so
            # a load step is covered immediately by stored oil, plus an
            # integral trim from position error, with anti-windup through the
            # saturation of acc_valve.
            # Closed-loop accumulator discharge: the discharge valve opens on
            # the shortfall between the pressure actually required to balance
            # the current load and position and the measured differential
            # pressure (feedforward, deadband keeps the accumulator idle at
            # steady state) so a load step is covered immediately by stored
            # oil, plus a small integral trim from position error, with
            # anti-windup through the saturation of acc_valve.
            acc_error = config.reference_m - state.x_m
            acc_valve_integral += 2.0 * acc_error * model.p.dt_s
            acc_valve_integral = max(-0.05, min(0.05, acc_valve_integral))
            # The accumulator is a distinct supervisory mode.  Treating LOCK
            # as accumulator-enabled erased the intended difference between
            # passive locking and stored-fluid compensation in the ablation.
            if (config.accumulator_closed_loop
                    and hold_policy is HoldMode.ACCUMULATOR):
                acc_valve = max(0.0, min(1.0,
                                         300.0 * max(pressure_deficit - config.accumulator_pressure_deficit_threshold_pa, 0.0)
                                         / parameters.valve_pressure_gain_pa
                                         + 125.0 * max(acc_error - 0.002, 0.0)
                                         + acc_valve_integral))
            command = max(-0.08, min(0.08, command))
        command = max(-1.0, min(1.0, command))
        # Optional lock-valve leakage sensitivity: the base model's leakage
        # remains the cylinder leakage; this additional term represents a
        # non-ideal valve/lock path during long-term hold.
        state_before = state
        leakage_multiplier = (config.leakage_step_multiplier
                              if config.leakage_step_time_s is not None
                              and time_s >= config.leakage_step_time_s else 1.0)
        state = model.step(state, command, load_n=load, temperature_c=temperature,
                           hold_mode=hydraulic_hold_mode,
                           hold_compensation=hold_compensation,
                           acc_valve=acc_valve,
                           leakage_multiplier=leakage_multiplier)
        if config.leakage_observer_enabled:
            observer.update_transition(
                pressure_before_pa=state_before.p_a_pa - state_before.p_b_pa,
                pressure_after_pa=state.p_a_pa - state.p_b_pa,
                position_before_m=state_before.x_m,
                command=command,
                load_n=load,
                dt=model.p.dt_s,
                cylinder_area_m2=model.p.cylinder_area_m2,
                stiffness_n_m=model.p.stiffness_n_m,
                coulomb_n=model.p.coulomb_n,
                temperature_c=temperature,
                hydraulic_hold_mode=hydraulic_hold_mode,
                hold_compensation=hold_compensation,
                accumulator_active=acc_valve > 0.0,
            )
            if (config.leakage_step_time_s is not None
                    and time_s >= config.leakage_step_time_s
                    and observer_detection_delay_s is None):
                target_coefficient = parameters.leakage_m3_s_pa * config.leakage_step_multiplier
                if (observer.leakage_estimate or 0.0) >= 0.9 * target_coefficient:
                    observer_detection_delay_s = time_s - config.leakage_step_time_s
        acc_valve_energy += acc_valve * acc_valve * model.p.dt_s
        if hydraulic_hold_mode and config.lock_valve_leakage_scale > 0.0:
            lock_flow = (parameters.leakage_m3_s_pa * config.lock_valve_leakage_scale
                         * max(state.p_a_pa - state.p_b_pa, 0.0))
            # Idealized accumulator compensation cancels a configurable share
            # of the lock-path leakage.  This is a theoretical actuator model,
            # not a claim about a calibrated accumulator circuit.
            lock_flow *= (1.0 - hold_compensation)
            state = LiftState(state.x_m - lock_flow / max(parameters.cylinder_area_m2, 1e-9)
                              * model.p.dt_s, state.v_mps, state.p_a_pa, state.p_b_pa,
                              state.valve, state.leakage_m3_s,
                              state.p_acc_pa, state.acc_oil_m3)
        filtered_velocity = 0.92 * filtered_velocity + 0.08 * state.v_mps
        error = config.reference_m - state.x_m
        errors.append(error); commands.append(command)
        velocities.append(state.v_mps)
        pressure_error = desired_pressure - (state.p_a_pa - state.p_b_pa)
        if config.velocity_gate_mode == "dual":
            gate_ok = (abs(state.v_mps) <= velocity_tolerance_mps and
                       abs(filtered_velocity) <= velocity_tolerance_mps)
        elif config.velocity_gate_mode == "raw" or not config.filtered_velocity_gate_enabled:
            gate_ok = abs(state.v_mps) <= velocity_tolerance_mps
        else:
            gate_ok = abs(filtered_velocity) <= velocity_tolerance_mps
        if not hold_mode and abs(error) <= hold_tolerance_m and gate_ok:
            in_hold_steps += 1
        elif not hold_mode:
            in_hold_steps = 0
        if hold_start_step is None and config.hold_enabled and in_hold_steps >= required_hold_steps:
            hold_start_step = step - required_hold_steps + 1
            hold_start_position = state.x_m
            hold_state = "HOLD_FINE"
        if hold_start_position is not None:
            min_hold_position = min(state.x_m, min_hold_position if min_hold_position is not None else state.x_m)
    hold_drop = None if hold_start_position is None else max(0.0, hold_start_position - min_hold_position)
    return {"rmse_m": (sum(error * error for error in errors) / len(errors)) ** 0.5,
            "max_error_m": max(abs(error) for error in errors),
            "dynamic_max_error_m": max((abs(error) for error in errors[:int(trajectory_time_s / model.p.dt_s)]), default=0.0),
            "settling_error_m": abs(errors[-1]),
            "hold_drop_m": hold_drop,
            "hold_started": hold_start_step is not None,
            "hold_start_time_s": None if hold_start_step is None else hold_start_step * model.p.dt_s,
            "hold_state": hold_state,
            "hold_mode_counts": hold_mode_counts,
            "observer_confidence_min": observer_confidence_min,
            "observer_leakage_max_m3_s": observer_leakage_max,
            "observer_final_coefficient_m3_s_pa": observer.leakage_estimate,
            "observer_update_count": observer.update_count,
            "observer_confidence_final": observer.confidence,
            "observer_detection_delay_s": observer_detection_delay_s,
            "max_velocity_mps": max((abs(v) for v in velocities), default=0.0),
            "required_pressure_pa": required_pressure_pa,
            "initial_pressure_difference_pa": initial_pressure_difference,
            "command_energy": sum(command * command for command in commands) * model.p.dt_s,
            "acc_valve_energy": acc_valve_energy,
            "final_position_m": state.x_m,
            "final_velocity_mps": state.v_mps}
