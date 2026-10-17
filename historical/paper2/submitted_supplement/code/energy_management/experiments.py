"""Unified energy-management benchmark protocol with DP and MPC baselines."""
from __future__ import annotations
from dataclasses import dataclass, field
from dataclasses import replace
from time import perf_counter
from config.parameters import PowertrainParameters
from common.profiles import (terrain_profile, high_variability_profile,
                              agri_workcycle_profile, low_load_agri_workcycle_profile,
                              stochastic_agri_workcycle_profile,
                              regenerative_agri_workcycle_profile)
from common.profiles import regenerative_low_load_agri_workcycle_profile
from common.profiles import smoothed_regenerative_low_load_agri_workcycle_profile
from os_ecvt_model import (OSECVTModel, DrivelineState, RealisticDieselMap,
                           RealisticMotorMap, EfficiencyMap, LiteratureBSFCMap)
from load_terrain_predictor import ProbabilisticPredictor
from dp_mpc_ecms import (OOLController, PowerFollowingController, ECMSController,
                         DeterministicMPCController, ScenarioMPCController,
                         RecursiveFeasibleScenarioMPCController,
                         DynamicProgrammingReference, RealisticOOLController,
                         SegmentReference, EngineStartStopSupervisor, EnergyCommand,
                         MapAwareECMSController)


# Solving a segment reference is deterministic for a fixed virtual plant and
# nominal cycle.  Retaining it within a batch prevents a common prior from
# being needlessly recomputed once per random seed; it never stores an actual
# stochastic trajectory.
_NOMINAL_STOCHASTIC_REFERENCE_CACHE: dict[tuple[object, ...], tuple[list[float], list[float]]] = {}
_WORKCYCLE_SEGMENT_BOUNDARIES_S = (0.0, 25.0, 30.0, 115.0, 120.0,
                                  235.0, 240.0, 265.0, 270.0)
_SMOOTH_REGEN_SEGMENT_BOUNDARIES_S = (0.0, 65.0, 70.0, 185.0, 190.0,
                                      235.0, 240.0, 295.0, 300.0)

@dataclass(frozen=True)
class ExperimentConfig:
    duration_s: float = 600.0
    initial_soc: float = 0.55
    terminal_soc_tolerance: float = 0.01
    mpc_horizon: int = 8
    scenario_count: int = 5
    profile_name: str = "standard"
    # Realistic BSFC-style engine island + motor map peaked inside the
    # operating band. Off by default so the original flat-map benchmark stays
    # reproducible; retained for explicit map-sensitivity diagnostics.
    realistic_maps: bool = False
    engine_map: EfficiencyMap | None = field(default=None, repr=False)
    motor_map: EfficiencyMap | None = field(default=None, repr=False)
    # Fair dual-baseline protocol: every controller serves the same
    # accessory load (added to the demand seen by the controller).  When
    # False the original protocol is kept, where only ``realistic_ool``
    # carries the accessory in the plant model.
    accessory_for_all_w: float = 0.0
    # Weight of the DP SOC-reference tracking term in the MPC objective.
    # Values are sensitivity settings, not a certified fuel-saving target.
    mpc_terminal_weight: float = 10000.0
    # An offline SOC reference is only admissible when its plant model also
    # represents all energy flows in the evaluated profile.  The regenerative
    # sensitivity protocols disable it because their explicit wheel-side
    # recovery injection is not part of the compact DP reference solver.
    use_offline_soc_reference: bool = True
    # Optional conservative terminal-SOC target for online MPC.  The
    # reported validity criterion always remains relative to ``initial_soc``;
    # this reserve is a charge-sustaining feasibility margin, not a way to
    # relax terminal-SOC accounting.
    online_terminal_soc_reserve: float = 0.0
    # Shared gain for the causal terminal-energy governor. Values above one
    # bring recovery forward when output-ramp limits make last-sample SOC
    # recovery physically unavailable.
    terminal_soc_correction_gain: float = 1.0
    # Scale of stochastic soil/grade disturbances (only used by the
    # ``stochastic_agri_workcycle`` profile).
    stochastic_disturbance_scale: float = 1.0
    # Retain a legacy step-disturbance audit only when explicitly requested.
    # The default evolves the same random-walk targets continuously within
    # each 10 s block, consistent with the imposed actuator slew limits.
    stochastic_smooth_disturbances: bool = True
    # Optional ablation switch: solve the offline segment reference even for
    # stochastic profiles. Disabled in the original 20-seed batch because it
    # is intentionally an expensive oracle computation.
    stochastic_offline_reference: bool = False
    # Use an SOC reference solved once on the zero-disturbance nominal task
    # sequence. Unlike ``stochastic_offline_reference``, this prior is shared
    # by every seed and does not reveal a realized soil/grade disturbance.
    stochastic_nominal_reference: bool = False
    # For stochastic work cycles, give online MPC a shared zero-disturbance
    # task-phase preview, adjusted only by the current measured demand.  This
    # replaces the former direct look-ahead into the evaluated seed's future
    # demand samples.
    stochastic_nominal_phase_preview: bool = False
    # Persistence weight for the measured disturbance residual added to a
    # shared nominal phase preview.  This is a forecast parameter, bounded
    # in the predictor, and never accesses an evaluated future sample.
    stochastic_phase_residual_gain: float = 1.0
    seed: int = 2026
    # Common engineering engine ramp limit.  ``None`` retains the legacy
    # parameter below so old experiment manifests remain reproducible.
    engine_ramp_limit_w_per_s: float | None = None
    # Legacy name retained for scripts created before the constraint was
    # correctly shared by the realistic baseline and both MPC controllers.
    realistic_ool_ramp_limit_w: float = 40000.0
    realistic_ool_minimum_engine_w: float = 60000.0
    engine_low_load_efficiency: float = 0.22
    battery_capacity_wh: float | None = None
    battery_power_limit_w: float | None = None
    motor_peak_w: float | None = None
    engine_rated_w: float | None = None
    regenerative_braking: bool = False
    regen_power_limit_w: float = 45000.0
    engine_start_stop: bool = False
    engine_stop_threshold_w: float = 25000.0
    engine_restart_threshold_w: float = 45000.0
    engine_minimum_on_s: float = 5.0
    engine_minimum_off_s: float = 5.0
    engine_start_fuel_g: float = 1.5
    # Explicit offline known-task schedule used only to cross-check the
    # dynamic-feasibility diagnostic against the shared plant constraints.
    # It is never an online-MPC candidate or a cross-cycle claim.
    phase_schedule_targets_w: tuple[float, ...] | None = None
    # Fixed public-task-phase power policy for the stochastic agricultural
    # cycle.  It may use the planned phase and present SOC only; its targets
    # must be selected on development seeds before any holdout evaluation.
    phase_policy_targets_w: tuple[float, ...] | None = None
    # Optional causal interpolation between the frozen phase target (zero)
    # and the current measured demand (one).  It never reads a future sample.
    phase_policy_tracking_gain: float = 0.0
    # Optional per-public-phase version of the causal tracking gain.  This
    # permits a pre-frozen policy to respond differently during idle,
    # transport, draft, and their known task transitions, while retaining the
    # same information set as ``phase_policy_tracking_gain``.  When absent,
    # the scalar gain above is used for every phase.
    phase_policy_tracking_gains: tuple[float, ...] | None = None
    # Optional SOC references keyed to the same public task phases.  They
    # shape a causal charge buffer but do not replace the terminal-SOC
    # closure, which remains relative to ``initial_soc``.  References must be
    # chosen on development seeds before held-out evaluation.
    phase_policy_soc_targets: tuple[float, ...] | None = None
    # First-order time constant used to turn the present SOC/reference error
    # into an engine-power correction.  It is bounded later by the same
    # electrical and applied-ramp envelopes as every other online command.
    phase_policy_soc_tracking_time_s: float = 60.0
    # Fixed equivalent battery-energy multiplier for the causal map-aware
    # ECMS ablation. It is a tuneable policy parameter, not a future preview.
    adaptive_ecms_equivalence_factor: float = 3.0


