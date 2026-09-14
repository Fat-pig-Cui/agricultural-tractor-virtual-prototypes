"""OS-ECVT longitudinal model with planetary split and efficiency maps."""
from __future__ import annotations
from dataclasses import dataclass
from math import exp
from config.parameters import PowertrainParameters

@dataclass
class DrivelineState:
    soc: float = 0.55
    speed_mps: float = 1.8
    engine_power_w: float = 0.0
    fuel_g: float = 0.0
    battery_current_a: float = 0.0
    engine_on: bool = True
    engine_starts: int = 0

class EfficiencyMap:
    def __init__(self, peak: float, width: float, center_rpm: float,
                 preferred_power_w: float = 180000.0,
                 power_width_w: float = 130000.0):
        self.peak, self.width, self.center_rpm = peak, width, center_rpm
        self.preferred_power_w = preferred_power_w
        self.power_width_w = power_width_w
    def efficiency(self, rpm: float, power_w: float) -> float:
        speed_factor = exp(-((rpm - self.center_rpm) / self.width) ** 2)
        # A representative BSFC island: low-load operation is inefficient,
        # while the mid-load region around 180 kW is preferred.  This is a
        # parameterized theoretical map, not a calibrated engine map.
        power_factor = exp(-((abs(power_w) - self.preferred_power_w) /
                             self.power_width_w) ** 2)
        # Diesel engines have a pronounced low-load BSFC penalty.  The
        # 0.45/0.55 weighting is a representative research proxy; it must be
        # replaced by a calibrated 2-D BSFC map for a product claim.
        load_floor = 0.42 if abs(power_w) < 20000.0 else 0.45
        efficiency = self.peak * (load_floor + 0.55 * power_factor) * (0.82 + 0.18 * speed_factor)
        return max(0.18, min(self.peak, efficiency))


class RealisticDieselMap(EfficiencyMap):
    """BSFC-style efficiency island with a strong low-load penalty.

    Efficiency falls to ``low_load_efficiency`` at low load and peaks at
    ``peak`` near ``preferred_power_w`` with island width
    ``power_width_w``.  This shape reproduces the low-load BSFC degradation
    of turbocharged diesel engines; it is still a research proxy until a
    calibrated 2-D BSFC map replaces it.
    """
    def __init__(self, peak: float = 0.43, width: float = 450.0,
                 center_rpm: float = 1500.0,
                 preferred_power_w: float = 180000.0,
                 power_width_w: float = 90000.0,
                 low_load_efficiency: float = 0.25):
        super().__init__(peak, width, center_rpm, preferred_power_w, power_width_w)
        self.low_load_efficiency = low_load_efficiency

    def efficiency(self, rpm: float, power_w: float) -> float:
        # Explicit 2-D BSFC-style grid. Values are a parameterized proxy and
        # should be replaced by a calibrated engine map for product claims.
        rpm_grid = (1000.0, 1500.0, 2000.0, 2400.0)
        load_grid = (0.0, 0.2, 0.4, 0.6, 0.8, 1.0)
        base = (
            (0.18, 0.27, 0.35, 0.40, 0.40, 0.37),
            (0.20, 0.31, 0.39, 0.43, 0.42, 0.39),
            (0.19, 0.30, 0.38, 0.41, 0.40, 0.37),
            (0.17, 0.27, 0.35, 0.38, 0.37, 0.34),
        )
        # Scale the idle column to expose the requested low-load sensitivity.
        rows = [list(row) for row in base]
        for row in rows:
            row[0] = self.low_load_efficiency
            # Treat the first 20% load column as part of the low-load island
            # as well. This makes the sensitivity parameter physically
            # meaningful for a realistic OOL held at its minimum stable
            # power, rather than changing only the exact zero-power point.
            row[1] = min(row[1], self.low_load_efficiency + 0.08)
        load = min(1.0, max(0.0, abs(power_w) / 300000.0))
        ri = min(range(len(rpm_grid)), key=lambda i: abs(rpm_grid[i] - rpm))
        if rpm <= rpm_grid[0]:
            r0 = r1 = 0; rf = 0.0
        elif rpm >= rpm_grid[-1]:
            r0 = r1 = len(rpm_grid) - 1; rf = 0.0
        else:
            r1 = next(i for i, value in enumerate(rpm_grid) if value >= rpm)
            r0 = r1 - 1; rf = (rpm - rpm_grid[r0]) / (rpm_grid[r1] - rpm_grid[r0])
        if load <= load_grid[0]:
            l0 = l1 = 0; lf = 0.0
        elif load >= load_grid[-1]:
            l0 = l1 = len(load_grid) - 1; lf = 0.0
        else:
            l1 = next(i for i, value in enumerate(load_grid) if value >= load)
            l0 = l1 - 1; lf = (load - load_grid[l0]) / (load_grid[l1] - load_grid[l0])
        e0 = rows[r0][l0] + lf * (rows[r0][l1] - rows[r0][l0])
        e1 = rows[r1][l0] + lf * (rows[r1][l1] - rows[r1][l0])
        return max(0.12, min(self.peak, e0 + rf * (e1 - e0)))


