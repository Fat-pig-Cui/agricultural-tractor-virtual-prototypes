"""DP, ECMS, deterministic MPC and scenario-robust MPC controllers."""
from __future__ import annotations
from dataclasses import dataclass, field
from math import inf
from math import exp
import numpy as np
from load_terrain_predictor import ProbabilisticPredictor, DemandPrediction
from os_ecvt_model import DrivelineState

def representative_engine_efficiency(engine_w: float) -> float:
    return max(0.22, 0.43 * (0.45 + 0.55 * exp(-((engine_w - 180000.0) / 130000.0) ** 2)))

@dataclass(frozen=True)
class EnergyCommand:
    engine_power_w: float
    objective: float = 0.0
    feasible: bool = True
    # A terminal-set safety filter is part of the recursive-feasibility MPC,
    # not an experiment-runner fallback.  The flag makes every intervention
    # auditable in the reported results.
    safety_filter_active: bool = False

class OOLController:
    def command(self, demand_w: float, soc: float) -> EnergyCommand:
        return EnergyCommand(min(300000.0, max(0.0, demand_w)))

@dataclass
class RealisticOOLController:
    """Non-ideal load-following baseline for engineering comparison."""
    minimum_engine_w: float = 60000.0
    # Ramp limit is expressed in W/s and converted with the plant sample
    # time in ``command``. The old implementation treated 40 kW/s as 40 kW
    # per 0.1 s sample, i.e. 400 kW/s.
    ramp_limit_w: float = 40000.0
    dt_s: float = 0.1
    accessory_w: float = 18000.0
    engine_rated_w: float = 300000.0
    previous_engine_w: float | None = None

    def command(self, demand_w: float, soc: float) -> EnergyCommand:
        # Accessory power is added by the plant model; do not count it twice
        # in the engine command target.
        target = max(self.minimum_engine_w, min(self.engine_rated_w, demand_w))
        if self.previous_engine_w is not None:
            step_limit = self.ramp_limit_w * self.dt_s
            target = max(self.previous_engine_w - step_limit,
                         min(self.previous_engine_w + step_limit, target))
        self.previous_engine_w = target
        return EnergyCommand(target)


@dataclass
class EngineStartStopSupervisor:
    """Shared engine on/off logic for a fair baseline/controller comparison.

    ``stop_threshold_w`` is evaluated on demanded traction/accessory power,
    not on the requested engine command, so an OOL that requests its minimum
    stable power can still shut down at idle.  Restart is forced whenever the
    motor alone cannot cover demand.  Timers are deliberately simple and
    auditable; they are engineering assumptions until measured start/stop
    data are available.
    """
    enabled: bool = False
    stop_threshold_w: float = 25000.0
    restart_threshold_w: float = 45000.0
    minimum_on_s: float = 5.0
    minimum_off_s: float = 5.0
    start_fuel_g: float = 1.5
    dt_s: float = 0.1
    motor_peak_w: float = 90000.0
    minimum_engine_w: float = 60000.0
    engine_on: bool = True
    on_time_s: float = 0.0
    off_time_s: float = 0.0
    starts: int = 0

    def apply(self, requested_engine_w: float, demand_w: float) -> tuple[float, bool, bool]:
        started = False
        if not self.enabled:
            # With start/stop disabled, an engineering comparator keeps its
            # engine running at the declared stable-power floor.  A zero
            # floor is reserved for the explicitly theoretical OOL reference.
            if self.minimum_engine_w > 0.0:
                return max(self.minimum_engine_w, max(0.0, requested_engine_w)), True, False
            on = requested_engine_w > 1000.0
            return max(0.0, requested_engine_w), on, False
        must_run = demand_w > self.motor_peak_w or demand_w >= self.restart_threshold_w
        can_stop = (demand_w <= self.stop_threshold_w and
                    self.on_time_s >= self.minimum_on_s and not must_run)
        if self.engine_on:
            if can_stop:
                self.engine_on = False
                self.off_time_s = 0.0
            else:
                self.on_time_s += self.dt_s
        else:
            self.off_time_s += self.dt_s
            # If the motor peak cannot cover demand, restart immediately;
            # waiting for the minimum-off timer would create an artificial
            # traction shortage.  The minimum-off timer only applies to a
            # discretionary restart below the motor peak.
            if (must_run or requested_engine_w >= self.restart_threshold_w) and (must_run or self.off_time_s >= self.minimum_off_s):
                self.engine_on = True
                self.on_time_s = 0.0
                self.starts += 1
                started = True
        if not self.engine_on:
            return 0.0, False, False
        # A running engine cannot be commanded below its stable operating
        # point. The plant and all controllers therefore share this rule.
        actual = max(self.minimum_engine_w, requested_engine_w)
        return actual, True, started

class PowerFollowingController:
    def command(self, demand_w: float, soc: float) -> EnergyCommand:
        return EnergyCommand(min(300000.0, max(0.0, demand_w * 0.82)))

class ECMSController:
    def command(self, demand_w: float, soc: float) -> EnergyCommand:
        assist = 80000.0 if soc > 0.55 else 15000.0
        return EnergyCommand(min(300000.0, max(0.0, demand_w - assist)))


