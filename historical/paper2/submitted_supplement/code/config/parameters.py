"""Centralized parameters for the paper-1 virtual prototype."""
from dataclasses import dataclass

@dataclass(frozen=True)
class LiftParameters:
    dt_s: float = 0.01
    cylinder_area_m2: float = 0.012
    chamber_volume_m3: float = 0.004
    bulk_modulus_pa: float = 1.2e9
    relief_pressure_pa: float = 21e6
    # The pressure state is a reduced-order virtual model. These terms govern
    # its documented command-to-pressure surrogate, not a valve data-sheet.
    valve_pressure_gain_pa: float = 8.0e6
    tracking_pressure_rate_s: float = 18.0
    hold_pressure_rate_s: float = 4.0
    hold_leakage_retention: float = 0.08
    minimum_common_pressure_pa: float = 1.0e6
    temperature_leakage_gain_per_c: float = 0.018
    leakage_m3_s_pa: float = 1.5e-12
    mass_kg: float = 1200.0
    viscous_n_s_m: float = 2200.0
    coulomb_n: float = 850.0
    stiffness_n_m: float = 18000.0
    stroke_m: float = 0.85
    sensor_std_m: float = 0.0015
    # Accumulator-assisted hold (theoretical parameterization): gas precharge
    # pressure, gas volume, discharge-valve flow coefficient and the charge
    # circuit replenishing the stored oil during sustained leakage.  Values
    # are engineering estimates.
    acc_precharge_pa: float = 12.0e6
    acc_volume_m3: float = 0.004
    acc_flow_m3_s_pa: float = 2.0e-12
    acc_charge_m3_s: float = 6.0e-5

@dataclass(frozen=True)
class PowertrainParameters:
    dt_s: float = 0.1
    engine_rated_w: float = 300e3
    motor_peak_w: float = 90e3
    battery_capacity_wh: float = 100e3
    battery_voltage_v: float = 650.0
    battery_resistance_ohm: float = 0.045
    battery_power_limit_w: float = 90000.0
    soc_min: float = 0.20
    soc_max: float = 0.80
    soc_target: float = 0.55
    vehicle_mass_kg: float = 18000.0
    wheel_radius_m: float = 0.94
    mechanical_efficiency: float = 0.88
    engine_bsfc_g_kwh: float = 205.0
    battery_aging_cost: float = 0.015
    # Simplified OS-ECVT planetary/MG limits for theoretical validation.
    planetary_ratio: float = 2.6
    engine_speed_rpm: float = 1500.0
    motor_speed_ratio: float = 1.8
    # Provisional MG1 electrical limit for the abstract split model.  It is
    # intentionally not claimed as a calibrated machine rating; the previous
    # 45 kW bound made the nominal high-efficiency charging schedule
    # infeasible by construction.
    mg1_power_limit_w: float = 90000.0
    mg1_speed_limit_rpm: float = 6000.0
    mg2_speed_limit_rpm: float = 6000.0

# Parameter tags: the numerical values are engineering estimates unless a source is cited.
PARAMETER_SOURCES = {
    "engine_rated_w": "[厂家范围/估计] 300 kW representative of ≥200 hp platform",
    "vehicle_mass_kg": "[同级机型估计] 15–20 t range",
    "wheel_radius_m": "[轮胎规格估计] 710/70R42 effective radius",
    "engine_bsfc_g_kwh": "[工程估计] 190–220 g/kWh",
    "battery_capacity_wh": "[工程估计] 50–150 kWh theoretical study range",
    "hydraulic": "[工程估计] cylinder, leakage and valve parameters require calibration",
}