class DeutzBSFCMap(EfficiencyMap):
    """Efficiency map derived from the published Deutz BF 6M 2012 C data.

    The hourly fuel consumption regression fitted to CAN-bus records of the
    Terrion ATM 4200 engine (Devyanin et al., 2023,
    DOI: 10.22314/2073-7599-2023-17-4-68-74) is used to compute a 2-D
    speed-load efficiency grid::

        G_TO = -0.7219 + 2.6123e-3*n + 4.93e-3*M + 0.1743e-3*n*M
                - 0.2092e-6*n^2 - 0.0172e-3*M^2    [L/h]

    with relative torque M in percent, nominal torque M_H = 592 N*m,
    diesel density 820 kg/m3 and specific-energy efficiency
    eta = 3600 / (ge * 42.7) with ge in g/kWh.  The grid is built on the
    rated 1500 rpm line and re-scaled to the project's engine rated power,
    so the map keeps the measured low-load penalty shape without claiming
    that the 300 kW platform was itself bench-calibrated.
    """

    def __init__(self, rated_power_w: float = 300000.0,
                 nominal_torque_nm: float = 592.0,
                 rated_rpm: float = 1500.0):
        super().__init__(0.33, 450.0, rated_rpm)
        self.rated_power_w = rated_power_w
        self.nominal_torque_nm = nominal_torque_nm
        self.rated_rpm = rated_rpm

    def _hourly_fuel_lph(self, rpm: float, torque_pct: float) -> float:
        n, m = rpm, torque_pct
        return (-0.7219 + 2.6123e-3 * n + 4.93e-3 * m + 0.1743e-3 * n * m
                - 0.2092e-6 * n * n - 0.0172e-3 * m * m)

    def _efficiency_at(self, rpm: float, torque_pct: float) -> float:
        power_w = (rpm * torque_pct / 100.0 * self.nominal_torque_nm
                   / 9550.0) * 1000.0
        if power_w <= 100.0:
            return 0.10
        fuel_kg_h = self._hourly_fuel_lph(rpm, torque_pct) * 820.0 / 1000.0
        ge = fuel_kg_h / (power_w / 1000.0) * 1000.0  # g/kWh
        efficiency = 3600.0 / (ge * 42.7)
        return max(0.08, min(0.35, efficiency))

    def efficiency(self, rpm: float, power_w: float) -> float:
        # Load the requested power on the rated-speed line as relative
        # torque, then interpolate the measured speed-load grid.
        load_pct = min(105.0, max(0.0, abs(power_w) / self.rated_power_w * 100.0))
        n_grid = (750.0, 1100.0, 1500.0, 1800.0, 2150.0, 2500.0)
        if rpm <= n_grid[0]:
            e_r = self._efficiency_at(n_grid[0], load_pct)
        elif rpm >= n_grid[-1]:
            e_r = self._efficiency_at(n_grid[-1], load_pct)
        else:
            r1 = next(i for i, value in enumerate(n_grid) if value >= rpm)
            r0 = r1 - 1
            f = (rpm - n_grid[r0]) / (n_grid[r1] - n_grid[r0])
            e0 = self._efficiency_at(n_grid[r0], load_pct)
            e1 = self._efficiency_at(n_grid[r1], load_pct)
            e_r = e0 + f * (e1 - e0)
        return max(0.08, min(0.35, e_r))