@dataclass
class MapAwareECMSController:
    """Causal ECMS using the active plant efficiency maps.

    The controller evaluates only the present demand and a fixed equivalent
    battery-energy multiplier. Terminal SOC is still enforced by the shared
    experiment-runner correction; this class has no demand look-ahead.
    """
    equivalence_factor: float = 3.0
    engine_efficiency: callable | None = None
    motor_efficiency: callable | None = None
    candidate_spacing_w: float = 5000.0

    def _engine_efficiency(self, engine_w: float) -> float:
        if self.engine_efficiency is not None:
            return max(0.05, float(self.engine_efficiency(1500.0, engine_w)))
        return representative_engine_efficiency(engine_w)

    def _motor_efficiency(self, motor_w: float) -> float:
        if self.motor_efficiency is not None:
            return max(0.60, float(self.motor_efficiency(2400.0, motor_w)))
        return 0.93

    def command(self, demand_w: float, engine_low_w: float, engine_high_w: float) -> EnergyCommand:
        low = max(60000.0, engine_low_w)
        high = max(low, engine_high_w)
        count = max(1, int((high - low) / self.candidate_spacing_w))
        candidates = [low + index * (high - low) / count for index in range(count + 1)]
        best = (inf, low)
        for engine_w in candidates:
            motor_w = demand_w - engine_w
            efficiency = self._motor_efficiency(motor_w)
            battery_bus_w = (motor_w / efficiency if motor_w >= 0.0
                             else motor_w * efficiency)
            idle_w = 12000.0 if engine_w > 1000.0 else 0.0
            fuel_equivalent_w = (engine_w + idle_w) / self._engine_efficiency(engine_w)
            objective = fuel_equivalent_w + self.equivalence_factor * battery_bus_w
            if objective < best[0]:
                best = (objective, engine_w)
        return EnergyCommand(best[1], best[0])

@dataclass
class DynamicProgrammingReference:
    soc_grid: tuple[float, ...] = tuple(0.20 + i * 0.005 for i in range(121))
    power_grid: tuple[float, ...] = tuple(i * 10000.0 for i in range(31))
    terminal_weight: float = 10000.0
    battery_capacity_wh: float = 100e3
    terminal_tolerance: float = 0.01
    battery_power_limit_w: float = 90000.0
    motor_peak_w: float = 90000.0
    engine_efficiency: callable | None = None
    motor_efficiency: callable | None = None

    def _nearest_soc(self, value: float) -> float:
        index = round((value - self.soc_grid[0]) / 0.005)
        index = max(0, min(len(self.soc_grid) - 1, index))
        return self.soc_grid[index]

    def _engine_eff(self, engine_w: float) -> float:
        if self.engine_efficiency is not None:
            return max(0.05, self.engine_efficiency(1500.0, engine_w))
        return representative_engine_efficiency(engine_w)

    def _motor_eff(self, battery_w: float) -> float:
        if self.motor_efficiency is not None:
            return max(0.60, self.motor_efficiency(2400.0, battery_w))
        return 0.92

    def solve_with_soc(self, demands: list[float], initial_soc: float = 0.55,
                       dt_s: float = 0.1) -> tuple[list[float], list[float]]:
        if not demands:
            return [], []
        value = {soc: (0.0 if abs(soc - initial_soc) <= self.terminal_tolerance else inf)
                 for soc in self.soc_grid}
        policies: list[dict[float, float]] = []
        for demand in reversed(demands):
            next_value, action = {}, {}
            for soc in self.soc_grid:
                best_cost, best_power = inf, 0.0
                for engine in self.power_grid:
                    next_soc = self.next_soc(soc, demand, engine, dt_s)
                    if next_soc is None:
                        continue
                    nearest = self._nearest_soc(next_soc)
                    cost = self.stage_cost(demand, engine, soc, dt_s) + value[nearest]
                    if cost < best_cost:
                        best_cost, best_power = cost, engine
                next_value[soc], action[soc] = best_cost, best_power
            value, policies = next_value, [action] + policies
        # Forward roll-out on the SOC grid: tracking the grid point
        # (instead of the exact state) bounds the quantization drift so the
        # terminal SOC check is consistent with the grid the policy used.
        soc, powers, socs = initial_soc, [], [initial_soc]
        for index, demand in enumerate(demands):
            nearest = self._nearest_soc(soc)
            engine = policies[index][nearest]
            next_soc = self.next_soc(nearest, demand, engine, dt_s)
            if next_soc is None:
                return [], []
            powers.append(engine)
            soc = self._nearest_soc(next_soc)
            socs.append(soc)
        if abs(soc - initial_soc) > self.terminal_tolerance:
            return [], []
        return powers, socs

    def next_soc(self, soc: float, demand_w: float, engine_w: float, dt_s: float) -> float | None:
        battery_w = demand_w - engine_w
        if abs(battery_w) > self.motor_peak_w:
            return None
        # Motor-map-consistent charge/discharge battery-bus power.
        motor_eff = self._motor_eff(battery_w)
        battery_bus_w = battery_w / motor_eff if battery_w >= 0 else battery_w * motor_eff
        if abs(battery_bus_w) > self.battery_power_limit_w:
            return None
        next_soc = soc - battery_bus_w * dt_s / (self.battery_capacity_wh * 3600.0)
        if not (self.soc_grid[0] <= next_soc <= self.soc_grid[-1]):
            return None
        return next_soc

    def stage_cost(self, demand_w: float, engine_w: float, soc: float, dt_s: float) -> float:
        battery_w = demand_w - engine_w
        # Idle/accessory fuel consistent with the plant model.
        idle_power = 12000.0 if engine_w > 1000.0 else 0.0
        fuel_cost = max(engine_w, 0.0) + idle_power
        fuel_cost = fuel_cost / 42.7e6 / self._engine_eff(engine_w) * dt_s
        soc_penalty = 0.0
        shortage = max(0.0, demand_w - engine_w - self.motor_peak_w) ** 2 / 1e10
        return fuel_cost + soc_penalty + shortage

    def solve(self, demands: list[float], initial_soc: float = 0.55, dt_s: float = 0.1) -> list[float]:
        if not demands:
            return []
        value = {soc: (0.0 if abs(soc - initial_soc) <= self.terminal_tolerance else inf)
                 for soc in self.soc_grid}
        policies: list[dict[float, float]] = []
        for demand in reversed(demands):
            next_value, action = {}, {}
            for soc in self.soc_grid:
                best_cost, best_power = inf, 0.0
                for engine in self.power_grid:
                    next_soc = self.next_soc(soc, demand, engine, dt_s)
                    if next_soc is None:
                        continue
                    nearest = self._nearest_soc(next_soc)
                    cost = self.stage_cost(demand, engine, soc, dt_s) + value[nearest]
                    if cost < best_cost:
                        best_cost, best_power = cost, engine
                next_value[soc], action[soc] = best_cost, best_power
            value, policies = next_value, [action] + policies
        soc = initial_soc
        reference = []
        for index, demand in enumerate(demands):
            nearest = self._nearest_soc(soc)
            engine = policies[index][nearest]
            reference.append(engine)
            soc = self.next_soc(soc, demand, engine, dt_s)
            if soc is None:
                break
        if not reference or soc is None or abs(soc - initial_soc) > self.terminal_tolerance:
            return []
        return reference

