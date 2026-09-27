"""Physics-consistent virtual power-split model and viability-filtered ECMS.

This V2 module is intentionally separate from the published v1.0.3 benchmark.
It is a theoretical model: parameters define a reproducible virtual platform
and are not calibrated measurements from a particular tractor.
"""
from __future__ import annotations

from dataclasses import dataclass, replace
from math import pi, sqrt
from time import perf_counter
from typing import Iterable

from os_ecvt_model import LiteratureBSFCMap, RealisticMotorMap


@dataclass(frozen=True)
class PowerSplitParameters:
    dt_s: float = 1.0
    engine_rated_w: float = 300_000.0
    engine_minimum_w: float = 60_000.0
    engine_ramp_w_per_s: float = 40_000.0
    engine_minimum_on_s: float = 5.0
    engine_minimum_off_s: float = 1.0
    engine_speed_candidates_rpm: tuple[float, ...] = (1200.0, 1500.0, 1800.0)
    engine_power_step_w: float = 10_000.0
    planetary_ratio: float = 2.6
    final_drive_ratio: float = 60.0
    wheel_radius_m: float = 0.94
    mg1_power_limit_w: float = 180_000.0
    mg2_power_limit_w: float = 180_000.0
    mg1_speed_limit_rpm: float = 7000.0
    mg2_speed_limit_rpm: float = 7000.0
    battery_bus_limit_w: float = 180_000.0
    electric_reserve_fraction: float = 0.65
    battery_capacity_wh: float = 200_000.0
    battery_nominal_voltage_v: float = 650.0
    battery_resistance_ohm: float = 0.045
    soc_min: float = 0.20
    soc_max: float = 0.80
    soc_target: float = 0.55
    accessory_power_w: float = 18_000.0
    start_fuel_g: float = 2.0
    fuel_lower_heating_value_j_kg: float = 42.7e6


@dataclass(frozen=True)
class PowerSplitState:
    soc: float = 0.55
    engine_power_w: float = 0.0
    engine_speed_rpm: float = 1500.0
    fuel_g: float = 0.0
    engine_starts: int = 0
    engine_on_time_s: float = 0.0
    engine_off_time_s: float = 1.0e9


@dataclass(frozen=True)
class PowerSplitAction:
    engine_power_w: float
    engine_speed_rpm: float


@dataclass(frozen=True)
class OperatingPoint:
    feasible: bool
    battery_bus_w: float
    battery_current_a: float
    next_soc: float
    fuel_g: float
    mg1_power_w: float
    mg2_power_w: float
    mg1_speed_rpm: float
    mg2_speed_rpm: float
    battery_loss_w: float
    reason: str = ""