def main_protocol_config() -> ExperimentConfig:
    """Historical assumed-island map sensitivity configuration.

    Earlier nominal 20% values from this configuration predated common
    applied-output ramp, stable-power, and combined battery-bus checks. It
    remains available for controlled remediation tests, not as a manuscript
    main result or an engineering-performance claim.
    """
    return ExperimentConfig(
        profile_name="smoothed_regenerative_low_load_agri_workcycle",
        engine_map=RealisticDieselMap(low_load_efficiency=0.08, power_width_w=90000.0),
        motor_map=RealisticMotorMap(),
        accessory_for_all_w=18000.0,
        mpc_terminal_weight=2000000.0,
        use_offline_soc_reference=False,
        regenerative_braking=True,
        regen_power_limit_w=45000.0,
        engine_rated_w=260000.0,
        battery_capacity_wh=200e3,
        battery_power_limit_w=150000.0,
        motor_peak_w=150000.0,
    )


def literature_reference_config() -> ExperimentConfig:
    """Historical literature-shaped map sensitivity configuration.

    It uses the Devyanin et al. (2023) Deutz BF 6M 2012 C consumption shape,
    rescaled to a nominal modern 300 kW platform. Earlier nominal values from
    this configuration are superseded pending strict applied-output and
    combined-bus revalidation.
    """
    return ExperimentConfig(
        profile_name="smoothed_regenerative_low_load_agri_workcycle",
        engine_map=LiteratureBSFCMap(),
        motor_map=RealisticMotorMap(),
        accessory_for_all_w=18000.0,
        mpc_terminal_weight=2000000.0,
        use_offline_soc_reference=False,
        regenerative_braking=True,
        regen_power_limit_w=45000.0,
        engine_rated_w=300000.0,
        battery_capacity_wh=200e3,
        battery_power_limit_w=150000.0,
        motor_peak_w=150000.0,
    )


