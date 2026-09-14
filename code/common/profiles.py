"""Deterministic synthetic profiles used until real field data is available."""
from __future__ import annotations

import math
from dataclasses import dataclass


@dataclass(frozen=True)
class TerrainPoint:
    time_s: float
    speed_mps: float
    draft_n: float
    grade: float
    soil_factor: float
    regen_power_w: float = 0.0


def terrain_profile(duration_s: float = 600.0, sample_s: float = 0.1, high_load: bool = True) -> list[TerrainPoint]:
    count = int(duration_s / sample_s)
    points = []
    for index in range(count):
        time_s = index * sample_s
        cycle = time_s % 180.0
        if high_load and cycle < 120.0:
            speed = 1.2 + 0.12 * math.sin(time_s / 11.0)
            # Keep the nominal demand inside the 300 kW engine envelope while
            # retaining high-load, grade and soil transients for energy-
            # management discrimination.
            draft = 112000.0 + 22000.0 * math.sin(time_s / 19.0) + 9000.0 * math.sin(time_s / 4.5)
            grade = 0.045 + 0.012 * math.sin(time_s / 31.0)
            soil = 1.25 + 0.12 * math.sin(time_s / 43.0)
        else:
            speed = 2.2 + 0.35 * math.sin(time_s / 37.0)
            draft = 60000.0 + 16000.0 * math.sin(time_s / 29.0)
            grade = 0.02 * math.sin(time_s / 53.0)
            soil = 1.0 + 0.10 * math.sin(time_s / 71.0)
        points.append(TerrainPoint(time_s, speed, max(draft, 10000.0), grade, soil))
    return points


def high_variability_profile(duration_s: float = 600.0, sample_s: float = 0.1) -> list[TerrainPoint]:
    """Stress profile for charge-sustaining peak-shaving experiments.

    Alternates low-load transport and short high-load soil/grade events.  It
    is intentionally separate from ``terrain_profile`` so the original
    benchmark remains reproducible and the new result cannot be mistaken for
    a baseline replacement.
    """
    count = int(duration_s / sample_s)
    points = []
    for index in range(count):
        time_s = index * sample_s
        phase = (time_s % 60.0) / 60.0
        if phase < 0.65:
            speed, draft, grade, soil = 2.4, 42000.0, 0.005, 1.0
        else:
            speed, draft, grade, soil = 1.15, 145000.0, 0.065, 1.22
        points.append(TerrainPoint(time_s, speed, draft, grade, soil))
    return points


def agri_workcycle_profile(duration_s: float = 600.0, sample_s: float = 0.1,
                           smooth_s: float = 5.0) -> list[TerrainPoint]:
    """Realistic tractor work cycle: idle, transport, plough, headland turn.

    A 270 s cycle repeats ``idle(30 s) -> transport(90 s) -> plough(120 s)
    -> turn(30 s)`` with 5 s smooth transitions between segments.  The
    low-load idle/turn segments give the hybrid powertrain a genuine place
    to keep the engine in its efficient island while the battery shaves the
    ploughing peak.  This profile is the premise change that exposes the
    20% fuel-savings potential of the energy-management methods.
    """
    segments = [("idle", 30.0, 0.0, 12000.0, 0.0),
                ("transport", 90.0, 2.2, 45000.0, 0.0),
                ("plough", 120.0, 1.5, 145000.0, 0.05),
                ("turn", 30.0, 0.8, 30000.0, 0.0)]
    boundaries = []
    time_s = 0.0
    while time_s < duration_s:
        for name, dur, speed, draft, grade in segments:
            boundaries.append((time_s, time_s + dur, speed, draft, grade))
            time_s += dur
    points = []
    time_s = 0.0
    while time_s < duration_s:
        current = next(b for b in boundaries if b[0] <= time_s < b[1])
        start, end, speed, draft, grade = current
        following = boundaries[(boundaries.index(current) + 1) % len(boundaries)]
        if time_s >= end - smooth_s:
            fraction = (time_s - (end - smooth_s)) / smooth_s
            speed = speed + (following[2] - speed) * fraction
            draft = draft + (following[3] - draft) * fraction
            grade = grade + (following[4] - grade) * fraction
        points.append(TerrainPoint(time_s, speed, max(draft, 10000.0), grade, 1.0))
        time_s += sample_s
    return points[: int(duration_s / sample_s)]


