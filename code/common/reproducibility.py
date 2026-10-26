"""Reproducibility helpers without external dependencies."""
from __future__ import annotations
import random

def seed_everything(seed: int) -> None:
    random.seed(seed)

def seeds(count: int = 20, start: int = 2026) -> list[int]:
    return [start + index for index in range(count)]
