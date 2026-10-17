"""Confirm the selected causal phase policy on never-inspected test seeds.

The policy target schedule and tracking gain are read from the completed
development/holdout screen and are not changed here. Test seeds 2046--2059
were not used during either schedule calibration or gain comparison.
"""
from __future__ import annotations

import json
from pathlib import Path

from run_paper2_phase_policy_screen import evaluate, make_baselines

ROOT = Path(__file__).parents[1]
RESULT_PATH = ROOT / "results" / "paper2_phase_policy_tracking_screen.json"
TEST_SEEDS = tuple(range(2046, 2060))


def main() -> None:
    screen = json.loads(RESULT_PATH.read_text(encoding="utf-8"))
    selected = next(
        item for item in screen["holdout_frozen_finalists"]
        if float(item["tracking_gain"]) == 0.75
    )
    targets = tuple(float(value) for value in selected["result"]["targets_w"])
    baseline, _ = make_baselines(TEST_SEEDS)
    result = evaluate(targets, TEST_SEEDS, baseline, tracking_gain=0.75, emit=True)
    output = {
        "purpose": (
            "Independent confirmation of the selected exploratory causal phase policy. "
            "The gain and targets are loaded unchanged from the prior development/holdout screen."),
        "source_screen": "results/paper2_phase_policy_tracking_screen.json",
        "frozen_tracking_gain": 0.75,
        "frozen_targets_w": list(targets),
        "test_seeds": list(TEST_SEEDS),
        "test_result": result,
    }
    path = ROOT / "results" / "paper2_phase_policy_tracking_confirmation.json"
    path.write_text(json.dumps(output, ensure_ascii=False, indent=2), encoding="utf-8")
    print(path)


if __name__ == "__main__":
    main()