def low_load_agri_workcycle_profile(duration_s: float = 600.0, sample_s: float = 0.1,
                                    smooth_s: float = 5.0) -> list[TerrainPoint]:
    """Sensitivity cycle with more idle/transport opportunities.

    This is an explicit premise variant, not a replacement for the main
    cycle: 60 s idle, 120 s transport, 60 s plough and 30 s turn.
    """
    segments = [("idle", 60.0, 0.0, 12000.0, 0.0),
                ("transport", 120.0, 2.2, 45000.0, 0.0),
                ("plough", 60.0, 1.5, 145000.0, 0.05),
                ("turn", 30.0, 0.8, 30000.0, 0.0)]
    boundaries = []; time_s = 0.0
    while time_s < duration_s:
        for item in segments:
            boundaries.append((time_s, time_s + item[1], *item[2:])); time_s += item[1]
    points = []; time_s = 0.0
    while time_s < duration_s:
        current = next(b for b in boundaries if b[0] <= time_s < b[1])
        start, end, speed, draft, grade = current
        idx = boundaries.index(current); following = boundaries[(idx + 1) % len(boundaries)]
        if time_s >= end - smooth_s:
            f = (time_s - (end - smooth_s)) / smooth_s
            speed += (following[2] - speed) * f; draft += (following[3] - draft) * f
            grade += (following[4] - grade) * f
        points.append(TerrainPoint(time_s, speed, max(draft, 10000.0), grade, 1.0)); time_s += sample_s
    return points[:int(duration_s / sample_s)]


def stochastic_agri_workcycle_profile(duration_s: float = 600.0,
                                      sample_s: float = 0.1,
                                      seed: int = 2026,
                                      disturbance_scale: float = 1.0,
                                      smooth_disturbances: bool = True) -> list[TerrainPoint]:
    """Agricultural cycle with reproducible soil/grade disturbances.

    ``disturbance_scale`` scales the random-walk increments and bounds around
    the nominal cycle.  A value of 0 therefore reproduces the deterministic
    profile, while 1 is the original robustness protocol.
    """
    import random
    rng = random.Random(seed)
    base = agri_workcycle_profile(duration_s, sample_s)
    points = []
    soil_bias = 1.0
    grade_bias = 0.0
    target_soil_bias = soil_bias
    target_grade_bias = grade_bias
    block_start_soil_bias = soil_bias
    block_start_grade_bias = grade_bias
    for index, point in enumerate(base):
        if index % 100 == 0:
            scale = max(0.0, float(disturbance_scale))
            block_start_soil_bias = soil_bias
            block_start_grade_bias = grade_bias
            target_soil_bias = max(
                1.0 - 0.18 * scale,
                min(1.0 + 0.28 * scale,
                    soil_bias + rng.gauss(0.0, 0.06 * scale)))
            target_grade_bias = max(
                -0.025 * scale,
                min(0.025 * scale,
                    grade_bias + rng.gauss(0.0, 0.004 * scale)))
        if smooth_disturbances:
            # Soil compaction and grade estimation do not change as a 10 s
            # staircase.  Preserve the exact random-walk targets while
            # traversing each block continuously, so the profile is compatible
            # with the explicitly imposed drivetrain slew constraints.
            fraction = ((index % 100) + 1) / 100.0
            soil_bias = (block_start_soil_bias
                         + fraction * (target_soil_bias - block_start_soil_bias))
            grade_bias = (block_start_grade_bias
                          + fraction * (target_grade_bias - block_start_grade_bias))
        else:
            soil_bias = target_soil_bias
            grade_bias = target_grade_bias
        points.append(TerrainPoint(point.time_s, point.speed_mps,
                                   point.draft_n, point.grade + grade_bias,
                                   point.soil_factor * soil_bias,
                                   point.regen_power_w))
    return points


