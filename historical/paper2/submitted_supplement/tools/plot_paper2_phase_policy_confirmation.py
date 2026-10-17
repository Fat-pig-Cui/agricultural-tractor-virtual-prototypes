"""Render the independently confirmed paper-2 phase-policy figure only."""
from __future__ import annotations

from plot_submission_figures import OUT, phase_policy_confirmation_figure


if __name__ == "__main__":
    OUT.mkdir(parents=True, exist_ok=True)
    phase_policy_confirmation_figure()