def run_definition(controller_name: str, config: ExperimentConfig = ExperimentConfig()) -> dict[str, object]:
    """Define one benchmark; this function is intentionally not called at import time."""
    if config.profile_name == "high_variability":
        profile = high_variability_profile(config.duration_s)
    elif config.profile_name == "agri_workcycle":
        profile = agri_workcycle_profile(config.duration_s)
    elif config.profile_name == "low_load_agri_workcycle":
        profile = low_load_agri_workcycle_profile(config.duration_s)
    elif config.profile_name == "stochastic_agri_workcycle":
        profile = stochastic_agri_workcycle_profile(
            config.duration_s, seed=config.seed,
            disturbance_scale=config.stochastic_disturbance_scale,
            smooth_disturbances=config.stochastic_smooth_disturbances)
    elif config.profile_name == "regenerative_agri_workcycle":
        profile = regenerative_agri_workcycle_profile(config.duration_s)
    elif config.profile_name == "regenerative_low_load_agri_workcycle":
        profile = regenerative_low_load_agri_workcycle_profile(config.duration_s)
    elif config.profile_name == "smoothed_regenerative_low_load_agri_workcycle":
        profile = smoothed_regenerative_low_load_agri_workcycle_profile(config.duration_s)
    else:
        profile = terrain_profile(config.duration_s)
    engine_map = config.engine_map
    motor_map = config.motor_map
    if config.realistic_maps:
        engine_map = RealisticDieselMap(low_load_efficiency=config.engine_low_load_efficiency,
                                        power_width_w=90000.0)
        motor_map = RealisticMotorMap()
    params = PowertrainParameters()
    overrides = {}
    if config.battery_capacity_wh is not None:
        overrides["battery_capacity_wh"] = config.battery_capacity_wh
    if config.battery_power_limit_w is not None:
        overrides["battery_power_limit_w"] = config.battery_power_limit_w
    if config.motor_peak_w is not None:
        overrides["motor_peak_w"] = config.motor_peak_w
    if config.engine_rated_w is not None:
        overrides["engine_rated_w"] = config.engine_rated_w
    if overrides:
        params = replace(params, **overrides)
    model = OSECVTModel(params, engine_map=engine_map, motor_map=motor_map)
    shared_ramp_limit_w_per_s = (
        config.engine_ramp_limit_w_per_s
        if config.engine_ramp_limit_w_per_s is not None
        else config.realistic_ool_ramp_limit_w
    )
    if shared_ramp_limit_w_per_s <= 0.0:
        raise ValueError("engine ramp limit must be positive")

    def largest_motor_power(sign: float) -> float:
        lower, upper = 0.0, model.p.motor_peak_w
        for _ in range(32):
            middle = (lower + upper) / 2.0
            efficiency = model.motor_map.efficiency(2400.0, sign * middle)
            bus_w = (sign * middle / max(efficiency, 1e-9)
                     if sign > 0.0 else sign * middle * efficiency)
            if abs(bus_w) <= model.p.battery_power_limit_w:
                lower = middle
            else:
                upper = middle
        return lower

    max_assist_w = largest_motor_power(1.0)
    max_charge_w = largest_motor_power(-1.0)

    def battery_aware_engine_bounds(demand_w: float) -> tuple[float, float]:
        """Translate battery-bus and motor limits into an engine interval."""
        return (max(0.0, demand_w - max_assist_w),
                min(model.p.engine_rated_w, demand_w + max_charge_w))
    state = DrivelineState(soc=config.initial_soc)
    predictor = ProbabilisticPredictor()
    controller_map = {"ool": OOLController(), "realistic_ool": RealisticOOLController(
                          ramp_limit_w=shared_ramp_limit_w_per_s,
                          minimum_engine_w=config.realistic_ool_minimum_engine_w,
                          engine_rated_w=params.engine_rated_w,
                          dt_s=model.p.dt_s),
                      "power_following": PowerFollowingController(), "ecms": ECMSController()}
    adaptive_ecms = MapAwareECMSController(
        equivalence_factor=config.adaptive_ecms_equivalence_factor,
        engine_efficiency=(engine_map.efficiency if engine_map else None),
        motor_efficiency=(motor_map.efficiency if motor_map else None))
    deterministic = DeterministicMPCController(horizon=config.mpc_horizon,
                                               ramp_limit_w=shared_ramp_limit_w_per_s * model.p.dt_s,
                                               terminal_weight=config.mpc_terminal_weight,
                                               battery_capacity_wh=params.battery_capacity_wh,
                                               battery_power_limit_w=params.battery_power_limit_w,
                                               motor_peak_w=params.motor_peak_w,
                                               engine_rated_w=params.engine_rated_w)
    robust = ScenarioMPCController(horizon=config.mpc_horizon, scenario_count=config.scenario_count,
                                   ramp_limit_w=shared_ramp_limit_w_per_s * model.p.dt_s,
                                   predictor=predictor, terminal_weight=config.mpc_terminal_weight,
                                   battery_capacity_wh=params.battery_capacity_wh,
                                   battery_power_limit_w=params.battery_power_limit_w,
                                   motor_peak_w=params.motor_peak_w,
                                   engine_rated_w=params.engine_rated_w)
    recursive_feasible = RecursiveFeasibleScenarioMPCController(
        horizon=config.mpc_horizon, scenario_count=config.scenario_count,
        ramp_limit_w=shared_ramp_limit_w_per_s * model.p.dt_s,
        predictor=predictor, terminal_weight=config.mpc_terminal_weight,
        battery_capacity_wh=params.battery_capacity_wh,
        battery_power_limit_w=params.battery_power_limit_w,
        motor_peak_w=params.motor_peak_w,
        engine_rated_w=params.engine_rated_w,
        terminal_soc_tolerance=config.terminal_soc_tolerance)
    supervisors = {name: EngineStartStopSupervisor(
        enabled=config.engine_start_stop,
        stop_threshold_w=config.engine_stop_threshold_w,
        restart_threshold_w=config.engine_restart_threshold_w,
        minimum_on_s=config.engine_minimum_on_s,
        minimum_off_s=config.engine_minimum_off_s,
        start_fuel_g=config.engine_start_fuel_g,
        dt_s=model.p.dt_s,
        motor_peak_w=model.p.motor_peak_w,
        # The instantaneous OOL is intentionally a theoretical reference;
        # all engineering controllers use the same stable-power floor.
        minimum_engine_w=(0.0 if name == "ool" else config.realistic_ool_minimum_engine_w),
    ) for name in ("ool", "realistic_ool", "power_following", "ecms",
                   "dp", "deterministic_mpc", "robust_mpc", "phase_schedule",
                   "recursive_feasible_mpc", "phase_policy", "adaptive_ecms")}
    if engine_map is not None:
        deterministic.engine_efficiency = engine_map.efficiency
        robust.engine_efficiency = engine_map.efficiency
        recursive_feasible.engine_efficiency = engine_map.efficiency
    if motor_map is not None:
        deterministic.motor_efficiency = motor_map.efficiency
        robust.motor_efficiency = motor_map.efficiency
        recursive_feasible.motor_efficiency = motor_map.efficiency
    raw_demands = [model.demand(point.speed_mps, point.draft_n * point.soil_factor, point.grade)
                   for point in profile]
    regen_powers = [
        min(config.regen_power_limit_w,
            max(0.0, float(getattr(point, "regen_power_w", 0.0))))
        if config.regenerative_braking else 0.0
        for point in profile
    ]
    # The controller's nominal forecast must use the same net wheel demand
    # as the plant.  In particular, scheduled regenerative braking is known
    # task information, not an unmodelled future disturbance.
    net_traction_demands = [max(0.0, raw - regen)
                            for raw, regen in zip(raw_demands, regen_powers)]
    # Offline reference: DP for the standard/high-variability profiles; the
    # plant-consistent segment optimum for the agri work-cycle profile
    # (discrete DP suffers grid-quantization drift over the long horizon).
    # The reference is solved on the same total demand (traction +
    # accessory) that every controller serves, so its SOC trajectory is
    # consistent with the closed-loop MPC.
    reference_demands = [d + config.accessory_for_all_w for d in net_traction_demands]
    nominal_reference_demands: list[float] = []
    nominal_profile = []
    if config.profile_name == "stochastic_agri_workcycle" and (
            config.stochastic_nominal_reference or config.stochastic_nominal_phase_preview):
        nominal_profile = stochastic_agri_workcycle_profile(
            config.duration_s, seed=0, disturbance_scale=0.0,
            smooth_disturbances=config.stochastic_smooth_disturbances)
        nominal_reference_demands = []
        for point in nominal_profile:
            raw_nominal = model.demand(point.speed_mps,
                                       point.draft_n * point.soil_factor,
                                       point.grade)
            regen_nominal = (min(config.regen_power_limit_w,
                                 max(0.0, float(getattr(point, "regen_power_w", 0.0))))
                             if config.regenerative_braking else 0.0)
            nominal_reference_demands.append(
                max(0.0, raw_nominal - regen_nominal) + config.accessory_for_all_w)
    dp_reference, dp_soc_reference = [], []
    needs_offline_reference = (controller_name == "dp" or (
        config.use_offline_soc_reference and
        controller_name in ("deterministic_mpc", "robust_mpc", "recursive_feasible_mpc")))
    if config.profile_name == "agri_workcycle" and needs_offline_reference:
        # idle(25s) trans(5s) transport(85s) trans(5s) plough(115s) trans(5s)
        # turn(25s) trans(5s) -> 8 segments per 270 s cycle; transitions are
        # separate segments so the reference can ramp without shortages.
        seg_ref = SegmentReference(segment_boundaries_s=_WORKCYCLE_SEGMENT_BOUNDARIES_S)
        dp_reference, dp_soc_reference = seg_ref.solve(model, reference_demands, profile,
                                                       config.initial_soc,
                                                       config.terminal_soc_tolerance,
                                                       model.p.dt_s,
                                                       engine_ramp_limit_w_per_s=shared_ramp_limit_w_per_s,
                                                       minimum_engine_w=config.realistic_ool_minimum_engine_w)
    elif config.profile_name == "stochastic_agri_workcycle" and needs_offline_reference:
        if config.stochastic_offline_reference:
            seg_ref = SegmentReference(segment_boundaries_s=_WORKCYCLE_SEGMENT_BOUNDARIES_S)
            dp_reference, dp_soc_reference = seg_ref.solve(
                model, reference_demands, profile, config.initial_soc,
                config.terminal_soc_tolerance, model.p.dt_s,
                engine_ramp_limit_w_per_s=shared_ramp_limit_w_per_s,
                minimum_engine_w=config.realistic_ool_minimum_engine_w)
        elif config.stochastic_nominal_reference:
            # A planned task sequence is a legitimate common prior, whereas
            # solving on ``profile`` would expose the evaluated trajectory's
            # future disturbances.  Generate this reference from the
            # disturbance-free cycle and share it unchanged across seeds.
            map_signature = lambda efficiency_map: (
                type(efficiency_map).__name__,
                tuple(sorted(vars(efficiency_map).items())))
            cache_key = (
                config.duration_s, config.initial_soc,
                config.terminal_soc_tolerance, config.accessory_for_all_w,
                tuple(sorted(vars(model.p).items())), map_signature(model.engine_map),
                map_signature(model.motor_map), _WORKCYCLE_SEGMENT_BOUNDARIES_S,
                shared_ramp_limit_w_per_s, config.realistic_ool_minimum_engine_w)
            cached_reference = _NOMINAL_STOCHASTIC_REFERENCE_CACHE.get(cache_key)
            if cached_reference is None:
                seg_ref = SegmentReference(segment_boundaries_s=_WORKCYCLE_SEGMENT_BOUNDARIES_S)
                cached_reference = seg_ref.solve(
                    model, nominal_reference_demands, nominal_profile, config.initial_soc,
                    config.terminal_soc_tolerance, model.p.dt_s,
                    engine_ramp_limit_w_per_s=shared_ramp_limit_w_per_s,
                    minimum_engine_w=config.realistic_ool_minimum_engine_w)
                _NOMINAL_STOCHASTIC_REFERENCE_CACHE[cache_key] = cached_reference
            dp_reference, dp_soc_reference = cached_reference
        else:
            # Robustness batch uses online prediction without re-solving the
            # expensive offline reference for every seed.
            dp_reference, dp_soc_reference = [], []
    elif config.regenerative_braking and needs_offline_reference:
        # The SOC prior is solved on the same net traction demand and explicit
        # wheel-side recovery update as the evaluated plant.  It is a common
        # task-sequence prior, not a controller-specific energy credit.
        seg_ref = SegmentReference(segment_boundaries_s=(0.0, 65.0, 70.0,
                                                         185.0, 190.0,
                                                         235.0, 240.0,
                                                         295.0, 300.0))
        dp_reference, dp_soc_reference = seg_ref.solve(
            model, reference_demands, profile, config.initial_soc,
            config.terminal_soc_tolerance, model.p.dt_s,
            regen_powers=regen_powers,
            engine_ramp_limit_w_per_s=shared_ramp_limit_w_per_s,
            minimum_engine_w=config.realistic_ool_minimum_engine_w)
    elif needs_offline_reference:
        dp_solver = DynamicProgrammingReference(
            engine_efficiency=(engine_map.efficiency if engine_map else None),
            motor_efficiency=(motor_map.efficiency if motor_map else None),
            battery_capacity_wh=model.p.battery_capacity_wh,
            battery_power_limit_w=model.p.battery_power_limit_w,
            motor_peak_w=model.p.motor_peak_w)
        dp_reference, dp_soc_reference = dp_solver.solve_with_soc(reference_demands, config.initial_soc, model.p.dt_s)
    demands, commands, shortages, currents = [], [], [], []
    decision_elapsed_s: list[float] = []
    fallback_count = 0
    ramp_envelope_infeasibility_count = 0
    safety_filter_activation_count = 0
    terminal_set_violation_count = 0
    constraint_violations = []
    regen_curtailments_w = []
    # A terminal-SOC correction occurs after the MPC candidate search.  Keep
    # it from bypassing the same engine-ramp limit applied inside each MPC.
    prior_actual_engine_w: dict[str, float | None] = {
        name: None for name in supervisors
    }
    prior_engine_on = {name: False for name in supervisors}
    engine_ramp_violations: list[float] = []
    start_stop_transitions = 0
    for index, point in enumerate(profile):
        regen_power = regen_powers[index]
        # Regeneration is a wheel-side braking input. It reduces net traction
        # demand, but the plant receives the corresponding charging power.
        demand = net_traction_demands[index]
        # Fair protocol: the accessory load is part of the demand seen by
        # every controller; the plant is not given a separate accessory.
        served_demand = demand + config.accessory_for_all_w
        decision_started = perf_counter()
        prediction = predictor.update(point, demand)
        terminal_target_soc = min(model.p.soc_max,
                                  config.initial_soc + config.online_terminal_soc_reserve)
        if controller_name in ("robust_mpc", "recursive_feasible_mpc"):
            phase_scenarios = None
            if config.profile_name == "stochastic_agri_workcycle" and config.stochastic_nominal_phase_preview:
                phase_window = [nominal_reference_demands[min(index + offset,
                                                               len(nominal_reference_demands) - 1)]
                                for offset in range(config.mpc_horizon)]
                phase_scenarios = predictor.phase_scenarios(
                    phase_window, served_demand, prediction, config.scenario_count,
                    residual_gain=config.stochastic_phase_residual_gain)
            controller = (recursive_feasible if controller_name == "recursive_feasible_mpc"
                          else robust)
            command = controller.command(served_demand, state.soc, prediction,
                                         terminal_reference=terminal_target_soc,
                                         remaining_steps=len(profile) - index,
                                         soc_reference=(dp_soc_reference[index] if dp_soc_reference else None),
                                         scenario_trajectories=phase_scenarios)
            if controller_name == "recursive_feasible_mpc":
                safety_filter_activation_count += int(command.safety_filter_active)
        elif controller_name == "deterministic_mpc":
            if config.profile_name == "stochastic_agri_workcycle" and config.stochastic_nominal_phase_preview:
                nominal_window = [nominal_reference_demands[min(index + offset,
                                                                 len(nominal_reference_demands) - 1)]
                                  for offset in range(config.mpc_horizon)]
                future = predictor.nominal_phase_preview(
                    nominal_window, served_demand,
                    residual_gain=config.stochastic_phase_residual_gain)
            elif config.profile_name == "stochastic_agri_workcycle":
                # The random future demand values are unavailable online.
                # Use the current causal predictor rather than the evaluated
                # seed's future samples, which would make this comparison an
                # oracle look-ahead experiment.
                future = [prediction.mean_w + config.accessory_for_all_w
                          for _ in range(config.mpc_horizon)]
            else:
                future = reference_demands[index:index + config.mpc_horizon]
            command = deterministic.command(served_demand, state.soc, future,
                                            terminal_reference=terminal_target_soc,
                                            remaining_steps=len(profile) - index,
                                            soc_reference=(dp_soc_reference[index] if dp_soc_reference else None))
        elif controller_name == "dp":
            if len(dp_reference) != len(raw_demands):
                return {"valid": False, "reason": "DP没有找到满足SOC、电池功率和终端约束的可行轨迹", "fuel_l": None}
            command = type("DPCommand", (), {"engine_power_w": dp_reference[index]})()
        elif controller_name == "phase_schedule":
            if (config.phase_schedule_targets_w is None
                    or config.profile_name != "smoothed_regenerative_low_load_agri_workcycle"
                    or len(config.phase_schedule_targets_w) != len(_SMOOTH_REGEN_SEGMENT_BOUNDARIES_S) - 1):
                return {"valid": False,
                        "reason": "离线任务相位诊断的分段目标与工况不匹配",
                        "fuel_l": None}
            local_s = (index * model.p.dt_s) % _SMOOTH_REGEN_SEGMENT_BOUNDARIES_S[-1]
            segment = next(
                (value for value in range(len(_SMOOTH_REGEN_SEGMENT_BOUNDARIES_S) - 1)
                 if (_SMOOTH_REGEN_SEGMENT_BOUNDARIES_S[value] <= local_s
                     < _SMOOTH_REGEN_SEGMENT_BOUNDARIES_S[value + 1])),
                len(_SMOOTH_REGEN_SEGMENT_BOUNDARIES_S) - 2)
            command = type("PhaseScheduleCommand", (), {
                "engine_power_w": config.phase_schedule_targets_w[segment]})()
        elif controller_name == "phase_policy":
            if (config.phase_policy_targets_w is None
                    or config.profile_name != "stochastic_agri_workcycle"
                    or len(config.phase_policy_targets_w) != len(_WORKCYCLE_SEGMENT_BOUNDARIES_S) - 1):
                return {"valid": False,
                        "reason": "公开作业阶段策略的分段目标与随机工况不匹配",
                        "fuel_l": None}
            local_s = (index * model.p.dt_s) % _WORKCYCLE_SEGMENT_BOUNDARIES_S[-1]
            segment = next(
                (value for value in range(len(_WORKCYCLE_SEGMENT_BOUNDARIES_S) - 1)
                 if (_WORKCYCLE_SEGMENT_BOUNDARIES_S[value] <= local_s
                     < _WORKCYCLE_SEGMENT_BOUNDARIES_S[value + 1])),
                len(_WORKCYCLE_SEGMENT_BOUNDARIES_S) - 2)
            target_w = config.phase_policy_targets_w[segment]
            if config.phase_policy_tracking_gains is not None:
                if len(config.phase_policy_tracking_gains) != len(config.phase_policy_targets_w):
                    return {"valid": False,
                            "reason": "公开作业阶段策略的分段跟随系数与目标数量不匹配",
                            "fuel_l": None}
                tracking_gain = config.phase_policy_tracking_gains[segment]
            else:
                tracking_gain = config.phase_policy_tracking_gain
            tracking_gain = max(0.0, min(1.0, tracking_gain))
            command = EnergyCommand(target_w + tracking_gain * (served_demand - target_w))
            if config.phase_policy_soc_targets is not None:
                if len(config.phase_policy_soc_targets) != len(config.phase_policy_targets_w):
                    return {"valid": False,
                            "reason": "公开作业阶段策略的SOC参考与目标数量不匹配",
                            "fuel_l": None}
                if config.phase_policy_soc_tracking_time_s <= 0.0:
                    return {"valid": False,
                            "reason": "公开作业阶段策略的SOC跟踪时间常数必须为正",
                            "fuel_l": None}
                soc_reference = config.phase_policy_soc_targets[segment]
                if not model.p.soc_min <= soc_reference <= model.p.soc_max:
                    return {"valid": False,
                            "reason": "公开作业阶段策略的SOC参考超出电池边界",
                            "fuel_l": None}
                soc_reference_correction_w = (
                    (soc_reference - state.soc) * model.p.battery_capacity_wh * 3600.0
                    / config.phase_policy_soc_tracking_time_s
                )
                command = EnergyCommand(command.engine_power_w + soc_reference_correction_w,
                                        command.objective, command.feasible)
        elif controller_name == "adaptive_ecms":
            engine_low, engine_high = battery_aware_engine_bounds(served_demand)
            command = adaptive_ecms.command(served_demand, engine_low, engine_high)
        else:
            command = controller_map[controller_name].command(served_demand, state.soc)
        # Charge-sustaining terminal correction shared by online controllers.
        # It is deliberately explicit so that a short-horizon candidate search
        # cannot trade away the terminal SOC constraint for nominal fuel.
        if controller_name in ("deterministic_mpc", "robust_mpc", "recursive_feasible_mpc", "realistic_ool", "phase_policy",
                               "adaptive_ecms"):
            remaining_s = max(model.p.dt_s, (len(profile) - index) * model.p.dt_s)
            # Fuel is compared directly rather than with an arbitrary
            # battery-energy equivalence factor.  Online fuel comparisons
            # therefore steer every controller back to the common initial
            # SOC, which is stricter than the reported validity band and
            # prevents residual electrical energy being mistaken for fuel.
            energy_error_w = ((terminal_target_soc - state.soc)
                              * model.p.battery_capacity_wh * 3600.0 / remaining_s)
            correction = max(-model.p.battery_power_limit_w,
                             min(model.p.battery_power_limit_w,
                                 config.terminal_soc_correction_gain * energy_error_w))
            # Keep the post-MPC terminal correction inside the same
            # bidirectional motor-power envelope used by the candidate search.
            engine_low, engine_high = battery_aware_engine_bounds(served_demand)
            if controller_name == "deterministic_mpc":
                engine_low = max(engine_low, deterministic.ramp_safe_engine_min_w)
                engine_high = min(engine_high, deterministic.ramp_safe_engine_max_w)
            elif controller_name == "robust_mpc":
                engine_low = max(engine_low, robust.ramp_safe_engine_min_w)
                engine_high = min(engine_high, robust.ramp_safe_engine_max_w)
            elif controller_name == "recursive_feasible_mpc":
                engine_low = max(engine_low, recursive_feasible.ramp_safe_engine_min_w)
                engine_high = min(engine_high, recursive_feasible.ramp_safe_engine_max_w)
            if engine_low > engine_high + 1e-9:
                # There is no command that simultaneously satisfies the
                # present electrical envelope and the forecast ramp envelope.
                # Preserve a diagnostic trajectory, but never certify it.
                ramp_envelope_infeasibility_count += 1
                engine_low, engine_high = battery_aware_engine_bounds(served_demand)
            if controller_name in ("deterministic_mpc", "robust_mpc", "recursive_feasible_mpc") and not command.feasible:
                # A finite candidate set can become empty when the predicted
                # terminal constraint and power envelope conflict.  Preserve
                # traction feasibility with an explicit charge-sustaining
                # fallback rather than silently using the first candidate.
                fallback_count += 1
                command = type(command)(max(engine_low, min(engine_high,
                                                           served_demand)),
                                        command.objective, False)
            command = type(command)(max(engine_low, min(engine_high,
                                                         command.engine_power_w + correction)),
                                    command.objective, command.feasible)
            # Power-feasibility guard: the engine must at least cover the
            # demand that the battery peak power cannot supply, so a small
            # mismatch between the MPC internal model and the plant can
            # never turn into a tractive-power shortage.
            if controller_name in ("deterministic_mpc", "robust_mpc", "recursive_feasible_mpc"):
                floor_w, _ = battery_aware_engine_bounds(served_demand)
                command = type(command)(max(engine_low, min(engine_high,
                                                           max(command.engine_power_w, floor_w))),
                                        command.objective, command.feasible)
        decision_elapsed_s.append(perf_counter() - decision_started)
        accessory = 0.0
        # Legacy asymmetric behavior (fair flag off): only ``realistic_ool``
        # carries the accessory inside the plant model.
        if config.accessory_for_all_w == 0.0:
            accessory = 18000.0 if controller_name == "realistic_ool" else 0.0
        # Apply the same optional start/stop supervisor to every controller.
        # This keeps engine-off fuel savings from being a baseline artifact.
        supervisor = supervisors[controller_name]
        actual_engine_w, engine_on, engine_started = supervisor.apply(
            command.engine_power_w, served_demand + accessory)
        if controller_name != "ool":
            prior_w = prior_actual_engine_w[controller_name]
            if prior_w is not None and engine_on and prior_engine_on[controller_name]:
                step_limit_w = shared_ramp_limit_w_per_s * model.p.dt_s
                actual_engine_w = max(prior_w - step_limit_w,
                                      min(prior_w + step_limit_w, actual_engine_w))
                engine_ramp_violations.append(
                    max(0.0, abs(actual_engine_w - prior_w) - step_limit_w))
            elif prior_w is not None and engine_on != prior_engine_on[controller_name]:
                # Start/stop transients are a separate model limitation and
                # are not used for the no-start/stop primary result.
                start_stop_transitions += 1
            prior_actual_engine_w[controller_name] = actual_engine_w
            prior_engine_on[controller_name] = engine_on
            # The stable-power floor and final output ramp limiter are plant
            # constraints.  MPC must use the applied value, rather than its
            # pre-supervisor proposal, as the initial condition next step.
            if controller_name == "deterministic_mpc":
                deterministic.previous_engine_w = actual_engine_w
            elif controller_name == "robust_mpc":
                robust.previous_engine_w = actual_engine_w
            elif controller_name == "recursive_feasible_mpc":
                recursive_feasible.previous_engine_w = actual_engine_w
        regen_bus_w = -regen_power * model.motor_map.efficiency(2400.0, -regen_power)
        # Use one battery bus for engine charging, traction assistance, and
        # wheel-side recovery.  The pre-clipping violation remains in the
        # constraint report; curtailed recovery is separately disclosed.
        split_motor_w = served_demand - actual_engine_w
        split_efficiency = model.motor_map.efficiency(2400.0, split_motor_w)
        split_bus_w = (split_motor_w / max(split_efficiency, 1e-9)
                       if split_motor_w >= 0.0 else split_motor_w * split_efficiency)
        admitted_bus_w = max(-model.p.battery_power_limit_w,
                             min(model.p.battery_power_limit_w,
                                 split_bus_w + regen_bus_w))
        regen_curtailments_w.append(max(0.0, admitted_bus_w - split_bus_w - regen_bus_w))
        state = model.step(state, served_demand, actual_engine_w,
                           accessory_power_w=accessory,
                           engine_on=engine_on,
                           engine_started=engine_started,
                           start_fuel_g=supervisor.start_fuel_g,
                           external_battery_bus_w=regen_bus_w)
        if (controller_name == "recursive_feasible_mpc"
                and not recursive_feasible.terminal_set_contains(
                    state.soc, len(profile) - index - 1, terminal_target_soc,
                    model.p.dt_s)):
            terminal_set_violation_count += 1
        demands.append(served_demand); commands.append(actual_engine_w)
        shortages.append(max(0.0, served_demand - actual_engine_w - model.p.motor_peak_w))
        violations = model.constraint_report(
            served_demand, actual_engine_w, point.speed_mps,
            regen_power_w=regen_power, external_battery_bus_w=regen_bus_w)
        constraint_violations.append(violations)
        currents.append(abs(state.battery_current_a))
    decision_ms = sorted(value * 1000.0 for value in decision_elapsed_s)
    decision_p95_index = min(len(decision_ms) - 1, int(0.95 * len(decision_ms)))
    return {"fuel_l": model.equivalent_fuel_l(state),
            "final_soc": state.soc,
            "soc_error": state.soc - config.initial_soc,
            # Validity includes the simplified OS-ECVT machine constraints.
            # A violation larger than 1 W or 1 rpm invalidates the run; the
            # violation magnitudes remain reported for diagnosis.
            "valid": (abs(state.soc - config.initial_soc) <= config.terminal_soc_tolerance
                      and max(shortages, default=0.0) <= 1.0
                      and max((v["motor_power_violation_w"] for v in constraint_violations), default=0.0) <= 1.0
                      and max((v["battery_power_violation_w"] for v in constraint_violations), default=0.0) <= 1.0
                      and max((v["mg1_power_violation_w"] for v in constraint_violations), default=0.0) <= 1.0
                      and max((v["mg1_speed_violation_rpm"] for v in constraint_violations), default=0.0) <= 1.0
                      and max((v["mg2_speed_violation_rpm"] for v in constraint_violations), default=0.0) <= 1.0
                      and max(engine_ramp_violations, default=0.0) <= 1.0
                      and ramp_envelope_infeasibility_count == 0
                      and (controller_name != "recursive_feasible_mpc"
                           or terminal_set_violation_count == 0)),
            "max_shortage_w": max(shortages, default=0.0),
            "max_mg1_power_violation_w": max((v["mg1_power_violation_w"] for v in constraint_violations), default=0.0),
            "max_motor_power_violation_w": max((v["motor_power_violation_w"] for v in constraint_violations), default=0.0),
            "max_battery_power_violation_w": max((v["battery_power_violation_w"] for v in constraint_violations), default=0.0),
            "max_mg1_speed_violation_rpm": max((v["mg1_speed_violation_rpm"] for v in constraint_violations), default=0.0),
            "max_mg2_speed_violation_rpm": max((v["mg2_speed_violation_rpm"] for v in constraint_violations), default=0.0),
            "mean_battery_current_a": sum(currents) / max(len(currents), 1),
            "fallback_count": fallback_count,
            "ramp_envelope_infeasibility_count": ramp_envelope_infeasibility_count,
            "safety_filter_activation_count": safety_filter_activation_count,
            "terminal_set_violation_count": terminal_set_violation_count,
            "engine_starts": state.engine_starts,
            "engine_ramp_limit_w_per_s": (
                None if controller_name == "ool" else shared_ramp_limit_w_per_s),
            "max_engine_ramp_violation_w": max(engine_ramp_violations, default=0.0),
            "start_stop_transition_count": start_stop_transitions,
            "max_regen_curtailment_w": max(regen_curtailments_w, default=0.0),
            "total_regen_curtailment_wh": sum(regen_curtailments_w) * model.p.dt_s / 3600.0,
            "decision_timing_ms": {
                "sample_count": len(decision_ms),
                "mean": sum(decision_ms) / max(len(decision_ms), 1),
                "p95": decision_ms[decision_p95_index] if decision_ms else 0.0,
                "maximum": max(decision_ms, default=0.0),
            },
            "demands_w": demands, "commands_w": commands, "dp_reference_w": dp_reference,
            "dp_soc_reference": dp_soc_reference,
            "baseline_type": ("theoretical_instantaneous" if controller_name == "ool" else
                               "realistic_dynamic" if controller_name == "realistic_ool" else
                               "offline_task_phase_diagnostic" if controller_name == "phase_schedule" else
                               "online_public_phase_policy" if controller_name == "phase_policy" else
                               "candidate")}