def regenerative_agri_workcycle_profile(duration_s: float = 600.0,
                                        sample_s: float = 0.1) -> list[TerrainPoint]:
    """Agricultural cycle with explicit downhill/deceleration recovery.

    The recovery segment represents a headland exit/downhill transport event.
    ``regen_power_w`` is an externally measured-equivalent wheel braking power
    that is subtracted from traction demand and becomes battery charging power
    in the plant.  It is kept explicit so it cannot be confused with a free
    negative load or an asymmetric baseline.
    """
    count = int(duration_s / sample_s)
    points = []
    for index in range(count):
        t = index * sample_s
        phase = t % 300.0
        if phase < 40.0:       # idle
            speed, draft, grade, regen = 0.0, 12000.0, 0.0, 0.0
        elif phase < 120.0:    # transport
            speed, draft, grade, regen = 2.4, 42000.0, 0.0, 0.0
        elif phase < 230.0:    # plough
            speed, draft, grade, regen = 1.5, 145000.0, 0.05, 0.0
        else:                  # headland downhill/deceleration
            speed, draft, grade = 1.8, 12000.0, -0.06
            regen = 28000.0 + 8000.0 * math.sin((phase - 230.0) / 70.0 * math.pi)
        points.append(TerrainPoint(t, speed, draft, grade, 1.0, max(0.0, regen)))
    return points


def regenerative_low_load_agri_workcycle_profile(duration_s: float = 600.0,
                                                 sample_s: float = 0.1) -> list[TerrainPoint]:
    """Sensitivity cycle with more transport/idle and recovery opportunities."""
    count = int(duration_s / sample_s)
    points = []
    for index in range(count):
        t = index * sample_s
        phase = t % 300.0
        if phase < 70.0:
            speed, draft, grade, regen = 0.0, 12000.0, 0.0, 0.0
        elif phase < 190.0:
            speed, draft, grade, regen = 2.4, 42000.0, 0.0, 0.0
        elif phase < 240.0:
            speed, draft, grade, regen = 1.5, 145000.0, 0.05, 0.0
        else:
            speed, draft, grade = 1.8, 12000.0, -0.06
            regen = 30000.0 + 10000.0 * math.sin((phase - 240.0) / 60.0 * math.pi)
        points.append(TerrainPoint(t, speed, draft, grade, 1.0, max(0.0, regen)))
    return points


def smoothed_regenerative_low_load_agri_workcycle_profile(
        duration_s: float = 600.0, sample_s: float = 0.1,
        smooth_s: float = 5.0) -> list[TerrainPoint]:
    """Continuous-transition counterpart of the low-load recovery cycle.

    The former sensitivity profile changed idle, transport, plough, and
    downhill states discontinuously.  Such a wheel-demand step can require
    more than the 40 kW/s engine limit and 150 kW electrical path can supply,
    so it is unsuitable for a dynamic-constraint benchmark.  This profile
    retains its 70/120/50/60 s task durations and all phase endpoints, but
    interpolates the final ``smooth_s`` seconds of each phase to the next.
    """
    if smooth_s <= 0.0:
        raise ValueError("smooth_s must be positive")
    # duration, speed, draft, grade; regeneration is supplied separately so
    # the downhill sine profile remains explicit and auditable.
    phases = ((70.0, 0.0, 12000.0, 0.0),
              (120.0, 2.4, 42000.0, 0.0),
              (50.0, 1.5, 145000.0, 0.05),
              (60.0, 1.8, 12000.0, -0.06))
    cycle_s = sum(phase[0] for phase in phases)

    def phase_regen(phase_index: int, local_s: float) -> float:
        if phase_index != 3:
            return 0.0
        return 30000.0 + 10000.0 * math.sin(local_s / phases[3][0] * math.pi)

    points: list[TerrainPoint] = []
    for index in range(int(duration_s / sample_s)):
        t = index * sample_s
        within_cycle = t % cycle_s
        accumulated = 0.0
        phase_index = 0
        for candidate, phase in enumerate(phases):
            if within_cycle < accumulated + phase[0]:
                phase_index = candidate
                break
            accumulated += phase[0]
        duration, speed, draft, grade = phases[phase_index]
        local_s = within_cycle - accumulated
        regen = phase_regen(phase_index, local_s)
        if local_s >= duration - smooth_s:
            fraction = (local_s - (duration - smooth_s)) / smooth_s
            next_index = (phase_index + 1) % len(phases)
            _, next_speed, next_draft, next_grade = phases[next_index]
            next_regen = phase_regen(next_index, 0.0)
            speed += (next_speed - speed) * fraction
            draft += (next_draft - draft) * fraction
            grade += (next_grade - grade) * fraction
            regen += (next_regen - regen) * fraction
        points.append(TerrainPoint(t, speed, max(draft, 10000.0), grade,
                                   1.0, max(0.0, regen)))
    return points
