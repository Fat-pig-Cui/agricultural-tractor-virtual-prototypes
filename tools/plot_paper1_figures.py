"""Regenerate only the paper-1 figures used by the current manuscript."""
from __future__ import annotations

from plot_submission_figures import OUT, lift_figures


if __name__ == "__main__":
    OUT.mkdir(parents=True, exist_ok=True)
    lift_figures()