class PowerSplitVirtualPlant:
    """Ideal planetary kinematics with explicit electric and battery losses."""

    def __init__(self, params: PowerSplitParameters | None = None,
                 engine_map=None, motor_map=None):
        self.p = params or PowerSplitParameters()
        self.engine_map = engine_map or LiteratureBSFCMap(
            peak=0.42, rated_power_w=self.p.engine_rated_w)
        self.motor_map = motor_map or RealisticMotorMap()

    def _electrical_power(self, mechanical_w: float, rpm: float) -> float:
        efficiency = max(0.60, float(self.motor_map.efficiency(rpm, mechanical_w)))
        if mechanical_w >= 0.0:
            return mechanical_w / efficiency
        return mechanical_w * efficiency

    def _battery_current(self, bus_w: float, soc: float) -> tuple[float, float] | None:
        p = self.p
        ocv = p.battery_nominal_voltage_v + 80.0 * (soc - p.soc_target)
        discriminant = ocv * ocv - 4.0 * p.battery_resistance_ohm * bus_w
        if discriminant < 0.0:
            return None
        current = (ocv - sqrt(discriminant)) / (2.0 * p.battery_resistance_ohm)
        return current, current * current * p.battery_resistance_ohm

    def candidate_actions(self, state: PowerSplitState) -> list[PowerSplitAction]:
        p = self.p
        engine_is_on = state.engine_power_w > 1.0
        actions = []
        if (not engine_is_on
                or state.engine_on_time_s >= p.engine_minimum_on_s):
            actions.append(PowerSplitAction(0.0, state.engine_speed_rpm))
        ramp = p.engine_ramp_w_per_s * p.dt_s
        power = p.engine_minimum_w
        while power <= p.engine_rated_w + 1e-9:
            if engine_is_on:
                admissible = abs(power - state.engine_power_w) <= ramp + 1e-9
            else:
                # A cold start enters only the minimum stable-power point;
                # subsequent increases obey the same applied-power ramp.
                admissible = (state.engine_off_time_s >= p.engine_minimum_off_s
                              and abs(power - p.engine_minimum_w) <= 1e-9)
            if admissible:
                actions.extend(PowerSplitAction(power, rpm)
                               for rpm in p.engine_speed_candidates_rpm)
            power += p.engine_power_step_w
        return actions

    def evaluate(self, state: PowerSplitState, action: PowerSplitAction,
                 wheel_demand_w: float, vehicle_speed_mps: float) -> OperatingPoint:
        p = self.p
        engine_w = max(0.0, min(p.engine_rated_w, action.engine_power_w))
        engine_on = engine_w > 1.0
        if engine_on and engine_w < p.engine_minimum_w - 1e-9:
            return OperatingPoint(False, 0, 0, state.soc, 0, 0, 0, 0, 0, 0,
                                  "engine stable-power floor")

        wheel_rpm = max(0.0, vehicle_speed_mps) / (2.0 * pi * p.wheel_radius_m) * 60.0
        ring_rpm = wheel_rpm * p.final_drive_ratio
        if engine_on:
            engine_rpm = action.engine_speed_rpm
            sun_rpm = (1.0 + p.planetary_ratio) * engine_rpm - p.planetary_ratio * ring_rpm
            ring_share = (p.planetary_ratio / (1.0 + p.planetary_ratio)
                          * ring_rpm / max(engine_rpm, 1.0))
            ring_power_w = engine_w * ring_share
            mg1_power_w = engine_w - ring_power_w
        else:
            engine_rpm = action.engine_speed_rpm
            sun_rpm = -p.planetary_ratio * ring_rpm
            ring_power_w = 0.0
            mg1_power_w = 0.0
        mg2_power_w = wheel_demand_w - ring_power_w
        mg2_rpm = ring_rpm

        if abs(mg1_power_w) > p.mg1_power_limit_w + 1e-9:
            return OperatingPoint(False, 0, 0, state.soc, 0, mg1_power_w,
                                  mg2_power_w, sun_rpm, mg2_rpm, 0, "MG1 power")
        if abs(mg2_power_w) > p.mg2_power_limit_w + 1e-9:
            return OperatingPoint(False, 0, 0, state.soc, 0, mg1_power_w,
                                  mg2_power_w, sun_rpm, mg2_rpm, 0, "MG2 power")
        if abs(sun_rpm) > p.mg1_speed_limit_rpm + 1e-9:
            return OperatingPoint(False, 0, 0, state.soc, 0, mg1_power_w,
                                  mg2_power_w, sun_rpm, mg2_rpm, 0, "MG1 speed")
        if abs(mg2_rpm) > p.mg2_speed_limit_rpm + 1e-9:
            return OperatingPoint(False, 0, 0, state.soc, 0, mg1_power_w,
                                  mg2_power_w, sun_rpm, mg2_rpm, 0, "MG2 speed")

        # Positive MG2 mechanical power consumes the bus. Positive MG1 power
        # is generated by the planetary branch and therefore charges the bus.
        mg2_bus_w = self._electrical_power(mg2_power_w, mg2_rpm)
        mg1_bus_w = self._electrical_power(-mg1_power_w, sun_rpm)
        battery_bus_w = mg2_bus_w + mg1_bus_w + p.accessory_power_w
        if abs(battery_bus_w) > p.battery_bus_limit_w + 1e-9:
            return OperatingPoint(False, battery_bus_w, 0, state.soc, 0,
                                  mg1_power_w, mg2_power_w, sun_rpm, mg2_rpm, 0,
                                  "battery bus")
        battery = self._battery_current(battery_bus_w, state.soc)
        if battery is None:
            return OperatingPoint(False, battery_bus_w, 0, state.soc, 0,
                                  mg1_power_w, mg2_power_w, sun_rpm, mg2_rpm, 0,
                                  "battery discriminant")
        current_a, battery_loss_w = battery
        capacity_ah = p.battery_capacity_wh / p.battery_nominal_voltage_v
        next_soc = state.soc - current_a * p.dt_s / (capacity_ah * 3600.0)
        if not p.soc_min - 1e-12 <= next_soc <= p.soc_max + 1e-12:
            return OperatingPoint(False, battery_bus_w, current_a, next_soc, 0,
                                  mg1_power_w, mg2_power_w, sun_rpm, mg2_rpm,
                                  battery_loss_w, "SOC")

        fuel_g = 0.0
        if engine_on:
            efficiency = max(0.08, float(self.engine_map.efficiency(engine_rpm, engine_w)))
            fuel_g = engine_w * p.dt_s / (efficiency * p.fuel_lower_heating_value_j_kg) * 1000.0
            if state.engine_power_w <= 1.0:
                fuel_g += p.start_fuel_g
        return OperatingPoint(True, battery_bus_w, current_a, next_soc, fuel_g,
                              mg1_power_w, mg2_power_w, sun_rpm, mg2_rpm,
                              battery_loss_w)

    def step(self, state: PowerSplitState, action: PowerSplitAction,
             point: OperatingPoint) -> PowerSplitState:
        if not point.feasible:
            raise ValueError(f"cannot apply infeasible action: {point.reason}")
        p = self.p
        started = state.engine_power_w <= 1.0 and action.engine_power_w > 1.0
        stopped = state.engine_power_w > 1.0 and action.engine_power_w <= 1.0
        engine_on = action.engine_power_w > 1.0
        return PowerSplitState(
            soc=point.next_soc,
            engine_power_w=action.engine_power_w,
            engine_speed_rpm=action.engine_speed_rpm,
            fuel_g=state.fuel_g + point.fuel_g,
            engine_starts=state.engine_starts + int(started),
            engine_on_time_s=(
                (0.0 if stopped else state.engine_on_time_s) + p.dt_s
                if engine_on else 0.0),
            engine_off_time_s=(
                (0.0 if started else state.engine_off_time_s) + p.dt_s
                if not engine_on else 0.0),
        )


