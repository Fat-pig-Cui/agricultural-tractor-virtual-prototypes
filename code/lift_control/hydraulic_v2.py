"""Two-chamber nonlinear hydraulic virtual prototype for Paper 1 V2.

The model is a reproducible theoretical plant, not a calibrated tractor.  It
replaces the earlier command-to-pressure surrogate with explicit valve flows,
two pressure continuity equations, spool dynamics, internal leakage, relief
limits, and finite accumulator gas/oil energy.
"""
from __future__ import annotations

from dataclasses import dataclass
from math import copysign, sqrt
from random import Random


@dataclass(frozen=True)
class HydraulicV2Parameters:
    dt_s: float = 0.01
    mass_kg: float = 1200.0
    piston_area_m2: float = 0.012
    chamber_dead_volume_m3: float = 0.004
    stroke_m: float = 0.85
    effective_bulk_modulus_pa: float = 2.0e8
    supply_pressure_pa: float = 21.0e6
    tank_pressure_pa: float = 0.2e6
    relief_pressure_pa: float = 22.0e6
    fluid_density_kg_m3: float = 850.0
    valve_discharge_coefficient: float = 0.62
    valve_max_area_m2: float = 5.0e-6
    valve_deadzone: float = 0.03
    valve_time_constant_s: float = 0.05
    internal_leakage_m3_s_pa: float = 5.0e-14
    temperature_leakage_gain_per_c: float = 0.018
    viscous_n_s_m: float = 2200.0
    coulomb_n: float = 850.0
    stribeck_n: float = 350.0
    stribeck_velocity_m_s: float = 0.004
    stiffness_n_m: float = 18000.0
    sensor_position_std_m: float = 0.0015
    sensor_pressure_std_pa: float = 50_000.0
    accumulator_precharge_pa: float = 8.0e6
    accumulator_shell_volume_m3: float = 0.004
    accumulator_initial_pressure_pa: float = 14.0e6
    accumulator_polytropic_index: float = 1.2
    accumulator_valve_coefficient_m3_s_pa_sqrt: float = 5.0e-8


@dataclass(frozen=True)
class HydraulicV2State:
    x_m: float = 0.15
    v_m_s: float = 0.0
    p_a_pa: float = 6.0e6
    p_b_pa: float = 5.25e6
    spool: float = 0.0
    accumulator_gas_volume_m3: float = 0.0025


@dataclass(frozen=True)
class HydraulicV2Step:
    state: HydraulicV2State
    q_a_m3_s: float
    q_b_m3_s: float
    q_internal_leak_m3_s: float
    q_accumulator_m3_s: float
    relief_active: bool