def battery_bus_power(battery_w: float, motor_eff: float = 0.93) -> float:
    """Convert motor/battery-side power to battery bus power."""
    if battery_w >= 0:
        return battery_w / max(motor_eff, 1e-9)
    return battery_w * max(motor_eff, 1e-9)

@dataclass
class DeterministicMPCController:
    horizon: int = 8
    # Representative 0.1 s engine-command ramp limit.  The former 30 kW
    # default made terminal SOC recovery infeasible after an early assist.
    ramp_limit_w: float = 90000.0
    terminal_weight: float = 10000.0
    previous_engine_w: float | None = None
    soc_reference: list[float] | None = None
    # Optional plant-consistent efficiency callables.  When provided the
    # MPC fuel cost and SOC prediction use the same maps as the plant model;
    # otherwise representative proxies are used for backward compatibility.
    engine_efficiency: callable | None = None
    motor_efficiency: callable | None = None
    battery_capacity_wh: float = 100e3
    battery_power_limit_w: float = 90000.0
    motor_peak_w: float = 90000.0
    engine_rated_w: float = 300000.0
    # Bounds on the present command that remain individually reachable over
    # the most recently evaluated prediction window.  The experiment runner
    # uses them to prevent a downstream terminal-SOC correction from undoing
    # this controller's ramp-feasibility screen.
    ramp_safe_engine_min_w: float = 0.0
    ramp_safe_engine_max_w: float = float("inf")
    _motor_power_limits_w: tuple[float, float] | None = field(default=None, init=False,
                                                               repr=False)

    def reachable(self, soc: float, demands: list[float], target: float, dt_s: float = 0.1) -> bool:
        capacity = self.battery_capacity_wh * 3600.0
        low = max(0.20, soc - self.battery_power_limit_w * len(demands) * dt_s / capacity)
        high = min(0.80, soc + self.battery_power_limit_w * len(demands) * dt_s / capacity)
        return low <= target <= high

    def _engine_eff(self, engine: float) -> float:
        if self.engine_efficiency is not None:
            return max(0.05, self.engine_efficiency(1500.0, engine))
        return max(0.22, 0.43 * (0.68 + 0.32 * exp(-((engine - 180000.0) / 130000.0) ** 2)))

    def _motor_eff(self, motor_w: float) -> float:
        if self.motor_efficiency is not None:
            return max(0.60, self.motor_efficiency(2400.0, motor_w))
        return 0.93

    def _battery_bus_power(self, motor_w: float) -> float:
        return battery_bus_power(motor_w, self._motor_eff(motor_w))

    def _motor_power_limits(self) -> tuple[float, float]:
        """Maximum discharge/charge mechanical power admitted by the battery."""
        if self._motor_power_limits_w is not None:
            return self._motor_power_limits_w

        def largest_feasible_motor_power(sign: float) -> float:
            lower, upper = 0.0, self.motor_peak_w
            for _ in range(32):
                middle = (lower + upper) / 2.0
                if abs(self._battery_bus_power(sign * middle)) <= self.battery_power_limit_w:
                    lower = middle
                else:
                    upper = middle
            return lower

        self._motor_power_limits_w = (largest_feasible_motor_power(1.0),
                                      largest_feasible_motor_power(-1.0))
        return self._motor_power_limits_w

    def _engine_power_bounds(self, demand_w: float) -> tuple[float, float]:
        """Engine interval satisfying both mechanical and battery-bus limits."""
        max_assist_w, max_charge_w = self._motor_power_limits()
        return (max(0.0, demand_w - max_assist_w),
                min(self.engine_rated_w, demand_w + max_charge_w))

    def _ramp_safe_initial_bounds(self, trajectories: list[list[float]]) -> tuple[float, float]:
        """Return necessary current-power bounds for all forecast trajectories.

        At offset ``k``, a present engine command can change by at most
        ``k * ramp_limit_w``.  Intersecting those backward-reachable power
        intervals blocks a high present command that cannot be reduced before
        an upcoming low-demand point exceeds the motor charging limit (and the
        analogous low-command traction case).
        """
        low_bound, high_bound = 0.0, self.engine_rated_w
        for trajectory in trajectories:
            for offset, demand in enumerate(trajectory[:self.horizon]):
                engine_low, engine_high = self._engine_power_bounds(demand)
                reachable_delta = offset * self.ramp_limit_w
                low_bound = max(low_bound, engine_low - reachable_delta)
                high_bound = min(high_bound, engine_high + reachable_delta)
        return low_bound, high_bound

    def _ramp_feasible_engine_path(self, initial_engine_w: float,
                                   trajectory: list[float],
                                   battery_target_w: float = 0.0) -> list[float] | None:
        """Construct a causal ramp-limited feasible engine trajectory.

        The legacy score held the current candidate fixed throughout a
        horizon.  That can reject a feasible engine ramp after a forecast
        load change, causing a hidden fallback policy to dominate.  Here each
        later setpoint tracks the SOC-guided preferred split only within the
        interval reachable from the preceding engine power and compatible
        with the motor envelope.
        """
        path: list[float] = []
        previous = initial_engine_w
        for offset, demand in enumerate(trajectory[:self.horizon]):
            engine_low, engine_high = self._engine_power_bounds(demand)
            if offset == 0:
                low, high = engine_low, engine_high
                preferred = initial_engine_w
            else:
                low = max(engine_low, previous - self.ramp_limit_w)
                high = min(engine_high, previous + self.ramp_limit_w)
                preferred = demand - battery_target_w
            if low > high + 1e-9:
                return None
            engine = max(low, min(high, preferred))
            path.append(engine)
            previous = engine
        return path

    def command(self, demand_w: float, soc: float, predicted_demands: list[float], terminal_reference: float = 0.55,
                remaining_steps: int | None = None, soc_reference: float | None = None) -> EnergyCommand:
        # Convert the remaining SOC error into a bounded battery-power target.
        # This is the receding-horizon analogue of a DP terminal SOC
        # constraint; it prevents the controller from spending the battery
        # early and discovering an infeasible terminal state at the end.
        # When a DP-style SOC reference trajectory is available it is used
        # instead: the terminal target is the reference at the end of the
        # prediction window, which avoids crude whole-remaining-time
        # extrapolation on non-stationary work cycles.
        remaining = max(1, remaining_steps or len(predicted_demands))
        horizon_target = terminal_reference
        if soc_reference is not None:
            # Reference at the end of the prediction window.
            horizon_target = soc_reference
        # Convert the SOC gap into a bounded battery-power target over the
        # WHOLE remaining cycle, not the prediction window: this is the
        # macro charge/discharge guidance (charge in idle/transport segments,
        # discharge in plough segments), while the window cost below handles
        # the micro fuel-vs-battery trade-off.
        battery_target = (soc - horizon_target) * self.battery_capacity_wh * 3600.0 / (remaining * 0.1)
        battery_target = max(-self.battery_power_limit_w, min(self.battery_power_limit_w, battery_target))
        # Engine candidates must also respect the bidirectional motor limit:
        # ``demand - engine`` is motor/battery bus power, so charging cannot
        # exceed the same 90 kW bound as traction assist.
        engine_low, engine_high = self._engine_power_bounds(demand_w)
        offsets = (-self.motor_peak_w, -0.5 * self.motor_peak_w, 0.0,
                   0.5 * self.motor_peak_w, self.motor_peak_w)
        candidates = [max(engine_low, min(engine_high, demand_w + offset - battery_target))
                      for offset in offsets]
        candidates += [max(engine_low, min(engine_high, p)) for p in
                       (60000.0, 90000.0, 120000.0, 135000.0, 150000.0,
                        165000.0, 180000.0, 195000.0, 210000.0, 225000.0,
                        240000.0, 270000.0, self.engine_rated_w)]
        candidates = list(dict.fromkeys(candidates))
        future_window = predicted_demands[: self.horizon]
        # The first horizon sample is the already measured present load, not
        # a forecast.  Leaving a predictor mean at k=0 can make the internal
        # ramp/electrical screen inconsistent with the applied current-load
        # bounds even though no future information is involved.
        future_window = ([demand_w] + future_window[1:]) if future_window else [demand_w]
        (self.ramp_safe_engine_min_w,
         self.ramp_safe_engine_max_w) = self._ramp_safe_initial_bounds([future_window])
        candidates += [max(engine_low, min(engine_high, value)) for value in
                       (self.ramp_safe_engine_min_w, self.ramp_safe_engine_max_w)]
        if self.previous_engine_w is not None:
            candidates += [max(engine_low, min(engine_high, value)) for value in
                           (self.previous_engine_w - self.ramp_limit_w,
                            self.previous_engine_w,
                            self.previous_engine_w + self.ramp_limit_w)]
        candidates = list(dict.fromkeys(candidates))
        best = (inf, candidates[0])
        dt_s = 0.1
        for engine in candidates:
            if self.previous_engine_w is not None and abs(engine - self.previous_engine_w) > self.ramp_limit_w:
                continue
            engine_path = self._ramp_feasible_engine_path(
                engine, future_window, battery_target)
            if engine_path is None:
                continue
            total = 0.0
            predicted_soc = soc
            # A horizon-length battery-power calculation cannot determine
            # reachability of a terminal target over the remaining cycle.
            # The candidate is therefore screened by its per-step envelope
            # and charged a terminal-SOC cost below; final feasibility is
            # evaluated on the simulated closed-loop trajectory.
            for future, planned_engine in zip(future_window, engine_path):
                battery = future - planned_engine
                if (abs(battery) > self.motor_peak_w
                        or abs(self._battery_bus_power(battery)) > self.battery_power_limit_w):
                    total = inf
                    break
                shortage = max(0.0, battery - self.motor_peak_w) ** 2 / 1e10
                efficiency = self._engine_eff(planned_engine)
                idle_power = 12000.0 if planned_engine > 1000.0 else 0.0
                total += (planned_engine + idle_power) / 42.7e6 / efficiency * dt_s + shortage + 0.015 * (abs(battery) / self.motor_peak_w) ** 2
                bus = battery_bus_power(battery, self._motor_eff(battery))
                predicted_soc -= bus * dt_s / (self.battery_capacity_wh * 3600.0)
            if total == inf:
                continue
            if soc_reference is not None:
                # Soft tracking of the DP SOC reference.  The battery-power
                # limit makes exact window-end matching physically
                # impossible, so a hard filter would reject every candidate
                # and fall back to a power-infeasible action; the macro SOC
                # closure is carried by the battery_target steering instead.
                total += self.terminal_weight * (predicted_soc - soc_reference) ** 2
            else:
                remaining_tail = max(0, remaining - len(future_window))
                tail_battery = (future_window[-1] - engine_path[-1]) if future_window else (demand_w - engine)
                tail_bus = battery_bus_power(tail_battery, self._motor_eff(tail_battery))
                terminal_soc_est = predicted_soc - tail_bus * remaining_tail * dt_s / (self.battery_capacity_wh * 3600.0)
                # A constant-demand tail is only a terminal-SOC estimate,
                # not a known future trajectory.  Treat it as a soft
                # terminal cost; rejecting every candidate on this estimate
                # silently turns the controller into a fallback policy.
                total += self.terminal_weight * (terminal_soc_est - terminal_reference) ** 2
            total += 0.15 * ((engine - 180000.0) / 180000.0) ** 2
            if total < best[0]:
                best = total, engine
        self.previous_engine_w = best[1]
        return EnergyCommand(best[1], best[0], best[0] < inf)

