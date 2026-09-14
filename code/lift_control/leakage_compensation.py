"""Leakage confidence and hysteretic hybrid hold-mode supervisor."""
from __future__ import annotations
from dataclasses import dataclass
from enum import Enum

class HoldMode(Enum):
    FINE_TRIM = "fine_trim"
    LOCK = "lock"
    ACCUMULATOR = "accumulator"

@dataclass
class HybridHoldSupervisor:
    # Thresholds are leakage *flow* thresholds.  With the theoretical
    # cylinder coefficient (1.5e-12 m3/s/Pa) and ~1 MPa differential pressure,
    # nominal leakage is O(1e-6 m3/s); the old O(1e-8) thresholds therefore
    # forced every case into ACCUMULATOR and were dimensionally misleading.
    lock_threshold: float = 2.0e-6
    accumulator_threshold: float = 8.0e-6
    hysteresis: float = 0.15
    accumulator_enabled: bool = True
    mode: HoldMode = HoldMode.FINE_TRIM

    def update(self, leakage_m3_s: float) -> HoldMode:
        level = abs(leakage_m3_s)
        high = self.accumulator_threshold * (1 + self.hysteresis)
        low = self.lock_threshold * (1 - self.hysteresis)
        if self.accumulator_enabled and level >= high:
            self.mode = HoldMode.ACCUMULATOR
        elif level >= self.lock_threshold:
            self.mode = HoldMode.LOCK
        elif level <= low:
            self.mode = HoldMode.FINE_TRIM
        return self.mode

    def command(self, leakage_m3_s: float) -> float:
        mode = self.update(leakage_m3_s)
        if mode is HoldMode.ACCUMULATOR:
            return -0.15 if leakage_m3_s > 0 else 0.15
        if mode is HoldMode.LOCK:
            return 0.0
        return -0.05 if leakage_m3_s > 0 else 0.05