class LiteratureBSFCMap(EfficiencyMap):
    """Two-dimensional BSFC map: measured low-load penalty shape, modern peak.

    The speed-load dependence of the hourly fuel consumption is taken from
    the CAN-bus regression of the Deutz BF 6M 2012 C in the Terrion ATM 4200
    (Devyanin et al., 2023, DOI: 10.22314/2073-7599-2023-17-4-68-74).  The
    measured shape is normalised to its peak and re-scaled to a modern
    large-displacement diesel peak (default 0.42, corresponding to roughly
    200-215 g/kWh), because the project platform is a 300 kW-class engine
    rather than the 155 kW Deutz unit.  The low-load penalty (10% load ->
    ~0.23, 20% -> ~0.31 at the modern peak) is therefore literature-based
    while the absolute efficiency level follows the modern platform.
    """

    def __init__(self, peak: float = 0.42, rated_power_w: float = 300000.0,
                 nominal_torque_nm: float = 592.0, rated_rpm: float = 1500.0):
        super().__init__(peak, 450.0, rated_rpm)
        self.peak_eff = peak
        self.rated_power_w = rated_power_w
        self.nominal_torque_nm = nominal_torque_nm
        self.rated_rpm = rated_rpm

    def _hourly_fuel_lph(self, rpm: float, torque_pct: float) -> float:
        n, m = rpm, torque_pct
        return (-0.7219 + 2.6123e-3 * n + 4.93e-3 * m + 0.1743e-3 * n * m
                - 0.2092e-6 * n * n - 0.0172e-3 * m * m)

    def _relative_efficiency(self, rpm: float, torque_pct: float) -> float:
        power_w = (rpm * torque_pct / 100.0 * self.nominal_torque_nm
                   / 9550.0) * 1000.0
        if power_w <= 100.0:
            return 0.30
        fuel_kg_h = self._hourly_fuel_lph(rpm, torque_pct) * 820.0 / 1000.0
        ge = fuel_kg_h / (power_w / 1000.0) * 1000.0  # g/kWh
        efficiency = 3600.0 / (ge * 42.7)
        # Measured Deutz peak ~0.329; normalise the shape.
        return max(0.25, efficiency / 0.329)

    def efficiency(self, rpm: float, power_w: float) -> float:
        load_pct = min(105.0, max(0.0, abs(power_w) / self.rated_power_w * 100.0))
        n_grid = (750.0, 1100.0, 1500.0, 1800.0, 2150.0, 2500.0)
        if rpm <= n_grid[0]:
            e_r = self._relative_efficiency(n_grid[0], load_pct)
        elif rpm >= n_grid[-1]:
            e_r = self._relative_efficiency(n_grid[-1], load_pct)
        else:
            r1 = next(i for i, value in enumerate(n_grid) if value >= rpm)
            r0 = r1 - 1
            f = (rpm - n_grid[r0]) / (n_grid[r1] - n_grid[r0])
            e0 = self._relative_efficiency(n_grid[r0], load_pct)
            e1 = self._relative_efficiency(n_grid[r1], load_pct)
            e_r = e0 + f * (e1 - e0)
        return max(0.10, min(self.peak_eff, self.peak_eff * e_r))

class RealisticMotorMap(EfficiencyMap):
    """Electric machine efficiency peaked inside its actual operating band."""

    def __init__(self, peak: float = 0.96, width: float = 1800.0,
                 center_rpm: float = 2400.0,
                 preferred_power_w: float = 45000.0,
                 power_width_w: float = 50000.0):
        super().__init__(peak, width, center_rpm, preferred_power_w, power_width_w)

    def efficiency(self, rpm: float, power_w: float) -> float:
        power_factor = exp(-((abs(power_w) - self.preferred_power_w) /
                             self.power_width_w) ** 2)
        return max(0.70, min(self.peak, self.peak * (0.75 + 0.25 * power_factor)))