@dataclass
class ScenarioMPCController(DeterministicMPCController):
    predictor: ProbabilisticPredictor | None = None
    scenario_count: int = 5
    aging_weight: float = 0.015

    def command(self, demand_w: float, soc: float, prediction: DemandPrediction, terminal_reference: float = 0.55,
                remaining_steps: int | None = None, soc_reference: float | None = None,
                scenario_trajectories: list[list[float]] | None = None) -> EnergyCommand:
        predictor = self.predictor or ProbabilisticPredictor()
        # Legacy scalar scenarios are retained for backwards-compatible
        # benchmarks.  A phase-aware caller can instead supply independent
        # horizon trajectories formed from common prior information and the
        # current measurement, never the evaluated future realization.
        scenarios = scenario_trajectories or [
            [value] * self.horizon
            for value in predictor.scenarios(prediction, self.scenario_count)
        ]
        # Anchor every scenario at the measured current demand.  Only future
        # offsets remain uncertain; this aligns the scenario constraints with
        # the current electrical interval used to form the first command.
        scenarios = [([demand_w] + scenario[1:]) if scenario else [demand_w]
                     for scenario in scenarios]
        remaining = max(1, remaining_steps or self.horizon)
        horizon_target = terminal_reference
        if soc_reference is not None:
            horizon_target = soc_reference
        battery_target = (soc - horizon_target) * self.battery_capacity_wh * 3600.0 / (remaining * 0.1)
        battery_target = max(-self.battery_power_limit_w, min(self.battery_power_limit_w, battery_target))
        engine_low, engine_high = self._engine_power_bounds(demand_w)
        offsets = (-self.motor_peak_w, -0.5 * self.motor_peak_w, 0.0,
                   0.5 * self.motor_peak_w, self.motor_peak_w)
        candidates = [max(engine_low, min(engine_high, demand_w + offset - battery_target))
                      for offset in offsets]
        candidates += [max(engine_low, min(engine_high, p)) for p in
                       (60000.0, 90000.0, 120000.0, 135000.0, 150000.0,
                        165000.0, 180000.0, 195000.0, 210000.0, 225000.0,
                        240000.0, 270000.0, self.engine_rated_w)]
        candidates = list(dict.fromkeys(candidates))
        (self.ramp_safe_engine_min_w,
         self.ramp_safe_engine_max_w) = self._ramp_safe_initial_bounds(scenarios)
        candidates += [max(engine_low, min(engine_high, value)) for value in
                       (self.ramp_safe_engine_min_w, self.ramp_safe_engine_max_w)]
        if self.previous_engine_w is not None:
            candidates += [max(engine_low, min(engine_high, value)) for value in
                           (self.previous_engine_w - self.ramp_limit_w,
                            self.previous_engine_w,
                            self.previous_engine_w + self.ramp_limit_w)]
        candidates = list(dict.fromkeys(candidates))
        best = (inf, candidates[0])
        for engine in candidates:
            if self.previous_engine_w is not None and abs(engine - self.previous_engine_w) > self.ramp_limit_w:
                continue
            scenario_paths = [self._ramp_feasible_engine_path(
                engine, scenario, battery_target) for scenario in scenarios]
            if any(path is None for path in scenario_paths):
                continue
            worst = 0.0
            for scenario, engine_path in zip(scenarios, scenario_paths):
                assert engine_path is not None
                # Each demand realization must carry an independent SOC
                # trajectory.  Averaging SOC changes across scenarios before
                # applying one terminal penalty hides the worst terminal
                # outcome and is not a scenario-MPC formulation.
                predicted_soc = soc
                scenario_cost = 0.0
                for future, planned_engine in zip(scenario[:self.horizon], engine_path):
                    battery = future - planned_engine
                    if (abs(battery) > self.motor_peak_w
                            or abs(self._battery_bus_power(battery)) > self.battery_power_limit_w):
                        scenario_cost = inf
                        break
                    wear = self.aging_weight * (abs(battery) / self.motor_peak_w) ** 2
                    bus = battery_bus_power(battery, self._motor_eff(battery))
                    predicted_soc -= bus * 0.1 / (self.battery_capacity_wh * 3600.0)
                    efficiency = self._engine_eff(planned_engine)
                    idle_power = 12000.0 if planned_engine > 1000.0 else 0.0
                    scenario_cost += ((planned_engine + idle_power) / 42.7e6 / efficiency * 0.1
                                      + wear)
                if scenario_cost == inf:
                    worst = inf
                    break
                if soc_reference is not None:
                    scenario_cost += self.terminal_weight * (predicted_soc - soc_reference) ** 2
                else:
                    remaining_tail = max(0, remaining - self.horizon)
                    tail_battery = ((scenario[-1] if scenario else demand_w)
                                    - engine_path[-1])
                    tail_bus = battery_bus_power(tail_battery, self._motor_eff(tail_battery))
                    terminal_soc_est = predicted_soc - tail_bus * remaining_tail * 0.1 / (self.battery_capacity_wh * 3600.0)
                    scenario_cost += self.terminal_weight * (terminal_soc_est - terminal_reference) ** 2
                worst = max(worst, scenario_cost)
            if worst == inf:
                continue
            objective = worst
            if objective < best[0]:
                best = objective, engine
        self.previous_engine_w = best[1]
        return EnergyCommand(best[1], best[0], best[0] < inf)


