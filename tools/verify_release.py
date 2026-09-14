"""Perform non-destructive release-integrity checks for the Zenodo archive."""
from __future__ import annotations

import json
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]

REQUIRED = (
    "README.md",
    "CITATION.cff",
    ".zenodo.json",
    "LICENSE.md",
    "requirements.txt",
    "MDPI_template_ACS/paper1_hitch_control_mdpi.tex",
    "MDPI_template_ACS/paper1_hitch_control_mdpi.pdf",
    "MDPI_template_ACS/paper2_energy_management_mdpi.tex",
    "MDPI_template_ACS/paper2_energy_management_mdpi.pdf",
    "results/paper1_statistics_20seeds.json",
)


def load_result(name: str) -> dict[str, object]:
    return json.loads((ROOT / "results" / name).read_text(encoding="utf-8"))


def main() -> None:
    missing = [path for path in REQUIRED if not (ROOT / path).is_file()]
    if missing:
        raise RuntimeError("missing release files: " + ", ".join(missing))

    traceability = load_result("paper1_traceability.json")
    validation = traceability.get("validation")
    if not isinstance(validation, dict) or not all(validation.values()):
        raise RuntimeError("paper-1 traceability validation did not pass")

    paper1_statistics = load_result("paper1_statistics_20seeds.json")
    hybrid = paper1_statistics.get("controllers", {}).get("hybrid")
    if not isinstance(hybrid, dict) or hybrid.get("hold_trigger_rate") != 1.0:
        raise RuntimeError("paper-1 hybrid hold-entry result is incomplete")

    for name in (
        "paper2_mpc_mechanism_map.json",
        "paper2_ideal_oracle_envelope.json",
    ):
        checks = load_result(name).get("acceptance_checks")
        if not isinstance(checks, dict) or not all(checks.values()):
            raise RuntimeError(f"acceptance checks failed in {name}")

    removed_names = ("Zhuo Hao", "Yang Yi", "Qingyang Li")
    for manuscript in (
        ROOT / "MDPI_template_ACS/paper1_hitch_control_mdpi.tex",
        ROOT / "MDPI_template_ACS/paper2_energy_management_mdpi.tex",
    ):
        text = manuscript.read_text(encoding="utf-8")
        residual = [name for name in removed_names if name in text]
        if residual:
            raise RuntimeError(f"removed authors remain in {manuscript.name}: {residual}")

    print("release verification passed")


if __name__ == "__main__":
    main()
