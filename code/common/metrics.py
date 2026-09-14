"""Shared metric functions for the two research prototypes."""
from __future__ import annotations

import math
from typing import Iterable


def rmse(errors: Iterable[float]) -> float:
    values = list(errors)
    if not values:
        return 0.0
    return math.sqrt(sum(value * value for value in values) / len(values))


def max_abs(errors: Iterable[float]) -> float:
    values = list(errors)
    return max((abs(value) for value in values), default=0.0)


def settling_time(times: Iterable[float], errors: Iterable[float], tolerance: float) -> float:
    pairs = list(zip(times, errors))
    for index, (time, _) in enumerate(pairs):
        if all(abs(error) <= tolerance for _, error in pairs[index:]):
            return time
    return float("inf")


def relative_saving(baseline: float, candidate: float) -> float:
    if baseline <= 0:
        raise ValueError("baseline must be positive")
    return (baseline - candidate) / baseline * 100.0
