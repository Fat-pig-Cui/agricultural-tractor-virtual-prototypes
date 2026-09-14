"""Statistics used by the manuscript; experiment runners call these functions."""
from __future__ import annotations
import math
from statistics import mean, stdev
from typing import Sequence

def summary(values: Sequence[float]) -> dict[str, float]:
    if not values:
        raise ValueError("values cannot be empty")
    deviation = stdev(values) if len(values) > 1 else 0.0
    half_width = 1.96 * deviation / math.sqrt(len(values))
    return {"n": float(len(values)), "mean": mean(values), "std": deviation,
            "ci95_low": mean(values) - half_width, "ci95_high": mean(values) + half_width}

def paired_difference(baseline: Sequence[float], candidate: Sequence[float]) -> dict[str, float]:
    if len(baseline) != len(candidate) or not baseline:
        raise ValueError("paired samples must have equal non-zero length")
    differences = [a - b for a, b in zip(baseline, candidate)]
    return summary(differences)