class OSECVTModel:
    def __init__(self, params: PowertrainParameters | None = None,
                 engine_map: EfficiencyMap | None = None,
                 motor_map: EfficiencyMap | None = None):
        self.p = params or PowertrainParameters()
        self.engine_map = engine_map or EfficiencyMap(0.43, 450.0, 1500.0)
        self.motor_map = motor_map or EfficiencyMap(0.95, 1800.0, 2400.0)

    def demand(self, speed_mps: float, draft_n: float, grade: float, rolling_n: float = 2500.0) -> float:
        return max(0.0, (draft_n + rolling_n + self.p.vehicle_mass_kg * 9.81 * grade) * speed_mps / self.p.mechanical_efficiency)

    def constraint_report(self, demand_w: float, engine_power_w: float,
                          speed_mps: float, regen_power_w: float = 0.0,
                          external_battery_bus_w: float = 0.0) -> dict[str, float]:
        """Check simplified planetary, MG1/MG2 and power limits explicitly."""
        p = self.p
        engine = max(0.0, min(p.engine_rated_w, engine_power_w))
        motor = demand_w - engine
        combined_mg2_power = motor - max(0.0, regen_power_w)
        motor_eff = self.motor_map.efficiency(2400.0, motor)
        split_battery_bus_w = (motor / max(motor_eff, 1e-9)
                               if motor >= 0.0 else motor * motor_eff)
        combined_battery_bus_w = split_battery_bus_w + external_battery_bus_w
        wheel_rpm = max(0.0, speed_mps) / (2.0 * 3.141592653589793 * p.wheel_radius_m) * 60.0
        mg1_rpm = abs((1.0 + p.planetary_ratio) * p.engine_speed_rpm - p.planetary_ratio * wheel_rpm)
        mg2_rpm = abs(wheel_rpm * p.motor_speed_ratio)
        mg1_power = 0.10 * abs(engine) + 0.20 * abs(motor)
        mg2_power = abs(combined_mg2_power)
        return {
            "motor_power_violation_w": max(0.0, mg2_power - p.motor_peak_w),
            "battery_power_violation_w": max(0.0, abs(combined_battery_bus_w) - p.battery_power_limit_w),
            "mg1_power_violation_w": max(0.0, mg1_power - p.mg1_power_limit_w),
            "mg1_speed_violation_rpm": max(0.0, mg1_rpm - p.mg1_speed_limit_rpm),
            "mg2_speed_violation_rpm": max(0.0, mg2_rpm - p.mg2_speed_limit_rpm),
        }

    def planetary_split(self, demand_w: float, engine_power_w: float) -> tuple[float, float]:
        engine = max(0.0, min(self.p.engine_rated_w, engine_power_w))
        motor = demand_w - engine
        return engine, motor

    def step(self, state: DrivelineState, demand_w: float, engine_power_w: float,
             accessory_power_w: float = 0.0, engine_on: bool | None = None,
             engine_started: bool = False, start_fuel_g: float = 0.0,
             external_battery_bus_w: float = 0.0) -> DrivelineState:
        p = self.p
        total_demand = demand_w + max(0.0, accessory_power_w)
        on = (engine_power_w > 1000.0) if engine_on is None else bool(engine_on)
        engine, motor = self.planetary_split(total_demand, engine_power_w if on else 0.0)
        motor_eff = self.motor_map.efficiency(2400.0, motor)
        battery_power = (motor / max(motor_eff, 1e-9)
                         if motor >= 0 else motor * motor_eff)
        battery_power += external_battery_bus_w
        battery_power = max(-p.battery_power_limit_w, min(p.battery_power_limit_w, battery_power))
        open_circuit_v = 570.0 + 80.0 * state.soc
        current = battery_power / max(open_circuit_v, 1.0)
        dsoc = -battery_power * p.dt_s / (p.battery_capacity_wh * 3600.0)
        # Nonzero idle/accessory fuel is included whenever the engine is on.
        idle_power = 12000.0 if engine > 1000.0 else 0.0
        fuel = (engine + idle_power) * p.dt_s / max(self.engine_map.efficiency(1500.0, engine) * 42.7e6, 1e-9) * 1000.0 if on else 0.0
        return DrivelineState(max(p.soc_min, min(p.soc_max, state.soc + dsoc)), state.speed_mps, engine,
                              state.fuel_g + fuel + (start_fuel_g if engine_started else 0.0), current,
                              on, state.engine_starts + (1 if engine_started else 0))

    def equivalent_fuel_l(self, state: DrivelineState) -> float:
        return state.fuel_g / 832.0
