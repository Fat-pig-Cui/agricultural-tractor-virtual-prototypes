"""Lift-control baselines and a virtual-prototype leakage estimator.

The estimator uses the known simulated command and a pressure-state transition
to infer the leakage coefficient.  It is deliberately model-level: it is not
presented as a calibrated online identifier for a physical hitch.
"""
from __future__ import annotations
from dataclasses import dataclass
from math import exp, tanh
from config.parameters import LiftParameters


_DEFAULT_LIFT_PARAMETERS = LiftParameters()

@dataclass
class AntiWindupPID:
    kp: float = 9.0; ki: float = 1.2; kd: float = 0.08; integral: float = 0.0; previous: float = 0.0
    def update(self, reference: float, measurement: float, dt: float) -> float:
        error = reference - measurement
        derivative = (error - self.previous) / max(dt, 1e-9)
        raw = self.kp * error + self.ki * self.integral + self.kd * derivative
        command = max(-1.0, min(1.0, raw))
        if abs(raw) < 1.0 or raw * command < 0:
            self.integral += error * dt
        self.previous = error
        return command

@dataclass
class PressureObserver:
    nominal_leakage_m3_s_pa: float = _DEFAULT_LIFT_PARAMETERS.leakage_m3_s_pa
    smoothing: float = 0.08
    temperature_leakage_gain_per_c: float = _DEFAULT_LIFT_PARAMETERS.temperature_leakage_gain_per_c
    valve_pressure_gain_pa: float = _DEFAULT_LIFT_PARAMETERS.valve_pressure_gain_pa
    tracking_pressure_rate_s: float = _DEFAULT_LIFT_PARAMETERS.tracking_pressure_rate_s
    hold_pressure_rate_s: float = _DEFAULT_LIFT_PARAMETERS.hold_pressure_rate_s
    hold_leakage_retention: float = _DEFAULT_LIFT_PARAMETERS.hold_leakage_retention
    leakage_estimate: float | None = None
    residual_rms: float = 0.0
    confidence: float = 0.0
    update_count: int = 0

    def __post_init__(self) -> None:
        if self.leakage_estimate is None:
            self.leakage_estimate = self.nominal_leakage_m3_s_pa

    def temperature_factor(self, temperature_c: float) -> float:
        return 1.0 + self.temperature_leakage_gain_per_c * max(0.0, temperature_c - 25.0)

    def flow_estimate(self, pressure_delta_pa: float, temperature_c: float) -> float:
        """Return the current model-level leakage-flow proxy."""
        return (self.leakage_estimate or self.nominal_leakage_m3_s_pa) * self.temperature_factor(temperature_c) * max(pressure_delta_pa, 0.0)

    def update_transition(self, *, pressure_before_pa: float, pressure_after_pa: float,
                          position_before_m: float, command: float, load_n: float,
                          dt: float, cylinder_area_m2: float, stiffness_n_m: float,
                          coulomb_n: float, temperature_c: float,
                          hydraulic_hold_mode: bool, hold_compensation: float,
                          accumulator_active: bool) -> float:
        """Update from one pressure transition of the virtual plant.

        The inversion follows the pressure-rate term implemented in
        :mod:`hydraulic_model`.  Updates are skipped while the accumulator is
        discharging because its unmeasured flow would confound a leakage-only
        residual.  That restriction is intentional and is reported by the
        experiment output.
        """
        pressure_before = max(pressure_before_pa, 0.0)
        pressure_after = max(pressure_after_pa, 0.0)
        if accumulator_active or pressure_before < 1.0e4 or dt <= 0.0:
            self.confidence *= 0.999
            return self.leakage_estimate or self.nominal_leakage_m3_s_pa

        equilibrium = (load_n + stiffness_n_m * position_before_m + coulomb_n) / max(cylinder_area_m2, 1.0e-12)
        valve_difference = (equilibrium + max(-1.0, min(1.0, command))
                            * self.valve_pressure_gain_pa)
        mode_gain = (self.hold_pressure_rate_s if hydraulic_hold_mode
                     else self.tracking_pressure_rate_s)
        leakage_gain = (self.hold_leakage_retention
                        * (1.0 - max(0.0, min(1.0, hold_compensation)))
                        if hydraulic_hold_mode else 1.0)
        if leakage_gain <= 1.0e-9:
            return self.leakage_estimate or self.nominal_leakage_m3_s_pa

        observed_rate = (pressure_after - pressure_before) / dt
        leakage_rate = max(mode_gain * (valve_difference - pressure_before) - observed_rate, 0.0)
        candidate = (cylinder_area_m2 * leakage_rate /
                     (pressure_before * leakage_gain * self.temperature_factor(temperature_c)))
        residual = candidate - (self.leakage_estimate or self.nominal_leakage_m3_s_pa)
        alpha = max(0.0, min(1.0, self.smoothing))
        self.leakage_estimate = max(0.0, (self.leakage_estimate or self.nominal_leakage_m3_s_pa) + alpha * residual)
        self.residual_rms = ((1.0 - alpha) * self.residual_rms ** 2
                             + alpha * residual ** 2) ** 0.5
        scale = max(abs(self.leakage_estimate), self.nominal_leakage_m3_s_pa * 0.05, 1.0e-15)
        self.confidence = exp(-self.residual_rms / scale)
        self.update_count += 1
        return self.leakage_estimate

@dataclass
class BoundaryLayerSMC:
    gain: float = 16.0; velocity_gain: float = 1.1; layer_m: float = 0.004
    def update(self, reference: float, x: float, v: float, leakage_bias: float) -> float:
        error = reference - x
        surface = self.gain * error - self.velocity_gain * v + leakage_bias
        return max(-1.0, min(1.0, tanh(surface / max(self.layer_m, 1e-9))))

@dataclass
class DI_SMACKernel:
    gain: float = 14.0; boundary_m: float = 0.003
    def update(self, reference: float, x: float, v: float) -> float:
        surface = self.gain * (reference - x) - v
        return max(-1.0, min(1.0, tanh(surface / self.boundary_m)))
