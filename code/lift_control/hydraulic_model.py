"""Reduced-order pressure-difference lift surrogate for algorithmic simulation."""
from __future__ import annotations
from dataclasses import dataclass
from config.parameters import LiftParameters

@dataclass
class LiftState:
    x_m: float = 0.35
    v_mps: float = 0.0
    p_a_pa: float = 12e6
    p_b_pa: float = 8e6
    valve: float = 0.0
    leakage_m3_s: float = 0.0
    p_acc_pa: float = 0.0
    acc_oil_m3: float = 0.0

class ElectroHydraulicLift:
    def __init__(self, params: LiftParameters | None = None):
        self.p = params or LiftParameters()

    def step(self, state: LiftState, command: float, load_n: float,
             temperature_c: float = 25.0, hold_mode: bool = False,
             hold_compensation: float = 0.0,
             acc_valve: float = 0.0,
             leakage_multiplier: float = 1.0) -> LiftState:
        p, dt = self.p, self.p.dt_s
        u = max(-1.0, min(1.0, command))
        da = p.cylinder_area_m2
        leakage = (p.leakage_m3_s_pa * max(leakage_multiplier, 0.0)
                   * (1.0 + p.temperature_leakage_gain_per_c
                      * max(0.0, temperature_c - 25.0)))
        pressure_difference = state.p_a_pa - state.p_b_pa
        equilibrium_difference = (load_n + p.stiffness_n_m * state.x_m + p.coulomb_n) / da
        valve_difference = equilibrium_difference + u * p.valve_pressure_gain_pa
        leakage_difference = leakage * max(pressure_difference, 0.0) / max(da, 1e-9)
        # Accumulator-assisted hold: gas precharge at p.acc_precharge_pa with
        # gas volume p.acc_volume_m3; oil stored in the accumulator is
        # discharged into the A chamber at a rate proportional to the valve
        # opening and the pressure head, raising the differential pressure.
        # Gas follows the isothermal law p_gas = p_pre * V0/(V0 + V_oil_out).
        # This is a parameterized theoretical model, not a claim about a
        # calibrated accumulator circuit.
        acc_open = max(0.0, min(1.0, acc_valve)) if p.acc_precharge_pa > 0.0 else 0.0
        acc_flow = 0.0
        next_acc_oil = state.acc_oil_m3
        p_acc = state.p_acc_pa
        if acc_open > 0.0 and p.acc_volume_m3 > 0.0:
            oil_out = max(0.0, p.acc_volume_m3 - state.acc_oil_m3)
            p_acc = max(pressure_difference * 1.01,
                        p.acc_precharge_pa * p.acc_volume_m3 / max(p.acc_volume_m3 + oil_out, 1e-12))
            acc_flow = (acc_open * p.acc_flow_m3_s_pa
                        * max(p_acc - pressure_difference, 0.0))
            # The charge circuit replenishes stored oil during sustained
            # leakage so the accumulator can keep covering the leak path.
            next_acc_oil = max(0.0, min(p.acc_volume_m3,
                                        state.acc_oil_m3 - acc_flow * dt + p.acc_charge_m3_s * dt))
            acc_flow = min(acc_flow, max((state.acc_oil_m3 + p.acc_charge_m3_s * dt) / max(dt, 1e-9), 0.0))
        if hold_mode:
            # Active fine-trim keeps the pressure close to the commanded
            # equilibrium; the small leakage term represents a load-holding
            # valve rather than an open proportional-valve path.  The
            # accumulator discharge injects flow into the A chamber and its
            # pressure-rate contribution follows the bulk-modulus relation
            # d(delta p)/dt = beta_e * q / V.
            compensation = max(0.0, min(1.0, hold_compensation))
            acc_term = p.bulk_modulus_pa * acc_flow / max(p.chamber_volume_m3, 1e-12)
            pressure_rate = (p.hold_pressure_rate_s
                             * (valve_difference - pressure_difference)
                             - p.hold_leakage_retention * (1.0 - compensation)
                             * leakage_difference
                             + acc_term)
            next_difference = max(0.0, min(p.relief_pressure_pa, pressure_difference + pressure_rate * dt))
        else:
            pressure_rate = (p.tracking_pressure_rate_s
                             * (valve_difference - pressure_difference)
                             - leakage_difference)
            next_difference = max(0.0, min(p.relief_pressure_pa, pressure_difference + pressure_rate * dt))
        common_pressure = max(
            p.minimum_common_pressure_pa,
            min(p.relief_pressure_pa - next_difference,
                (state.p_a_pa + state.p_b_pa) / 2.0))
        pa = min(p.relief_pressure_pa, common_pressure + next_difference / 2.0)
        pb = max(0.0, common_pressure - next_difference / 2.0)
        pressure_force = da * next_difference
        friction = p.viscous_n_s_m * state.v_mps + p.coulomb_n * (1 if state.v_mps > 0 else -1 if state.v_mps < 0 else 0)
        acceleration = (pressure_force - load_n - friction - p.stiffness_n_m * state.x_m) / p.mass_kg
        velocity = state.v_mps + acceleration * dt
        position = max(0.0, min(p.stroke_m, state.x_m + velocity * dt))
        return LiftState(position, velocity, pa, pb, u, leakage * max(next_difference, 0.0),
                         p_acc, next_acc_oil)