class TwoChamberHydraulicPlant:
    def __init__(self, params: HydraulicV2Parameters | None = None):
        self.p = params or HydraulicV2Parameters()

    def accumulator_pressure(self, state: HydraulicV2State) -> float:
        p = self.p
        initial_gas = (p.accumulator_shell_volume_m3
                       * (p.accumulator_precharge_pa
                          / p.accumulator_initial_pressure_pa)
                       ** (1.0 / p.accumulator_polytropic_index))
        constant = (p.accumulator_initial_pressure_pa
                    * initial_gas ** p.accumulator_polytropic_index)
        return constant / max(state.accumulator_gas_volume_m3, 1e-9) ** p.accumulator_polytropic_index

    def initial_state(self, load_n: float = 9000.0) -> HydraulicV2State:
        p = self.p
        delta = (load_n + p.stiffness_n_m * 0.15) / p.piston_area_m2
        common = 5.0e6
        initial_gas = (p.accumulator_shell_volume_m3
                       * (p.accumulator_precharge_pa
                          / p.accumulator_initial_pressure_pa)
                       ** (1.0 / p.accumulator_polytropic_index))
        return HydraulicV2State(
            x_m=0.15,
            p_a_pa=common + delta / 2.0,
            p_b_pa=common - delta / 2.0,
            accumulator_gas_volume_m3=initial_gas,
        )

    def _orifice(self, area_m2: float, pressure_drop_pa: float) -> float:
        if area_m2 <= 0.0 or pressure_drop_pa <= 0.0:
            return 0.0
        return (self.p.valve_discharge_coefficient * area_m2
                * sqrt(2.0 * pressure_drop_pa / self.p.fluid_density_kg_m3))

    def valve_flows(self, spool: float, p_a_pa: float, p_b_pa: float) -> tuple[float, float]:
        p = self.p
        opening = max(0.0, (abs(spool) - p.valve_deadzone)
                      / max(1.0 - p.valve_deadzone, 1e-9))
        area = p.valve_max_area_m2 * opening
        if spool >= 0.0:
            q_a = self._orifice(area, p.supply_pressure_pa - p_a_pa)
            q_b = self._orifice(area, p_b_pa - p.tank_pressure_pa)
        else:
            q_a = -self._orifice(area, p_a_pa - p.tank_pressure_pa)
            q_b = -self._orifice(area, p.supply_pressure_pa - p_b_pa)
        return q_a, q_b

    def _rates(self, state: HydraulicV2State, command: float, load_n: float,
               temperature_c: float, accumulator_valve: float = 0.0,
               leakage_scale: float = 1.0, step_s: float | None = None) -> tuple:
        """Continuous plant rates used by the optional higher-order audit.

        The submitted path remains in :meth:`step` below.  This helper keeps
        the same valve, leakage, accumulator and friction laws, but exposes
        their rates so an RK4 plant update can be tested without changing the
        10 ms controller or measurement interface.
        """
        p = self.p
        h = p.dt_s if step_s is None else step_s
        command = max(-1.0, min(1.0, command))
        spool_rate = (command - state.spool) / max(p.valve_time_constant_s, h)
        q_a, q_b = self.valve_flows(state.spool, state.p_a_pa, state.p_b_pa)
        temperature_factor = 1.0 + p.temperature_leakage_gain_per_c * max(
            0.0, temperature_c - 25.0)
        q_leak = (p.internal_leakage_m3_s_pa * leakage_scale
                  * temperature_factor * (state.p_a_pa - state.p_b_pa))
        p_acc = self.accumulator_pressure(state)
        acc_open = max(0.0, min(1.0, accumulator_valve))
        q_acc = (acc_open * p.accumulator_valve_coefficient_m3_s_pa_sqrt
                 * sqrt(max(p_acc - state.p_a_pa, 0.0)))
        available_oil = max(0.0, p.accumulator_shell_volume_m3
                            - state.accumulator_gas_volume_m3)
        q_acc = min(q_acc, available_oil / max(h, 1e-9))
        volume_a = p.chamber_dead_volume_m3 + p.piston_area_m2 * state.x_m
        volume_b = (p.chamber_dead_volume_m3
                    + p.piston_area_m2 * (p.stroke_m - state.x_m))
        dp_a = (p.effective_bulk_modulus_pa / max(volume_a, 1e-8)
                * (q_a + q_acc - p.piston_area_m2 * state.v_m_s - q_leak))
        dp_b = (p.effective_bulk_modulus_pa / max(volume_b, 1e-8)
                * (p.piston_area_m2 * state.v_m_s - q_b + q_leak))
        velocity_sign = 0.0 if abs(state.v_m_s) < 1e-7 else copysign(1.0, state.v_m_s)
        stribeck = (p.coulomb_n + p.stribeck_n
                    * max(0.0, 1.0 - abs(state.v_m_s) / p.stribeck_velocity_m_s))
        friction = p.viscous_n_s_m * state.v_m_s + velocity_sign * stribeck
        force = (p.piston_area_m2 * (state.p_a_pa - state.p_b_pa) - load_n
                 - p.stiffness_n_m * state.x_m - friction)
        acceleration = force / p.mass_kg
        return (state.v_m_s, acceleration, dp_a, dp_b, spool_rate, q_acc,
                q_a, q_b, q_leak)

    def step_rk4(self, state: HydraulicV2State, command: float, load_n: float,
                 temperature_c: float, accumulator_valve: float = 0.0,
                 leakage_scale: float = 1.0) -> HydraulicV2Step:
        """One event-clipped RK4 plant step for convergence auditing.

        Pressure and stroke events are projected at the end of the step,
        matching the safety bounds of the submitted implementation.  This is
        a numerical refinement arm, not a replacement of the nominal path.
        """
        h = self.p.dt_s
        def add(s, k, scale):
            return HydraulicV2State(s.x_m + scale*k[0], s.v_m_s + scale*k[1],
                                    s.p_a_pa + scale*k[2], s.p_b_pa + scale*k[3],
                                    s.spool + scale*k[4],
                                    s.accumulator_gas_volume_m3 + scale*k[5])
        k1 = self._rates(state, command, load_n, temperature_c,
                         accumulator_valve, leakage_scale, h)
        k2 = self._rates(add(state, k1, h/2), command, load_n, temperature_c,
                         accumulator_valve, leakage_scale, h)
        k3 = self._rates(add(state, k2, h/2), command, load_n, temperature_c,
                         accumulator_valve, leakage_scale, h)
        k4 = self._rates(add(state, k3, h), command, load_n, temperature_c,
                         accumulator_valve, leakage_scale, h)
        vals = [sum(w*k[i] for w,k in zip((1,2,2,1),(k1,k2,k3,k4))) * h/6
                for i in range(6)]
        p = self.p
        position = state.x_m + vals[0]
        velocity = state.v_m_s + vals[1]
        p_a = state.p_a_pa + vals[2]
        p_b = state.p_b_pa + vals[3]
        spool = state.spool + vals[4]
        gas_volume = state.accumulator_gas_volume_m3 + vals[5]
        relief = p_a > p.relief_pressure_pa or p_b > p.relief_pressure_pa
        p_a = max(p.tank_pressure_pa, min(p.relief_pressure_pa, p_a))
        p_b = max(p.tank_pressure_pa, min(p.relief_pressure_pa, p_b))
        if position <= 0.0 or position >= p.stroke_m:
            position = max(0.0, min(p.stroke_m, position))
            velocity = 0.0
        next_state = HydraulicV2State(
            position, velocity, p_a, p_b,
            max(-1.0, min(1.0, spool)),
            max(0.0, min(p.accumulator_shell_volume_m3, gas_volume)),
        )
        # Diagnostics use the endpoint rates, so the reported flows remain
        # comparable with the Euler path while the state update is RK4.
        end = self._rates(next_state, command, load_n, temperature_c,
                          accumulator_valve, leakage_scale, h)
        return HydraulicV2Step(next_state, end[6], end[7], end[8], end[5], relief)

    def step(self, state: HydraulicV2State, command: float, load_n: float,
             temperature_c: float, accumulator_valve: float = 0.0,
             leakage_scale: float = 1.0) -> HydraulicV2Step:
        p, dt = self.p, self.p.dt_s
        command = max(-1.0, min(1.0, command))
        spool = state.spool + (command - state.spool) * min(
            1.0, dt / max(p.valve_time_constant_s, dt))
        q_a, q_b = self.valve_flows(spool, state.p_a_pa, state.p_b_pa)

        temperature_factor = 1.0 + p.temperature_leakage_gain_per_c * max(
            0.0, temperature_c - 25.0)
        q_leak = (p.internal_leakage_m3_s_pa * leakage_scale
                  * temperature_factor * (state.p_a_pa - state.p_b_pa))

        p_acc = self.accumulator_pressure(state)
        acc_open = max(0.0, min(1.0, accumulator_valve))
        q_acc = (acc_open * p.accumulator_valve_coefficient_m3_s_pa_sqrt
                 * sqrt(max(p_acc - state.p_a_pa, 0.0)))
        available_oil = max(0.0, p.accumulator_shell_volume_m3
                            - state.accumulator_gas_volume_m3)
        q_acc = min(q_acc, available_oil / max(dt, 1e-9))

        volume_a = p.chamber_dead_volume_m3 + p.piston_area_m2 * state.x_m
        volume_b = (p.chamber_dead_volume_m3
                    + p.piston_area_m2 * (p.stroke_m - state.x_m))
        dp_a = (p.effective_bulk_modulus_pa / max(volume_a, 1e-8)
                * (q_a + q_acc - p.piston_area_m2 * state.v_m_s - q_leak))
        dp_b = (p.effective_bulk_modulus_pa / max(volume_b, 1e-8)
                * (p.piston_area_m2 * state.v_m_s - q_b + q_leak))
        p_a = state.p_a_pa + dp_a * dt
        p_b = state.p_b_pa + dp_b * dt
        relief = p_a > p.relief_pressure_pa or p_b > p.relief_pressure_pa
        p_a = max(p.tank_pressure_pa, min(p.relief_pressure_pa, p_a))
        p_b = max(p.tank_pressure_pa, min(p.relief_pressure_pa, p_b))

        velocity_sign = 0.0 if abs(state.v_m_s) < 1e-7 else copysign(1.0, state.v_m_s)
        stribeck = (p.coulomb_n + p.stribeck_n
                    * max(0.0, 1.0 - abs(state.v_m_s) / p.stribeck_velocity_m_s))
        friction = p.viscous_n_s_m * state.v_m_s + velocity_sign * stribeck
        force = (p.piston_area_m2 * (p_a - p_b) - load_n
                 - p.stiffness_n_m * state.x_m - friction)
        acceleration = force / p.mass_kg
        velocity = state.v_m_s + acceleration * dt
        position = state.x_m + velocity * dt
        if position <= 0.0 or position >= p.stroke_m:
            position = max(0.0, min(p.stroke_m, position))
            velocity = 0.0
        gas_volume = min(p.accumulator_shell_volume_m3,
                         state.accumulator_gas_volume_m3 + q_acc * dt)
        next_state = HydraulicV2State(position, velocity, p_a, p_b, spool, gas_volume)
        return HydraulicV2Step(next_state, q_a, q_b, q_leak, q_acc, relief)