@dataclass(frozen=True)
class ECMSSettings:
    base_equivalence_factor: float = 1.0
    proportional_gain: float = 80.0
    integral_gain: float = 0.0
    battery_throughput_weight: float = 0.02
    switching_weight_g: float = 0.2
    viability_band_soc: float = 0.015
    terminal_soc_tolerance: float = 0.001


class EnergyManager:
    def __init__(self, plant: PowerSplitVirtualPlant, mode: str,
                 settings: ECMSSettings | None = None, total_steps: int = 600):
        self.plant = plant
        self.mode = mode
        self.settings = settings or ECMSSettings()
        self.total_steps = total_steps
        self.integral_soc_error = 0.0
        self.shield_activations = 0
        self.empty_action_sets = 0

    def _soc_reference(self, step_index: int) -> float:
        """Public task-phase SOC buffer with terminal return to 0.55."""
        elapsed_s = step_index * self.plant.p.dt_s
        phase_s = elapsed_s % 270.0
        if phase_s < 120.0:
            reference = self.plant.p.soc_target + 0.015
        elif phase_s < 240.0:
            fraction = (phase_s - 120.0) / 120.0
            reference = self.plant.p.soc_target + 0.015 - 0.020 * fraction
        else:
            fraction = (phase_s - 240.0) / 30.0
            reference = self.plant.p.soc_target - 0.005 + 0.005 * fraction
        remaining_s = (self.total_steps - step_index) * self.plant.p.dt_s
        if remaining_s <= 120.0:
            reference = self.plant.p.soc_target
        elif remaining_s < 270.0:
            reference = (self.plant.p.soc_target
                         + (reference - self.plant.p.soc_target)
                         * (remaining_s - 120.0) / 150.0)
        return reference

    def _equivalence_factor(self, state: PowerSplitState, target_soc: float) -> float:
        settings = self.settings
        if self.mode in ("adaptive_ecms", "viability_ecms"):
            error = target_soc - state.soc
            self.integral_soc_error += error * self.plant.p.dt_s
            return max(0.05, settings.base_equivalence_factor
                       + settings.proportional_gain * error
                       + settings.integral_gain * self.integral_soc_error)
        return settings.base_equivalence_factor

    def _score(self, state: PowerSplitState, action: PowerSplitAction,
               point: OperatingPoint, equivalence_factor: float) -> float:
        p = self.plant.p
        battery_fuel_g = (point.battery_bus_w * p.dt_s
                          / (p.fuel_lower_heating_value_j_kg * 0.40) * 1000.0)
        throughput = abs(point.battery_bus_w) * p.dt_s / 3.6e6
        switching = (self.settings.switching_weight_g
                     if (state.engine_power_w <= 1.0) != (action.engine_power_w <= 1.0)
                     else 0.0)
        return (point.fuel_g + equivalence_factor * battery_fuel_g
                + self.settings.battery_throughput_weight * throughput + switching)

    def command(self, state: PowerSplitState, wheel_demand_w: float,
                vehicle_speed_mps: float, step_index: int) -> tuple[PowerSplitAction, OperatingPoint]:
        evaluated = [(action, self.plant.evaluate(state, action, wheel_demand_w,
                                                   vehicle_speed_mps))
                     for action in self.plant.candidate_actions(state)]
        feasible = [(action, point) for action, point in evaluated if point.feasible]
        electric_only = [item for item in feasible
                         if item[0].engine_power_w <= 1.0]
        reserve_limit = (self.plant.p.electric_reserve_fraction
                         * self.plant.p.battery_bus_limit_w)
        if (electric_only
                and abs(electric_only[0][1].battery_bus_w) > reserve_limit):
            reserve_safe = [item for item in feasible
                            if item[0].engine_power_w > 1.0]
            if reserve_safe:
                feasible = reserve_safe
        if not feasible:
            self.empty_action_sets += 1
            raise RuntimeError(
                "no feasible power-split action "
                f"(step={step_index}, demand_w={wheel_demand_w:.1f}, "
                f"engine_w={state.engine_power_w:.1f}, "
                f"on_s={state.engine_on_time_s:.1f}, off_s={state.engine_off_time_s:.1f})")

        if self.mode == "load_following":
            target = self._soc_reference(step_index)
            remaining_s = max(self.plant.p.dt_s,
                              (self.total_steps - step_index) * self.plant.p.dt_s)
            target_bus_w = ((state.soc - target)
                            * self.plant.p.battery_capacity_wh * 3600.0
                            / remaining_s)
            target_bus_w = max(-self.plant.p.battery_bus_limit_w,
                               min(self.plant.p.battery_bus_limit_w, target_bus_w))
            remaining_fraction = max(0.0, (self.total_steps - step_index - 1)
                                     / max(1, self.total_steps - 1))
            band = (0.1 * self.settings.terminal_soc_tolerance
                    + 0.002 * remaining_fraction)
            safe = [item for item in feasible
                    if target - band <= item[1].next_soc <= target + band]
            if not safe:
                safe = sorted(feasible, key=lambda item: abs(item[1].next_soc - target))[:1]
            return min(safe, key=lambda item: (
                abs(item[1].battery_bus_w - target_bus_w), item[1].fuel_g,
                abs(item[0].engine_power_w - state.engine_power_w)))

        target = self._soc_reference(step_index)
        factor = self._equivalence_factor(state, target)
        proposed = min(feasible, key=lambda item: self._score(
            state, item[0], item[1], factor))
        if self.mode != "viability_ecms":
            return proposed

        remaining_fraction = max(0.0, (self.total_steps - step_index - 1)
                                 / max(1, self.total_steps - 1))
        band = self.settings.viability_band_soc * remaining_fraction ** 2
        safe = [item for item in feasible
                if target - band <= item[1].next_soc <= target + band]
        if not safe:
            self.empty_action_sets += 1
            selected = min(feasible, key=lambda item: (
                abs(item[1].next_soc - target),
                self._score(state, item[0], item[1], factor)))
            self.shield_activations += int(selected[0] != proposed[0])
            return selected
        selected = min(safe, key=lambda item: self._score(
            state, item[0], item[1], factor))
        if selected[0] != proposed[0]:
            self.shield_activations += 1
        return selected


