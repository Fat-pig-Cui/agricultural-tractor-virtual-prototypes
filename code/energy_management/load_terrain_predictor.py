"""Probabilistic short-horizon demand predictor and scenario generator."""
from __future__ import annotations
from dataclasses import dataclass
from collections import deque
from random import Random
from common.profiles import TerrainPoint

@dataclass(frozen=True)
class DemandPrediction:
    mean_w: float
    std_w: float
    grade_mean: float
    grade_std: float

class ProbabilisticPredictor:
    def __init__(self, window: int = 12, noise_ratio: float = 0.08, seed: int = 2026):
        self.history: deque[float] = deque(maxlen=window)
        self.grade_history: deque[float] = deque(maxlen=window)
        self.noise_ratio = noise_ratio
        self.seed = seed
        self._scenario_calls = 0

    def update(self, point: TerrainPoint, demand_w: float) -> DemandPrediction:
        self.history.append(demand_w); self.grade_history.append(point.grade)
        mean_w = sum(self.history) / len(self.history)
        spread = max(5000.0, max(self.history) - min(self.history) if len(self.history) > 1 else mean_w * self.noise_ratio)
        return DemandPrediction(mean_w, spread * self.noise_ratio, point.grade, max(0.002, abs(point.grade) * 0.15))

    def scenarios(self, prediction: DemandPrediction, count: int = 5, seed: int | None = None) -> list[float]:
        # Advance a deterministic sequence between MPC updates.  Resetting
        # the same seed on every call makes a nominal scenario count appear
        # configurable while repeatedly evaluating the identical samples.
        rng = Random((self.seed + self._scenario_calls) if seed is None else seed)
        self._scenario_calls += 1
        return [max(0.0, rng.gauss(prediction.mean_w, prediction.std_w)) for _ in range(count)]

    def nominal_phase_preview(self, nominal_demands: list[float], observed_demand_w: float,
                              residual_gain: float = 1.0) -> list[float]:
        """Adjust a public task-phase preview using only the current demand.

        A scheduled tillage sequence may be known in advance, but the realized
        soil/grade disturbance is not.  The current mismatch is therefore
        retained as an additive short-horizon residual; no future realization
        is read from the evaluated trajectory.
        """
        if not nominal_demands:
            return []
        # ``residual_gain`` distinguishes knowledge of the recurring task
        # phase from persistence of the current unknown soil/grade bias.  It
        # is restricted to [0, 1] so a preview cannot amplify an unobserved
        # disturbance or use a future sample.
        gain = max(0.0, min(1.0, residual_gain))
        residual_w = gain * (observed_demand_w - nominal_demands[0])
        return [max(0.0, value + residual_w) for value in nominal_demands]

    def phase_scenarios(self, nominal_demands: list[float], observed_demand_w: float,
                        prediction: DemandPrediction, count: int = 5,
                        residual_gain: float = 1.0) -> list[list[float]]:
        """Return reproducible correlated demand trajectories around a phase prior."""
        mean_trajectory = self.nominal_phase_preview(
            nominal_demands, observed_demand_w, residual_gain=residual_gain)
        if not mean_trajectory:
            return []
        rng = Random(self.seed + self._scenario_calls)
        self._scenario_calls += 1
        # Keep innovations tied to the online predictor.  A persistent offset
        # represents a short-horizon soil/grade bias; a small slope separates
        # otherwise identical scenarios without using actual future samples.
        spread_w = max(250.0, prediction.std_w)
        trajectories = []
        for _ in range(max(1, count)):
            offset_w = rng.gauss(0.0, spread_w)
            slope_w = rng.gauss(0.0, 0.2 * spread_w)
            trajectories.append([max(0.0, value + offset_w + step * slope_w)
                                 for step, value in enumerate(mean_trajectory)])
        return trajectories