@dataclass
class RecursiveFeasibleScenarioMPCController(ScenarioMPCController):
    """Scenario MPC with a terminal backward-reachable set and safety filter.

    The nominal scenario search remains deliberately small and causal.  If it
    cannot provide an admissible first action, the controller projects a
    charge-sustaining command into the *actual* current electrical/ramp set
    and retains only actions whose successor SOC lies in a terminal-energy
    viability envelope.  The construction prevents a finite candidate search
    from silently delegating an empty intersection to the experiment runner.
    It is a conditional recursive-feasibility structure for the declared
    virtual input bounds, verified on the frozen paths; it is not a formal
    robust-feasibility proof for arbitrary unmodelled load jumps.
    """

    terminal_soc_tolerance: float = 1e-4
    safety_filter_activations: int = 0

    def _present_feasible_engine_bounds(self, demand_w: float) -> tuple[float, float]:
        """Intersect the measured-load electrical interval with the ramp set."""
        low, high = self._engine_power_bounds(demand_w)
        if self.previous_engine_w is not None:
            low = max(low, self.previous_engine_w - self.ramp_limit_w)
            high = min(high, self.previous_engine_w + self.ramp_limit_w)
        return low, high

    def terminal_reachable_soc_bounds(self, remaining_steps: int,
                                      terminal_reference: float,
                                      dt_s: float = 0.1) -> tuple[float, float]:
        """Terminal-energy viability envelope for the declared terminal band.

        The virtual battery may exchange at most ``battery_power_limit_w`` at
        every remaining sample.  It is a necessary terminal-energy envelope;
        present mechanical and ramp feasibility is checked separately before
        an action is chosen.  The full closed-loop path is reported so this
        approximation cannot be mistaken for a universal robust certificate.
        """
        capacity_j = self.battery_capacity_wh * 3600.0
        delta_soc = self.battery_power_limit_w * max(0, remaining_steps) * dt_s / capacity_j
        return (max(0.20, terminal_reference - delta_soc - self.terminal_soc_tolerance),
                min(0.80, terminal_reference + delta_soc + self.terminal_soc_tolerance))

    def terminal_set_contains(self, soc: float, remaining_steps: int,
                              terminal_reference: float,
                              dt_s: float = 0.1) -> bool:
        low, high = self.terminal_reachable_soc_bounds(
            remaining_steps, terminal_reference, dt_s)
        return low - 1e-10 <= soc <= high + 1e-10

    def _successor_soc(self, soc: float, demand_w: float, engine_w: float,
                       dt_s: float = 0.1) -> float:
        battery_w = demand_w - engine_w
        bus_w = self._battery_bus_power(battery_w)
        return soc - bus_w * dt_s / (self.battery_capacity_wh * 3600.0)

    def _terminal_safe_action(self, requested_engine_w: float, demand_w: float,
                              soc: float, terminal_reference: float,
                              remaining_steps: int) -> tuple[float, bool] | None:
        """Project a request onto the present action set and next terminal set."""
        low, high = self._present_feasible_engine_bounds(demand_w)
        if low > high + 1e-9:
            return None
        next_low, next_high = self.terminal_reachable_soc_bounds(
            max(0, remaining_steps - 1), terminal_reference)
        # Battery bus power is monotone over the virtual map, but use a small
        # deterministic grid instead of assuming an analytic inverse of a
        # user-supplied component map.
        candidates = [low, high, max(low, min(high, requested_engine_w))]
        candidates.extend(float(value) for value in np.linspace(low, high, 65))
        candidates = list(dict.fromkeys(candidates))
        admissible = [
            value for value in candidates
            if next_low - 1e-10 <= self._successor_soc(soc, demand_w, value) <= next_high + 1e-10
        ]
        if not admissible:
            closest = min(candidates, key=lambda value: abs(
                self._successor_soc(soc, demand_w, value)
                - max(next_low, min(next_high,
                                    self._successor_soc(soc, demand_w, value)))))
            return closest, False
        return min(admissible, key=lambda value: abs(value - requested_engine_w)), True

    def command(self, demand_w: float, soc: float, prediction: DemandPrediction,
                terminal_reference: float = 0.55, remaining_steps: int | None = None,
                soc_reference: float | None = None,
                scenario_trajectories: list[list[float]] | None = None) -> EnergyCommand:
        remaining = max(1, remaining_steps or self.horizon)
        nominal = super().command(
            demand_w, soc, prediction, terminal_reference=terminal_reference,
            remaining_steps=remaining, soc_reference=soc_reference,
            scenario_trajectories=scenario_trajectories)

        # A failed finite scenario intersection is resolved inside the
        # controller by its declared terminal-set policy, not by an opaque
        # command inserted later by the experiment runner.
        capacity_j = self.battery_capacity_wh * 3600.0
        terminal_bus_target_w = ((soc - terminal_reference) * capacity_j
                                 / max(0.1, remaining * 0.1))
        requested = nominal.engine_power_w if nominal.feasible else demand_w - terminal_bus_target_w
        safe = self._terminal_safe_action(requested, demand_w, soc,
                                          terminal_reference, remaining)
        if safe is None:
            # The virtual plant itself has no current ramp/electrical action.
            # Preserve the failed status; this exceptional condition remains
            # visible to the normal experiment validity accounting.
            return EnergyCommand(nominal.engine_power_w, nominal.objective, False, True)
        engine_w, successor_in_terminal_set = safe
        safety_filter_active = (not nominal.feasible
                                or abs(engine_w - nominal.engine_power_w) > 1e-7)
        if safety_filter_active:
            self.safety_filter_activations += 1
        self.previous_engine_w = engine_w
        # The post-policy terminal governor must be constrained only by the
        # measured-load/ramp set.  A forecast intersection belongs to the
        # nominal optimizer, not to the recursive safety certificate.
        self.ramp_safe_engine_min_w, self.ramp_safe_engine_max_w = (
            self._present_feasible_engine_bounds(demand_w))
        return EnergyCommand(engine_w, nominal.objective, successor_in_terminal_set,
                             safety_filter_active)