def run_cycle(points: Iterable, mode: str, settings: ECMSSettings | None = None,
              params: PowerSplitParameters | None = None,
              engine_map=None, motor_map=None) -> dict[str, object]:
    points = list(points)
    plant = PowerSplitVirtualPlant(params, engine_map=engine_map,
                                   motor_map=motor_map)
    state = PowerSplitState(soc=plant.p.soc_target)
    manager = EnergyManager(plant, mode, settings, len(points))
    max_abs_bus = 0.0
    max_abs_mg1 = 0.0
    max_abs_mg2 = 0.0
    max_abs_current = 0.0
    battery_loss_wh = 0.0
    decision_times_ms = []
    trajectory = []
    for index, profile_point in enumerate(points):
        wheel_demand = plant.p.accessory_power_w * 0.0 + max(
            0.0,
            (profile_point.draft_n * profile_point.soil_factor + 2500.0
             + 18_000.0 * 9.81 * profile_point.grade)
            * profile_point.speed_mps / 0.88)
        decision_started = perf_counter()
        action, operating = manager.command(state, wheel_demand,
                                            profile_point.speed_mps, index)
        decision_times_ms.append((perf_counter() - decision_started) * 1000.0)
        state = plant.step(state, action, operating)
        max_abs_bus = max(max_abs_bus, abs(operating.battery_bus_w))
        max_abs_mg1 = max(max_abs_mg1, abs(operating.mg1_power_w))
        max_abs_mg2 = max(max_abs_mg2, abs(operating.mg2_power_w))
        max_abs_current = max(max_abs_current, abs(operating.battery_current_a))
        battery_loss_wh += operating.battery_loss_w * plant.p.dt_s / 3600.0
        if index % max(1, int(30.0 / plant.p.dt_s)) == 0 or index == len(points) - 1:
            trajectory.append({
                "time_s": float(profile_point.time_s),
                "soc": state.soc,
                "engine_power_w": action.engine_power_w,
                "engine_speed_rpm": action.engine_speed_rpm,
                "battery_bus_w": operating.battery_bus_w,
            })
    soc_error = state.soc - plant.p.soc_target
    terminal_tolerance = (settings or ECMSSettings()).terminal_soc_tolerance
    terminal_energy_j = (-soc_error * plant.p.battery_capacity_wh * 3600.0)
    normalized_fuel_g = (state.fuel_g + terminal_energy_j
                         / (plant.p.fuel_lower_heating_value_j_kg * 0.42) * 1000.0)
    return {
        "mode": mode,
        "fuel_l": state.fuel_g / 832.0,
        "fuel_g": state.fuel_g,
        "energy_normalized_fuel_l": normalized_fuel_g / 832.0,
        "final_soc": state.soc,
        "soc_error": soc_error,
        "strict_valid": abs(soc_error) <= terminal_tolerance,
        "terminal_soc_tolerance": terminal_tolerance,
        "engine_starts": state.engine_starts,
        "shield_activations": manager.shield_activations,
        "empty_action_sets": manager.empty_action_sets,
        "max_abs_battery_bus_w": max_abs_bus,
        "max_abs_mg1_power_w": max_abs_mg1,
        "max_abs_mg2_power_w": max_abs_mg2,
        "max_abs_battery_current_a": max_abs_current,
        "battery_loss_wh": battery_loss_wh,
        "decision_timing_ms": {
            "mean": sum(decision_times_ms) / max(1, len(decision_times_ms)),
            "p95": sorted(decision_times_ms)[min(
                len(decision_times_ms) - 1,
                int(0.95 * len(decision_times_ms)))],
            "maximum": max(decision_times_ms, default=0.0),
        },
        "trajectory_30s": trajectory,
    }


def with_power_step(params: PowerSplitParameters, step_w: float) -> PowerSplitParameters:
    return replace(params, engine_power_step_w=step_w)
