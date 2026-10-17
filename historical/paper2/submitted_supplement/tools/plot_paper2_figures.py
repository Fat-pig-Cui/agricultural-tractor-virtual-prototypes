#!/usr/bin/env python3
"""Regenerate the Paper 2 figures from the frozen result files."""
from plot_submission_figures import energy_figures
from plot_v2_submission_figures import architecture_paper2, results_paper2


if __name__ == "__main__":
    energy_figures()
    architecture_paper2()
    results_paper2()