@dataclass
class SegmentReference:
    """Offline optimal piecewise-constant engine-power reference.

    For a work cycle built from repeated segments (idle/transport/plough/
    turn) the offline optimum is one constant engine power per segment with
    terminal SOC closure.  The reference trajectory is used by the MPC as
    the DP-style SOC schedule to track; this avoids the grid-quantization
    drift of the discrete DP on long horizons while keeping a strictly
    plant-consistent optimality benchmark.
    """

    segment_count: int = 4
    maxiter: int = 800
    # Boundaries (seconds, within one work-cycle repetition) that delimit
    # the segments, e.g. (0, 30, 120, 240, 270) for idle/transport/plough/
    # turn.  When empty the horizon is split into equal parts.  Smooth
    # 5 s transitions between work phases must be given their own segments
    # (e.g. (0, 25, 30, 115, 120, 235, 240, 265, 270)) so the reference can
    # ramp power during the transition instead of producing a shortage.
    segment_boundaries_s: tuple[float, ...] = ()

    def solve(self, model, demands: list[float], profile, initial_soc: float = 0.55,
              terminal_tolerance: float = 0.01, dt_s: float = 0.1,
              battery_power_limit_w: float = 90000.0,
              regen_powers: list[float] | None = None,
              engine_ramp_limit_w_per_s: float | None = None,
              minimum_engine_w: float = 0.0) -> tuple[list[float], list[float]]:
        """Return (engine_power_reference, soc_reference) of length len(demands)."""
        demands = np.asarray(demands, dtype=float)
        horizon = len(demands)
        if regen_powers is None:
            regen_powers = [0.0] * horizon
        if len(regen_powers) != horizon:
            raise ValueError("regen_powers must have the same length as demands")

        def applied_power_sequence(requested_powers):
            """Apply the same continuous-engine constraints as the plant run."""
            requested = np.asarray(requested_powers, dtype=float)
            if engine_ramp_limit_w_per_s is None:
                return requested
            applied = np.empty(horizon)
            previous = None
            step_limit_w = engine_ramp_limit_w_per_s * dt_s
            for index, request in enumerate(requested):
                target = max(minimum_engine_w, float(request))
                if previous is not None:
                    target = max(previous - step_limit_w,
                                 min(previous + step_limit_w, target))
                applied[index] = target
                previous = target
            return applied

        def regen_bus(regen_power_w: float) -> float:
            return -regen_power_w * model.motor_map.efficiency(2400.0, -regen_power_w)
        if self.segment_boundaries_s:
            boundaries = self.segment_boundaries_s
            cycle_s = boundaries[-1]
            segment_of = np.zeros(horizon, dtype=int)
            for i in range(horizon):
                t = (i * dt_s) % cycle_s
                for s in range(len(boundaries) - 1):
                    if boundaries[s] <= t < boundaries[s + 1]:
                        segment_of[i] = s
                        break
                else:
                    segment_of[i] = len(boundaries) - 2
            segment_count = len(boundaries) - 1
        else:
            segment_count = self.segment_count
            segment_of = np.zeros(horizon, dtype=int)
            cycle = horizon // segment_count
            for s in range(segment_count):
                segment_of[s * cycle:(s + 1) * cycle] = s
            for i in range(segment_count * cycle, horizon):
                segment_of[i] = i % segment_count

        def simulate(requested_powers):
            powers = applied_power_sequence(requested_powers)
            state = DrivelineState(soc=initial_soc)
            shortage = 0.0
            violations = 0.0
            for d, e, regen_power, point in zip(demands, powers, regen_powers, profile):
                external_bus_w = regen_bus(float(regen_power))
                state = model.step(state, d, float(e),
                                   external_battery_bus_w=external_bus_w)
                shortage = max(shortage, max(0.0, d - float(e) - model.p.motor_peak_w))
                report = model.constraint_report(
                    float(d), float(e), point.speed_mps,
                    regen_power_w=float(regen_power),
                    external_battery_bus_w=external_bus_w)
                violations = max(violations, *report.values())
            return model.equivalent_fuel_l(state), state.soc - initial_soc, shortage, violations

        def seq_from(x):
            seq = np.empty(horizon)
            for s in range(segment_count):
                seq[segment_of == s] = np.clip(x[s], 0.0, model.p.engine_rated_w)
            return seq

        def objective(x):
            fuel, _, shortage, violation = simulate(seq_from(x))
            # Feasibility pressure: a reference with a power shortage is
            # useless, so the shortage enters the objective quadratically.
            return (fuel + 1e-6 * max(0.0, shortage - 1.0) ** 2
                    + 1e-6 * max(0.0, violation - 1.0) ** 2)

        def closure(x):
            return simulate(seq_from(x))[1]

        from scipy.optimize import minimize as _minimize
        # Multi-start: the segment problem is non-convex, so a single SLSQP
        # run from the mean-power start can land on a poor local optimum
        # (e.g. charging hard during idle).  Start from a few physically
        # sensible schedules and keep the best feasible solution.
        segment_means = [demands[segment_of == s].mean() for s in range(segment_count)]
        starts = []
        starts.append(np.array([m for m in segment_means]))
        starts.append(np.full(segment_count, demands.mean() * 0.9))
        high_efficiency = np.array([segment_means, np.full(segment_count, 180000.0)]).mean(axis=0)
        starts.append(high_efficiency)
        if segment_count == 8:
            starts.append(np.array([90000.0, 120000.0, 150000.0, 160000.0,
                                    200000.0, 200000.0, 110000.0, 120000.0]))
            starts.append(np.array([105000.0, 105000.0, 190000.0, 190000.0,
                                    205000.0, 205000.0, 129000.0, 129000.0]))
        best = None
        for start in starts:
            res = _minimize(objective, np.clip(start, 0.0, model.p.engine_rated_w),
                            method="SLSQP",
                            constraints={"type": "eq", "fun": closure},
                            bounds=[(0.0, model.p.engine_rated_w)] * segment_count,
                            options={"maxiter": self.maxiter, "ftol": 1e-7})
            x = np.clip(res.x, 0.0, model.p.engine_rated_w)
            fuel, soc_err, shortage, violation = simulate(seq_from(x))
            if abs(soc_err) <= terminal_tolerance and shortage <= 1.0 and violation <= 1.0:
                if best is None or fuel < best[0]:
                    best = (fuel, x)
        if best is None:
            return [], []
        _, x_best = best
        powers = applied_power_sequence(seq_from(x_best))
        soc_traj = [initial_soc]
        state = DrivelineState(soc=initial_soc)
        for index, (d, e, regen_power) in enumerate(zip(demands, powers, regen_powers)):
            if index < len(demands) - 1:
                state = model.step(state, d, float(e),
                                   external_battery_bus_w=regen_bus(float(regen_power)))
                soc_traj.append(state.soc)
        return list(powers), soc_traj