@dataclass
class InterfaceObserver:
    dt_s: float
    piston_area_m2: float
    stiffness_n_m: float
    x_hat: float = 0.15
    v_hat: float = 0.0
    load_hat_n: float = 9000.0
    leakage_hat_m3_s_pa: float = 5.0e-14
    p_a_hat_pa: float = 6.0e6
    p_b_hat_pa: float = 5.25e6

    def update(self, measured_x_m: float, measured_p_a_pa: float,
               measured_p_b_pa: float, command: float,
               plant: TwoChamberHydraulicPlant) -> None:
        innovation = measured_x_m - self.x_hat
        previous_v = self.v_hat
        self.x_hat += self.v_hat * self.dt_s + 0.08 * innovation
        self.v_hat += 0.0005 / self.dt_s * innovation
        self.p_a_hat_pa += 0.18 * (measured_p_a_pa - self.p_a_hat_pa)
        self.p_b_hat_pa += 0.18 * (measured_p_b_pa - self.p_b_hat_pa)
        acceleration_hat = (self.v_hat - previous_v) / self.dt_s
        pressure_force = self.piston_area_m2 * (self.p_a_hat_pa - self.p_b_hat_pa)
        raw_load = pressure_force - self.stiffness_n_m * self.x_hat - 1200.0 * acceleration_hat
        self.load_hat_n += 0.005 * (raw_load - self.load_hat_n)
        if abs(command) < 0.08 and abs(self.v_hat) < 0.01:
            delta_p = max(self.p_a_hat_pa - self.p_b_hat_pa, 1.0e4)
            pressure_decay = max(0.0, measured_p_a_pa - self.p_a_hat_pa)
            candidate = max(0.0, pressure_decay * 1e-9 / delta_p)
            self.leakage_hat_m3_s_pa += 0.01 * (candidate - self.leakage_hat_m3_s_pa)


def noisy_measurement(state: HydraulicV2State, params: HydraulicV2Parameters,
                      rng: Random, pressure_bias_pa: float = 0.0,
                      position_bias_m: float = 0.0) -> tuple[float, float, float]:
    return (
        state.x_m + position_bias_m + rng.gauss(0.0, params.sensor_position_std_m),
        state.p_a_pa + pressure_bias_pa + rng.gauss(0.0, params.sensor_pressure_std_pa),
        state.p_b_pa + pressure_bias_pa + rng.gauss(0.0, params.sensor_pressure_std_pa),
    )
